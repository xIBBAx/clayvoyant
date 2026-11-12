"""Fonts, colours and text layout shared by the renderers."""

from __future__ import annotations

import functools
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

from ..errors import ConfigError
from ..text.speech import has_devanagari

FONT_DIR = resources.files("sastudio.data").joinpath("fonts")
LATIN = "AtkinsonHyperlegibleNext[wght].ttf"
DEVANAGARI = {"regular": "Mukta-Regular.ttf", "bold": "Mukta-Bold.ttf"}
# The other Indian scripts, by the first code point of their Unicode block. Each Noto font also carries Latin, so a
# line that mixes a script with a web address or a number draws whole.
INDIC = {0x0980: "NotoSansBengali[wdth,wght].ttf", 0x0A00: "NotoSansGurmukhi[wdth,wght].ttf",
         0x0A80: "NotoSansGujarati[wdth,wght].ttf", 0x0B00: "NotoSansOriya[wdth,wght].ttf",
         0x0B80: "NotoSansTamil[wdth,wght].ttf", 0x0C00: "NotoSansTelugu[wdth,wght].ttf",
         0x0C80: "NotoSansKannada[wdth,wght].ttf", 0x0D00: "NotoSansMalayalam[wdth,wght].ttf"}
WEIGHTS = {"regular": 400, "medium": 500, "semibold": 600, "bold": 700, "extrabold": 800}
HAS_RAQM = features.check("raqm")


@dataclass(frozen=True)
class Palette:
    primary: str = "#1E4E5F"
    accent: str = "#E07A3F"
    background: str = "#F4EFE6"
    text: str = "#1C1C1E"

    @classmethod
    def from_config(cls, cfg: dict | None) -> Palette:
        cfg = cfg or {}
        return cls(**{k: cfg[k] for k in ("primary", "accent", "background", "text") if k in cfg})


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance(hex_color: str) -> float:
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb(hex_color)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def readable_on(bg: str, preferred: str = "#1C1C1E") -> str:
    """Pick text colour with at least 4.5:1 contrast (WCAG AA for body text)."""
    if contrast(bg, preferred) >= 4.5:
        return preferred
    return "#FFFFFF" if contrast(bg, "#FFFFFF") >= contrast(bg, "#111111") else "#111111"


def script(text: str) -> str | int:
    """Which font a piece of text needs: "devanagari", the block of another Indian script, or "latin"."""
    if has_devanagari(text):
        return "devanagari"
    for ch in text:
        block = ord(ch) & ~0x7F
        if block in INDIC:
            return block
    return "latin"


@functools.lru_cache(maxsize=128)
def font(size: int, weight: str = "regular", devanagari: bool = False, script: str | int = "latin") -> ImageFont.FreeTypeFont:
    engine = ImageFont.Layout.RAQM if HAS_RAQM else ImageFont.Layout.BASIC
    if devanagari or script == "devanagari":
        path = FONT_DIR.joinpath(DEVANAGARI["bold" if weight in ("bold", "semibold") else "regular"])
        return ImageFont.truetype(str(path), size, layout_engine=engine)
    f = ImageFont.truetype(str(FONT_DIR.joinpath(INDIC.get(script, LATIN))), size, layout_engine=engine)
    try:
        # every axis at its default except the weight (the Noto fonts also have a width axis)
        f.set_variation_by_axes([WEIGHTS[weight] if a.get("name") in (b"Weight", "Weight") else a["default"]
                                 for a in f.get_variation_axes()])
    except (OSError, ValueError):  # FreeType without variation support: regular only
        pass
    return f


def font_for(text: str, size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    return font(size, weight, script=script(text))


def text_width(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=f)
    return right - left


def wrap_px(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_w: int, max_lines: int | None = None) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if text_width(draw, cand, f) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and text_width(draw, lines[-1] + "…", f) > max_w:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines


def fit_text(draw, text: str, max_w: int, max_h: int, *, start: int, minimum: int, weight: str = "bold",
             line_gap: float = 1.18, max_lines: int = 4):
    """Largest font size (from `start` down to `minimum`) at which `text` fits the box."""
    size = start
    while size >= minimum:
        f = font_for(text, size, weight)
        lines = wrap_px(draw, text, f, max_w)
        h = int(len(lines) * size * line_gap)
        if len(lines) <= max_lines and h <= max_h:
            return f, lines, size
        size -= 2
    f = font_for(text, minimum, weight)
    return f, wrap_px(draw, text, f, max_w, max_lines), minimum


def load_image(path: Path, max_side: int = 4096) -> Image.Image:
    """Open an untrusted image safely: size-capped, converted to RGBA."""
    Image.MAX_IMAGE_PIXELS = 40_000_000
    try:
        with Image.open(path) as im:
            im.load()
            if max(im.size) > max_side:
                im.thumbnail((max_side, max_side))
            return im.convert("RGBA")
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as e:
        raise ConfigError(f"{Path(path).name} is not a readable image ({type(e).__name__}).",
                          "Replace it with a valid PNG, JPG or WebP file under 40 megapixels.") from None


def fit_inside(im: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """Scale an image to fit a box keeping its aspect ratio (handles very wide or tall logos)."""
    w, h = im.size
    s = min(box_w / w, box_h / h)
    return im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)


def cover(im: Image.Image, w: int, h: int) -> Image.Image:
    iw, ih = im.size
    s = max(w / iw, h / ih)
    im = im.resize((max(1, int(iw * s)), max(1, int(ih * s))), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))
