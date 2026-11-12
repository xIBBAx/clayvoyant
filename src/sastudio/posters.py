"""Posters: each scene's lesson as a printed page, for a notice board, a classroom wall or a phone.

One page per scene and language, A4 or US Letter at 300 dots per inch, and one PDF per language with every
page in order. Everything on a page comes from the project: the scene's topic, headline and key point, the
people in it, the organisation's name, logo and colours, and where to report. No new words are invented here;
a scene with neither a headline nor a key point has nothing to put on a wall and gets no page.

Text is set in the font its script needs (Latin, Devanagari and eight more Indian scripts) and kept at 4.5:1
contrast with whatever is behind it.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .build import topic_label, ui_label, visuals
from .render import style as S

SIZES = {"a4": (2480, 3508), "letter": (2550, 3300)}      # 300 dpi


def _portraits(project, scene, vis) -> list[Image.Image]:
    """The people who speak in the scene, in order of first line: clay portraits when they have been made
    (`sastudio clay portraits`), otherwise the drawn figure or the portrait file the character already uses."""
    out, seen = [], []
    for ln in scene.lines:
        if ln.who and ln.who not in seen:
            seen.append(ln.who)
    for cid in seen[:3]:
        clay = project.root / "assets" / "characters" / f"{cid}_clay.png"
        if clay.is_file():
            out.append(S.load_image(clay))
        elif cid in vis.portraits:
            out.append(vis.portraits[cid])
    return out


def _text(d, xy, lines, f, size, fill, gap=1.2) -> int:
    x, y = xy
    for ln in lines:
        d.text((x, y), ln, font=f, fill=fill)
        y += int(size * gap)
    return y


def page(project, scene, lang: str, size: str = "a4", vis=None) -> Image.Image | None:
    """One scene's poster, or None when the scene has nothing to put on it."""
    headline = project.display(scene.field_for("headline", lang, project.language), lang)
    takeaway = project.display(scene.field_for("takeaway", lang, project.language), lang)
    if not (headline or takeaway):
        return None
    vis = vis or visuals(project, False, set())[0]
    pal = vis.palette
    W, H = SIZES[size]
    u = W / 2480
    m = int(170 * u)                       # page margin
    im = Image.new("RGBA", (W, H), S.rgb(pal.background) + (255,))
    d = ImageDraw.Draw(im)

    # the organisation, on a band of its own colour
    band = int(380 * u)
    d.rectangle((0, 0, W, band), fill=pal.primary)
    on_band = S.readable_on(pal.primary, "#FFFFFF")
    logo_w = 0
    if vis.logo is not None:
        lg = S.fit_inside(vis.logo, int(560 * u), int(200 * u))
        pad = int(26 * u)
        plate = Image.new("RGBA", (lg.width + 2 * pad, lg.height + 2 * pad), (0, 0, 0, 0))
        ImageDraw.Draw(plate).rounded_rectangle((0, 0, plate.width - 1, plate.height - 1), radius=int(24 * u),
                                                fill=S.rgb(pal.background) + (255,))
        plate.alpha_composite(lg, (pad, pad))
        im.alpha_composite(plate, (W - m - plate.width, (band - plate.height) // 2))
        logo_w = plate.width + int(60 * u)
    org = project.display("{org.name}", lang)
    f, lines, sz = S.fit_text(d, org, W - 2 * m - logo_w, band - int(120 * u), start=int(92 * u), minimum=int(52 * u),
                              weight="bold", max_lines=2)
    _text(d, (m, (band - int(len(lines) * sz * 1.2)) // 2), lines, f, sz, on_band)

    y = band + int(170 * u)
    on_page = S.readable_on(pal.background, pal.text)
    accent = pal.accent if S.contrast(pal.background, pal.accent) >= 4.5 else on_page
    if scene.topic:
        t = topic_label(project, scene.topic, lang)
        t = t.upper() if t.isascii() else t
        ft = S.font_for(t, int(64 * u), "bold")
        d.text((m, y), t, font=ft, fill=accent)
        y += int(130 * u)
    if headline:
        hcol = pal.primary if S.contrast(pal.background, pal.primary) >= 4.5 else on_page
        f, lines, sz = S.fit_text(d, headline, W - 2 * m, int(820 * u), start=int(176 * u), minimum=int(96 * u),
                                  weight="bold", max_lines=4)
        y = _text(d, (m, y), lines, f, sz, hcol, 1.16) + int(90 * u)
    if takeaway:
        d.rectangle((m, y, m + int(16 * u), y + int(40 * u)), fill=pal.accent)
        lab = ui_label(project, "key_point", lang)
        lab = lab.upper() if lab.isascii() else lab
        d.text((m + int(44 * u), y - int(6 * u)), lab, font=S.font_for(lab, int(52 * u), "bold"), fill=accent)
        y += int(110 * u)
        f, lines, sz = S.fit_text(d, takeaway, W - 2 * m, int(1000 * u), start=int(104 * u), minimum=int(60 * u),
                                  weight="semibold", max_lines=9)
        y = _text(d, (m, y), lines, f, sz, on_page, 1.28) + int(60 * u)

    # where to report, along the foot of the page
    foot = int(330 * u)
    d.rectangle((0, H - foot, W, H), fill=pal.primary)
    where = project.org.get("reporting_url") or project.org.get("security_email") or ""
    prompt = ui_label(project, "report_prompt", lang)
    fp = S.font_for(prompt, int(56 * u), "semibold")
    d.text((m, H - foot + int(70 * u)), prompt, font=fp, fill=on_band)
    if where:
        shown = where.removeprefix("https://").removeprefix("http://").rstrip("/")
        fw, lines, sz = S.fit_text(d, shown, W - 2 * m, int(130 * u), start=int(104 * u), minimum=int(60 * u),
                                   weight="bold", max_lines=1)
        d.text((m, H - foot + int(160 * u)), lines[0], font=fw, fill=on_band)

    # the people in the scene, standing on the footer
    people = _portraits(project, scene, vis)
    room = H - foot - y - int(40 * u)
    if people and room > int(500 * u):
        ph = min(room, int(1250 * u))
        scaled = [p.resize((max(1, int(p.width * ph / p.height)), ph), Image.LANCZOS) for p in people]
        gap = int(40 * u)
        total = sum(p.width for p in scaled) + gap * (len(scaled) - 1)
        if total > W - 2 * m:
            k = (W - 2 * m) / total
            scaled = [p.resize((max(1, int(p.width * k)), max(1, int(ph * k))), Image.LANCZOS) for p in scaled]
            total = W - 2 * m
        x = (W - total) // 2
        for p in scaled:
            im.alpha_composite(p.convert("RGBA"), (x, H - foot - p.height))
            x += p.width + gap
    return im.convert("RGB")


def make(project, lang: str | None = None, size: str = "a4", out: Path | None = None) -> list[Path]:
    """Every scene's poster in `lang` as PNG, and all of them as one PDF. Returns the files written."""
    lang = lang or project.language
    if lang not in project.languages:
        from .errors import ConfigError

        raise ConfigError(f"This project has no {lang} text.", f"Languages: {', '.join(project.languages)}.")
    out = Path(out) if out else project.root / project.render_cfg.get("output", "build") / lang / "posters"
    out.mkdir(parents=True, exist_ok=True)
    vis = visuals(project, False, set())[0]
    pages, written = [], []
    n = 0
    for scene in (s for s in project.scenes if s.enabled):
        im = page(project, scene, lang, size, vis)
        if im is None:
            continue
        n += 1
        p = out / f"{n:02d}_{scene.id}.{lang}.png"
        tmp = p.with_suffix(".part.png")
        im.save(tmp, dpi=(300, 300), optimize=True)
        tmp.replace(p)
        pages.append(im)
        written.append(p)
    if pages:
        pdf = out / f"posters.{lang}.pdf"
        tmp = pdf.with_suffix(".part.pdf")
        pages[0].save(tmp, save_all=True, append_images=pages[1:], resolution=300.0)
        tmp.replace(pdf)
        written.append(pdf)
    return written
