"""Build a film (or some scenes) from a project.

    project -> resolved dialogue -> voices (cached) -> cleaned line audio -> timelines
            -> scene videos (only changed scenes re-render) -> film video + mixed audio
            -> MP4 + SRT + VTT + transcript + manifest

The output folder must be inside the project. Nothing outside it is written.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageDraw

from . import __version__
from .audio import ffmpeg as ff
from .errors import ConfigError, RenderError
from .project import Project, is_placeholder_host, placeholder_contacts, validate
from .project import errors as only_errors
from .render import cards, figures
from .render.style import Palette, load_image
from .safepath import atomic_write_text, ensure_output_dir, safe_name
from .subtitles import check as check_subs
from .subtitles import to_srt, to_transcript, to_vtt
from .timeline import (
    INTRO_S,
    OUTRO_S,
    TITLE_S,
    Beat,
    SceneTimeline,
    film_cues,
    frames_for,
    line_beat,
    reading_seconds,
    scene_audio,
)
from .voices.engine import STATE_DIR, build_plan, generate

FPS = 24
PREP_VERSION = "1"
RENDER_VERSION = "1"

# Words the renderer itself puts on screen. Projects override them per language in `project.labels`.
UI_LABELS = {
    "key_point": {"default": "Key point", "hi": "मुख्य बात"},
    "report_prompt": {"default": "Seen something suspicious? Report it to", "hi": "कुछ संदिग्ध दिखा? यहाँ report कीजिए"},
}


def _by_lang(table: dict | None, lang: str) -> str | None:
    if not table:
        return None
    return table.get(lang) or table.get(lang.split("-")[0]) or table.get("default")


def ui_label(project: Project, key: str, lang: str) -> str:
    """An on-screen label in `lang`: the project's own wording first, then the built-in one."""
    own = (project.data["project"].get("labels") or {}).get(key)
    return project.display(_by_lang(own, lang) or _by_lang(UI_LABELS[key], lang), lang)


def topic_label(project: Project, topic: str, lang: str) -> str:
    own = ((project.data["project"].get("labels") or {}).get("topics") or {}).get(topic)
    found = _by_lang(own, lang)
    return project.display(found, lang) if found else topic.replace("_", " ")


@dataclass
class BuildResult:
    language: str
    video: Path | None
    srt: Path | None
    vtt: Path | None
    transcript: Path | None
    manifest: Path
    rendered: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- voices for a build
def resolve_voices(project: Project, lang: str, scene_ids, *, fallback: str | None, log,
                   override: str | None = None) -> tuple[dict[str, Path], set[str]]:
    """Audio for every line. `override`: one free provider for the whole cast in this build, whatever the project says."""
    plan = build_plan(project, [lang], scene_ids, fallback_provider=override)
    generate(project, plan, live=False, log=log)  # free/local voices only; never billable
    missing = [it for it in plan.items if not it.path.exists()]
    fallback_lines: set[str] = set()
    if missing:
        if not fallback:
            names = ", ".join(sorted({f"{it.utt.line_id} ({it.req.provider})" for it in missing})[:12])
            raise RenderError(
                f"{len(missing)} line(s) have no generated audio yet: {names}" + (" ..." if len(missing) > 12 else ""),
                "Run `sastudio voices generate --live --max-characters N` (paid), or render a preview with "
                "`--voice-fallback offline` (free placeholder voices, clearly labelled).",
            )
        fb_plan = build_plan(project, [lang], scene_ids, fallback_provider=fallback)
        by_line = {it.utt.line_id: it for it in fb_plan.items}
        sub = [by_line[it.utt.line_id] for it in missing]
        from .voices.engine import Plan

        generate(project, Plan(sub, fb_plan.cache_dir), live=False, log=log)
        for it in sub:
            fallback_lines.add(it.utt.line_id)
        plan.items = [by_line[it.utt.line_id] if it in missing else it for it in plan.items]
    return {it.utt.line_id: it.path for it in plan.items}, fallback_lines


def prepare_lines(raw: dict[str, Path], out_dir: Path, jobs: int) -> dict[str, Path]:
    out: dict[str, Path] = {}
    todo = []
    for line_id, src in raw.items():
        dst = out_dir / f"{src.stem}.p{PREP_VERSION}.wav"
        out[line_id] = dst
        if not dst.exists():
            todo.append((src, dst))
    if todo:
        with ProcessPoolExecutor(max_workers=max(1, jobs)) as ex:
            futs = [ex.submit(ff.prepare_line, s, d) for s, d in dict((d, (s, d)) for s, d in todo).values()]
            for f in as_completed(futs):
                f.result()
    return out


# --------------------------------------------------------------------------- timelines
def scene_timelines(project: Project, lang: str, scene_ids, audio: dict[str, Path]) -> list[SceneTimeline]:
    gap = float((project.data.get("speech") or {}).get("gap_seconds", 0.35))
    names = {cid: (c.text_view().form("name", lang) or c.name) for cid, c in project.characters.items()}
    out = []
    for scene in project.enabled_scenes(scene_ids):
        beats: list[Beat] = []
        title = project.display(scene.field_for("title", lang, project.language), lang)
        beats.append(Beat("title", frames_for(TITLE_S, FPS), title, extra={"topic": topic_label(project, scene.topic, lang)}))
        cast: list[str] = []
        for ln in scene.lines:
            tmpl = ln.template_for(lang, project.language, project.fallback)
            text = project.display(tmpl, lang)
            if ln.is_card:
                secs = ln.card.get("seconds") or reading_seconds(text, 2.5)
                beats.append(Beat("card", frames_for(secs, FPS), text, line_id=ln.id))
                continue
            if ln.who not in cast:
                cast.append(ln.who)
            wav = audio[ln.id]
            seconds = ff.wav_info(wav)[3]
            if seconds > 300:
                raise RenderError(f"Line {ln.id} audio is {seconds:.0f}s long, which looks broken.",
                                  "Delete its cached audio and generate it again.")
            pause = gap if ln.pause_after is None else ln.pause_after
            beats.append(line_beat(text=text, speaker=ln.who, speaker_name=names[ln.who], wav=wav, seconds=seconds,
                                   pause=pause, fps=FPS, line_id=ln.id))
        takeaway = project.display(scene.field_for("takeaway", lang, project.language), lang)
        if takeaway:
            beats.append(Beat("takeaway", frames_for(reading_seconds(takeaway), FPS), takeaway,
                              extra={"label": ui_label(project, "key_point", lang)}))
        tl = SceneTimeline(scene.id, title, lang, FPS, beats, cast,
                           project.display(scene.field_for("headline", lang, project.language), lang), scene.setting)
        if scene.max_seconds and tl.seconds > scene.max_seconds:
            raise RenderError(f"Scene {scene.id} runs {tl.seconds:.1f}s; its max_seconds is {scene.max_seconds}.",
                              "Shorten dialogue, remove a card, or raise max_seconds.")
        out.append(tl)
    return out


def bookends(project: Project, lang: str) -> tuple[SceneTimeline | None, SceneTimeline | None]:
    rc = project.render_cfg
    org = project.org
    intro = outro = None
    if rc.get("intro", True):
        title = project.display(project.title, lang)
        sub = project.display(project.data["project"].get("subtitle", ""), lang)
        beat = Beat("intro", frames_for(INTRO_S, FPS), title,
                    extra={"org": org["name"], "subtitle": sub, "announcement": project.display(org.get("announcement", ""), lang)})
        intro = SceneTimeline("_intro", title, lang, FPS, [beat], [])
    if rc.get("outro", True):
        credits = project.data["project"].get("credits") or {}
        lines = []
        if credits.get("show", True):
            if credits.get("creator"):
                lines.append(credits["creator"])
            lines += [project.display(x, lang) for x in credits.get("extra") or []]
        contact, url = org["security_email"], org.get("reporting_url", "")
        if url and is_placeholder_host(contact.rsplit("@", 1)[-1]) and not is_placeholder_host(urlsplit(url).hostname or ""):
            # a real portal and a placeholder address: the film's last word is the portal, never an address nobody reads
            contact, url = url.removeprefix("https://").removeprefix("http://").rstrip("/"), ""
        beat = Beat("outro", frames_for(OUTRO_S, FPS), "",
                    extra={"ask": ui_label(project, "report_prompt", lang), "contact": contact, "url": url,
                           "credits": lines})
        outro = SceneTimeline("_outro", "", lang, FPS, [beat], [])
    return intro, outro


# --------------------------------------------------------------------------- visuals
def visuals(project: Project, burn: bool, fallback_lines: set[str]) -> tuple[cards.Visuals, dict]:
    org = project.org
    sig: dict = {"palette": org.get("palette") or {}, "burn": burn, "fallback": sorted(fallback_lines)}
    logo = None
    if org.get("logo"):
        p = project.path(org["logo"], "organization.logo")
        logo = load_image(p)
        sig["logo"] = _file_sha(p)
    portraits, colors = {}, {}
    drawn: dict[str, dict] = {}
    default_style = figures.style_code(project.render_cfg.get("character_style"))
    for cid, ch in project.characters.items():
        look = ch.look or {}
        style = figures.style_code(look.get("style") or default_style)
        if style == "v4" and not look.get("portrait") and look.get("design"):
            style = "v2"  # a character described in text but without a portrait is drawn flat
        if style in figures.DRAWN_STYLES and (look.get("design") or look.get("preset") in figures.BUILTIN_DESIGNS):
            design = figures.normalize(look.get("design"), look.get("preset"))
            drawn[cid] = draw_figures(project, cid, design, style)
            portraits[cid] = drawn[cid]["rest"]
            sig[f"figure:{cid}"] = [style, design, figures.FIGURES_VERSION]
        elif look.get("portrait"):
            p = project.path(look["portrait"], f"characters.{cid}.look.portrait")
            portraits[cid] = load_image(p)
            sig[f"portrait:{cid}"] = _file_sha(p)
        colors[cid] = (look.get("colors") or {}).get("top") or "#5B6C7D"
    backdrops = {}
    for s in project.scenes:
        if s.setting.get("image"):
            p = project.path(s.setting["image"], f"{s.id}.setting.image")
            backdrops[s.id] = load_image(p)
            sig[f"backdrop:{s.id}"] = _file_sha(p)
    sig["names"] = {cid: c.name for cid, c in project.characters.items()}
    sig["colors"] = colors
    vis = cards.Visuals(Palette.from_config(org.get("palette")), org["name"], logo, portraits,
                        {cid: c.name for cid, c in project.characters.items()}, colors, burn, fallback_lines, backdrops,
                        figures=drawn)
    return vis, sig


FIGURE_HEIGHT = 820


def draw_figures(project: Project, cid: str, design: dict, style: str) -> dict:
    """A drawn character's variants, kept in .studio/work/figures so each is drawn once per design."""
    key = _sha(json.dumps({"d": design, "s": style, "v": figures.FIGURES_VERSION, "h": FIGURE_HEIGHT, "id": cid},
                          sort_keys=True).encode())[:20]
    folder = project.root / ".studio" / "work" / "figures" / key
    paths = {v: folder / f"{v}.png" for v in figures.VARIANTS}
    out: dict = {}
    if all(p.is_file() for p in paths.values()):
        try:
            for v, p in paths.items():
                with Image.open(p) as im:
                    out[v] = im.convert("RGBA")
            return out
        except OSError:
            out = {}  # a damaged cache file: draw again
    out = figures.figure_set(design, style, FIGURE_HEIGHT, key=cid)
    folder.mkdir(parents=True, exist_ok=True)
    for v, im in out.items():
        tmp = paths[v].with_name(paths[v].stem + ".part.png")
        im.save(tmp, optimize=False)
        tmp.replace(paths[v])
    return out


def _render_one(tl: SceneTimeline, vis: cards.Visuals, out: Path, preset: str, threads: int) -> str:
    cards.render_scene(tl, vis, out, preset, threads)
    return tl.id


# --------------------------------------------------------------------------- main entry
def build(project: Project, *, language: str | None = None, scene_ids=None, preset: str | None = None,
          fallback: str | None = None, burn: bool | None = None, jobs: int | None = None,
          renderer: str | None = None, allow_placeholder_contacts: bool = False, voices: str | None = None,
          log: Callable[[str], None] = print) -> BuildResult:
    t0 = time.time()
    lang = language or project.language
    if lang not in project.languages:
        raise ConfigError(f"Language {lang} is not in project.languages.", f"Add it: {project.languages + [lang]}")
    issues = validate(project, only=scene_ids)
    errs = only_errors(issues)
    if errs:
        raise ConfigError("Fix these problems first:\n  " + "\n  ".join(str(e) for e in errs[:20]),
                          "Run `sastudio validate` for the full list.")
    rc = project.render_cfg
    preset = preset or rc.get("preset", "preview")
    if preset not in cards.PRESETS:
        raise ConfigError(f"Unknown preset '{preset}'.", f"Use one of: {', '.join(cards.PRESETS)}.")
    placeholders = placeholder_contacts(project)
    if placeholders and preset == "final" and not allow_placeholder_contacts:
        raise ConfigError("This film would tell viewers to report incidents to a placeholder address that "
                          "nobody receives: " + "; ".join(placeholders) + ".",
                          "Put your real reporting address in studio.yaml (organization.security_email and "
                          "organization.reporting_url). For a demonstration film, add --allow-placeholder-contacts.")
    renderer = renderer or rc.get("renderer", "cards")
    if renderer not in ("cards", "clay"):
        raise ConfigError(f"Unknown renderer '{renderer}'.", "Use cards or clay.")
    if renderer == "clay":  # fail before any voice or scene work
        from .render import clay as clayr

        clayr.require_engine()
    burn = rc.get("burn_subtitles", False) if burn is None else burn
    cpu = os.cpu_count() or 2
    jobs = jobs or max(1, min(cpu // 2, 6))
    out_root = ensure_output_dir(project.root, rc.get("output", "build"))
    out = out_root / lang
    out.mkdir(parents=True, exist_ok=True)
    work = project.root / STATE_DIR / "work" / lang
    log(f"Building {project.title!r} [{lang}] preset={preset} jobs={jobs}")

    if voices and voices not in ("kokoro", "offline", "recorded"):
        raise ConfigError(f"--voices {voices} is not a free provider.", "Use kokoro, recorded or offline; paid providers are set per character.")
    raw, fallback_lines = resolve_voices(project, lang, scene_ids, fallback=fallback, log=log, override=voices)
    prepared = prepare_lines(raw, project.root / STATE_DIR / "work" / "lines", jobs)
    tls = scene_timelines(project, lang, scene_ids, prepared)
    intro, outro = bookends(project, lang) if not scene_ids else (None, None)
    sequence = [t for t in [intro, *tls, outro] if t is not None]
    vis, sig = visuals(project, burn, fallback_lines)
    if renderer == "clay":
        from . import direction, stopmotion

        plans = {p.scene: p for p in direction.plan(project)}
        scenes = {sc.id: sc for sc in project.scenes}
        log("Filming in clay (one shot at a time; unchanged shots are reused)")
        for tl in tls:
            spans = stopmotion.spans_from_timeline(scenes[tl.id], tl)
            phonemes = {}
            for sp in spans:        # when the voice provider reported its sounds, the mouths follow them exactly
                meta = raw[sp.line.id].with_suffix(".json") if sp.line.id in raw else None
                if meta is not None and meta.exists():
                    marks = json.loads(meta.read_text("utf-8")).get("phonemes")
                    if marks:
                        phonemes[sp.line.id] = marks
            opens = tl.beats[0].frames if tl.beats and tl.beats[0].kind == "title" else 0
            filmed = stopmotion.film_scene(project, scenes[tl.id], plans[tl.id], spans, preset, lang, log=log,
                                           phonemes=phonemes, title_frames=opens)
            if stopmotion.TITLE_KEY + tl.id in filmed:
                vis.clay_titles[tl.id] = filmed.pop(stopmotion.TITLE_KEY + tl.id)
                vis.clay_fades[tl.id] = plans[tl.id].transition_in == "fade_from_black"
            vis.clay.update(filmed)
            seen: set[str] = set()
            for b in tl.beats:       # a name tag the first time each person speaks in a scene
                if b.kind == "line" and b.speaker not in seen:
                    seen.add(b.speaker)
                    vis.clay_names.add(b.line_id)
                    mark = vis.clay.get(b.line_id)
                    if mark is not None and (mark / stopmotion.SPEAKER_UNTIL).exists():
                        vis.clay_name_until[b.line_id] = int((mark / stopmotion.SPEAKER_UNTIL).read_text())
        vis.clay_step = stopmotion.STEP
        sig["clay"] = {k: v.name for k, v in vis.clay.items()}
        sig["clay_name_until"] = dict(sorted(vis.clay_name_until.items()))
        sig["clay_titles"] = {k: v.name for k, v in vis.clay_titles.items()}

    # Scene videos: re-render only when the scene's content, the look or the tool changed.
    result = BuildResult(lang, None, None, None, None, out / "manifest.json")
    todo = []
    scene_files = []
    for tl in sequence:
        key = _sha(json.dumps({"tl": tl.to_json(), "sig": sig, "preset": preset, "r": RENDER_VERSION,
                               "v": __version__}, sort_keys=True, default=str).encode())
        path = work / "scenes" / f"{safe_name(tl.id)}.{preset}.mp4"
        stamp = path.with_suffix(".key")
        scene_files.append(path)
        cached = path.exists() and stamp.exists() and stamp.read_text() == key
        if cached and _scene_ok(path, tl.frames):
            result.reused.append(tl.id)
        else:
            if cached:
                log(f"  {tl.id}: the stored scene video is damaged; rendering it again")
            todo.append((tl, path, stamp, key))
    if todo:
        threads = max(1, cpu // max(1, min(jobs, len(todo))))
        with ProcessPoolExecutor(max_workers=max(1, min(jobs, len(todo)))) as ex:
            futs = {ex.submit(_render_one, tl, vis, path, preset, threads): (tl, path, stamp, key)
                    for tl, path, stamp, key in todo}
            for fut in as_completed(futs):
                tl, path, stamp, key = futs[fut]
                fut.result()  # re-raises a scene failure; a failed scene is never skipped silently
                stamp.write_text(key)
                result.rendered.append(tl.id)
                log(f"  rendered {tl.id} ({tl.seconds:.1f}s)")

    # Audio: frame-exact concatenation, then mix and normalise once for the whole film.
    dialogue = work / "dialogue.wav"
    ff.write_wav(dialogue, b"".join(scene_audio(tl) for tl in sequence))
    music = project.path(rc["music"], "render.music") if rc.get("music") else None
    mixed = work / "film_audio.wav"
    loud = ff.master_audio(dialogue, mixed, music=music, music_db=float(rc.get("music_volume_db", -24)))

    base = safe_name(project.display(project.title, lang)) + ("" if not scene_ids else "_" + "-".join(scene_ids))
    base = safe_name(base)
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in scene_files), encoding="utf-8")
    video_only = work / "video.mp4"
    ff.run([ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i",
            str(listing), "-c", "copy", str(video_only)], what="Joining scenes")
    final = out / f"{base}.{lang}.mp4"
    tmp = out / f".{base}.{lang}.part.mp4"
    meta_title = project.display(project.title, lang)
    ff.run([ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video_only), "-i", str(mixed),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-map_metadata", "-1", "-metadata", f"title={meta_title}", "-metadata:s:a:0", f"language={_iso639_2(lang)}",
            "-movflags", "+faststart", str(tmp)], what="Muxing")
    os.replace(tmp, final)

    cues = film_cues(sequence)
    result.warnings += check_subs(cues)
    labels = bool(rc.get("subtitle_speaker_labels", False))
    srt = out / f"{base}.{lang}.srt"
    vtt = out / f"{base}.{lang}.vtt"
    atomic_write_text(srt, to_srt(cues, speaker_labels=labels))
    atomic_write_text(vtt, to_vtt(cues, speaker_labels=True, language=lang))
    rows = []
    for tl in tls:
        rows.append((tl.title, None, ""))
        for b in tl.beats:
            if b.kind == "line":
                rows.append((None, b.speaker_name, b.text))
            elif b.kind in ("card", "takeaway"):
                rows.append((None, None, b.text))
    transcript = out / f"{base}.{lang}.transcript.txt"
    atomic_write_text(transcript, to_transcript(rows, meta_title))

    probe = probe_summary(final)
    total_frames = sum(t.frames for t in sequence)
    if probe["video_frames"] != total_frames:
        raise RenderError(f"The film has {probe['video_frames']} frames; the timeline has {total_frames}.")
    if abs(probe["audio_seconds"] - total_frames / FPS) > 0.1:
        raise RenderError(f"Audio is {probe['audio_seconds']:.2f}s but video is {total_frames / FPS:.2f}s.")
    if fallback_lines:
        result.warnings.append(f"{len(fallback_lines)} line(s) use placeholder voices (labelled 'Preview voice').")
    if placeholders:
        result.warnings.append("Placeholder reporting contacts, which nobody receives: " + "; ".join(placeholders) + ".")
    manifest = {
        "tool": "Clayvoyant", "version": __version__, "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "language": lang, "preset": preset, "renderer": renderer, "fps": FPS,
        "scenes": [{"id": t.id, "frames": t.frames, "seconds": round(t.seconds, 3)} for t in sequence],
        "rendered": sorted(result.rendered), "reused": sorted(result.reused),
        "voices": _voice_summary(project, raw, fallback_lines),
        "audio": loud, "probe": probe,
        "outputs": {p.name: {"bytes": p.stat().st_size, "sha256": _file_sha(p)} for p in (final, srt, vtt, transcript)},
        "warnings": result.warnings, "seconds_to_build": round(time.time() - t0, 1),
    }
    atomic_write_text(result.manifest, json.dumps(manifest, indent=1, ensure_ascii=False))
    result.video, result.srt, result.vtt, result.transcript = final, srt, vtt, transcript
    log(f"Done: {final.name} ({total_frames / FPS:.1f}s, {probe['width']}x{probe['height']}, "
        f"{loud.get('lufs') if loud.get('lufs') is not None else 'silent'} LUFS) in {manifest['seconds_to_build']}s")
    return result


def _voice_summary(project: Project, raw: dict[str, Path], fallback_lines: set[str]) -> dict:
    counts: dict[str, int] = {}
    for _line_id, p in raw.items():
        prov = p.parent.parent.name
        counts[prov] = counts.get(prov, 0) + 1
    return {"lines_by_provider": counts, "placeholder_lines": sorted(fallback_lines)}


def _iso639_2(lang: str) -> str:
    return {"en": "eng", "hi": "hin", "bn": "ben", "ta": "tam", "te": "tel", "mr": "mar", "gu": "guj", "kn": "kan",
            "ml": "mal", "pa": "pan", "od": "ori"}.get(lang.split("-")[0], "und")


def _scene_ok(path: Path, frames: int) -> bool:
    """A stored scene video is reused only if it still decodes to exactly the frames its timeline needs."""
    try:
        res = subprocess.run([ff.ffprobe_exe(), "-v", "error", "-select_streams", "v:0", "-count_packets",
                              "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, timeout=120, check=False)
        return res.returncode == 0 and res.stdout.strip() == str(frames)
    except (OSError, subprocess.TimeoutExpired):
        return False


def probe_summary(path: Path) -> dict:
    res = ff.run([ff.ffprobe_exe(), "-v", "error", "-count_packets", "-show_entries",
                  "stream=codec_type,codec_name,width,height,r_frame_rate,nb_read_packets,sample_rate,channels,duration,"
                  "pix_fmt,color_primaries,color_transfer,color_space", "-of", "json", str(path)], what="ffprobe")
    data = json.loads(res.stdout)
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    return {
        "video_codec": v["codec_name"], "width": v["width"], "height": v["height"], "fps": v["r_frame_rate"],
        "video_frames": int(v.get("nb_read_packets", 0)), "pix_fmt": v.get("pix_fmt"),
        "color": [v.get("color_primaries"), v.get("color_transfer"), v.get("color_space")],
        "audio_codec": a["codec_name"] if a else None, "audio_rate": int(a["sample_rate"]) if a else None,
        "audio_channels": a.get("channels") if a else None, "audio_seconds": float(a.get("duration", 0)) if a else 0.0,
    }


def clean(project: Project) -> None:
    """Delete rendered scene videos and work files (keeps the voice cache, which may have cost money)."""
    shutil.rmtree(project.root / STATE_DIR / "work", ignore_errors=True)


def cast_sheet(project: Project, styles: list[str], height: int = 520) -> Image.Image:
    """The project's cast drawn in each style, one row per style: a preview before choosing."""
    from .render.style import font, text_width

    codes = []
    for st in styles:
        code = figures.STYLE_ALIASES.get(st.lower())
        if code is None:
            raise ConfigError(f"Unknown character style '{st}'.", "Use v1 (sketch), v2 (flat), v3 (cutout) or v4 (clay).")
        codes.append(code)
    pal = Palette.from_config(project.org.get("palette"))
    cast = list(project.characters.items())
    col, label_w, row_h = round(height * 0.5), 260, height + 110
    im = Image.new("RGB", (label_w + col * len(cast) + 40, row_h * len(codes) + 40), pal.background)
    d = ImageDraw.Draw(im)
    for r, code in enumerate(codes):
        y0 = 20 + r * row_h
        d.text((30, y0 + height // 2 - 40), code, font=font(56, "bold"), fill=pal.primary)
        d.text((32, y0 + height // 2 + 26), figures.STYLES[code], font=font(30, "regular"), fill=pal.text)
        for i, (cid, ch) in enumerate(cast):
            look = ch.look or {}
            fig = None
            if code in figures.DRAWN_STYLES and (look.get("design") or look.get("preset") in figures.BUILTIN_DESIGNS):
                fig = draw_figures(project, cid, figures.normalize(look.get("design"), look.get("preset")), code)["rest"]
            elif code == "v4" and look.get("portrait"):
                fig = load_image(project.path(look["portrait"], f"characters.{cid}.look.portrait")).convert("RGBA")
            x0 = label_w + i * col
            if fig is not None:
                fig = fig.resize((max(1, round(fig.width * height / fig.height)), height), Image.LANCZOS)
                im.paste(fig, (x0 + (col - fig.width) // 2, y0), fig)
            else:
                d.text((x0 + 20, y0 + height // 2), "no art", font=font(26, "regular"), fill=pal.text)
            f = font(30, "bold")
            d.text((x0 + (col - text_width(d, ch.name, f)) // 2, y0 + height + 18), ch.name, font=f, fill=pal.text)
    return im

