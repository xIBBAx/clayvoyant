"""Scene direction: presets, automatic shot planning and validation (no rendering)."""

import pytest

from sastudio import direction as D
from sastudio.cli import main
from sastudio.project import load_project

from .conftest import write_project


@pytest.fixture(scope="module")
def starter(tmp_path_factory):
    root = tmp_path_factory.mktemp("d") / "film"
    assert main(["init", str(root)]) == 0
    return load_project(root)


def test_starter_plans_without_problems(starter):
    assert [p for p in D.validate(starter) if p.level == "error"] == []
    plans = D.plan(starter)
    assert len(plans) == len([s for s in starter.scenes if s.enabled])
    for p in plans:
        covered = [lid for sh in p.shots for lid in sh.lines]
        scene = next(s for s in starter.scenes if s.id == p.scene)
        assert covered == [ln.id for ln in scene.lines]  # every line, once, in order


def test_plan_is_deterministic(starter):
    from dataclasses import asdict

    assert [asdict(x) for x in D.plan(starter)] == [asdict(x) for x in D.plan(starter)]


def test_film_grammar_of_the_automatic_plan(starter):
    plans = D.plan(starter)
    openers = {p.shots[0].camera for p in plans}
    assert len(openers) >= 3, "every scene opens the same way"
    for p in plans:
        cams = [s.camera for s in p.shots]
        assert not any(a == b == c for a, b, c in zip(cams, cams[1:], cams[2:], strict=False)), p.scene
        for x, y in zip(p.shots, p.shots[1:], strict=False):
            assert not (x.camera == y.camera and x.who == y.who), f"jump cut in {p.scene}"
        assert all(s.seconds <= D.MAX_HOLD + 0.01 or s.move == "push_in" or len(s.lines) == 1 for s in p.shots)
        assert set(p.sides.values()) <= {"left", "right"}
    # the place itself is shown by the opening shot that carries the scene's title; the first line shows the people in it
    assert plans[0].shots[0].camera == "wide" and set(plans[0].shots[0].who) == set(plans[0].sides)


def _scene(root, direction_yaml: str = "", line_extra: str = ""):
    p = root / "studio.yaml"
    t = p.read_text(encoding="utf-8")
    t = t.replace('      - {{ id: l1, who: ana, say: "Hello {{dev}}, check the device." }}'.replace("{{", "{").replace("}}", "}"),
                  '      - { id: l1, who: ana, say: "Hello {dev}, check the device."' + line_extra + ' }', 1)
    if direction_yaml:
        t = t.replace("  - id: one\n", "  - id: one\n" + direction_yaml, 1)
    p.write_text(t, encoding="utf-8")
    return load_project(root)


def _errors(project):
    return [p for p in D.validate(project) if p.level == "error"]


def test_explicit_shots_are_honoured(tmp_path):
    proj = _scene(write_project(tmp_path / "p"),
                  "    direction:\n      set: meeting_room\n      lighting: suspense\n"
                  "      shots:\n        - { lines: [l1], camera: close_up, who: ana, move: push_in, lens_mm: 85 }\n")
    assert _errors(proj) == []
    p = D.plan(proj)[0]
    assert (p.set, p.lighting) == ("meeting_room", "suspense")
    assert (p.shots[0].camera, p.shots[0].who, p.shots[0].move, p.shots[0].lens) == ("close_up", ["ana"], "push_in", 85)


@pytest.mark.parametrize("direction_yaml,line_extra,needle", [
    ("    direction: { set: spaceship }\n", "", "Unknown set 'spaceship'"),
    ("    direction: { lighting: warm_interor }\n", "", "Did you mean warm_interior"),
    ("    direction:\n      shots:\n        - { lines: [l1], camera: close_up, who: zed }\n", "", "'zed' is not in this scene"),
    ("    direction:\n      shots:\n        - { lines: [l1], camera: two_shot, who: ana }\n", "", "shows 2-2 characters"),
    ("    direction:\n      shots:\n        - { lines: [l1], camera: insert, who: rocket }\n", "", "An insert shot shows one prop"),
    ("    direction:\n      shots:\n        - { lines: [l1], camera: medium, who: ana, focus: dev }\n", "", "is not in the shot"),
    ("    direction:\n      shots:\n        - { lines: [l1], camera: medium, who: ana, seconds: 0.5 }\n", "", "longer than 0.5 s"),
    ("    direction:\n      shots:\n        - { lines: [l9], camera: medium }\n", "", "No line 'l9'"),
    ("    direction: { set: home_desk, transition_in: door_reveal }\n", "", "has no door"),
    ("    direction: { transition_in: follow_object, object: rocket }\n", "", "has no 'rocket'"),
    ("    direction: { transition_in: spin }\n", "", "Unknown transition 'spin'"),
    ("", ", act: [phone_to_ear, typing]", "both need the right arm"),
    ("", ", act: [moonwalk]", "Unknown gesture 'moonwalk'"),
    ("    direction: { set: corridor }\n", ", act: [typing]", "needs a laptop"),
    ("    direction: { set: corridor }\n", ", act: [sit_down]", "has no seats"),
    ("", ", camera: closeup", "Did you mean close_up"),
])
def test_impossible_direction_is_reported_never_ignored(tmp_path, direction_yaml, line_extra, needle):
    proj = _scene(write_project(tmp_path / "p"), direction_yaml, line_extra)
    msgs = " | ".join(f"{p.message} {p.hint or ''}" for p in _errors(proj))
    assert needle in msgs, msgs


def test_fade_from_black_needs_the_first_scene_or_a_time_jump(tmp_path):
    root = write_project(tmp_path / "p")
    p = root / "studio.yaml"
    t = p.read_text(encoding="utf-8").replace("  - id: two\n", "  - id: two\n    direction: { transition_in: fade_from_black }\n", 1)
    p.write_text(t, encoding="utf-8")
    assert any("first scene or a jump in time" in x.message for x in _errors(load_project(root)))
    p.write_text(t.replace("fade_from_black }", "fade_from_black, time_jump: true }"), encoding="utf-8")
    assert _errors(load_project(root)) == []


def test_unknown_emotion_is_a_warning_not_an_error(tmp_path):
    proj = _scene(write_project(tmp_path / "p"), "", ", emotion: grumpy")
    probs = D.validate(proj)
    assert any(p.level == "warning" and "grumpy" in p.message for p in probs) and not _errors(proj)


def test_direction_errors_fail_project_validation(tmp_path, capsys):
    root = write_project(tmp_path / "p")
    _scene(root, "    direction: { set: spaceship }\n")
    assert main(["validate", str(root)]) == 2
    assert "Unknown set 'spaceship'" in capsys.readouterr().out


def test_direct_command_prints_the_shot_list(starter, capsys):
    assert main(["direct", str(starter.root), "--scenes", "helpful_caller"]) == 0
    out = capsys.readouterr().out
    assert "helpful_caller:" in out and " mm " in out and "shot(s) in 1 scene(s)" in out
    assert main(["direct", str(starter.root), "--json"]) == 0


def test_presets_are_distinct():
    rows = {tuple(v.items()) for v in D.LIGHTING.values()}
    assert len(rows) == len(D.LIGHTING)  # no two lighting presets are the same
    assert len({v["lens"] for v in D.SHOTS.values()}) >= 7
    assert set(D.TRANSITIONS) == {"cut", "match_cut", "follow_object", "door_reveal", "fade_from_black"}


def test_direction_guide_lists_every_preset():
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[1] / "docs" / "DIRECTION.md").read_text(encoding="utf-8")
    for group in (D.SHOTS, D.MOVES, D.LIGHTING, D.GESTURES, D.SETS, D.TRANSITIONS):
        for name in group:
            assert f"`{name}`" in doc, f"docs/DIRECTION.md does not list {name}"
