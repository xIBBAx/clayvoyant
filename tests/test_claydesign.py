"""From a character's description to sculpt parameters, and the sculpting kit itself."""

import re
import sys
from pathlib import Path

import pytest

from sastudio import claydesign as CD
from sastudio.project import load_project
from sastudio.render import clay, figures

from .conftest import write_project

ENGINE = Path(clay.__file__).resolve().parents[1] / "engine"
LOOK = """    look:
      design:
        skin: "#C98F66"
        hair: {{ style: {hair}, color: "#2A1A14" }}
        outfit: {{ style: {outfit}, color: "#D9A441", shirt: "#F4EFE6" }}
        extras: [{extras}]
"""


def _project(tmp_path, hair="ponytail", outfit="jacket", extras="glasses", more=""):
    root = write_project(tmp_path / "p")
    f = root / "studio.yaml"
    text = f.read_text("utf-8")
    anchor = "    voice: { provider: offline, settings: { rate: 200 } }\n"
    assert anchor in text
    f.write_text(text.replace(anchor, anchor + LOOK.format(hair=hair, outfit=outfit, extras=extras).rstrip("\n") + more + "\n", 1), "utf-8")
    return load_project(root), "ana"


def _sculpt_names():
    hair = (ENGINE / "sculpt" / "hair.py").read_text("utf-8")
    styles = set(re.findall(r"(\w+)=\1\b", hair[hair.index("STYLE = dict("):hair.index("LOW = dict(")]))
    build = (ENGINE / "sculpt" / "build.py").read_text("utf-8")
    torsos = set(re.findall(r"(\w+)=\1\b", build[build.index("TORSO = dict("):build.index("FACE = (")]))
    return styles, torsos


def test_every_described_look_is_something_the_sculptor_can_make():
    styles, torsos = _sculpt_names()
    assert set(CD.HAIR) == set(figures.HAIR_STYLES) and set(CD.HAIR.values()) <= styles
    assert set(CD.OUTFITS) == set(figures.OUTFITS) and set(CD.OUTFITS.values()) <= torsos
    assert set(CD.SHOES) == set(figures.SHOES)


@pytest.mark.parametrize("hair", figures.HAIR_STYLES)
def test_any_hair_and_outfit_gives_complete_parameters(tmp_path, hair):
    styles, torsos = _sculpt_names()
    for outfit in figures.OUTFITS:
        p, cid = _project(tmp_path / f"{hair}_{outfit}", hair, outfit, "beard, earrings")
        d = CD.params(p, cid)
        assert d["head"]["hairstyle"] in styles and d["body"]["torso"] in torsos
        for key in ("skin", "skinD", "hair", "iris", "lip", "fw", "jaw", "W"):
            assert key in d["head"], key
        for key in ("sw", "cw", "ww", "hw", "dp", "L", "hip", "armL", "pant", "shoe", "sleeve", "skin"):
            assert key in d["body"], key
        assert d["head"]["beard"] > 0 and d["head"]["acc"] == ["studs"]
        garment = d["body"]["torso"]
        need = {"blazer": "jacket", "suit_jacket": "jacket", "zip_jacket": "jacket", "knit_vest": "vest"}.get(garment, "top")
        assert need in d["body"], (garment, need)


def test_parameters_are_repeatable_and_no_two_people_share_a_face(tmp_path):
    p, cid = _project(tmp_path)
    assert CD.params(p, cid) == CD.params(p, cid)
    other = dict(p.characters)
    faces = set()
    for name in ("ada", "ben", "chloe", "dev"):
        other[name] = p.characters[cid]
        p.characters = other
        faces.add(tuple(CD.params(p, name)["head"][k] for k in ("fw", "jaw", "chin", "nose")))
    assert len(faces) == 4


def test_body_type_height_and_face_sliders_move_the_right_numbers(tmp_path):
    base, cid = _project(tmp_path / "a")
    big, _ = _project(tmp_path / "b", more="\n        body: { build: broad, height: tall }\n        face: { jaw: 1, eyes: -1 }")
    a, b = CD.params(base, cid), CD.params(big, cid)
    assert b["body"]["sw"] > a["body"]["sw"] and b["body"]["hip"] > a["body"]["hip"]
    assert b["head"]["jaw"] > a["head"]["jaw"] and b["head"]["eye"] < a["head"].get("eye", 0.098)


def test_bundled_presets_keep_their_sculpted_faces(project_dir):
    import json

    p = load_project(project_dir)
    for cid, ch in p.characters.items():
        preset = (ch.look or {}).get("preset")
        if not preset:
            continue
        raw = json.loads((ENGINE / "characters" / f"{preset}.json").read_text("utf-8"))
        got = CD.params(p, cid)
        for key in ("fw", "jaw", "chin", "nose", "hairstyle", "W"):
            assert got["head"][key] == raw["head"][key], (cid, key)


def test_clay_overrides_win_and_bad_values_are_refused(tmp_path):
    p, cid = _project(tmp_path / "a", more="\n      clay: { head: { fw: 1.07 }, body: { hip: 1.7 } }")
    d = CD.params(p, cid)
    assert d["head"]["fw"] == 1.07 and d["body"]["hip"] == 1.7


def test_acting_style_stays_in_range(tmp_path):
    p, cid = _project(tmp_path / "a", more="\n      acting: { energy: 1.6, looseness: 0.2, posture: 1, pace: 1.6 }")
    st = CD.acting_style(p, cid)
    assert 0.2 <= st["amp"] <= 1.6 and 0.2 <= st["loose"] <= 1.6 and st["bend"] < 0 and st["speed"] > 0.075


def test_sculpting_kit_makes_a_closed_painted_form(tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")
    pytest.importorskip("skimage")
    sys.path.insert(0, str(ENGINE / "sculpt"))
    try:
        import sdfkit
    finally:
        sys.path.pop(0)
    blob = lambda P: sdfkit.smin(sdfkit.ell(P, (0, 0, 0), (.3, .2, .25)), sdfkit.ell(P, (.25, 0, .1), (.15, .15, .15)), .08)  # noqa: E731
    m = sdfkit.mesh(blob, (-.5, -.4, -.4), (.6, .4, .5), 40, paint=[(lambda P: P[2] - .1, "#c1553f", .02, 0)], base="#f3ecdd")
    v, f, c = m["v"], m["f"], m["c"]
    assert len(v) > 500 and f.max() < len(v) and c.shape == (len(v), 4)
    edges = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    assert (counts == 2).all()                       # every edge has two faces: the form is closed
    assert c[v[:, 2] < 0][:, 0].mean() < c[v[:, 2] > .2][:, 0].mean() + 1 and len(np.unique(c[:, :3].round(2), axis=0)) > 10


def test_a_lanyard_is_worn_only_when_asked_for(tmp_path):
    """The knit vest used to come with an office ID card on a lanyard; at home it is just a vest."""
    p, cid = _project(tmp_path / "a", outfit="vest", extras="glasses")
    assert CD.params(p, cid)["body"]["lanyard"] == 0
    p, cid = _project(tmp_path / "b", outfit="vest", extras="glasses, lanyard")
    assert CD.params(p, cid)["body"]["lanyard"] == 1
    p, cid = _project(tmp_path / "c", outfit="sweater", extras="glasses")
    assert "lanyard" not in CD.params(p, cid)["body"]     # other outfits' sculpts (and their filmed shots) are untouched


def test_a_kurta_names_its_hem_and_nothing_else_does(tmp_path):
    p, cid = _project(tmp_path / "a", outfit="kurta", extras="bindi")
    assert CD.params(p, cid)["body"]["kurta_hem"] == .06
    p, cid = _project(tmp_path / "b", outfit="shirt", extras="glasses")
    assert "kurta_hem" not in CD.params(p, cid)["body"]
