"""Regenerate the project's logo files in docs/media/brand/ (run from the repository root)."""

from pathlib import Path

from PIL import Image, ImageDraw

from sastudio.render.style import font, text_width

OUT = Path("docs/media/brand")
TEAL, ORANGE, INK, PAPER = "#1E4E5F", "#E07A3F", "#16191D", "#F4EFE6"


def mark_svg(frame: str, lens: str, pupil: str) -> str:
    # A rounded film frame holding a lens: making films, and paying attention.
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="Clayvoyant">
  <rect x="4" y="10" width="56" height="44" rx="12" fill="{frame}"/>
  <path d="M14 32 C22 20, 42 20, 50 32 C42 44, 22 44, 14 32 Z" fill="{lens}"/>
  <circle cx="32" cy="32" r="6.5" fill="{pupil}"/>
  <circle cx="34.6" cy="29.6" r="1.8" fill="{lens}"/>
</svg>
"""


def mark_png(size: int, frame: str, lens: str, pupil: str) -> Image.Image:
    """Drawn at 4x and scaled down, for smooth edges."""
    big = _mark_png(size * 4, frame, lens, pupil)
    return big.resize((size, size), Image.LANCZOS)


def _mark_png(size: int, frame: str, lens: str, pupil: str) -> Image.Image:
    s = size / 64
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((4 * s, 10 * s, 60 * s, 54 * s), radius=12 * s, fill=frame)
    pts = []
    for i in range(0, 61):
        t = i / 60
        # upper and lower curves of the lens (cubic Bezier, matching the SVG)
        x = (1 - t) ** 3 * 14 + 3 * (1 - t) ** 2 * t * 22 + 3 * (1 - t) * t ** 2 * 42 + t ** 3 * 50
        y = (1 - t) ** 3 * 32 + 3 * (1 - t) ** 2 * t * 20 + 3 * (1 - t) * t ** 2 * 20 + t ** 3 * 32
        pts.append((x * s, y * s))
    pts += [(x, 64 * s - y) for x, y in reversed(pts)]
    d.polygon(pts, fill=lens)
    d.ellipse(((32 - 6.5) * s, (32 - 6.5) * s, (32 + 6.5) * s, (32 + 6.5) * s), fill=pupil)
    d.ellipse(((34.6 - 1.8) * s, (29.6 - 1.8) * s, (34.6 + 1.8) * s, (29.6 + 1.8) * s), fill=lens)
    return im


def wordmark(bg: str | None, fg: str, sub: str, mark_cols, path: Path, height: int = 240) -> None:
    mark = mark_png(height, *mark_cols)
    f1, f2 = font(int(height * .36), "bold"), font(int(height * .2), "medium")
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    w = height + int(height * .18) + max(text_width(probe, "Security Awareness", f1), text_width(probe, "STUDIO", f2)) + 20
    im = Image.new("RGBA", (w, height), (0, 0, 0, 0) if bg is None else bg)
    im.alpha_composite(mark, (0, 0))
    d = ImageDraw.Draw(im)
    x = height + int(height * .18)
    d.text((x, int(height * .14)), "Security Awareness", font=f1, fill=fg)
    d.text((x + 4, int(height * .6)), "STUDIO", font=f2, fill=sub)
    im.save(path, optimize=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    colour = (TEAL, ORANGE, INK)
    (OUT / "mark.svg").write_text(mark_svg(*colour), encoding="utf-8")
    (OUT / "mark-on-dark.svg").write_text(mark_svg(PAPER, ORANGE, INK), encoding="utf-8")
    (OUT / "mark-mono.svg").write_text(mark_svg(INK, PAPER, INK), encoding="utf-8")
    mark_png(512, *colour).save(OUT / "mark-512.png", optimize=True)
    wordmark(None, INK, TEAL, colour, OUT / "logo-for-light.png")
    wordmark(None, PAPER, "#E9B48F", (PAPER, ORANGE, INK), OUT / "logo-for-dark.png")
    print("brand files written to", OUT)


if __name__ == "__main__":
    main()
