"""Phone films: the film laid out for a phone held upright, small enough to forward.

    sastudio share PROJECT [--lang LANG] [--max-mb 15]

For each language it first builds the film without subtitles in the picture, into build/clean/<lang>/ next to
its .srt (a copy that is useful on its own, for players that show their own captions). Every voice, sculpt and
filmed shot is reused, so this is only the assembly. Then it lays the film out at 720x1280: the organisation and
the film's title at the top, the film across the middle over a blurred copy of itself, each line's words below it
in large type set in the font its script needs, and where to report along the foot. The encode is sized to stay
under --max-mb.

Written next to the film as <film>.phone.mp4.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from .audio.ffmpeg import ffmpeg_exe, ffprobe_exe
from .build import build, ui_label
from .errors import RenderError
from .render import style as S

W, H = 720, 1280
FILM_Y = 290                 # where the film sits; it is W wide and W * 9 / 16 tall
CAPTION_Y = FILM_Y + W * 9 // 16 + 70
AUDIO_BPS = 96_000
_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def read_srt(text: str) -> list[tuple[float, float, str]]:
    """(start, end, text) for every cue of an SRT file."""
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        rows = block.strip().splitlines()
        stamp = next((i for i, r in enumerate(rows) if "-->" in r), None)
        if stamp is None:
            continue
        a, b = (_TIME.search(x) for x in rows[stamp].split("-->"))
        if not a or not b:
            continue
        t = [int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000 for h, m, s, ms in (a.groups(), b.groups())]
        cues.append((t[0], t[1], " ".join(r.strip() for r in rows[stamp + 1:] if r.strip())))
    return cues


def _layer(project, lang: str, caption: str | None) -> Image.Image:
    """Everything drawn over the film for one stretch of time: the header, the foot and (when a line is being said)
    its words. Transparent wherever the film or its blurred copy should show."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pal = S.Palette.from_config(project.org.get("palette"))
    d.rectangle((0, 0, W, 230), fill=S.rgb(pal.primary) + (235,))
    on = S.readable_on(pal.primary, "#FFFFFF")
    org = project.display("{org.name}", lang)
    d.text((40, 52), org, font=S.font_for(org, 30, "semibold"), fill=on)
    f, lines, size = S.fit_text(d, project.title, W - 80, 110, start=58, minimum=36, weight="bold", max_lines=2)
    y = 100
    for ln in lines:
        d.text((40, y), ln, font=f, fill=on)
        y += int(size * 1.15)
    where = (project.org.get("reporting_url") or project.org.get("security_email") or "")
    where = where.removeprefix("https://").removeprefix("http://").rstrip("/")
    if where:
        d.rectangle((0, H - 130, W, H), fill=S.rgb(pal.primary) + (235,))
        prompt = ui_label(project, "report_prompt", lang)
        d.text((40, H - 112), prompt, font=S.font_for(prompt, 26, "semibold"), fill=on)
        d.text((40, H - 74), where, font=S.font_for(where, 40, "bold"), fill=on)
    if caption:
        f, lines, size = S.fit_text(d, caption, W - 120, H - 150 - CAPTION_Y - 40, start=52, minimum=34,
                                    weight="semibold", line_gap=1.25, max_lines=5)
        h = int(len(lines) * size * 1.25) + 44
        d.rounded_rectangle((30, CAPTION_Y, W - 30, CAPTION_Y + h), radius=22, fill=(14, 14, 16, 215))
        y = CAPTION_Y + 18
        for ln in lines:
            d.text(((W - S.text_width(d, ln, f)) // 2, y), ln, font=f, fill="#FFFFFF")
            y += int(size * 1.25)
    return im


def _duration(path: Path) -> float:
    out = subprocess.run([ffprobe_exe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out)


def compose(project, lang: str, film: Path, srt: Path, out: Path, max_mb: float = 15.0) -> Path:
    """The phone layout of an already built film (without burned-in subtitles) and its SRT."""
    dur = _duration(film)
    cues = read_srt(srt.read_text("utf-8"))
    with tempfile.TemporaryDirectory(prefix="sas-share-") as tmp:
        tmp = Path(tmp)
        blank = tmp / "blank.png"
        _layer(project, lang, None).save(blank)
        rows, t = [], 0.0
        for i, (a, b, text) in enumerate(cues):
            if a > t + 0.01:
                rows += [f"file '{blank.as_posix()}'", f"duration {a - t:.3f}"]
            png = tmp / f"cue{i:04d}.png"
            _layer(project, lang, text).save(png)
            rows += [f"file '{png.as_posix()}'", f"duration {max(0.04, b - max(a, t)):.3f}"]
            t = b
        rows += [f"file '{blank.as_posix()}'", f"duration {max(0.04, dur - t):.3f}", f"file '{blank.as_posix()}'"]
        (tmp / "layers.txt").write_text("\n".join(rows) + "\n", "utf-8")
        graph = (f"[0:v]split=2[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                 f"boxblur=24:2,eq=brightness=-0.22:saturation=0.85[bg];[b]scale={W}:-2[fg];"
                 f"[bg][fg]overlay=0:{FILM_Y}[v0];[1:v]fps=24,format=rgba[ov];[v0][ov]overlay=0:0:eof_action=repeat,"
                 "format=yuv420p[v]")
        budget = max_mb * 1_000_000 * 8 * 0.94 / dur - AUDIO_BPS
        vbps = int(min(2_400_000, max(250_000, budget)))
        out.parent.mkdir(parents=True, exist_ok=True)
        part = out.with_name(out.stem + ".part.mp4")
        for _ in range(3):
            cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(film), "-f", "concat", "-safe", "0",
                   "-i", str(tmp / "layers.txt"), "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-t", f"{dur:.3f}",
                   "-c:v", "libx264", "-preset", "slow", "-b:v", str(vbps), "-maxrate", str(int(vbps * 1.4)),
                   "-bufsize", str(vbps * 2), "-r", "24", "-g", "48", "-c:a", "aac", "-b:a", str(AUDIO_BPS),
                   "-movflags", "+faststart", "-map_metadata", "-1", str(part)]
            r = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if r.returncode != 0:
                part.unlink(missing_ok=True)
                raise RenderError(f"The phone film could not be encoded: {r.stderr.strip()[-300:]}")
            size = part.stat().st_size
            if size <= max_mb * 1_000_000:
                break
            vbps = int(vbps * max_mb * 1_000_000 / size * 0.92)
        else:
            part.unlink(missing_ok=True)
            raise RenderError(f"The phone film stays over {max_mb} MB.", "Give --max-mb a larger value.")
        part.replace(out)
    return out


def share(project, lang: str | None = None, max_mb: float = 15.0, log=print) -> Path:
    """Build the film without subtitles in the picture (reusing everything already made), then lay it out for a phone."""
    lang = lang or project.language
    rc = project.data.setdefault("render", {})
    own = rc.get("output", "build")
    rc["output"] = f"{own}/clean"
    try:
        res = build(project, language=lang, burn=False, log=log)
    finally:
        rc["output"] = own
    if res.video is None or res.srt is None:
        raise RenderError("Nothing was built to lay out.", "Check that the project has enabled scenes.")
    out = project.root / own / lang / res.video.name.replace(f".{lang}.mp4", f".{lang}.phone.mp4")
    compose(project, lang, res.video, res.srt, out, max_mb)
    log(f"[{lang}] {out} ({out.stat().st_size / 1e6:.1f} MB, {_duration(out):.1f} s); "
        f"without subtitles in the picture: {res.video}")
    return out
