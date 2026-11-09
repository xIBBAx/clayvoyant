"""The 'cards' renderer: a clean 2D layout that works on any computer (no GPU, no Blender).

It draws each beat of a scene timeline: the backdrop, the organisation's logo, the scene
headline, the cast (the speaker in front, the others quieter), the speaker's name and,
optionally, burned-in subtitles. Frames are piped straight into FFmpeg.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from ..audio.ffmpeg import ffmpeg_exe
from ..errors import RenderError
from ..timeline import Beat, SceneTimeline
from . import style
from .style import Palette, fit_text, font_for, readable_on, rgb, text_width, wrap_px

PRESETS = {
    "draft": {"size": (960, 540), "crf": 30, "x264": "veryfast"},
    "preview": {"size": (1280, 720), "crf": 23, "x264": "fast"},
    "final": {"size": (1920, 1080), "crf": 16, "x264": "slow"},
}


@dataclass
class Visuals:
    palette: Palette
    org_name: str
    logo: Image.Image | None = None
    portraits: dict[str, Image.Image] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    colors: dict[str, str] = field(default_factory=dict)
    burn_subtitles: bool = False
    fallback_lines: set[str] = field(default_factory=set)
    backdrop_images: dict[str, Image.Image] = field(default_factory=dict)  # scene id -> image
    clay: dict[str, Path] = field(default_factory=dict)  # line id -> folder of rendered clay frames
    clay_step: int = 2


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def avatar(name: str, color: str, size: int) -> Image.Image:
    """A plain initials portrait for characters without artwork."""
    im = Image.new("RGBA", (size, int(size * 1.25)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = rgb(color)
    d.ellipse((size * .18, 0, size * .82, size * .64), fill=c + (255,))
    d.rounded_rectangle((0, size * .62, size, size * 1.25), radius=int(size * .32), fill=c + (255,))
    initials = "".join(p[0] for p in name.split()[:2]).upper() or "?"
    f = font_for(initials, int(size * .26), "bold")
    w = text_width(d, initials, f)
    d.text(((size - w) / 2, size * .18), initials, font=f, fill=readable_on(color, "#FFFFFF"))
    return im


class SceneRenderer:
    def __init__(self, tl: SceneTimeline, vis: Visuals, preset: str):
        self.tl, self.vis = tl, vis
        self.W, self.H = PRESETS[preset]["size"]
        self.s = self.H / 1080.0
        self.pal = vis.palette
        self._base_cache: dict = {}
        self._portrait_cache: dict = {}

    # ---------------------------------------------------------------- helpers
    def S(self, v: float) -> int:
        return int(round(v * self.s))

    def background(self) -> Image.Image:
        bg = self.vis.backdrop_images.get(self.tl.id)
        if bg is not None:
            im = style.cover(bg, self.W, self.H).convert("RGB")
            shade = Image.new("RGB", (self.W, self.H), rgb(self.pal.background))
            return Image.blend(im, shade, 0.18)
        top = rgb(self.pal.background)
        bottom = tuple(max(0, int(c * 0.92)) for c in top)
        grad = Image.new("RGB", (1, 256))
        for y in range(256):
            t = y / 255
            grad.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
        return grad.resize((self.W, self.H))

    def portrait(self, cid: str, height: int) -> Image.Image:
        key = (cid, height)
        if key not in self._portrait_cache:
            src = self.vis.portraits.get(cid)
            if src is None:
                src = avatar(self.vis.names.get(cid, cid), self.vis.colors.get(cid, self.pal.primary), 512)
            w = max(1, int(src.width * height / src.height))
            self._portrait_cache[key] = src.resize((w, height), Image.LANCZOS)
        return self._portrait_cache[key]

    def top_bar(self, im: Image.Image, title: str) -> None:
        d = ImageDraw.Draw(im)
        f = font_for(title, self.S(30), "semibold")
        d.text((self.S(64), self.S(44)), title, font=f, fill=self.pal.text)
        if self.vis.logo is not None:
            lg = style.fit_inside(self.vis.logo, self.S(260), self.S(84))
            im.paste(lg, (self.W - self.S(64) - lg.width, self.S(36)), lg)

    def cast_layout(self, cast: list[str]) -> list[tuple[str, int, int]]:
        n = max(1, len(cast))
        frac = 0.66 if n <= 2 else (0.56 if n <= 4 else 0.46)
        h = int(self.H * frac)
        slots = []
        margin = self.S(120)
        span = self.W - 2 * margin
        for i, cid in enumerate(cast):
            cx = margin + span * (i + 0.5) / n
            slots.append((cid, int(cx), h))
        return slots

    def headline(self, im: Image.Image, text: str) -> None:
        if not text:
            return
        d = ImageDraw.Draw(im)
        f, lines, size = fit_text(d, text, int(self.W * 0.62), self.S(150), start=self.S(60), minimum=self.S(40),
                                  weight="bold", max_lines=2)
        y = self.S(110)
        for ln in lines:
            d.text((self.S(64), y), ln, font=f, fill=self.pal.primary)
            y += int(size * 1.15)

    def name_pill(self, im: Image.Image, name: str, cx: int, top: int, alpha: float) -> None:
        if alpha <= 0:
            return
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        f = font_for(name, self.S(32), "bold")
        w = text_width(d, name, f)
        pad_x, pad_y = self.S(22), self.S(10)
        x0 = max(self.S(24), min(self.W - w - 2 * pad_x - self.S(24), cx - (w + 2 * pad_x) // 2))
        y0 = max(self.S(180), top - self.S(70))
        box = (x0, y0, x0 + w + 2 * pad_x, y0 + self.S(32) + 2 * pad_y)
        d.rounded_rectangle(box, radius=self.S(26), fill=rgb(self.pal.primary) + (int(255 * alpha),))
        d.text((x0 + pad_x, y0 + pad_y - self.S(3)), name, font=f,
               fill=rgb(readable_on(self.pal.primary, "#FFFFFF")) + (int(255 * alpha),))
        im.alpha_composite(layer)

    def subtitles(self, im: Image.Image, text: str) -> None:
        if not text:
            return
        d = ImageDraw.Draw(im)
        f = font_for(text, self.S(46), "semibold")
        lines = []
        for part in text.split("\n"):
            lines += wrap_px(d, part, f, int(self.W * 0.8))
        lines = lines[:2]
        lh = int(self.S(46) * 1.25)
        widths = [text_width(d, ln, f) for ln in lines]
        bw = max(widths) + self.S(56)
        bh = lh * len(lines) + self.S(30)
        x0, y0 = (self.W - bw) // 2, self.H - self.S(48) - bh
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=self.S(14), fill=(12, 12, 14, 200))
        im.alpha_composite(layer)
        y = y0 + self.S(12)
        for ln, w in zip(lines, widths, strict=True):
            d.text(((self.W - w) // 2, y), ln, font=f, fill="#FFFFFF")
            y += lh

    def badge(self, im: Image.Image, text: str) -> None:
        d = ImageDraw.Draw(im)
        f = font_for(text, self.S(24), "semibold")
        w = text_width(d, text, f)
        x0, y0 = (self.W - w) // 2 - self.S(16), self.S(20)
        d.rounded_rectangle((x0, y0, x0 + w + self.S(32), y0 + self.S(40)), radius=self.S(20), fill=(30, 30, 30))
        d.text((x0 + self.S(16), y0 + self.S(6)), text, font=f, fill="#FFFFFF")

    # ---------------------------------------------------------------- beats
    def line_base(self, beat: Beat, speaker: str) -> Image.Image:
        key = ("line", speaker)
        if key in self._base_cache:
            return self._base_cache[key]
        im = self.background().convert("RGBA")
        self.top_bar(im, self.tl.title)
        self.headline(im, self.tl.headline)
        bg = rgb(self.pal.background)
        for cid, cx, h in self.cast_layout(self.tl.cast):
            if cid == speaker:
                continue
            p = self.portrait(cid, int(h * 0.94))
            faded = p.copy()
            alpha = faded.getchannel("A").point(lambda a: int(a * 0.55))
            tint = Image.new("RGBA", faded.size, bg + (0,))
            faded = Image.blend(faded, tint, 0.0)
            faded.putalpha(alpha)
            im.alpha_composite(faded, (cx - faded.width // 2, self.H - faded.height))
        self._base_cache[key] = im
        return im

    def clay_frame(self, beat: Beat, f: int) -> Image.Image | None:
        folder = self.vis.clay.get(beat.line_id or "")
        if folder is None:
            return None
        idx = f - f % self.vis.clay_step + 1
        path = Path(folder) / f"{idx:05d}.png"
        key = ("clay", str(path))
        if key not in self._base_cache:
            if not path.exists():
                raise RenderError(f"Missing clay frame {path.name} for line {beat.line_id}.")
            self._base_cache = {k: v for k, v in self._base_cache.items() if k[0] != "clay"}
            with Image.open(path) as src:
                self._base_cache[key] = src.convert("RGB").resize((self.W, self.H), Image.LANCZOS).convert("RGBA")
        return self._base_cache[key]

    def frame_line(self, beat: Beat, f: int) -> Image.Image:
        clay = self.clay_frame(beat, f)
        if clay is not None:
            im = clay.copy()
            self.top_bar_shaded(im)
            self.name_pill(im, beat.speaker_name or beat.speaker, self.S(220), self.H - self.S(250), ease(f / 6.0))
            return self._overlays(im, beat, f)
        im = self.line_base(beat, beat.speaker).copy()
        slot = next((s for s in self.cast_layout(self.tl.cast) if s[0] == beat.speaker), None)
        if slot is not None:
            cid, cx, h = slot
            env = beat.env[f] if f < len(beat.env) else 0.0
            level = round(env * 6) / 6  # quantise so resized portraits can be cached
            grow = ease(f / 5.0)
            ph = int(h * (0.94 + 0.04 * grow + 0.012 * level))
            p = self.portrait(cid, ph)
            y = self.H - p.height - int(self.S(10) * level)
            im.alpha_composite(p, (cx - p.width // 2, max(0, y)))
            self.name_pill(im, beat.speaker_name or cid, cx, self.H - ph, ease(f / 6.0))
        return self._overlays(im, beat, f)

    def _overlays(self, im: Image.Image, beat: Beat, f: int) -> Image.Image:
        if self.vis.burn_subtitles:
            t = f / self.tl.fps
            for (s, e, text) in beat.cues:
                if s <= t < e:
                    self.subtitles(im, text)
                    break
        if beat.line_id in self.vis.fallback_lines:
            self.badge(im, "Preview voice")
        return im

    def top_bar_shaded(self, im: Image.Image) -> None:
        """Scene title and logo over a picture: a soft dark band keeps them readable."""
        band = Image.new("RGBA", (self.W, self.S(140)), (0, 0, 0, 0))
        d = ImageDraw.Draw(band)
        for y in range(band.height):
            d.line([(0, y), (self.W, y)], fill=(10, 10, 12, int(120 * (1 - y / band.height))))
        im.alpha_composite(band)
        d = ImageDraw.Draw(im)
        f = font_for(self.tl.title, self.S(30), "semibold")
        d.text((self.S(64), self.S(44)), self.tl.title, font=f, fill="#FFFFFF")
        if self.vis.logo is not None:
            lg = style.fit_inside(self.vis.logo, self.S(200), self.S(64))
            self._paste_logo_plate(im, lg, top=True)

    def frame_card(self, beat: Beat, f: int, *, label: str | None = None) -> Image.Image:
        key = ("card", beat.text, label)
        if key not in self._base_cache:
            im = Image.new("RGBA", (self.W, self.H), rgb(self.pal.primary) + (255,))
            d = ImageDraw.Draw(im)
            fg = readable_on(self.pal.primary, "#FFFFFF")
            d.rectangle((self.S(120), self.S(300), self.S(132), self.H - self.S(300)), fill=self.pal.accent)
            y0 = self.S(300)
            if label:
                lf = font_for(label, self.S(34), "bold")
                d.text((self.S(170), y0), label.upper(), font=lf, fill=self.pal.accent)
                y0 += self.S(70)
            ft, lines, size = fit_text(d, beat.text, self.W - self.S(340), self.H - y0 - self.S(260),
                                       start=self.S(84), minimum=self.S(44), weight="bold", max_lines=5)
            y = y0
            for ln in lines:
                d.text((self.S(170), y), ln, font=ft, fill=fg)
                y += int(size * 1.2)
            if self.vis.logo is not None:
                lg = style.fit_inside(self.vis.logo, self.S(200), self.S(64))
                self._paste_logo_plate(im, lg)
            self._base_cache[key] = im
        return self._fade(self._base_cache[key], f)

    def _paste_logo_plate(self, im: Image.Image, lg: Image.Image, top: bool = False) -> None:
        pad = self.S(14)
        x = self.W - self.S(64) - lg.width - 2 * pad
        y = self.S(30) if top else self.H - self.S(56) - lg.height - 2 * pad
        plate = Image.new("RGBA", (lg.width + 2 * pad, lg.height + 2 * pad), (0, 0, 0, 0))
        ImageDraw.Draw(plate).rounded_rectangle((0, 0, plate.width - 1, plate.height - 1), radius=self.S(12),
                                                fill=rgb(self.pal.background) + (255,))
        plate.alpha_composite(lg, (pad, pad))
        im.alpha_composite(plate, (x, y))

    def frame_title(self, beat: Beat, f: int) -> Image.Image:
        key = ("title", beat.text)
        if key not in self._base_cache:
            im = self.background().convert("RGBA")
            d = ImageDraw.Draw(im)
            topic = beat.extra.get("topic", "")
            y = self.H // 2 - self.S(120)
            if topic:
                tf = font_for(topic, self.S(32), "bold")
                d.text((self.S(140), y), topic.upper(), font=tf, fill=self.pal.accent)
                y += self.S(64)
            ft, lines, size = fit_text(d, beat.text, self.W - self.S(280), self.S(300), start=self.S(104),
                                       minimum=self.S(56), weight="bold", max_lines=2)
            for ln in lines:
                d.text((self.S(140), y), ln, font=ft, fill=self.pal.primary)
                y += int(size * 1.12)
            if self.vis.logo is not None:
                lg = style.fit_inside(self.vis.logo, self.S(240), self.S(80))
                im.alpha_composite(lg, (self.W - self.S(64) - lg.width, self.S(40)))
            self._base_cache[key] = im
        return self._fade(self._base_cache[key], f)

    def frame_intro(self, beat: Beat, f: int) -> Image.Image:
        key = ("intro",)
        if key not in self._base_cache:
            im = self.background().convert("RGBA")
            d = ImageDraw.Draw(im)
            y = self.S(250)
            if self.vis.logo is not None:
                lg = style.fit_inside(self.vis.logo, self.S(520), self.S(150))
                im.alpha_composite(lg, ((self.W - lg.width) // 2, self.S(150)))
                y = self.S(150) + lg.height + self.S(80)
            for text, size, weight, color in (
                (beat.extra.get("org", ""), 36, "semibold", self.pal.text),
                (beat.text, 92, "bold", self.pal.primary),
                (beat.extra.get("subtitle", ""), 40, "regular", self.pal.text),
            ):
                if not text:
                    continue
                ft, lines, sz = fit_text(d, text, self.W - self.S(300), self.S(size * 2.6), start=self.S(size),
                                         minimum=self.S(size * 0.6), weight=weight, max_lines=2)
                for ln in lines:
                    w = text_width(d, ln, ft)
                    d.text(((self.W - w) // 2, y), ln, font=ft, fill=color)
                    y += int(sz * 1.18)
                y += self.S(24)
            note = beat.extra.get("announcement", "")
            if note:
                ft = font_for(note, self.S(30), "regular")
                lines = wrap_px(d, note, ft, self.W - self.S(400), 2)
                yy = self.H - self.S(150)
                for ln in lines:
                    w = text_width(d, ln, ft)
                    d.text(((self.W - w) // 2, yy), ln, font=ft, fill=self.pal.text)
                    yy += self.S(40)
            self._base_cache[key] = im
        return self._fade(self._base_cache[key], f)

    def frame_outro(self, beat: Beat, f: int) -> Image.Image:
        key = ("outro",)
        if key not in self._base_cache:
            im = Image.new("RGBA", (self.W, self.H), rgb(self.pal.primary) + (255,))
            d = ImageDraw.Draw(im)
            fg = readable_on(self.pal.primary, "#FFFFFF")
            y = self.S(250)
            for text, size, weight, color in (
                (beat.extra.get("ask", ""), 52, "semibold", fg),
                (beat.extra.get("contact", ""), 88, "bold", self.pal.accent if style.contrast(self.pal.accent, self.pal.primary) >= 3 else fg),
                (beat.extra.get("url", ""), 38, "regular", fg),
            ):
                if not text:
                    continue
                ft, lines, sz = fit_text(d, text, self.W - self.S(240), self.S(size * 2.5), start=self.S(size),
                                         minimum=self.S(size * 0.5), weight=weight, max_lines=2)
                for ln in lines:
                    w = text_width(d, ln, ft)
                    d.text(((self.W - w) // 2, y), ln, font=ft, fill=color)
                    y += int(sz * 1.2)
                y += self.S(30)
            credits = beat.extra.get("credits") or []
            cy = self.H - self.S(70) - len(credits) * self.S(40)
            for c in credits:
                ft = font_for(c, self.S(28), "regular")
                w = text_width(d, c, ft)
                d.text(((self.W - w) // 2, cy), c, font=ft, fill=fg)
                cy += self.S(40)
            self._base_cache[key] = im
        return self._fade(self._base_cache[key], f)

    def _fade(self, im: Image.Image, f: int, n: int = 8) -> Image.Image:
        if f >= n:
            return im
        bg = Image.new("RGBA", im.size, rgb(self.pal.background) + (255,))
        return Image.blend(bg, im, ease((f + 1) / n))

    # ---------------------------------------------------------------- driver
    def frames(self):
        for beat in self.tl.beats:
            last_key, last = None, None
            for f in range(beat.frames):
                if beat.kind == "line":
                    env = beat.env[f] if f < len(beat.env) else 0.0
                    t = f / self.tl.fps
                    cue = next((c[2] for c in beat.cues if c[0] <= t < c[1]), None) if self.vis.burn_subtitles else None
                    clay_idx = f - f % self.vis.clay_step if beat.line_id in self.vis.clay else None
                    key = ("line", round(env * 6), min(f, 6), cue, clay_idx)
                    if key != last_key or last is None:
                        last = self.frame_line(beat, f).convert("RGB").tobytes()
                        last_key = key
                    yield last
                    continue
                key = (beat.kind, min(f, 8))
                if key != last_key or last is None:
                    if beat.kind == "title":
                        im = self.frame_title(beat, f)
                    elif beat.kind == "intro":
                        im = self.frame_intro(beat, f)
                    elif beat.kind == "outro":
                        im = self.frame_outro(beat, f)
                    elif beat.kind == "takeaway":
                        im = self.frame_card(beat, f, label=beat.extra.get("label", "Key point"))
                    else:
                        im = self.frame_card(beat, f)
                    last = im.convert("RGB").tobytes()
                    last_key = key
                yield last


def render_scene(tl: SceneTimeline, vis: Visuals, out: Path, preset: str = "preview", threads: int = 0) -> None:
    if preset not in PRESETS:
        raise RenderError(f"Unknown preset '{preset}'.", f"Use one of {', '.join(PRESETS)}.")
    r = SceneRenderer(tl, vis, preset)
    p = PRESETS[preset]
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part.mp4")
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{r.W}x{r.H}", "-r", str(tl.fps), "-i", "pipe:0", "-c:v", "libx264", "-preset", p["x264"],
           "-crf", str(p["crf"]), "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
           # setparams tags the frames themselves: FFmpeg 9 takes colour tags from the frames, not the
           # options above, and would otherwise write "unknown" primaries and transfer.
           "-color_trc", "bt709", "-color_range", "tv", "-vf", "scale=out_color_matrix=bt709:out_range=tv,"
           "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
           "-g", str(tl.fps * 2), "-threads", str(threads), "-movflags", "+faststart", "-an", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    n = 0
    try:
        for frame in r.frames():
            proc.stdin.write(frame)
            n += 1
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace")
        code = proc.wait(timeout=600)
    except BrokenPipeError:
        err = proc.stderr.read().decode("utf-8", "replace")
        code = proc.wait()
    if code != 0:
        tmp.unlink(missing_ok=True)
        raise RenderError(f"Encoding scene {tl.id} failed: {err.strip()[-300:]}")
    if n != tl.frames:
        tmp.unlink(missing_ok=True)
        raise RenderError(f"Scene {tl.id}: wrote {n} frames, expected {tl.frames}.")
    tmp.replace(out)


__all__ = ["PRESETS", "Visuals", "render_scene", "avatar", "math", "ImageFilter"]
