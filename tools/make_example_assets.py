"""Draw the fictional Northgate Logistics logo used by examples/northgate (run from the repository root).

Northgate Logistics is an invented organisation for demonstrations; its web and email addresses use
the reserved .example domain, so they can never belong to a real company.
"""

from pathlib import Path

from PIL import Image, ImageDraw

from sastudio.render.style import font, text_width

OUT = Path("examples/northgate/assets/logo.png")
GREEN, AMBER, INK, PAPER = "#23493B", "#D9A441", "#1C1C1E", "#F3EFE6"


def mark(size: int) -> Image.Image:
    """A gate: an arch cut from a rounded square, with a small north pointer above it. Drawn at 4x."""
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s * 0.22, fill=GREEN)
    w, top, bottom = s * 0.44, s * 0.40, s * 0.84
    x0 = (s - w) / 2
    d.rectangle((x0, top + w / 2, x0 + w, bottom), fill=PAPER)
    d.pieslice((x0, top, x0 + w, top + w), 180, 360, fill=PAPER)
    d.polygon([(s / 2, s * 0.10), (s / 2 + s * 0.085, s * 0.27), (s / 2 - s * 0.085, s * 0.27)], fill=AMBER)
    return im.resize((size, size), Image.LANCZOS)


def logo() -> Image.Image:
    h = 220
    im = Image.new("RGBA", (780, h), (0, 0, 0, 0))
    im.alpha_composite(mark(196), (12, 12))
    d = ImageDraw.Draw(im)
    big, small = font(104, "bold"), font(40, "bold")
    d.text((240, 26), "Northgate", font=big, fill=INK)
    word, x = "LOGISTICS", 244
    for ch in word:  # letter-spaced caption
        d.text((x, 150), ch, font=small, fill=GREEN)
        x += text_width(d, ch, small) + 9
    return im.crop(im.getbbox())


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    logo().save(OUT, optimize=True)
    print(f"wrote {OUT}")
