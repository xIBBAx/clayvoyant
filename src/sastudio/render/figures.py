"""Drawn characters in three styles, made from a short text description.

A character's *design* (skin, hair, outfit, shoes and a few extras) is turned into one set of
shapes in a 34 x 100 unit figure space. Three painters draw those shapes in different visual
languages:

* ``v1`` sketch: graphite outlines over a light wash, hatched shadows, like a storyboard page.
* ``v2`` flat: clean flat colour with one rim shadow per shape, like an explainer video.
* ``v3`` cut-out: layered paper pieces with cut edges, cast shadows and paper grain.

(``v4`` is the clay style: the bundled clay portraits, not drawn here.)

Every figure exists in talking and blinking variants, so the cards renderer can animate the
speaker. Drawing is deterministic: the same design, style and variant always give the same pixels.
Pure Pillow; no other dependency, no files read.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field

from PIL import Image, ImageChops, ImageDraw, ImageFilter

FIGURES_VERSION = "1"
W, H, CX = 34.0, 100.0, 17.0
TOP = 8.0  # headroom above y = 0 for tall hair
SUPERSAMPLE = 3

STYLES = {"v1": "sketch", "v2": "flat", "v3": "cutout", "v4": "clay"}
STYLE_ALIASES = {name: code for code, name in STYLES.items()} | {code: code for code in STYLES}
DRAWN_STYLES = ("v1", "v2", "v3")
HAIR_STYLES = ("short", "side_sweep", "swept_back", "curls", "bob", "bun", "long", "ponytail", "headscarf", "bald")
OUTFITS = ("blazer", "suit", "jacket", "shirt", "sweater", "kurta", "hoodie", "vest")
SHOES = ("flat", "sneaker", "brogue", "heel", "boot")
EXTRAS = ("glasses", "necklace", "lapel_pin", "freckles", "earrings", "beard", "moustache", "bindi")
VARIANTS = ("rest", "talk1", "talk2", "blink", "talk1_blink", "talk2_blink")

# The five bundled characters, drawn to match their clay portraits.
BUILTIN_DESIGNS: dict[str, dict] = {
    "mira": {"skin": "#C8916A", "eyes": "#2A1A10", "hair": {"style": "bob", "color": "#1C1517"},
             "outfit": {"style": "blazer", "color": "#2E6F73", "shirt": "#F2ECE2"}, "trousers": "#26343F",
             "shoes": {"style": "flat", "color": "#6B4A3A"}, "extras": ["necklace"]},
    "leo": {"skin": "#8D5A3B", "eyes": "#24160C", "hair": {"style": "side_sweep", "color": "#1B120D"},
            "outfit": {"style": "jacket", "color": "#8C5A3C", "shirt": "#F1E6D3"}, "trousers": "#2F3A4A",
            "shoes": {"style": "sneaker", "color": "#F2EFE8"}, "extras": []},
    "aarav": {"skin": "#D9A47C", "eyes": "#2A1A0E", "hair": {"style": "curls", "color": "#121012"},
              "outfit": {"style": "suit", "color": "#3D5A80", "shirt": "#EEF1F4"}, "trousers": "#2A3346",
              "shoes": {"style": "brogue", "color": "#3A2A22"}, "extras": ["glasses", "lapel_pin"]},
    "nadia": {"skin": "#E6B896", "eyes": "#3A2A1A", "hair": {"style": "bun", "color": "#3B2418"},
              "outfit": {"style": "suit", "color": "#6B4E71", "shirt": "#F5EDE3"}, "trousers": "#3A2E40",
              "shoes": {"style": "heel", "color": "#2A2226"}, "extras": ["freckles", "lapel_pin"]},
    "rook": {"skin": "#C9A07A", "eyes": "#2C2218", "hair": {"style": "swept_back", "color": "#151214"},
             "outfit": {"style": "suit", "color": "#3B3B3F", "shirt": "#D9D4CC"}, "trousers": "#26262A",
             "shoes": {"style": "brogue", "color": "#1C1C1E"}, "extras": ["lapel_pin"]},
}

DEFAULT_DESIGN = {"skin": "#C99B78", "eyes": "#2A1C12", "hair": {"style": "short", "color": "#2A1E18"},
                  "outfit": {"style": "blazer", "color": "#4A6274", "shirt": "#F1ECE4"}, "trousers": "#2C3440",
                  "shoes": {"style": "flat", "color": "#3A2C24"}, "extras": []}
GOLD, INK = "#E2B856", "#26201D"
HEAD_SCALE, HEAD_PIVOT = 1.14, (CX, 25.0)
HEAD_PIECES = {"hair_back", "bun", "bun_coil", "bun_pin", "tail", "ear1", "ear-1", "ear_in1", "ear_in-1", "head",
               "freckle", "cheek", "beard", "eye", "eye_hi", "eye_closed", "brow", "nose", "moustache", "mouth",
               "teeth", "tongue", "scarf", "hair", "curl", "curl_hi", "streak", "part", "lens", "bridge",
               "temple", "earring", "bindi", "quiff", "wave"}


# --------------------------------------------------------------------------- colours and geometry
def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    x, y = rgb(a), rgb(b)
    r, g, b = (round(p + (q - p) * t) for p, q in zip(x, y, strict=True))
    return f"#{r:02X}{g:02X}{b:02X}"


def shade(c: str, t: float) -> str:
    return mix(c, "#141420", t)


def tint(c: str, t: float) -> str:
    return mix(c, "#FFFFFF", t)


def luminance(c: str) -> float:
    r, g, b = (v / 255 for v in rgb(c))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ell(cx, cy, rx, ry, a0=0.0, a1=360.0, n=44):
    """Points on an ellipse from angle a0 to a1 (degrees; 0 = right, 90 = down, 270 = top)."""
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def bez(p0, p1, p2, p3, n=14):
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


def mirror(pts):
    return [(2 * CX - x, y) for x, y in pts]


def capsule(p0, p1, r0, r1, n=12):
    """A tapered limb from p0 (radius r0) to p1 (radius r1)."""
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    out = []
    for i in range(n + 1):
        a = ang + math.pi / 2 + math.pi * i / n
        out.append((p1[0] + r1 * math.cos(a - math.pi), p1[1] + r1 * math.sin(a - math.pi)))
    for i in range(n + 1):
        a = ang - math.pi / 2 + math.pi * i / n
        out.append((p0[0] + r0 * math.cos(a + math.pi), p0[1] + r0 * math.sin(a + math.pi)))
    return out


HEAD = (CX, 15.6, 8.4, 9.7)  # centre x, centre y, radius x, radius y


def head_pts(grow=1.0, a0=0.0, a1=360.0, n=60):
    cx, cy, rx, ry = HEAD
    out = []
    for x, y in ell(cx, cy, rx * grow, ry * grow, a0, a1, n):
        if y > cy:  # the jaw narrows towards the chin
            x = cx + (x - cx) * (1 - 0.13 * (y - cy) / (ry * grow))
        out.append((x, y))
    return out


@dataclass
class Piece:
    name: str
    pts: list
    fill: str | None = None
    kind: str = "poly"  # poly | line
    width: float = 0.0  # line width in units
    role: str = "cloth"  # skin | hair | cloth | shoe | feature | accent
    alpha: float = 1.0
    holes: list = field(default_factory=list)
    shadow: bool = True  # casts a shadow in the cut-out style


# --------------------------------------------------------------------------- the design
def normalize(design: dict | None, preset: str | None = None) -> dict:
    """Merge a (possibly partial) design over the preset's or the default design."""
    base = BUILTIN_DESIGNS.get(preset or "", DEFAULT_DESIGN)
    d = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v) for k, v in base.items()}
    for k, v in (design or {}).items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            d[k] = {**d[k], **v}
        else:
            d[k] = v
    return d


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


# --------------------------------------------------------------------------- shapes
def build(d: dict, variant: str = "rest", seed: int = 0) -> list[Piece]:
    skin, hair = d["skin"], d["hair"]["color"]
    hs, outfit = d["hair"]["style"], d["outfit"]["style"]
    outfit = {"hoodie": "sweater", "vest": "sweater"}.get(outfit, outfit)  # drawn like the nearest outfit these styles know
    top, shirt = d["outfit"]["color"], d["outfit"].get("shirt", "#F1ECE4")
    extras = set(d.get("extras") or [])
    talk = 2 if "talk2" in variant else 1 if "talk1" in variant else 0
    blink = "blink" in variant
    P: list[Piece] = []
    add = P.append

    # hair behind the head and body
    if hs == "bob":
        add(Piece("hair_back", bez((7.6, 24.8), (5.6, 18.0), (6.0, 8.0), (CX, 4.7))
                  + bez((CX, 4.7), (28.0, 8.0), (28.4, 18.0), (26.4, 24.8))
                  + bez((26.4, 24.8), (23.0, 26.2), (11.0, 26.2), (7.6, 24.8)), hair, role="hair"))
    elif hs == "long":
        add(Piece("hair_back", bez((6.6, 40.0), (4.6, 22.0), (5.4, 6.0), (CX, 4.6))
                  + bez((CX, 4.6), (28.6, 6.0), (29.4, 22.0), (27.4, 40.0))
                  + bez((27.4, 40.0), (22.0, 42.0), (12.0, 42.0), (6.6, 40.0)), hair, role="hair"))
    elif hs == "bun":
        add(Piece("bun", ell(25.6, 22.6, 3.1, 2.9), hair, role="hair"))
        add(Piece("bun_coil", ell(25.7, 22.6, 1.8, 1.6, 200, 520, 30), shade(hair, 0.35), "line", 0.32, "feature",
                  shadow=False))
        add(Piece("bun_pin", [(24.0, 20.6), (27.9, 21.7)], GOLD, "line", 0.42, "accent", shadow=False))
    elif hs == "ponytail":
        add(Piece("tail", bez((23.0, 8.6), (30.5, 9.0), (30.0, 22.0), (27.6, 31.0))
                  + bez((27.6, 31.0), (26.0, 24.0), (25.4, 15.0), (22.0, 12.0)), hair, role="hair"))
    elif hs == "headscarf":
        add(Piece("scarf_back", bez((5.6, 19.0), (5.0, 6.0), (11.0, 3.6), (CX, 3.6))
                  + bez((CX, 3.6), (23.0, 3.6), (29.0, 6.0), (28.4, 19.0))
                  + [(29.4, 33.6), (4.6, 33.6)], hair, role="hair"))

    # legs and shoes
    hem = 74.0 if outfit == "kurta" else 57.6
    for side in (1, -1):
        leg = [(9.5, 55.0), (16.7, 55.0), (16.5, 92.0), (11.0, 92.0)]
        if outfit == "kurta":
            leg = [(10.4, 55.0), (16.6, 55.0), (16.0, 92.0), (11.8, 92.0)]
        pts = leg if side == 1 else mirror(leg)
        add(Piece(f"leg{side}", pts, d["trousers"], role="cloth"))
    add(Piece("seat", [(9.5, 55.0), (24.5, 55.0), (24.4, 61.5), (9.6, 61.5)], d["trousers"], role="cloth",
              shadow=False))
    sh, scol = d["shoes"]["style"], d["shoes"]["color"]
    for side in (1, -1):
        if sh == "heel":
            shoe = bez((11.4, 92.0), (10.2, 93.0), (10.0, 95.6), (11.6, 95.8)) + [(16.0, 95.8), (16.2, 92.0)]
        elif sh == "boot":
            shoe = [(10.6, 87.8), (16.6, 87.8), (16.8, 96.0)] + bez((16.8, 96.0), (12.0, 96.4), (8.8, 96.2), (9.0, 93.6))
        else:
            low = 0.6 if sh == "flat" else 0.0
            shoe = bez((11.0, 91.8 + low), (9.0, 92.4 + low), (8.4, 96.0), (10.4, 96.2)) + [(16.8, 96.2), (16.8, 91.8 + low)]
        add(Piece(f"shoe{side}", shoe if side == 1 else mirror(shoe), scol, role="shoe"))
        if sh == "sneaker":
            sole = [(8.7, 95.0), (16.8, 95.0), (16.8, 96.4), (8.9, 96.4)]
            add(Piece(f"sole{side}", sole if side == 1 else mirror(sole), shade(scol, 0.55), role="accent",
                      shadow=False))
            stripe = [(11.4, 93.3), (14.6, 92.6)]
            add(Piece(f"stripe{side}", stripe if side == 1 else mirror(stripe), "#C8553D", "line", 0.45, "accent",
                      shadow=False))
        if sh == "brogue":
            cap = bez((9.2, 94.4), (10.4, 93.4), (11.8, 93.2), (12.6, 94.0))
            add(Piece(f"toecap{side}", cap if side == 1 else mirror(cap), tint(scol, 0.22), "line", 0.25, "feature",
                      shadow=False))

    # neck
    add(Piece("neck", [(15.0, 22.0), (19.0, 22.0), (19.5, 29.6), (14.5, 29.6)], skin, role="skin"))
    add(Piece("neck_shade", [(15.0, 23.4), (19.0, 23.4), (19.2, 25.6), (14.8, 25.6)], shade(skin, 0.25),
              role="feature", shadow=False, alpha=0.55))

    # torso
    left = (bez((14.2, 28.3), (11.4, 28.4), (8.2, 28.6), (7.0, 31.9))
            + [(7.5, 40.0), (8.6, 50.0), (9.0 if outfit != "kurta" else 8.2, hem)])
    torso = left + [(CX, hem + 0.3)] + mirror(left)[::-1]
    body_col = shirt if outfit == "shirt" else top
    add(Piece("torso", torso, body_col, role="cloth"))

    if outfit in ("blazer", "suit"):
        apex = 40.5 if outfit == "blazer" else 39.0
        add(Piece("shirt_v", [(14.3, 28.4), (19.7, 28.4), (CX, apex)], shirt, role="cloth", shadow=False))
        lapel = [(14.3, 28.3), (12.4, 30.0), (13.2, 34.6), (16.6, apex), (CX, apex + 0.4), (14.9, 31.0)]
        add(Piece("lapel_l", lapel, shade(top, 0.18), role="cloth"))
        add(Piece("lapel_r", mirror(lapel), shade(top, 0.18), role="cloth"))
        for y in ((44.0, 49.0) if outfit == "blazer" else (43.0,)):
            add(Piece("button", ell(CX, y, 0.42, 0.42, n=16), shade(top, 0.45), role="feature", shadow=False))
        flap = [(10.0, 49.6), (13.6, 49.6), (13.6, 50.4), (10.1, 50.4)]
        add(Piece("pocket_l", flap, shade(top, 0.25), role="feature", shadow=False))
        add(Piece("pocket_r", mirror(flap), shade(top, 0.25), role="feature", shadow=False))
        collar = [(14.3, 28.2), (16.6, 29.0), (15.2, 31.8)]
        add(Piece("collar_l", collar, tint(shirt, 0.15), role="cloth", shadow=False))
        add(Piece("collar_r", mirror(collar), tint(shirt, 0.15), role="cloth", shadow=False))
        if outfit == "suit":
            for x in (12.1, 21.9):
                add(Piece("shoulder_seam", [(x, 29.3), (x + (0.6 if x < CX else -0.6), 32.0)], shade(top, 0.3),
                          "line", 0.2, "feature", shadow=False))
    elif outfit == "jacket":
        add(Piece("tee", [(14.6, 28.4), (19.4, 28.4), (18.6, hem), (15.4, hem)], shirt, role="cloth"))
        add(Piece("tee_neck", ell(CX, 28.2, 2.6, 1.5, 0, 180, 16), shade(shirt, 0.2), "line", 0.32, "feature",
                  shadow=False))
        edge = [(14.6, 28.6), (13.2, 33.0), (14.8, 40.0), (15.4, hem)]
        add(Piece("jacket_edge_l", edge, shade(top, 0.25), "line", 0.45, "feature", shadow=False))
        add(Piece("jacket_edge_r", mirror(edge), shade(top, 0.25), "line", 0.45, "feature", shadow=False))
        add(Piece("jacket_l", [(14.6, 28.6), (13.2, 33.0), (14.8, 40.0), (15.4, hem), (9.0, hem), (8.6, 30.0)],
                  top, role="cloth", shadow=False))
        add(Piece("jacket_r", mirror([(14.6, 28.6), (13.2, 33.0), (14.8, 40.0), (15.4, hem), (9.0, hem), (8.6, 30.0)]),
                  top, role="cloth", shadow=False))
    elif outfit == "shirt":
        collar = [(14.0, 28.0), (16.8, 29.4), (14.8, 32.0)]
        add(Piece("collar_l", collar, tint(shirt, 0.25), role="cloth", shadow=False))
        add(Piece("collar_r", mirror(collar), tint(shirt, 0.25), role="cloth", shadow=False))
        add(Piece("placket", [(CX, 30.0), (CX, hem - 0.4)], shade(shirt, 0.22), "line", 0.25, "feature", shadow=False))
        for y in (34.0, 39.5, 45.0, 50.5):
            add(Piece("button", ell(CX + 0.5, y, 0.32, 0.32, n=12), shade(shirt, 0.3), role="feature", shadow=False))
    elif outfit == "sweater":
        collar = [(14.4, 28.0), (16.6, 28.9), (15.1, 30.6)]
        add(Piece("collar_l", collar, shirt, role="cloth", shadow=False))
        add(Piece("collar_r", mirror(collar), shirt, role="cloth", shadow=False))
        add(Piece("crew", ell(CX, 28.4, 2.9, 1.9, 0, 180, 18), shade(top, 0.28), "line", 0.6, "feature", shadow=False))
        add(Piece("rib", [(9.0, hem - 2.6), (25.0, hem - 2.6), (25.0, hem), (9.0, hem)], shade(top, 0.14),
                  role="cloth", shadow=False))
    elif outfit == "kurta":
        add(Piece("placket", [(CX, 28.6), (CX, 39.0)], shade(top, 0.3), "line", 0.32, "feature", shadow=False))
        for y in (31.5, 34.5, 37.5):
            add(Piece("button", ell(CX + 0.6, y, 0.3, 0.3, n=12), GOLD, role="feature", shadow=False))
        add(Piece("neckline", ell(CX, 28.3, 2.4, 1.3, 0, 180, 16), shade(top, 0.3), "line", 0.32, "feature",
                  shadow=False))
        for x in (8.6, 25.4):
            add(Piece("slit", [(x, hem - 7.0), (x + (0.5 if x < CX else -0.5), hem)], shade(top, 0.35), "line", 0.3,
                      "feature", shadow=False))
    if "necklace" in extras and outfit in ("blazer", "suit", "shirt"):
        add(Piece("necklace", bez((15.0, 29.6), (15.6, 31.6), (18.4, 31.6), (19.0, 29.6)), GOLD, "line", 0.26,
                  "accent", shadow=False))
        add(Piece("pendant", ell(CX, 31.9, 0.45, 0.55, n=12), GOLD, role="accent", shadow=False))
    if "lapel_pin" in extras and outfit in ("blazer", "suit", "jacket"):
        add(Piece("pin", ell(12.9, 33.8, 0.55, 0.55, n=16), GOLD, role="accent", shadow=False))

    # arms
    sleeve_col = shirt if outfit == "shirt" else top
    for side in (1, -1):
        upper = capsule((8.3, 32.2), (6.6, 43.4), 2.3, 2.08)
        lower = capsule((6.6, 43.0), (6.2, 54.4), 2.06, 1.85)
        hand = ell(6.15, 57.2, 1.8, 2.3)
        add(Piece(f"sleeve{side}", upper if side == 1 else mirror(upper), sleeve_col, role="cloth"))
        add(Piece(f"forearm{side}", lower if side == 1 else mirror(lower), sleeve_col, role="cloth"))
        if outfit in ("blazer", "suit"):
            cuff = capsule((6.25, 53.9), (6.2, 55.0), 1.78, 1.72)
            add(Piece(f"cuff{side}", cuff if side == 1 else mirror(cuff), shirt, role="cloth", shadow=False))
        add(Piece(f"hand{side}", hand if side == 1 else mirror(hand), skin, role="skin"))
        thumb = capsule((7.2, 56.0), (7.7, 57.6), 0.6, 0.5, 8)
        add(Piece(f"thumb{side}", thumb if side == 1 else mirror(thumb), shade(skin, 0.12), role="feature",
                  shadow=False))

    # head
    if hs != "headscarf":
        for side in (1, -1):
            ear = ell(CX - 8.2 * side, 16.4, 1.3, 1.9)
            add(Piece(f"ear{side}", ear, skin, role="skin"))
            add(Piece(f"ear_in{side}", ell(CX - 8.3 * side, 16.5, 0.55, 0.95), shade(skin, 0.2), role="feature",
                      shadow=False))
    add(Piece("head", head_pts(), skin, role="skin"))
    if "freckles" in extras:
        rnd = random.Random(seed + 7)
        for _ in range(14):
            x = CX + rnd.uniform(-5.4, 5.4)
            y = 18.6 + rnd.uniform(-0.9, 1.1) + abs(x - CX) * 0.08
            if abs(x - CX) > 0.9:
                add(Piece("freckle", ell(x, y, 0.19, 0.19, n=8), shade(skin, 0.32), role="feature", shadow=False,
                          alpha=0.8))
    blush = d.get("blush") or mix(skin, "#F2647E", 0.55)
    blush_alpha = 0.05 + 0.13 * luminance(skin)
    for x in (12.0, 22.0):
        add(Piece("cheek", ell(x, 19.9, 1.35, 0.9), blush, role="feature", shadow=False, alpha=blush_alpha))
    if "beard" in extras:
        beard = head_pts(1.02, 8, 172, 40) + bez((7.9, 19.2), (10.5, 21.0), (13.5, 23.6), (CX, 23.8))[1:] \
            + bez((CX, 23.8), (20.5, 23.6), (23.5, 21.0), (26.1, 19.2))[1:]
        add(Piece("beard", beard, hair, role="hair"))
    eye_col = d.get("eyes") or INK
    for side in (1, -1):
        ex = CX - 3.4 * side
        if blink:
            add(Piece("eye_closed", bez((ex - 1.0, 16.6), (ex - 0.4, 17.3), (ex + 0.4, 17.3), (ex + 1.0, 16.6), 8),
                      INK, "line", 0.36, "feature", shadow=False))
        else:
            add(Piece("eye", ell(ex, 16.5, 1.02, 1.3, n=20), eye_col, role="feature", shadow=False))
            add(Piece("eye_hi", ell(ex - 0.34, 16.0, 0.34, 0.34, n=10), "#FFFFFF", role="feature", shadow=False))
        brow = bez((ex - 1.45 * side, 13.6), (ex - 0.6 * side, 12.85), (ex + 0.6 * side, 12.85), (ex + 1.3 * side, 13.3), 8)
        add(Piece("brow", brow, shade(hair, 0.15) if hs not in ("bald",) else shade(skin, 0.45), "line", 0.55,
                  "feature", shadow=False))
    add(Piece("nose", bez((16.3, 19.0), (16.6, 19.9), (17.4, 19.9), (17.7, 19.0), 8), shade(skin, 0.3), "line", 0.32,
              "feature", shadow=False))
    if "moustache" in extras:
        add(Piece("moustache", bez((14.6, 21.4), (15.6, 20.2), (18.4, 20.2), (19.4, 21.4))
                  + bez((19.4, 21.4), (18.2, 21.0), (15.8, 21.0), (14.6, 21.4)), hair, role="hair", shadow=False))
    lip = d.get("lip") or mix(skin, "#8E2F38", 0.45)
    if talk == 0:
        add(Piece("mouth", bez((15.3, 21.7), (16.2, 22.7), (17.8, 22.7), (18.7, 21.7), 10), shade(lip, 0.35), "line",
                  0.42, "feature", shadow=False))
    else:
        rx, ry, cy = (1.15, 0.62, 22.0) if talk == 1 else (1.45, 1.05, 22.2)
        add(Piece("mouth", ell(CX, cy, rx, ry, n=24), "#4A1C1E", role="feature", shadow=False))
        if talk == 2:
            add(Piece("teeth", ell(CX, cy - ry * 0.62, rx * 0.68, ry * 0.24, n=16), "#FBF7F0", role="feature",
                      shadow=False))
        add(Piece("tongue", ell(CX, cy + ry * 0.42, rx * 0.55, ry * 0.36, n=16), "#C45A5E", role="feature",
                  shadow=False))

    # hair in front
    if hs == "headscarf":
        ring = Piece("scarf", head_pts(1.13, 120, 420, 70), hair, role="hair",
                     holes=[ell(CX, 16.4, 6.9, 8.4, n=50)])
        add(ring)
        add(Piece("scarf_fold", bez((9.6, 26.8), (12.0, 30.6), (22.0, 30.6), (24.4, 26.8)), shade(hair, 0.22), "line",
                  0.5, "feature", shadow=False))
    elif hs != "bald":
        add(_hair_front(hs, hair, seed))
        if hs == "curls":
            rnd = random.Random(seed + 3)
            for a in range(186, 356, 13):
                x = CX + 8.9 * math.cos(math.radians(a))
                y = 14.8 + 9.9 * math.sin(math.radians(a)) + rnd.uniform(-0.2, 0.2)
                r = 1.75 + rnd.uniform(-0.2, 0.25)
                add(Piece("curl", ell(x, y, r, r, n=18), hair, role="hair", shadow=False))
            for x in (11.0, 13.4, 15.8, 18.2, 20.6, 23.0):
                add(Piece("curl", ell(x, 9.4 + rnd.uniform(-0.3, 0.3), 1.35, 1.35, n=16), hair, role="hair",
                          shadow=False))
            for x, y in ((12.6, 7.2), (17.0, 6.0), (21.4, 7.2)):
                add(Piece("curl_hi", ell(x, y, 0.9, 0.6, 200, 340, 10), tint(hair, 0.28), "line", 0.3, "feature",
                          shadow=False))
        elif hs == "side_sweep":
            add(Piece("quiff", bez((11.0, 9.8), (10.6, 4.6), (15.0, 1.4), (20.6, 2.0)) + bez((20.6, 2.0), (25.4, 2.6), (27.2, 6.2), (25.6, 9.6))
                      + bez((25.6, 9.6), (23.0, 6.6), (19.0, 6.4), (16.0, 8.2)) + bez((16.0, 8.2), (14.0, 9.4), (12.6, 10.6), (11.0, 9.8)),
                      hair, role="hair"))
            add(Piece("wave", bez((13.4, 6.6), (16.0, 3.8), (20.4, 3.4), (23.8, 5.0), 10), tint(hair, 0.22), "line", 0.32,
                      "feature", shadow=False))
        elif hs == "swept_back":
            add(Piece("quiff", bez((10.2, 8.8), (9.0, 2.0), (14.0, -1.2), (20.0, -0.6)) + bez((20.0, -0.6), (25.6, 0.0), (27.0, 4.4), (25.2, 8.6))
                      + bez((25.2, 8.6), (22.6, 5.6), (17.0, 5.4), (13.6, 7.6)) + bez((13.6, 7.6), (12.4, 8.4), (11.4, 9.2), (10.2, 8.8)),
                      hair, role="hair"))
            for k in range(4):
                x0 = 11.5 + k * 2.6
                add(Piece("streak", bez((x0, 9.6), (x0 + 0.8, 5.6), (x0 + 2.4, 3.2), (x0 + 4.6, 2.6), 10),
                          tint(hair, 0.22), "line", 0.32, "feature", shadow=False))
        elif hs == "bun":
            add(Piece("part", [(CX, 6.4), (CX, 9.9)], shade(hair, 0.35), "line", 0.35, "feature", shadow=False))

    if "glasses" in extras:
        for side in (1, -1):
            ex = CX - 3.4 * side
            add(Piece("lens", ell(ex, 16.4, 2.1, 1.95, n=36), "#1D1D20", "line", 0.4, "accent", shadow=False))
        add(Piece("bridge", bez((15.2, 16.0), (16.0, 15.2), (18.0, 15.2), (18.8, 16.0), 8), "#1D1D20", "line", 0.36,
                  "accent", shadow=False))
        for side in (1, -1):
            t = [(CX - 5.5 * side, 16.0), (CX - 8.4 * side, 15.6)]
            add(Piece("temple", t, "#1D1D20", "line", 0.32, "accent", shadow=False))
    if "earrings" in extras and hs != "headscarf":
        for side in (1, -1):
            add(Piece("earring", ell(CX - 8.3 * side, 18.8, 0.45, 0.45, n=12), GOLD, role="accent", shadow=False))
    if "bindi" in extras:
        add(Piece("bindi", ell(CX, 12.6, 0.42, 0.42, n=12), "#B8232E", role="accent", shadow=False))
    px, py = HEAD_PIVOT
    for p in P:
        if p.name in HEAD_PIECES:
            p.pts = [(px + (x - px) * HEAD_SCALE, py + (y - py) * HEAD_SCALE) for x, y in p.pts]
            p.holes = [[(px + (x - px) * HEAD_SCALE, py + (y - py) * HEAD_SCALE) for x, y in h] for h in p.holes]
            p.width *= HEAD_SCALE
    return P


def _hair_front(hs: str, hair: str, seed: int) -> Piece:
    """The hair cap over the top of the head, ending in a hairline over the forehead."""
    if hs == "swept_back":
        pts = (bez((8.2, 14.2), (7.8, 6.0), (11.0, 0.9), (17.6, 1.0)) + bez((17.6, 1.0), (24.0, 1.1), (26.6, 5.4), (25.8, 14.2))
               + bez((25.8, 14.2), (24.6, 9.8), (21.0, 8.6), (CX, 8.6)) + bez((CX, 8.6), (13.0, 8.6), (9.6, 9.8), (8.2, 14.2)))
    elif hs == "side_sweep":
        pts = (bez((8.1, 15.0), (7.4, 7.0), (11.0, 3.4), (16.0, 3.6)) + bez((16.0, 3.6), (22.0, 2.8), (27.0, 5.6), (25.9, 14.0))
               + bez((25.9, 14.0), (24.6, 10.6), (23.6, 9.8), (21.4, 9.6)) + bez((21.4, 9.6), (17.0, 9.8), (13.0, 12.6), (8.1, 15.0)))
    elif hs == "bob":
        pts = (bez((8.0, 19.0), (6.8, 8.0), (11.0, 4.3), (CX, 4.4)) + bez((CX, 4.4), (24.0, 4.3), (27.4, 8.0), (26.2, 17.0))
               + bez((26.2, 17.0), (25.0, 12.0), (21.0, 10.0), (17.6, 10.0)) + bez((17.6, 10.0), (13.4, 10.6), (10.6, 12.6), (8.0, 19.0)))
    elif hs in ("bun", "long", "ponytail"):
        pts = (bez((8.2, 16.2), (7.4, 7.6), (11.0, 4.6), (CX, 4.6)) + bez((CX, 4.6), (23.0, 4.6), (26.6, 7.6), (25.8, 16.2))
               + bez((25.8, 16.2), (24.4, 11.0), (20.6, 9.8), (CX, 9.9)) + bez((CX, 9.9), (13.4, 9.8), (9.6, 11.0), (8.2, 16.2)))
    else:  # short, curls
        pts = (bez((8.2, 14.6), (7.6, 7.0), (11.0, 4.6), (CX, 4.6)) + bez((CX, 4.6), (23.0, 4.6), (26.4, 7.0), (25.8, 14.6))
               + bez((25.8, 14.6), (24.6, 10.4), (21.0, 9.6), (CX, 9.8)) + bez((CX, 9.8), (13.0, 9.6), (9.4, 10.4), (8.2, 14.6)))
    return Piece("hair", pts, hair, role="hair")


# --------------------------------------------------------------------------- painters
class Canvas:
    def __init__(self, height: int):
        self.s = height * SUPERSAMPLE / (H + TOP)
        self.size = (round(W * self.s), round((H + TOP) * self.s))
        self.im = Image.new("RGBA", self.size, (0, 0, 0, 0))

    def px(self, pts):
        return [(x * self.s, (y + TOP) * self.s) for x, y in pts]

    def mask(self, p: Piece, grow: float = 0.0) -> Image.Image:
        m = Image.new("L", self.size, 0)
        d = ImageDraw.Draw(m)
        if p.kind == "line":
            d.line(self.px(p.pts), fill=255, width=max(1, round((p.width + grow) * self.s)), joint="curve")
            r = (p.width + grow) * self.s / 2
            for x, y in (self.px(p.pts)[0], self.px(p.pts)[-1]):
                d.ellipse((x - r, y - r, x + r, y + r), fill=255)
        else:
            d.polygon(self.px(p.pts), fill=255)
            for hole in p.holes:
                d.polygon(self.px(hole), fill=0)
            if grow:
                m = m.filter(ImageFilter.MaxFilter(_odd(grow * self.s * 2)))
        return m

    def fill(self, mask: Image.Image, color: str, alpha: float = 1.0) -> None:
        box = mask.getbbox()
        if box is None:
            return
        m = mask.crop(box)
        if alpha < 1.0:
            m = m.point(lambda v: round(v * alpha))
        layer = Image.new("RGBA", m.size, rgb(color) + (255,))
        if alpha >= 1.0:
            self.im.paste(layer, box[:2], m)
        else:
            self.im.alpha_composite(Image.composite(layer, Image.new("RGBA", m.size, (0, 0, 0, 0)), m), box[:2])


def _odd(v: float) -> int:
    n = max(3, int(v))
    return n if n % 2 else n + 1


def _shift(m: Image.Image, dx: float, dy: float) -> Image.Image:
    return ImageChops.offset(m, round(dx), round(dy))


def _rim(c: Canvas, m: Image.Image, dx: float, dy: float) -> Image.Image:
    """The part of a shape that a copy shifted by (dx, dy) does not cover: a crescent along one side."""
    return ImageChops.subtract(m, _shift(m, dx * c.s, dy * c.s))


def paint_flat(pieces: list[Piece], c: Canvas, seed: int, start: int = 0) -> None:
    for p in pieces:
        m = c.mask(p)
        c.fill(m, p.fill, p.alpha)
        if p.kind == "poly" and p.role in ("cloth", "skin", "hair", "shoe") and p.alpha >= 1.0:
            c.fill(_rim(c, m, -0.9, -0.55), shade(p.fill, 0.2 if p.role != "hair" else 0.32))
            if p.role in ("hair", "shoe"):
                c.fill(_rim(c, m, 0.55, 0.5), tint(p.fill, 0.18), 0.85)


def _wobble(pts, amp: float, seed: int, closed: bool = True):
    """Move each point along its normal by smooth low-frequency noise: a hand-drawn or hand-cut edge."""
    rnd = random.Random(seed)
    k1, k2, ph1, ph2 = rnd.uniform(3, 6), rnd.uniform(9, 15), rnd.uniform(0, 6.3), rnd.uniform(0, 6.3)
    n = len(pts)
    out = []
    for i, (x, y) in enumerate(pts):
        a, b = pts[i - 1] if (closed or i) else pts[i], pts[(i + 1) % n] if (closed or i < n - 1) else pts[i]
        nx, ny = -(b[1] - a[1]), b[0] - a[0]
        ln = math.hypot(nx, ny) or 1.0
        t = i / max(1, n)
        off = amp * (0.7 * math.sin(2 * math.pi * k1 * t + ph1) + 0.3 * math.sin(2 * math.pi * k2 * t + ph2))
        out.append((x + nx / ln * off, y + ny / ln * off))
    return out


def _densify(pts, step: float = 0.6, closed: bool = True):
    out = []
    seq = pts + [pts[0]] if closed else pts
    for a, b in zip(seq, seq[1:], strict=False):
        n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / step))
        out += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n)]
    return out if closed else out + [pts[-1]]


PAPER = "#FBF6EA"
GRAPHITE = "#2B2623"


def _hatch(c: Canvas) -> Image.Image:
    if getattr(c, "hatch", None) is None:
        hatch = Image.new("L", c.size, 0)
        hd = ImageDraw.Draw(hatch)
        step = 0.85 * c.s
        for k in range(-int(c.size[1] / step), int(c.size[0] / step) + 2):
            x0 = k * step
            hd.line([(x0, 0), (x0 + c.size[1], c.size[1])], fill=255, width=max(1, round(0.13 * c.s)))
        c.hatch = hatch
    return c.hatch


def paint_sketch(pieces: list[Piece], c: Canvas, seed: int, start: int = 0) -> None:
    hatch = _hatch(c)
    for i, p in enumerate(pieces, start):
        m = c.mask(p)
        if p.role == "feature" or p.role == "accent":
            c.fill(m, p.fill if p.fill not in ("#FFFFFF",) else "#FFFFFF", p.alpha)
            continue
        # skin keeps its real tone; clothes and hair take the paper wash
        wash = mix(p.fill, PAPER, {"skin": 0.1, "hair": 0.2}.get(p.role, 0.42))
        c.fill(m, wash, p.alpha)
        if p.kind == "poly" and p.alpha >= 1.0:
            rim = _rim(c, m, -1.1, -0.7)
            c.fill(ImageChops.multiply(rim, hatch), GRAPHITE, 0.45)
            d = ImageDraw.Draw(c.im)
            line = _densify(p.pts)
            for k, (amp, w, a) in enumerate(((0.16, 0.26, 235), (0.24, 0.13, 120))):
                pts = c.px(_wobble(line, amp, seed + i * 31 + k))
                d.line(pts + [pts[0]], fill=rgb(GRAPHITE) + (a,), width=max(1, round(w * c.s)), joint="curve")


def _grain(size: tuple[int, int], seed: int, cell: int = 3) -> Image.Image:
    rnd = random.Random(seed)
    w, h = max(1, size[0] // cell), max(1, size[1] // cell)
    small = Image.new("L", (w, h))
    small.putdata([128 + int(rnd.gauss(0, 18)) for _ in range(w * h)])
    return small.resize(size, Image.BILINEAR)


def paint_cutout(pieces: list[Piece], c: Canvas, seed: int, start: int = 0) -> None:
    for i, p in enumerate(pieces, start):
        if p.kind == "poly" and p.role in ("cloth", "skin", "hair", "shoe"):
            q = Piece(p.name, _wobble(_densify(p.pts, 0.8), 0.1, seed + i), p.fill, p.kind, p.width, p.role, p.alpha,
                      [_wobble(_densify(h, 0.8), 0.08, seed + i + 1) for h in p.holes], p.shadow)
        else:
            q = p
        m = c.mask(q)
        bbox = m.getbbox()
        if bbox is None:
            continue
        if q.shadow and q.alpha >= 1.0:
            pad = round(1.4 * c.s)
            box = (max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(c.size[0], bbox[2] + pad), min(c.size[1], bbox[3] + pad))
            sh = m.crop(box).filter(ImageFilter.GaussianBlur(0.45 * c.s)).point(lambda v: round(v * 0.38))
            full = Image.new("L", c.size, 0)
            full.paste(sh, (box[0] + round(0.32 * c.s), box[1] + round(0.42 * c.s)))
            c.fill(full, "#1E1A16")
            edge = Image.new("L", c.size, 0)
            edge.paste(m.crop(box).filter(ImageFilter.MaxFilter(_odd(0.22 * c.s))), box[:2])
            c.fill(edge, mix(q.fill, "#FFFDF6", 0.55))
        c.fill(m, q.fill, q.alpha)
        if q.kind == "poly" and q.role in ("cloth", "skin", "hair", "shoe") and q.alpha >= 1.0:
            c.fill(_rim(c, m, -0.7, -0.45), shade(q.fill, 0.12), 0.8)


def finish_cutout(c: Canvas, seed: int) -> None:
    alpha = c.im.getchannel("A")
    grain = _grain(c.size, seed, cell=4)
    rgbim = c.im.convert("RGB")
    lit = ImageChops.overlay(rgbim, Image.merge("RGB", (grain, grain, grain)))
    out = Image.blend(rgbim, lit, 0.32)
    out.putalpha(alpha)
    c.im = out


PAINTERS = {"v1": paint_sketch, "v2": paint_flat, "v3": paint_cutout}
FINISH = {"v3": finish_cutout}
FACE = {"eye", "eye_closed"}  # the first piece that differs between variants


# --------------------------------------------------------------------------- public API
def style_code(style: str | None) -> str:
    return STYLE_ALIASES.get(str(style or "v4").lower(), "v4")


def _crop(im: Image.Image, height: int) -> Image.Image:
    im = im.resize((round(W * height / (H + TOP)), height), Image.LANCZOS)
    bb = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox() or (0, 0, im.width, im.height)
    pad = round(height * 0.02)
    im = im.crop((max(0, bb[0] - pad), max(0, bb[1] - pad), min(im.width, bb[2] + pad), min(im.height, bb[3] + pad)))
    return im.resize((round(im.width * height / im.height), height), Image.LANCZOS)


def draw_variants(design: dict, style: str, variants=VARIANTS, height: int = 820, key: str = "") -> dict[str, Image.Image]:
    """Several variants of one figure. The body is painted once; only the face is repainted per variant."""
    code = style_code(style)
    if code not in PAINTERS:
        raise ValueError(f"style {style!r} is not drawn by this module")
    seed = _seed(key or repr(sorted(design.items(), key=str)), code)
    paint, finish = PAINTERS[code], FINISH.get(code)
    built = {v: build(design, v, seed) for v in variants}
    first = built[variants[0]]
    split = next((i for i, p in enumerate(first) if p.name in FACE), len(first))
    base = Canvas(height)
    paint(first[:split], base, seed, 0)
    out = {}
    for v, pieces in built.items():
        c = Canvas.__new__(Canvas)
        c.s, c.size, c.im = base.s, base.size, base.im.copy()
        c.hatch = getattr(base, "hatch", None)
        paint(pieces[split:], c, seed, split)
        if finish:
            finish(c, seed)
        out[v] = _crop(c.im, height)
    return out


def draw(design: dict, style: str = "v2", variant: str = "rest", height: int = 820, key: str = "") -> Image.Image:
    """One figure, cropped to its outline plus a small margin, `height` pixels tall."""
    return draw_variants(design, style, (variant,), height, key)[variant]


def figure_set(design: dict, style: str, height: int = 820, key: str = "") -> dict[str, Image.Image]:
    """Every variant the cards renderer uses for one character (rest, talking, blinking)."""
    return draw_variants(design, style, VARIANTS, height, key)


DEVANAGARI_VOWELS = set("अआइईउऊएऐओऔािीुूेैोौ")


def mouth_for(text: str, pos: float) -> int:
    """Mouth opening (0 closed, 1 half, 2 open) for a spoken line at relative position 0..1."""
    if not text:
        return 0
    ch = text[min(len(text) - 1, max(0, int(pos * len(text))))]
    if ch.lower() in "aeiouy" or ch in DEVANAGARI_VOWELS:
        return 2
    return 1 if ch.isalnum() else 0
