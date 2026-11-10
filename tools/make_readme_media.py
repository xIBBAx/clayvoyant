"""Compose the README cover, social card, thumbnail and cast board from the project's own brand
files and character portraits (run from the repository root).

    python tools/make_readme_media.py

Everything is drawn from files in this repository; nothing is taken from elsewhere.
"""

from pathlib import Path

from PIL import Image, ImageDraw

from sastudio.render.style import font, text_width, wrap_px

BRAND = Path("docs/media/brand")
CAST_DIR = Path("src/sastudio/templates/starter/assets/characters")
OUT = Path("docs/media")
TEAL, ORANGE, INK, PAPER, MUTED = "#1E4E5F", "#E07A3F", "#16191D", "#F4EFE6", "#4A5A60"
CAST = [("mira", "Mira", "Security lead"), ("leo", "Leo", "New starter"), ("aarav", "Aarav", "Finance"),
        ("nadia", "Nadia", "Operations manager"), ("rook", "Rook", "The impersonator")]
HEADLINE = "Security-awareness films, built from plain text."
SUB = "Your organisation, characters, languages and voices.\nOpen source, offline-first, no GPU needed."


def portrait(cid: str, height: int) -> Image.Image:
    im = Image.open(CAST_DIR / f"{cid}.png").convert("RGBA")
    return im.resize((round(im.width * height / im.height), height), Image.LANCZOS)


def logo(width: int, dark: bool = False) -> Image.Image:
    im = Image.open(BRAND / ("logo-for-dark.png" if dark else "logo-for-light.png")).convert("RGBA")
    return im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)


def lineup(height: int, gap: int, ids=None) -> Image.Image:
    figs = [portrait(c, height) for c in (ids or [c[0] for c in CAST])]
    w = sum(f.width for f in figs) + gap * (len(figs) - 1)
    im = Image.new("RGBA", (w, height), (0, 0, 0, 0))
    x = 0
    for f in figs:
        im.alpha_composite(f, (x, 0))
        x += f.width + gap
    return im


def text_block(d: ImageDraw.ImageDraw, x: int, y: int, text: str, size: int, weight: str, fill: str, max_w: int,
               leading: float = 1.18) -> int:
    f = font(size, weight)
    for line in [ln for para in text.split("\n") for ln in wrap_px(d, para, f, max_w)]:
        d.text((x, y), line, font=f, fill=fill)
        y += round(size * leading)
    return y


def cover(w: int, h: int) -> Image.Image:
    """Text on the left, the cast on the right; the text column is measured from the cast's position."""
    s = h / 640
    im = Image.new("RGBA", (w, h), PAPER)
    d = ImageDraw.Draw(im)
    left, gutter = round(64 * s), round(44 * s)
    wide = w / h > 1.9
    cast = lineup(round((380 if wide else 320) * s), round(-4 * s))
    cx = w - cast.width - round(56 * s)
    col = cx - left - gutter
    lg = logo(min(round(380 * s), col))
    hs, ss = round((36 if wide else 30) * s), round((21 if wide else 17) * s)
    head = wrap_px(d, HEADLINE, font(hs, "bold"), col)
    sub = [ln for para in SUB.split("\n") for ln in wrap_px(d, para, font(ss, "regular"), col)]
    block = lg.height + round(40 * s) + len(head) * round(hs * 1.18) + round(18 * s) + len(sub) * round(ss * 1.4)
    y = (h - block) // 2
    im.alpha_composite(lg, (left, y))
    y += lg.height + round(40 * s)
    y = text_block(d, left, y, HEADLINE, hs, "bold", INK, col)
    text_block(d, left, y + round(18 * s), SUB, ss, "regular", MUTED, col, 1.4)
    im.alpha_composite(cast, (cx, (h - cast.height) // 2 + round(8 * s)))
    return im


def thumbnail() -> Image.Image:
    w, h = 1280, 720
    im = Image.new("RGBA", (w, h), TEAL)
    d = ImageDraw.Draw(im)
    f = font(118, "bold")
    d.text((80, 150), "Security", font=f, fill=PAPER)
    d.text((80, 285), "Awareness", font=f, fill=PAPER)
    d.text((86, 445), "Training films from plain text", font=font(44, "bold"), fill="#F2A877")
    d.text((86, 520), "Open source. Make it yours.", font=font(32, "regular"), fill="#CFE0E3")
    cast = lineup(560, 6, ["mira", "rook"])
    im.alpha_composite(cast, (w - cast.width - 90, h - cast.height - 40))
    return im


def cast_board() -> Image.Image:
    w, h = 1600, 900
    im = Image.new("RGBA", (w, h), PAPER)
    d = ImageDraw.Draw(im)
    d.text((80, 64), "The cast", font=font(52, "bold"), fill=INK)
    d.text((82, 136), "Five characters, ready to rename, re-voice and re-cast.", font=font(26, "regular"),
           fill=MUTED)
    col_w = (w - 160) // len(CAST)
    for i, (cid, name, role) in enumerate(CAST):
        fig = portrait(cid, 520)
        cx = 80 + col_w * i + col_w // 2
        im.alpha_composite(fig, (cx - fig.width // 2, 214))
        fn, fr = font(36, "bold"), font(24, "regular")
        d.text((cx - text_width(d, name, fn) // 2, 760), name, font=fn, fill=INK)
        d.text((cx - text_width(d, role, fr) // 2, 812), role, font=fr, fill=TEAL)
    return im


def styles_board() -> Image.Image:
    """The starter cast in the four styles, drawn by the package itself in a temporary project."""
    import tempfile

    from sastudio.build import cast_sheet
    from sastudio.cli import main
    from sastudio.project import load_project

    with tempfile.TemporaryDirectory(prefix="sas-styles-") as tmp:
        main(["init", f"{tmp}/film"])
        return cast_sheet(load_project(Path(tmp) / "film"), ["v1", "v2", "v3", "v4"], height=380)


def save(im: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(path, optimize=True)  # no text chunks, no EXIF
    print(f"wrote {path} {im.size[0]}x{im.size[1]} {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    save(cover(1280, 640), OUT / "film" / "cover-1280x640.png")
    save(cover(1920, 1080), OUT / "film" / "cover-1920x1080.png")
    save(thumbnail(), OUT / "film" / "thumbnail-1280x720.png")
    save(cast_board(), OUT / "characters" / "cast-1600x900.png")
    save(styles_board(), OUT / "characters" / "styles.png")
