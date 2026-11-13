"""Bodies that do not pass through things, measured in Blender. Skipped where Blender is not installed.

The staging project (tests/data/staging) puts three people of different builds and habits (tall, broad and older;
short, slight and nervous; a long tunic) through sitting on a sofa, chairs, a bench and pupils' chairs, getting up,
walking in and out, turning, laughing, a phone, a mug and a desk to type at. Every drawing of every planned shot is
posed exactly as filming would pose it and measured triangle against triangle; nothing may pass through anything.
It takes about a quarter of an hour (it sculpts three people first)."""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.blender

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "src" / "sastudio" / "engine" / "clay"


def _blender():
    from sastudio import stopmotion as SM

    try:
        return SM.find_blender()[0]
    except Exception:
        pytest.skip("Blender is not installed")


def test_nobody_passes_through_anything_in_the_staging_project(tmp_path):
    pytest.importorskip("skimage", reason="needs the clay extra: pip install -e '.[clay]'")
    _blender()
    from sastudio.project import load_project
    from sastudio.render import clay
    from sastudio.stopmotion import check as C

    if not clay.engine_included():
        pytest.skip("the clay engine is not in this installation")
    shutil.copytree(ROOT / "tests" / "data" / "staging", tmp_path / "staging")
    project = load_project(tmp_path / "staging")
    jobs = C.planned_jobs(project, log=lambda *_: None)
    assert len(jobs) >= 20
    rep = C.check(jobs, every=2, workers=2, log=lambda *_: None)
    assert not rep.failed, [(s.label, s.error) for s in rep.failed]
    assert rep.drawings > 300
    assert rep.contacts == [], "\n".join(C.said(c) for c in rep.contacts[:40])


def _engine(code: str) -> dict:
    """Run a few lines inside Blender with the engine importable; they print one JSON object."""
    exe = _blender()
    script = f"import sys, json\nsys.path.insert(0, {str(ENGINE)!r})\n" + textwrap.dedent(code)
    out = subprocess.run([exe, "-b", "--factory-startup", "--python-expr", script], capture_output=True, text=True, timeout=300)
    line = next((ln for ln in out.stdout.splitlines() if ln.startswith("{")), None)
    assert line, out.stdout[-2000:] + out.stderr[-2000:]
    return json.loads(line)


def test_feet_stay_planted_while_they_carry_the_weight_and_take_turns_to_step_round():
    res = _engine("""
        import math, acting as A
        class P: pass
        a = A.Actor('x', P(), (0, 0))
        end = a.walk(0, (4.0, 0.0))
        done = a.turn(end + 2, 0.0)          # walked towards +x; now round to face the camera
        a.finish()
        slide, gap, last = 0.0, 9.0, None
        for f in range(0, done + 12):
            pos, feet, yaw, amt = a.locate(f)
            if not feet:
                continue
            mv, st, side, lift, fr = feet[:5]
            if last is not None and last[0] == side:      # the same foot carries the weight: it must not move
                slide = max(slide, math.hypot(st[0] - last[1][0], st[1] - last[1][1]))
            gap = min(gap, math.hypot(mv[0] - st[0], mv[1] - st[1]))
            last = (side, st)
        print(json.dumps(dict(slide=slide, gap=gap, end=end, done=done, stance=a.stance(done + 1))))
    """)
    assert res["slide"] < 1e-6                  # a planted foot never skates
    assert res["gap"] > .12                     # the feet never cross through each other, walking or turning
    assert res["done"] > res["end"] + 10 and abs(res["stance"]) < 1e-6


def test_a_foot_on_the_floor_never_moves_or_turns_until_it_lifts_round_corners_turns_and_changes_of_mind():
    res = _engine("""
        import math, acting as A
        class P: pass
        a = A.Actor('x', P(), (0, 0))
        e1 = a.walk(0, (3.0, 0.0))                  # a route with corners, each leg straight on from the last
        e2 = a.walk(e1, (3.0, 2.5))
        e3 = a.walk(e2, (1.0, 3.5))
        t1 = a.turn(e3 + 2, 2.5)                    # round on the spot two frames after arriving
        a.walk(t1 + 20, (-2.0, 3.5))
        mid = t1 + 40
        a.walk(mid, (-2.0, 0.0))                    # told to go somewhere else before arriving
        a.finish()
        st = a.st['stance']
        prev, worst_slide, worst_turn, both_up, frames = None, 0.0, 0.0, 0, 0
        for f in range(-2, mid + 160):
            pos, feet, _h, _m = a.locate(f)
            if feet:
                mv, sd, side, lift = feet[:4]
                yw = feet[5] if len(feet) > 5 else (None, None)
                foot = {side: (mv, lift, yw[0]), -side: (sd, 0.0, yw[1])}
            else:
                psi = a.stance(f)
                foot = {s: (A.standing_foot(pos, s, psi, st), 0.0, psi) for s in (-1, 1)}
            both_up += foot[1][1] > 1e-9 and foot[-1][1] > 1e-9
            if prev is not None:
                for s in (-1, 1):
                    (p0, l0, y0), (p1, l1, y1) = prev[s], foot[s]
                    if l0 < 1e-9 and l1 < 1e-9:             # on the floor at both frames: it must not have moved
                        worst_slide = max(worst_slide, math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
                        if y0 is not None and y1 is not None:
                            worst_turn = max(worst_turn, abs(A._ang(y1 - y0)))
            prev, frames = foot, frames + 1
        print(json.dumps(dict(slide=worst_slide, turn=worst_turn, both_up=both_up, frames=frames)))
    """)
    assert res["slide"] < 1e-6, res       # no foot on the floor ever moves along it: not at a corner, a turn or a stop
    assert res["turn"] < 1e-6, res        # nor swivels: a foot turns while it is in the air
    assert res["both_up"] == 0, res       # walking is never a hop


def test_blinking_follows_what_a_person_is_doing_and_a_speaker_looks_away_as_a_line_begins():
    res = _engine("""
        import acting as A
        class P: pass
        S = A.Performance(fps=24)
        a = S.add(A.Actor('ana', P(), (0, 0)))
        b = S.add(A.Actor('ben', P(), (1, 0)))
        S.say('ana', 0, 2400, [], to='ben')                     # 100 seconds of talking
        a.key(2400, dict(g='read'))                              # then 100 reading
        a.key(4800, dict(g='rest'))                              # then 100 at rest, listening to ben
        for i in range(12):
            S.say('ben', 4800 + i * 200, 4800 + i * 200 + 150, [], to='ana')
        for i in range(40):                                      # lines of every length for the look away
            S.say('ben', 8000 + i * 300, 8000 + i * 300 + 30 + i * 6, [], to='ana')
        S.finish()
        def per_minute(f0, f1):
            n = sum(1 for f in range(f0, f1) if a.blink(f, S) == A.BLINK[0] and a.blink(f - 1, S) == 0)
            return n * 60 * 24 / (f1 - f0)
        ends = [l.e for l in S.lines if l.who == 'ben' and l.s < 8000]
        after = sum(1 for e in ends if any(a.blink(f, S) > 0 for f in range(e + 1, e + 12)))
        away = []
        for l in [l for l in S.lines if l.who == 'ben' and l.s >= 8000]:
            v = [b.aversion(f, S)[0] for f in range(l.s, l.e)]
            away.append(dict(n=l.e - l.s, start=max(v[:max(1, len(v) // 2)]), end=max(v[-6:])))
        again = [a.blink(f, S) for f in range(0, 7200)]
        print(json.dumps(dict(talk=per_minute(0, 2400), read=per_minute(2400, 4800), rest=per_minute(4800, 7200),
                              after=after, ends=len(ends), away=away, same=again == [a.blink(f, S) for f in range(0, 7200)])))
    """)
    # talking, at rest, reading: the measured order and roughly the measured rates (26, 17 and 4.5 a minute)
    assert res["talk"] > res["rest"] > res["read"], res
    assert 20 <= res["talk"] <= 32 and 12 <= res["rest"] <= 24 and 3 <= res["read"] <= 7.5, res
    assert res["after"] >= res["ends"] * .5, res              # most of the time a listener blinks as a line ends
    away = res["away"]
    assert all(x["end"] == 0 for x in away)                     # always back on the listener before the line ends
    looked = [x for x in away if x["start"] > .5]
    assert 0 < len(looked) < len(away)                          # often, never always: no two lines alike
    long_ = [x for x in away if x["n"] > 150]
    assert sum(x["start"] > .5 for x in long_) >= len(long_) * .5   # a long line nearly always starts with a look away
    assert res["same"]


def test_two_people_walk_the_same_way_differently():
    res = _engine("""
        import acting as A
        class P: pass
        quick = A.Actor('q', P(), (0, 0), dict(speed=.095, step=1.0))
        slow = A.Actor('s', P(), (0, 0), dict(speed=.062, step=.78))
        out = {}
        for a in (quick, slow):
            end = a.walk(0, (5.0, 0.0))
            a.finish()
            out[a.name] = dict(frames=end, steps=len(a.steps()))
        print(json.dumps(out))
    """)
    assert res["s"]["frames"] > res["q"]["frames"] * 1.3
    assert res["s"]["steps"] > res["q"]["steps"]
