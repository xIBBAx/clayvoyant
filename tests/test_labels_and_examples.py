"""On-screen labels follow the film's language, and the shipped examples stay valid."""

from pathlib import Path

import pytest

from sastudio.build import bookends, scene_timelines, topic_label, ui_label
from sastudio.cli import main
from sastudio.errors import ConfigError
from sastudio.project import load_project

from .conftest import write_project

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = sorted(p.parent for p in (REPO / "examples").glob("*/studio.yaml")) if (REPO / "examples").is_dir() else []


def _labels(root: Path, block: str) -> Path:
    f = root / "studio.yaml"
    f.write_text(f.read_text("utf-8").replace("  languages: [en-IN, hi-IN]", "  languages: [en-IN, hi-IN]\n" + block), "utf-8")
    return root


def test_english_labels_are_unchanged(project_dir):
    p = load_project(project_dir)
    assert ui_label(p, "key_point", "en-IN") == "Key point"
    assert ui_label(p, "report_prompt", "en-IN") == "Seen something suspicious? Report it to"
    assert topic_label(p, "incident_reporting", "en-IN") == "incident reporting"


def test_hindi_has_built_in_labels(tmp_path):
    p = load_project(write_project(tmp_path / "p", languages="[en-IN, hi-IN]"))
    assert ui_label(p, "key_point", "hi-IN") == "मुख्य बात"
    assert "report" in ui_label(p, "report_prompt", "hi-IN") and "Seen" not in ui_label(p, "report_prompt", "hi-IN")
    # Languages without built-in words fall back to English rather than failing.
    assert ui_label(p, "key_point", "ta-IN") == "Key point"


def test_project_labels_override_built_ins(tmp_path):
    root = _labels(write_project(tmp_path / "p", languages="[en-IN, hi-IN]"),
                   "  labels:\n    key_point: { default: \"Remember\", hi-IN: \"याद रखें\" }\n"
                   "    report_prompt: { default: \"Tell {org.name} at\" }\n"
                   "    topics: { phishing: { hi-IN: \"फ़िशिंग\" } }\n")
    p = load_project(root)
    assert ui_label(p, "key_point", "en-IN") == "Remember"
    assert ui_label(p, "key_point", "hi-IN") == "याद रखें"
    assert ui_label(p, "report_prompt", "hi-IN") == "Tell Test Org at"
    assert topic_label(p, "phishing", "hi-IN") == "फ़िशिंग"
    assert topic_label(p, "phishing", "en-IN") == "phishing"
    _intro, outro = bookends(p, "en-IN")
    assert outro.beats[0].extra["ask"] == "Tell Test Org at"


def test_unknown_label_is_a_schema_error(tmp_path):
    root = _labels(write_project(tmp_path / "p", languages="[en-IN, hi-IN]"), "  labels: { chapter: { default: \"x\" } }\n")
    with pytest.raises(ConfigError, match="labels"):
        load_project(root)


def test_takeaway_cards_use_the_label_for_their_language(tmp_path):
    root = write_project(tmp_path / "p")
    f = root / "studio.yaml"
    f.write_text(f.read_text("utf-8").replace('    title: "Scene One"\n', '    title: "Scene One"\n    takeaway: "Report it."\n'),
                 "utf-8")
    p = load_project(root)
    silent = {ln.id: None for s in p.scenes for ln in s.lines if ln.who}
    tl = scene_timelines(p, "en-IN", ["one"], {k: _wav(tmp_path, k) for k in silent})[0]
    assert [b.extra.get("label") for b in tl.beats if b.kind == "takeaway"] == ["Key point"]


def _wav(tmp_path: Path, name: str) -> Path:
    from .conftest import wav_bytes

    path = tmp_path / f"{name}.wav"
    path.write_bytes(wav_bytes(0.3))
    return path


@pytest.mark.skipif(not EXAMPLES, reason="examples are not part of this install")
@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
def test_examples_validate_strictly(example, capsys):
    assert main(["validate", str(example), "--strict"]) == 0
    assert "0 error(s), 0 warning(s)" in capsys.readouterr().out


@pytest.mark.skipif(not EXAMPLES, reason="examples are not part of this install")
@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
def test_example_portraits_are_the_template_portraits(example):
    tpl = REPO / "src" / "sastudio" / "templates" / "starter" / "assets" / "characters"
    for png in (example / "assets" / "characters").glob("*.png"):
        assert png.read_bytes() == (tpl / png.name).read_bytes(), f"{png} differs from the template portrait"
