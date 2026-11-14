"""A film's whole soundtrack, from the build's timelines: what the build calls.

For each scene: its place on the film's clock, its room and its air, the sound events the engine found in its plan
(clay films) and the cues its direction asks for. Then the mix (sound.mix) and the master (sound.master). Nothing here
draws or calls Blender: the engine's events are read once per scene and cached (stopmotion.scene_events), so changing
the music, a cue, a level or the master never films anything again."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from . import ambience, config, master, mix
from .dsp import RATE
from .events import Event, dedupe, snap_to_drawings
from .kit import Kit, SoundFileError

UNIT_M = .5          # one set unit is half a metre (engine/clay)
SHOE = dict(sneaker="soft", hitop="soft", heel="heel", flat="hard", brogue="hard")


def surface(obj_name: str | None, set_name: str | None) -> str:
    """What a foot or a chair leg is on, from the name of the set object under it and the set it is in."""
    n = (obj_name or "").lower()
    if "rug" in n:
        return "rug"
    if "carpet" in n:
        return "carpet"
    if "plank" in n or "board" in n or "table" in n:
        return "wood"
    if "road" in n:
        return "pavement"
    if "kerb" in n:
        return "stone"
    if "tile" in n:
        return {"street": "pavement", "corridor": "stone"}.get(set_name or "", "tile")
    return ambience.room_of(set_name)["floor"] if set_name else "wood"


def engine_events(raw: list[dict], scene_id: str, set_name: str | None, beats: list[tuple[int, int]], fps: int) -> list[Event]:
    """The engine's reports (engine/clay/sounds.py) as events on the scene's clock, each heard on the first drawing that
    shows it."""
    out = []
    for r in raw:
        p = dict(r.get("params") or {})
        if "shoe" in p:
            p["shoe"] = SHOE.get(p["shoe"], "hard")
        fr = snap_to_drawings(float(r["frame"]), beats)
        pos = r.get("pos")
        out.append(Event(kind=r["kind"], t=fr / fps, scene=scene_id, who=r.get("who"), thing=r.get("thing"),
                         surface=surface(r.get("surface_obj"), set_name) if r["kind"] in ("footstep", "scrape") else None,
                         intensity=.5 if p.get("light") else 1.0, duration=float(r.get("frames", 0)) / fps,
                         pos=tuple(v * UNIT_M for v in pos) if pos else None, params=p, source="engine", frame=float(r["frame"])))
    return out


def line_spans(tl, fps: int) -> dict[str, tuple[float, float]]:
    """line id -> (when its voice starts, when it ends), seconds from the scene's start."""
    out, at = {}, 0
    for b in tl.beats:
        if b.kind == "line" and b.line_id:
            t0 = (at + b.audio_offset) / fps
            ends = [c[1] for c in b.cues] if b.cues else []
            t1 = at / fps + (max(ends) if ends else b.frames / fps)
            out[b.line_id] = (t0, max(t0, t1))
        at += b.frames
    return out


def make(project, sequence, dialogue_pcm: bytes, fps: int, clay_events: dict | None = None, log=print):
    """-> (the mixed soundtrack (n, 2) at 48 kHz, ready to master; what was measured and used; every event placed; the
    project's sound settings)."""
    sp = config.plan(project)
    scenes_by_id = {sc.id: sc for sc in project.scenes}
    dialogue = np.frombuffer(dialogue_pcm, dtype="<i2").astype(np.float64) / 32768.0
    spf = RATE // fps
    scenes, start, placed = [], 0, []
    for tl in sequence:
        length = tl.frames * spf
        sc = scenes_by_id.get(tl.id)
        if sc is None:          # the film's opening and closing cards: music may play, nothing else
            scenes.append(mix.SceneMix(id=tl.id, start=start, length=length))
            start += length
            continue
        d = config.scene_sound(sc)
        set_name = (sc.direction or {}).get("set")
        events: list[Event] = []
        mute = set(d.get("mute") or [])
        if sp.effects and d.get("effects", True) is not False:
            beats, at = [], 0
            for b in tl.beats:
                beats.append((at, b.frames))
                at += b.frames
            events += engine_events((clay_events or {}).get(tl.id) or [], tl.id, set_name, beats, fps)
        events += config.cue_events(project, sc, line_spans(tl, fps), fps)
        events = dedupe([e for e in events if e.kind not in mute])
        bed, bed_file, bed_db = config.bed_for(project, sc, set_name, sp)
        scenes.append(mix.SceneMix(id=tl.id, start=start, length=length, room=ambience.room_of(set_name) if set_name else None,
                                   bed=bed, bed_file=bed_file, bed_db=bed_db, events=events,
                                   music=d.get("music", True) not in (False, "off"), effects=d.get("effects", True) is not False))
        placed += events
        start += length
    if start != len(dialogue):
        raise ValueError(f"the scenes add up to {start} samples but the dialogue has {len(dialogue)}")
    kit = Kit(sp.library)
    try:
        mixed, _buses, rep = mix.mix(dialogue, scenes, sp.music, sp.levels, kit)
    except SoundFileError as e:
        from ..errors import ConfigError
        raise ConfigError(f"A sound file cannot be used: {e}", "Check the path, and that FFmpeg can play the file.") from e
    info = dict(mix=asdict(rep), sources=rep.sources, credits=sp.credits)
    for w in rep.warnings:
        log(f"  sound: {w}")
    log(f"  sound: {rep.events} effect(s) placed ({', '.join(f'{v} {k}' for k, v in sorted(rep.sources.items())) or 'none'}); "
        f"dialogue {rep.dialogue_lufs if rep.dialogue_lufs is not None else 'silent'} LUFS; "
        f"music {len(sp.music)} cue(s)")
    return mixed, info, placed, sp


def finish(mixed: np.ndarray, sp, wav: Path, mux, log=print) -> dict:
    """Master the mix, write it, let `mux(wav)` encode it into the film (it returns the film's path), then measure the
    film itself. If the codec pushed a peak over the ceiling, master again with the ceiling that much lower and encode
    again (at most three times). -> what the film measures and whether its targets are met."""
    t = sp.target
    margin = master.codec_margin(t.bitrate)
    for attempt in range(3):
        out, info = master.master(mixed, t, margin=margin)
        master.write_wav(wav, out)
        film = mux(wav)
        if info.get("silent"):
            return dict(master=info, measured=None, verdict=dict(met=None, said="silent: nothing to measure"), target=asdict(t))
        m = master.measure(film)
        if m["true_peak"] is None or m["true_peak"] <= t.true_peak + 1e-6 or attempt == 2:
            v = master.verdict(m, t, info)
            log(f"  sound: the film measures {v['said']}" + ("" if v["met"] else " (targets NOT met)"))
            return dict(master=info, measured=m, verdict=v, target=asdict(t), encodes=attempt + 1)
        margin += m["true_peak"] - t.true_peak + .1
        log(f"  sound: the encoder pushed a peak to {m['true_peak']:.2f} dBTP; limiting {margin:.1f} dB under the ceiling and encoding again")
    raise AssertionError("unreachable")


def save_events(path: Path, events: list[Event]) -> None:
    from ..safepath import atomic_write_text
    atomic_write_text(path, json.dumps([e.to_json() for e in events], indent=1, ensure_ascii=False))
