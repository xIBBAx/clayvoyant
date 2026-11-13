"""How a body of any size sits on a seat of any shape (engine/clay/body.py), and how a character's habits become their
way of moving (claydesign.acting_style). Pure arithmetic: no Blender, no rendering."""

from __future__ import annotations

import itertools
import math
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1] / "src" / "sastudio" / "engine" / "clay"
sys.path.insert(0, str(ENGINE))
import body as B  # noqa: E402

# bodies from a small, slight person to a tall, broad one (the sculpt's own numbers: hip height, hip width)
BODIES = {"short_slim": dict(hip=1.30, hw=.29, sw=.36), "short": dict(hip=1.485, hw=.328, sw=.46),
          "average": dict(hip=1.58, hw=.34, sw=.46), "tall": dict(hip=1.66, hw=.36, sw=.48),
          "tall_broad": dict(hip=1.75, hw=.40, sw=.52)}
# seats as the film measures them (film.measure_seat): plain chairs low and high, a pupil's chair under a desk, a
# soft sofa with a deep seat and a base that stands out under it, a bench, a backless stool, and a very low seat
SEATS = {
    "chair": dict(top=.825, front=.26, base_front=.25, back=-.40, floor=0.0),
    "high_chair": dict(top=.96, front=.26, base_front=.25, back=-.40, floor=0.0),
    "pupil_chair": dict(top=.745, front=.26, base_front=.25, back=-.40, floor=0.0, under=1.225),
    "sofa": dict(top=.826, soft=.055, front=.74, base_front=.78, back=-.38, floor=.02),
    "deep_sofa": dict(top=.80, soft=.07, front=1.0, base_front=1.02, back=-.5, floor=0.0),
    "bench": dict(top=.835, front=.385, base_front=.0, back=-.35, floor=0.0),
    "stool": dict(top=.82, front=.4, base_front=.36, back=None, floor=0.0),
    "low_seat": dict(top=.55, soft=.04, front=.5, base_front=.45, back=-.4, floor=0.0),
    "desk_with_panel": dict(top=.825, front=.26, base_front=.25, back=-.40, floor=0.0, ahead=.95),
    # a chair with its legs out at the sides, drawn in to a round table on one foot: room to draw the feet in under it
    "chair_at_table_foot": dict(top=.83, front=.26, base_front=.16, back=-.40, floor=0.0, under=1.36, base_front_at=[],
                                feet_ahead=[(round(-.4 + .08 * i, 2), .88) for i in range(11)]),
    # a cafe chair drawn in to a round table on one foot: the table's base stands on the floor in front of the feet
    "cafe_chair": dict(top=.84, front=.26, base_front=.2, back=-.38, floor=0.0, under=1.36,
                       feet_ahead=[(round(-.4 + .08 * i, 2), 1.32 + .02 * abs(-.4 + .08 * i)) for i in range(11)]),
}


def _body(name):
    return B.Body.from_meta(BODIES[name])


@pytest.mark.parametrize("bname,sname", list(itertools.product(BODIES, SEATS)))
def test_every_body_sits_on_every_seat_without_passing_through_it(bname, sname):
    body, seat = _body(bname), SEATS[sname]
    s = B.seated(body, seat, prefer=0.0)
    soft = seat.get("soft", 0.0)
    # the thighs lie on the (pressed) seat: not in it, not floating above it
    rest = s["joint_z"] - body["seat_drop"]
    assert seat["top"] - soft <= rest <= seat["top"] - soft + .01
    # the legs are as long as they are: thigh and shin keep their length whatever the pose
    kn, an = s["knee"], s["ankle"]
    assert math.hypot(kn[0] - s["u"], kn[1] - s["joint_z"]) == pytest.approx(body["thigh"], abs=1e-6)
    assert math.hypot(an[0] - kn[0], an[1] - kn[1]) == pytest.approx(body["shin"], abs=1e-6)
    # the backs of the knees clear the front edge; heels stay in front of whatever stands under the seat, and the toes
    # short of whatever stands on the floor in front of it (a table's foot)
    assert kn[0] - body["knee_r"] >= seat["front"] + .02 - 1e-9 or "deeper than these thighs" in " ".join(s["notes"])
    assert an[0] - body["heel"] >= seat["base_front"] + .03 - 1e-9 or "no room for the feet" in " ".join(s["notes"])
    if seat.get("feet_ahead"):
        assert an[0] + body["toe"] <= min(u for _d, u in seat["feet_ahead"]) - .02 or "no room for the feet" in " ".join(s["notes"])
    # feet are on the floor, or above it with the toes pointing down to it: never below it
    assert an[1] >= seat["floor"] + body["ankle"] - 1e-9
    assert s["lift"] == pytest.approx(max(0.0, an[1] - seat["floor"] - body["ankle"]), abs=1e-9)
    assert 0 <= s["toe"] <= .6 and (s["toe"] > 0) == (s["lift"] > .002)
    # the pelvis is on the seat, never in the backrest; the knees fit under a table and short of a desk's panel
    assert s["u"] <= seat["front"] - .16 + 1e-9
    if seat.get("back") is not None:
        assert s["u"] - body["pelvis_back"] >= seat["back"] + .02 - 1e-9 or "too shallow" in " ".join(s["notes"])
    if seat.get("under") is not None:
        assert kn[1] + body["knee_r"] <= seat["under"] - .02 or "lowered" in " ".join(s["notes"])
    if seat.get("ahead") is not None:
        assert kn[0] + body["knee_r"] <= seat["ahead"] - .01 or "no room for the knees" in " ".join(s["notes"])
    # a soft seat with a backrest is settled into; a hard one is not
    assert (s["lean"] < 0) == (soft > 0 and seat.get("back") is not None and (s["u"] - body["pelvis_back"]) - seat["back"] > .04)


def test_the_standing_place_for_a_seat_keeps_the_heels_clear_of_it():
    for bname, sname in itertools.product(BODIES, SEATS):
        body, seat = _body(bname), SEATS[sname]
        u = B.stand_point(body, seat)
        assert u - body["heel"] >= seat["base_front"] + .05, (bname, sname)
        assert u >= seat["front"] + body["shin_r"], (bname, sname)


def test_every_body_finds_room_for_its_feet_between_a_chair_and_a_table_foot():
    for bname in BODIES:
        s = B.seated(_body(bname), SEATS["chair_at_table_foot"])
        assert not any("no room" in n for n in s["notes"]), (bname, s["notes"])
        assert s["ankle"][0] + _body(bname)["toe"] <= .88 - .02


def test_different_bodies_sit_differently_on_the_same_seat():
    seat = SEATS["sofa"]
    poses = {n: B.seated(_body(n), seat, prefer=0.0) for n in BODIES}
    knees = {round(p["knee"][1], 3) for p in poses.values()}
    places = {round(p["u"], 3) for p in poses.values()}
    assert len(knees) == len(BODIES) and len(places) >= 3
    # the short, slight person cannot reach the floor from a sofa that suits a tall one: toes down, not legs stretched
    assert poses["short_slim"]["lift"] > 0 and poses["tall"]["lift"] == 0
    assert poses["tall_broad"]["knee"][1] > poses["short_slim"]["knee"][1]


def test_sitting_down_goes_back_then_down_and_getting_up_is_the_reverse():
    stand, sit = (1.0, 0.0), (.2, -.6)
    path = [B.sit_path(t / 20, stand, sit) for t in range(21)]
    assert path[0][:2] == pytest.approx(stand) and path[-1][:2] == pytest.approx(sit)
    us, zs = [p[0] for p in path], [p[1] for p in path]
    assert all(b <= a + 1e-9 for a, b in zip(us, us[1:])) and all(b <= a + 1e-9 for a, b in zip(zs, zs[1:]))
    # the hips are already on their way back before they start down: the weight stays over the feet
    assert (us[0] - us[4]) / (us[0] - us[-1]) > (zs[0] - zs[4]) / (zs[0] - zs[-1]) + .05
    assert max(p[2] for p in path) > .2 and path[0][2] == pytest.approx(0) and path[-1][2] == pytest.approx(0, abs=1e-9)


def test_a_bigger_body_needs_more_room_to_stand():
    assert _body("tall_broad").footprint() > _body("short_slim").footprint()
    assert B.personal_space(_body("average"), _body("average")) > 2 * _body("average").footprint()


# ---------------------------------------------------------------- habits
def _project(tmp_path, acting: dict):
    from sastudio.project import load_project

    from .conftest import write_project

    root = write_project(tmp_path / "p")
    t = (root / "studio.yaml").read_text("utf-8")
    flow = ", ".join(f"{k}: {v}" for k, v in acting.items())
    t = t.replace("    voice: { provider: offline, settings: { rate: 200 } }",
                  "    voice: { provider: offline, settings: { rate: 200 } }\n    look: { acting: { " + flow + " } }", 1)
    (root / "studio.yaml").write_text(t, "utf-8")
    return load_project(root)


def test_a_project_without_habits_moves_as_it_always_did(tmp_path):
    from sastudio import claydesign as C

    st = C.acting_style(_project(tmp_path, {"energy": 1.2, "looseness": 1.1, "posture": .5, "pace": .9}), "ana")
    assert (st["amp"], st["loose"], st["bend"], st["speed"], st["step"]) == (1.2, 1.1, -.015, .0675, .886)


@pytest.mark.parametrize("manner", ["calm", "confident", "nervous", "lively", "reserved", "warm", "stern"])
def test_every_manner_is_its_own_way_of_moving(tmp_path, manner):
    from sastudio import claydesign as C

    plain = C.acting_style(_project(tmp_path / "a", {}), "ana")
    st = C.acting_style(_project(tmp_path / "b", {"manner": manner}), "ana")
    assert st != plain
    assert set(st) == set(plain)


def test_nervous_and_confident_people_differ_where_it_shows(tmp_path):
    from sastudio import claydesign as C

    nerv = C.acting_style(_project(tmp_path / "n", {"manner": "nervous"}), "ana")
    conf = C.acting_style(_project(tmp_path / "c", {"manner": "confident"}), "ana")
    assert nerv["gaze"] > conf["gaze"] and nerv["blink"] > conf["blink"] and nerv["gest"] < conf["gest"]
    assert nerv["bend"] > conf["bend"]           # a nervous body folds a little forward; a confident one stands up
    old = C.acting_style(_project(tmp_path / "o", {"age": "older"}), "ana")
    young = C.acting_style(_project(tmp_path / "y", {"age": "young"}), "ana")
    assert old["sit"] > young["sit"] and old["speed"] < young["speed"] and old["turn_step"] > young["turn_step"]


def test_numbers_override_a_manner_and_the_result_is_always_the_same(tmp_path):
    from sastudio import claydesign as C

    p = _project(tmp_path, {"manner": "nervous", "blink": .6, "reaction": .5})
    a, b = C.acting_style(p, "ana"), C.acting_style(p, "ana")
    assert a == b and a["blink"] == .6 and a["react"] == 12


def test_unknown_manners_and_ages_are_refused(tmp_path):
    from sastudio.errors import ConfigError

    with pytest.raises(ConfigError):
        _project(tmp_path / "m", {"manner": "grumpy"})
    with pytest.raises(ConfigError):
        _project(tmp_path / "a", {"age": "ancient"})


# ---------------------------------------------------------------- feet on the floor
def test_a_turn_on_the_spot_never_puts_one_foot_where_the_other_stands():
    # 60 degrees a pair of steps at most (acting.Actor.turn): the opening foot lands clear of the one still standing
    for deg in range(5, 61, 5):
        th = math.radians(deg)
        assert B.feet_gap(_stand(1, th), th, _stand(-1, 0.0), 0.0)[0] >= .02, deg
        assert B.feet_gap(_stand(-1, -th), -th, _stand(1, 0.0), 0.0)[0] >= .02, deg


def test_two_shoes_side_by_side_clear_each_other_and_one_on_the_other_does_not():
    gap, _n = B.feet_gap((-.192, 0), 0.0, (.192, 0), 0.0)
    assert gap == pytest.approx(.384 - 2 * B.SHOE[2], abs=1e-9)
    assert B.feet_gap((0, 0), 0.0, (.05, .1), .4)[0] < 0
    # a shoe is long: two feet one behind the other need their length between them, not their width
    assert B.feet_gap((0, 0), 0.0, (0, .5), 0.0)[0] < 0 < B.feet_gap((0, 0), 0.0, (0, .8), 0.0)[0]


def _stand(side, psi, st=.24):
    back = .02 if side < 0 else -.03
    return (math.cos(psi) * st * .8 * side - math.sin(psi) * back, math.sin(psi) * st * .8 * side + math.cos(psi) * back)


@pytest.mark.parametrize("A,Bp,ya,yb,Os,yo", [
    ((.2, .6), (.2, -.6), 0.0, 0.0, (0.0, 0.0), 0.0),          # past it, too close beside it
    ((.3, .5), (.25, -.5), 0.0, .6, (0.0, 0.0), 0.0),           # past it close beside, turning as it goes
    # the opening step of a turn on the spot, 60 degrees round, from a foot left behind by a walk's last stride
    ((.24, .45), _stand(1, 1.05), 0.0, 1.05, _stand(-1, 0.0), 0.0),
    ((-.24, .45), _stand(-1, -1.05), 0.0, -1.05, _stand(1, 0.0), 0.0),
])
def test_a_stepping_foot_goes_round_the_standing_one_never_through_it(A, Bp, ya, yb, Os, yo):
    assert B.feet_gap(A, ya, Os, yo)[0] >= .02 and B.feet_gap(Bp, yb, Os, yo)[0] >= .02     # where it starts and lands
    path = [B.swing(A + (0,), Bp + (0,), ya, yb, Os, yo, i / 200) for i in range(201)]
    assert path[0][:2] == pytest.approx(A) and path[-1][:2] == pytest.approx(Bp)
    for i, p in enumerate(path):
        t = i / 200
        assert B.feet_gap(p[:2], ya + B._ang(yb - ya) * t, Os, yo)[0] >= .02, (i, p)
    # and it is a smooth way, not a jump: no drawing moves it more than a long stride's share
    assert max(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(path, path[1:])) < .05


def test_a_step_that_clears_the_other_foot_goes_straight():
    A, Bp = (.4, .5, 0), (.4, -.5, 0)
    for i in range(11):
        assert B.swing(A, Bp, 0.0, 0.0, (-.2, 0.0), 0.0, i / 10)[:2] == pytest.approx((.4, .5 - i / 10))
