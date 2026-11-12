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
        covered: list[str] = []
        pieces: dict[str, list] = {}
        for sh in p.shots:
            for lid in sh.lines:
                if sh.part:
                    pieces.setdefault(lid, []).append(sh.part)
                if not covered or covered[-1] != lid or not sh.part:
                    covered.append(lid)
        scene = next(s for s in starter.scenes if s.id == p.scene)
        assert covered == [ln.id for ln in scene.lines]  # every line, once, in order
        for lid, ps in pieces.items():                   # a line cut in two is covered from start to end
            assert ps[0][0] == 0 and ps[-1][1] == 1 and all(a[1] == b[0] for a, b in zip(ps, ps[1:], strict=False)), lid


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


def test_long_lines_cut_to_the_listener_part_way_through(starter):
    plans = D.plan(starter)
    reactions = [sh for p in plans for sh in p.shots if sh.camera == "reaction"]
    assert reactions, "no reaction cut anywhere in the starter film"
    for p in plans:
        for a, b in zip(p.shots, p.shots[1:], strict=False):
            if b.camera == "reaction" and b.part:
                assert a.lines == b.lines and a.part == [0, b.part[0]], "the speaker's piece comes first"
                assert b.who and b.who[0] not in a.who, "the reaction is on someone other than the speaker"
                assert .5 <= b.part[0] <= .7
    assert "%-100%" in D.describe(plans)       # the shot list shows where a line is cut


def test_reactions_can_be_turned_off_per_scene(tmp_path):
    proj = _scene(write_project(tmp_path / "p"), "    direction:\n      reactions: false\n")
    assert not any(sh.part for sh in D.plan(proj)[0].shots)


def test_a_line_can_be_cut_by_hand_and_its_pieces_must_meet(tmp_path):
    ok = _scene(write_project(tmp_path / "a"), "    direction:\n      shots:\n"
                "        - { lines: [l1], camera: close_up, who: ana, part: [0, 0.5] }\n"
                "        - { lines: [l1], camera: reaction, who: dev, part: [0.5, 1] }\n")
    assert _errors(ok) == []
    first = D.plan(ok)[0].shots[:2]
    assert [(s.camera, s.part) for s in first] == [("close_up", [0, 0.5]), ("reaction", [0.5, 1])]
    gap = _scene(write_project(tmp_path / "b"), "    direction:\n      shots:\n"
                 "        - { lines: [l1], camera: close_up, who: ana, part: [0, 0.4] }\n"
                 "        - { lines: [l1], camera: reaction, who: dev, part: [0.5, 1] }\n")
    assert any("without gaps" in p.message for p in _errors(gap))


def test_a_scene_tunes_its_light_on_top_of_the_preset(tmp_path):
    from sastudio import stopmotion as SM

    plain = _scene(write_project(tmp_path / "a"), "    direction:\n      lighting: daylight\n")
    tuned = _scene(write_project(tmp_path / "b"), "    direction:\n      lighting: daylight\n      light: { key_direction: 70, "
                   "key_height: 20, temperature: 3000, tint: '#FFE0C0', bounce: 0.4, sky: 0.5, practicals: true }\n")
    jobs = []
    for proj in (plain, tuned):
        plan = D.plan(proj)[0]
        scene = proj.scenes[0]
        jobs.append(SM.scene_job(proj, scene, plan, SM.spans_estimated(proj, scene))["lighting"])
    assert jobs[0] == dict(D.LIGHTING["daylight"], name="daylight"), "an untuned scene keeps its job (and its cache)"
    assert jobs[1] == dict(D.LIGHTING["daylight"], name="daylight", key_azimuth=70, key_height=20, key_k=3000,
                           tint="#FFE0C0", bounce=0.4, sky=0.5, practicals=True)
    assert "tuned: bounce, key_direction" in D.describe(D.plan(tuned))


def test_light_knobs_are_checked(tmp_path):
    from sastudio.errors import ConfigError

    with pytest.raises(ConfigError) as e:
        _scene(write_project(tmp_path / "p"), "    direction:\n      light: { key_height: 120 }\n")
    assert "scenes[0].direction.light.key_height: 120 is greater than the maximum of 85" in e.value.message
    with pytest.raises(ConfigError) as e:
        _scene(write_project(tmp_path / "q"), "    direction:\n      light: { glow: 1 }\n")
    assert "direction.light: Unknown setting ('glow' was unexpected)" in e.value.message


def test_beats_put_business_inside_a_line(tmp_path):
    from sastudio import stopmotion as SM

    proj = _scene(write_project(tmp_path / "p"), line_extra=", beats: [ { at: 0.5, who: dev, act: nod, feeling: worried } ]")
    assert _errors(proj) == []
    scene = proj.scenes[0]
    plan = D.plan(proj)[0]
    spans = SM.spans_estimated(proj, scene)
    sp = next(x for x in spans if x.line.id == "l1")
    keys = SM.scene_job(proj, scene, plan, spans)["keys"]
    mid = int(sp.start + .5 * (sp.end - sp.start))
    assert {"who": "dev", "frame": mid, "f": "worry"} in keys
    assert any(k["who"] == "dev" and k.get("nod") and mid < k["frame"] <= mid + 3 for k in keys)


@pytest.mark.parametrize("beat, says", [
    ("{ at: 0.5, act: moonwalk }", "Unknown gesture 'moonwalk'"),
    ("{ at: 0.5, who: dev, act: walk_out }", "moves someone across the set"),
    ("{ at: 0.5, who: zed, act: nod }", "'zed' is not in this scene"),
])
def test_bad_beats_are_refused(tmp_path, beat, says):
    proj = _scene(write_project(tmp_path / "p"), line_extra=f", beats: [ {beat} ]")
    assert any(says in p.message for p in _errors(proj))


def test_no_two_scenes_in_a_row_end_the_same_way(starter):
    ends = [(p.shots[-1].camera, p.shots[-1].move) for p in D.plan(starter)]
    assert all(a != b for a, b in zip(ends, ends[1:], strict=False)), ends
    assert ends[0] == ("close_up", "push_in")
    assert len(set(ends)) >= 2


def test_a_scene_can_say_how_it_ends_and_why(tmp_path):
    proj = _scene(write_project(tmp_path / "p"), "    direction:\n      end_with: { camera: wide, move: pull_out, "
                  "why: 'leave him alone with it' }\n")
    assert _errors(proj) == []
    last = D.plan(proj)[0].shots[-1]
    assert (last.camera, last.move, last.reason) == ("wide", "pull_out", "leave him alone with it")
    bad = _scene(write_project(tmp_path / "q"), "    direction:\n      end_with: { camera: wiide }\n")
    assert any("Unknown camera 'wiide'" in p.message for p in _errors(bad))


def test_a_wall_clock_tells_the_scene_s_time(tmp_path):
    from sastudio import stopmotion as SM
    from sastudio.errors import ConfigError

    def set_of(proj):
        scene, plan = proj.scenes[0], D.plan(proj)[0]
        return SM.scene_job(proj, scene, plan, SM.spans_estimated(proj, scene))["set"]

    night = _scene(write_project(tmp_path / "a"), "    setting: { time_of_day: night }\n    direction:\n      set: classroom\n")
    assert set_of(night)["clock"] == "22:50"
    told = _scene(write_project(tmp_path / "b"), "    direction:\n      set: home_desk\n      clock: '07:05'\n")
    assert set_of(told)["clock"] == "07:05"
    office = _scene(write_project(tmp_path / "c"), "    direction:\n      set: office\n      clock: '07:05'\n")
    assert "clock" not in set_of(office), "no clock on the wall: the job (and the cache) is unchanged"
    assert any(p.level == "warning" and "no wall clock" in p.message for p in D.validate(office))
    with pytest.raises(ConfigError, match="clock"):
        _scene(write_project(tmp_path / "d"), "    direction:\n      set: classroom\n      clock: '25:00'\n")


def test_a_line_that_names_its_camera_is_not_cut_in_two(tmp_path):
    long = "This is a long line, long enough to be cut in two by the planner when nobody says otherwise."
    root = _scene(write_project(tmp_path / "p")).root
    t = (root / "studio.yaml").read_text(encoding="utf-8")
    old = 'say: "Report to {org.security_email}." }'
    assert old in t
    t = t.replace(old, f'say: "{long}" }}\n      - {{ id: l3, who: ana, say: "Fine." }}')
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    auto = [s for s in D.plan(load_project(root))[0].shots if "l2" in s.lines]
    assert len(auto) == 2 and auto[1].camera == "reaction", "left alone, the planner cuts this line"
    (root / "studio.yaml").write_text(t.replace(f'say: "{long}" }}', f'say: "{long}", camera: close_up }}'), encoding="utf-8")
    named = [s for s in D.plan(load_project(root))[0].shots if "l2" in s.lines]
    assert len(named) == 1 and named[0].camera == "close_up" and not named[0].part


def test_dressing_is_asked_for_by_name_and_checked(tmp_path):
    from sastudio import stopmotion as SM

    def set_of(proj):
        scene, plan = proj.scenes[0], D.plan(proj)[0]
        return SM.scene_job(proj, scene, plan, SM.spans_estimated(proj, scene))["set"]

    cafe = _scene(write_project(tmp_path / "a"), "    direction:\n      set: cafe\n      dressing: [steam, birds]\n")
    assert _errors(cafe) == [] and set_of(cafe)["dressing"] == ["birds", "steam"]
    plain = _scene(write_project(tmp_path / "b"), "    direction:\n      set: cafe\n")
    assert "dressing" not in set_of(plain), "no dressing asked for: the job (and the cache) is unchanged"
    odd = _scene(write_project(tmp_path / "c"), "    direction:\n      set: corridor\n      dressing: [birds, fog]\n")
    probs = D.validate(odd)
    assert any(p.level == "error" and "Unknown dressing 'fog'" in p.message for p in probs)
    assert any(p.level == "warning" and "no window" in p.message for p in probs)
