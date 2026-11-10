"""Drawn character styles (v1 sketch, v2 flat, v3 cut-out) and their use in projects and renders."""

import hashlib
import json

import pytest
from PIL import Image

from sastudio.project import load_project, validate
from sastudio.render import figures as F

from .conftest import HAS_FFMPEG, write_project

CAST = sorted(F.BUILTIN_DESIGNS)


def _digest(im: Image.Image) -> str:
    return hashlib.sha256(im.tobytes()).hexdigest()


@pytest.mark.parametrize("code", F.DRAWN_STYLES)
def test_every_bundled_character_draws_in_every_style(code):
    for cid in CAST:
        im = F.draw(F.normalize(None, cid), code, "rest", 240, key=cid)
        assert im.mode == "RGBA" and im.height == 240
        assert 2.4 < im.height / im.width < 4.6, (cid, im.size)  # a standing figure, like the clay portraits
        assert im.getchannel("A").getextrema()[1] == 255


def test_drawing_is_deterministic():
    d = F.normalize(None, "nadia")
    for code in F.DRAWN_STYLES:
        assert _digest(F.draw(d, code, "talk2", 200, key="nadia")) == _digest(F.draw(d, code, "talk2", 200, key="nadia"))


def test_variants_change_only_the_face():
    d = F.normalize(None, "mira")
    v = F.draw_variants(d, "v2", ("rest", "talk2", "blink"), 400, key="mira")
    for other in ("talk2", "blink"):
        a, b = v["rest"], v[other]
        assert a.size == b.size
        box = Image.eval(Image.frombytes("L", a.size, bytes(abs(x - y) for x, y in zip(
            a.convert("L").tobytes(), b.convert("L").tobytes(), strict=True))), lambda p: 255 if p > 24 else 0).getbbox()
        assert box is not None, f"{other} looks the same as rest"
        assert box[3] < a.height * 0.32, f"{other} changed pixels below the face: {box}"


@pytest.mark.parametrize("field,values", [
    ("hair", F.HAIR_STYLES), ("outfit", F.OUTFITS), ("shoes", F.SHOES), ("extras", F.EXTRAS),
])
def test_every_documented_option_draws(field, values):
    for value in values:
        design = {"extras": [value]} if field == "extras" else {field: {"style": value}}
        im = F.draw(F.normalize(design), "v2", "rest", 160, key=f"{field}:{value}")
        assert im.getchannel("A").getbbox() is not None, value


def test_mouth_follows_letters():
    assert F.mouth_for("aaaa", 0.5) == 2
    assert F.mouth_for("tttt", 0.5) == 1
    assert F.mouth_for("a  a", 0.5) == 0
    assert F.mouth_for("कआ", 0.9) == 2  # a Devanagari vowel opens the mouth
    assert F.mouth_for("", 0.3) == 0


def test_style_names_and_aliases():
    assert F.style_code("flat") == "v2" and F.style_code("CUTOUT") == "v3" and F.style_code("v1") == "v1"
    assert F.style_code(None) == "v4" and F.style_code("clay") == "v4"


def _with(root, look_extra: str = "", render_extra: str = ""):
    p = root / "studio.yaml"
    t = p.read_text(encoding="utf-8")
    if look_extra:
        t = t.replace("  - id: ana\n", "  - id: ana\n" + look_extra, 1)
    if render_extra:
        t += render_extra
    p.write_text(t, encoding="utf-8")
    return load_project(root)


def test_schema_accepts_designs_and_styles(tmp_path):
    good = _with(write_project(tmp_path / "good"),
                 '    look: { style: v3, design: { hair: { style: headscarf, color: "#3F6E8C" }, '
                 'outfit: { style: kurta, color: "#E2D4BC" }, extras: [bindi] } }\n',
                 "render:\n  character_style: flat\n")
    assert not [i for i in validate(good) if i.level == "error"]


@pytest.mark.parametrize("look", [
    '    look: { design: { hair: { style: mohawk } } }\n',
    '    look: { style: v9 }\n',
    '    look: { design: { extras: [cape] } }\n',
])
def test_schema_rejects_unknown_design_values(tmp_path, look):
    from sastudio.errors import ConfigError

    with pytest.raises(ConfigError):
        _with(write_project(tmp_path / "bad"), look)


def test_default_style_leaves_cache_signature_untouched(tmp_path):
    from sastudio.build import visuals

    plain = load_project(write_project(tmp_path / "a"))
    _vis, sig = visuals(plain, False, set())
    assert not any(k.startswith("figure:") for k in sig)  # existing projects keep their render cache keys

    drawn = _with(write_project(tmp_path / "b"), '    look: { design: { hair: { style: bob } } }\n')
    vis, sig = visuals(drawn, False, set())
    assert sig["figure:ana"][0] == "v2"  # described, no portrait: drawn flat
    assert set(vis.figures["ana"]) == set(F.VARIANTS)
    assert len(list((drawn.root / ".studio" / "work" / "figures").glob("*/rest.png"))) == 1
    vis2, _ = visuals(drawn, False, set())  # second time: from the cache, same pixels
    assert _digest(vis2.figures["ana"]["talk2"]) == _digest(vis.figures["ana"]["talk2"])


def test_speaker_talks_and_blinks_only_when_drawn():
    from sastudio.render.cards import SceneRenderer, Visuals
    from sastudio.render.style import Palette
    from sastudio.timeline import Beat, SceneTimeline

    beat = Beat(kind="line", frames=24 * 6, speaker="ana", cues=[(0.0, 5.0, "Hello, check the device please.")],
                env=[0.0] * (24 * 6))
    tl = SceneTimeline(id="s", title="S", language="en-IN", fps=24, beats=[beat], cast=["ana"])
    figs = F.figure_set(F.normalize(None, "mira"), "v2", 120, key="ana")
    drawn = SceneRenderer(tl, Visuals(Palette(), "Org", figures={"ana": figs}), "draft")
    states = [drawn.speaker_variant(beat, f) for f in range(beat.frames)]
    assert {"talk1", "talk2"} <= set(states) and any("blink" in s for s in states)
    assert all(states[f] == states[f + 1] for f in range(0, len(states) - 1, 2))  # animated on twos
    assert set(states[24 * 5 + 2:]) <= {"rest", "blink"}  # quiet after the line ends
    still = SceneRenderer(tl, Visuals(Palette(), "Org"), "draft")
    assert {still.speaker_variant(beat, f) for f in range(beat.frames)} == {"rest"}


def test_cast_sheet_command(tmp_path, capsys):
    from sastudio.cli import main

    root = tmp_path / "film"
    assert main(["init", str(root)]) == 0
    out = tmp_path / "sheet.png"
    assert main(["characters", str(root), "--sheet", str(out), "--styles", "v2,clay"]) == 0
    text = capsys.readouterr().out
    assert "style: v4 clay (portrait)" in text and "Cast sheet:" in text
    with Image.open(out) as im:
        assert im.width > 1000 and im.height > 900
    assert main(["characters", str(root), "--sheet", str(tmp_path / "x.jpg")]) != 0


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_drawn_style_film_renders_and_moves(tmp_path):
    from sastudio.build import build, probe_summary

    root = write_project(tmp_path / "p")
    p = root / "studio.yaml"
    p.write_text(p.read_text(encoding="utf-8")
                 .replace("  - id: ana\n", "  - id: ana\n    look: { preset: mira }\n", 1)
                 + "render:\n  character_style: cutout\n", encoding="utf-8")
    res = build(load_project(root), preset="draft", jobs=2, log=lambda m: None)
    man = json.loads(res.manifest.read_text(encoding="utf-8"))
    assert probe_summary(res.video)["video_frames"] == sum(s["frames"] for s in man["scenes"])
    assert (root / ".studio" / "work" / "figures").is_dir()
