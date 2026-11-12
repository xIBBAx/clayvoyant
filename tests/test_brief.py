"""The writing brief: what it promises a writer must be true of the validator."""

import re

import yaml

from sastudio import direction as D
from sastudio.brief import EXAMPLE, brief
from sastudio.cli import main
from sastudio.project import load_project


def _film(tmp_path):
    root = tmp_path / "film"
    assert main(["init", str(root)]) == 0
    return root


def test_the_example_scene_is_a_valid_scene(tmp_path):
    root = _film(tmp_path)
    data = yaml.safe_load((root / "studio.yaml").read_text("utf-8"))
    cast = data["characters"]
    # the example's two people, with looks and voices borrowed from the starter's first two
    for new_id, new_name, c in (("mina", "Mina", cast[0]), ("joss", "Joss", cast[1])):
        c["id"], c["name"] = new_id, new_name
        c.pop("forms", None)
    data["characters"] = cast[:2]
    (root / "scenes" / "late_bus.yaml").write_text(EXAMPLE, "utf-8")
    data["scenes"] = [{"file": "scenes/late_bus.yaml"}]
    (root / "studio.yaml").write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), "utf-8")
    p = load_project(root)
    assert [i for i in p.issues if i.level == "error"] == []
    assert [x for x in D.validate(p) if x.level == "error"] == []
    plan = D.plan(p)[0]
    assert [lid for sh in plan.shots for lid in sh.lines][-1] == "lb_03"


def test_the_brief_lists_everything_the_validator_accepts_and_nothing_else(tmp_path):
    text = brief(load_project(_film(tmp_path)), "A lost umbrella.", scenes=3, seconds=30)
    for table in (D.SETS, D.GESTURES, D.EMOTIONS, D.LIGHTING, D.TRANSITIONS, D.DRESSING):
        for name in table:
            assert f"`{name}`" in text, name
    for s in D.SETS.values():
        for mark in s["marks"]:
            assert f"`{mark}`" in text, mark
    known = set(D.SETS) | set(D.GESTURES) | set(D.EMOTIONS) | set(D.LIGHTING) | set(D.TRANSITIONS) | set(D.DRESSING)
    known |= set(D.SHOTS) | set(D.CLOCK_AT) | {m for s in D.SETS.values() for m in s["marks"] + s["props"]}
    acting = text.split("## Acting")[1].split("## What to send back")[0]
    assert set(re.findall(r"`([a-z_0-9]+)`", acting)) - {"camera", "business"} <= known
    assert "A lost umbrella." in text and "3 scenes of about 30 seconds" in text


def test_every_character_is_named_and_no_idea_means_ask(tmp_path):
    p = load_project(_film(tmp_path))
    text = brief(p)
    for c in p.characters.values():
        assert f"`{c.id}`: {c.name}" in text
    assert "ask me before you write anything" in text


def test_cli_writes_the_brief_and_refuses_silly_sizes(tmp_path, capsys):
    root = _film(tmp_path)
    out = tmp_path / "brief.md"
    assert main(["brief", str(root), "Two friends and one umbrella.", "--scenes", "1", "--out", str(out)]) == 0
    assert out.read_text("utf-8").startswith("# Writing brief") and "one scene of about 40 seconds" in out.read_text("utf-8")
    assert main(["brief", str(root), "--scenes", "0"]) != 0
    assert main(["brief", str(root), "--seconds", "999"]) != 0
    capsys.readouterr()
    assert main(["brief", str(root)]) == 0
    assert capsys.readouterr().out.startswith("# Writing brief")
