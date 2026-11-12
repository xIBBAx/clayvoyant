"""From a character's description to the numbers the clay sculptor needs.

Every character has a `look`. The same `look.design` that the drawn styles read (skin, hair, outfit, shoes, extras)
is turned here into the parameters of the sculpt engine (engine/sculpt): the proportions of a skull, the width of a
jaw, the cut of a jacket. Nobody has to write those numbers: a body type and a height are chosen by name, a face is
varied a little for each character id so no two people in a cast look alike, and anything can be nudged with
`look.design.face`, `look.design.body`, or set outright with `look.clay`.

A character whose `look.preset` names one of the bundled clay characters starts from that character's file instead,
so the five bundled faces stay exactly as they were sculpted.
"""

from __future__ import annotations

import hashlib
import json
from importlib import resources

from .errors import ConfigError
from .render import figures
from .safepath import resolve_inside

ENGINE = resources.files("sastudio").joinpath("engine")
HAIR = {"short": "short", "side_sweep": "side_sweep", "swept_back": "swept_back", "curls": "curls", "bob": "bob", "bun": "low_bun",
        "long": "long", "ponytail": "ponytail", "headscarf": "headscarf", "bald": "bald"}
OUTFITS = {"blazer": "blazer", "suit": "suit_jacket", "jacket": "zip_jacket", "shirt": "shirt", "sweater": "sweater",
           "kurta": "kurta", "hoodie": "hoodie", "vest": "knit_vest"}
SHOES = {"flat": "flat", "sneaker": "sneaker", "brogue": "brogue", "heel": "heel", "boot": "hitop"}
BUILDS = {"slim": 0.93, "average": 1.0, "broad": 1.08}
HEIGHTS = {"short": 0.94, "average": 1.0, "tall": 1.05}
# Face sliders (-1..1) and the sculpt parameters each one moves, with how far.
FACE = {"width": [("fw", 0.05)], "jaw": [("jaw", 0.07), ("jawc", 0.25)], "chin": [("chin", 0.10), ("chinh", 0.05)],
        "nose": [("nose", 0.10), ("nl", 0.06)], "nose_width": [("nw", 0.10)], "cheeks": [("cheek", 0.07)],
        "brows": [("browH", 0.004), ("ridge", 0.2)], "eyes": [("eye", 0.008)], "length": [("long", 0.012)],
        "mouth": [("W", 0.008)], "lips": [("lipU", 0.008), ("lipL", 0.010)]}
# Two bodies and two heads to start from; a neutral character is half way between them.
BASE = {
    "feminine": {
        "head": dict(fw=.955, jaw=.875, chin=.90, long=.027, nose=.93, nl=.98, nb=.92, nw=.965, cheek=.95, ridge=.1, browW=.103,
                     browH=.018, browArch=.038, W=.103, wing=1),
        "body": dict(sw=.382, cw=.333, ww=.27, hw=.353, dp=.68, L=1.045, bust=.7, hip=1.445, armL=.48, hscale=.945, hs=.9, nk=.1)},
    "masculine": {
        "head": dict(fw=.94, jaw=.937, jawc=.36, chin=1.03, chinh=1.03, long=.027, nose=1.02, nl=1.07, nb=1.01, nw=.98, cheek=.9,
                     ridge=.45, browW=.108, browH=.0213, browArch=.033, W=.109),
        "body": dict(sw=.46, cw=.382, ww=.34, hw=.328, dp=.6, L=1.133, bust=0, hip=1.58, armL=.513, hscale=.953, hs=1.02, nk=.11)},
}
VARY = dict(fw=.03, jaw=.045, chin=.06, nose=.06, nl=.05, nb=.06, nw=.06, cheek=.045, browArch=.12, W=.03)


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a: str, b: str, t: float) -> str:
    x, y = _rgb(a), _rgb(b)
    r, g, b = (round(p + (q - p) * t) for p, q in zip(x, y, strict=True))
    return f"#{r:02x}{g:02x}{b:02x}"


def _unit(*parts) -> float:
    """A repeatable number in -1..1 from the parts."""
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF * 2 - 1


def presets() -> list[str]:
    return sorted(p.name[:-5] for p in ENGINE.joinpath("characters").iterdir() if p.name.endswith(".json"))


def _preset_file(project, preset: str) -> dict | None:
    local = project.root / "characters" / f"{preset}.json"
    if local.exists():
        path = resolve_inside(project.root, f"characters/{preset}.json", what="character preset", must_exist=True)
        if path.stat().st_size > 200_000:
            raise ConfigError(f"characters/{preset}.json is too large.")
        return json.loads(path.read_text("utf-8"))
    f = ENGINE.joinpath("characters").joinpath(f"{preset}.json")
    return json.loads(f.read_text("utf-8")) if f.is_file() else None


def _base(kind: str) -> dict:
    f, m = BASE["feminine"], BASE["masculine"]
    if kind in BASE:
        return {s: dict(BASE[kind][s]) for s in ("head", "body")}
    out = {}
    for s in ("head", "body"):
        out[s] = {k: round((f[s].get(k, m[s].get(k, 0)) + m[s].get(k, f[s].get(k, 0))) / 2, 4) for k in {*f[s], *m[s]} if k != "wing"}
    out["body"]["bust"] = .3
    return out


def _apply_design(data: dict, d: dict, given: dict | None = None) -> None:
    """Write a design's colours and choices into sculpt parameters. `given`: only these keys (for presets)."""
    use = (lambda k: k in given) if given is not None else (lambda k: True)
    head, body = data["head"], data["body"]
    if use("skin"):
        sk = d["skin"]
        head.update(skin=sk, skinD=mix(sk, "#3d2314", .2), blush=d.get("blush") or mix(sk, "#d4604e", .26))
        body["skin"] = sk
    if use("blush") and d.get("blush"):
        head["blush"] = d["blush"]
    if use("eyes"):
        head.update(iris=d["eyes"], iris2=mix(d["eyes"], "#c9a05a", .38))
    if use("lip") or (use("skin") and given is None):
        head["lip"] = d.get("lip") or mix(d["skin"], "#a23c44", .52)
    hair = d.get("hair") or {}
    if use("hair"):
        if (given is None or "style" in (given.get("hair") or {})) and hair.get("style"):
            head["hairstyle"] = HAIR[hair["style"]]
            if hair["style"] == "bun":
                head.setdefault("pin", "#e7c15c")
        if (given is None or "color" in (given.get("hair") or {})) and hair.get("color"):
            head.update(hair=hair["color"], hairHi=hair.get("highlight") or mix(hair["color"], "#9a7a5c", .22),
                        hairFade=mix(hair["color"], d["skin"], .35))
    outfit = d.get("outfit") or {}
    if use("outfit"):
        g = given.get("outfit") if given is not None else outfit
        col, shirt = outfit.get("color", "#4a6274"), outfit.get("shirt", "#f1ece4")
        if "style" in g:
            body["torso"] = OUTFITS[outfit["style"]]
        t = body.get("torso", "blazer")
        if "color" in g or "style" in g or "shirt" in g:
            if t in ("blazer", "suit_jacket", "zip_jacket"):
                body.update(jacket=col, top=shirt, sleeve=col, cuff=mix(col, "#000000", .14))
            elif t == "knit_vest":
                body.update(vest=col, shirt=shirt, sleeve=shirt, cuff=shirt, lan=body.get("lan", "#2f8fa8"))
            else:
                body.update(top=col, shirt=shirt, sleeve=col, cuff=mix(col, "#000000", .12))
            body["fabric"] = {"sweater": "knit", "hoodie": "jersey", "zip_jacket": "jersey", "knit_vest": "knit", "kurta": "jersey",
                              "shirt": "jersey"}.get(t, "wool")
    if use("trousers"):
        body["pant"] = d["trousers"]
    shoes = d.get("shoes") or {}
    if use("shoes"):
        g = given.get("shoes") if given is not None else shoes
        if "style" in g:
            body["shoe_style"] = SHOES[shoes["style"]]
        if "color" in g:
            body.update(shoe=shoes["color"], sole=mix(shoes["color"], "#000000", .55) if figures.luminance(shoes["color"]) > .5 else "#efe3cb")
    if use("extras"):
        ex = set(d.get("extras") or [])
        acc = (["specs"] if "glasses" in ex else []) + (["studs"] if "earrings" in ex else [])
        if acc:
            head.update(acc=acc, accColor="#24252b" if "glasses" in ex else "#e9e2d2")
        else:
            head.pop("acc", None)
        head["freckle"] = 16 if "freckles" in ex else min(int(head.get("freckle", 3)), 5)
        for key, val in (("beard", .85), ("moustache", 1.0)):
            if key in ex:
                head[key] = val
            else:
                head.pop(key, None)
        if "bindi" in ex:
            head["bindi"] = "#b0202a"
        else:
            head.pop("bindi", None)
        body["necklace"] = 1 if "necklace" in ex else 0
        body["pin"] = 1 if "lapel_pin" in ex else 0
        if body.get("torso") == "knit_vest":
            body["lanyard"] = 1 if "lanyard" in ex else 0     # an ID card is worn to work, not with every vest
        if body.get("torso") == "kurta":
            # named, so a kurta sculpted with the old hem (over the tops of the legs) is sculpted again
            body.setdefault("kurta_hem", .06)


def _shape(data: dict, d: dict) -> None:
    """Body type, height and face sliders."""
    head, body = data["head"], data["body"]
    b = d.get("body") or {}
    k = BUILDS[b.get("build", "average")]
    for key in ("sw", "cw", "ww", "hw"):
        body[key] = round(body[key] * k, 4)
    body["nk"] = round(body.get("nk", .105) * (.5 + .5 * k), 4)
    h = HEIGHTS[b.get("height", "average")]
    body["hip"] = round(body["hip"] * h, 4)
    body["L"] = round(body["L"] * (.4 + .6 * h), 4)
    body["armL"] = round(body["armL"] * h, 4)
    for name, amount in (d.get("face") or {}).items():
        for key, span in FACE.get(name, ()):
            default = {"jawc": 0.0, "chinh": 1.0, "eye": .098, "lipU": .036, "lipL": .045, "ridge": .3}.get(key, 1.0)
            head[key] = round(max(0.0, head.get(key, default) + span * max(-1.0, min(1.0, float(amount)))), 4)


def params(project, cid: str) -> dict:
    """Sculpt parameters {"head": {...}, "body": {...}} for one character of a project."""
    ch = project.characters[cid]
    look = ch.look or {}
    design_given = look.get("design") or {}
    preset = look.get("preset")
    data = _preset_file(project, preset) if preset else None
    if data is not None:
        if not isinstance(data, dict) or not isinstance(data.get("head"), dict) or not isinstance(data.get("body"), dict):
            raise ConfigError(f"Preset '{preset}' must have 'head' and 'body' objects.")
        # the old colour shorthands of a preset
        colors = look.get("colors") or {}
        keys = {"skin": [("head", "skin"), ("body", "skin")], "hair": [("head", "hair")], "eyes": [("head", "iris")],
                "top": [("body", "jacket"), ("body", "vest")], "accent": [("body", "lan"), ("body", "cuff")], "bottom": [("body", "pant")]}
        for name, color in colors.items():
            for section, key in keys.get(name, []):
                if key in data[section] or name in ("skin", "hair", "eyes", "bottom"):
                    data[section][key] = color
        if "top" in colors and data["body"].get("torso") in ("blazer", "suit_jacket", "zip_jacket"):
            data["body"]["sleeve"] = colors["top"]
        if design_given:
            _apply_design(data, figures.normalize(design_given, preset), design_given)
            _shape(data, design_given)
    else:
        if preset and preset not in figures.BUILTIN_DESIGNS:
            raise ConfigError(f"No clay preset '{preset}' for character '{cid}'.", "Built-in presets: " + ", ".join(presets())
                              + ". Or describe the character with look.design (docs/CHARACTERS.md).")
        d = figures.normalize(design_given, preset)
        kind = {"feminine": "feminine", "masculine": "masculine"}.get((ch.gender or "").lower(), "neutral")
        if (d.get("body") or {}).get("frame") in BASE:
            kind = d["body"]["frame"]
        data = _base(kind)
        seed = look.get("seed", cid)
        for key, span in VARY.items():       # nobody shares a face: each id gets its own small differences
            if key in data["head"]:
                data["head"][key] = round(data["head"][key] * (1 + span * _unit(seed, key)), 4)
        s = int(hashlib.sha256(str(seed).encode()).hexdigest()[:6], 16)
        data["head"].update(seed=100 + s % 97, moles=[[round(.12 + .16 * abs(_unit(seed, "mx")), 3) * (1 if s % 2 else -1),
                                                       round(.26 + .2 * abs(_unit(seed, "mz")), 3), .0068]])
        data["body"].update(pfabric="wool")
        _apply_design(data, d)
        _shape(data, d)
    for section in ("head", "body"):
        for k, v in ((look.get("clay") or {}).get(section) or {}).items():
            data[section][k] = v
    for section in ("head", "body"):
        for k, v in data[section].items():
            if not isinstance(v, (int, float, str, list)) or (isinstance(v, str) and len(v) > 40):
                raise ConfigError(f"Character '{cid}': {section}.{k} must be a number, a short string or a list.")
    return data


def acting_style(project, cid: str) -> dict:
    """How a character carries themselves, for the acting engine: from look.acting (all optional)."""
    a = (project.characters[cid].look or {}).get("acting") or {}
    energy, loose = float(a.get("energy", 1.0)), float(a.get("looseness", 1.0))
    posture = float(a.get("posture", 0.0))          # -1 slouched .. 1 very upright
    pace = float(a.get("pace", 1.0))
    return {"amp": round(max(.2, min(1.6, energy)), 3), "loose": round(max(.2, min(1.6, loose)), 3),
            "bend": round(-.03 * posture, 4), "speed": round(.075 * max(.6, min(1.6, pace)), 4),
            "step": round(.9 * (.85 + .15 * max(.6, min(1.6, pace))), 3)}
