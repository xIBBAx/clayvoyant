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
        import body as Bd
        st = a.st['stance']
        prev, worst_slide, worst_turn, both_up, frames, closest = None, 0.0, 0.0, 0, 0, 9.0
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
            if foot[1][2] is not None and foot[-1][2] is not None:
                closest = min(closest, Bd.feet_gap(foot[1][0], foot[1][2], foot[-1][0], foot[-1][2])[0])
            if prev is not None:
                for s in (-1, 1):
                    (p0, l0, y0), (p1, l1, y1) = prev[s], foot[s]
                    if l0 < 1e-9 and l1 < 1e-9:             # on the floor at both frames: it must not have moved
                        worst_slide = max(worst_slide, math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
                        if y0 is not None and y1 is not None:
                            worst_turn = max(worst_turn, abs(A._ang(y1 - y0)))
            prev, frames = foot, frames + 1
        print(json.dumps(dict(slide=worst_slide, turn=worst_turn, both_up=both_up, frames=frames, closest=closest)))
    """)
    assert res["slide"] < 1e-6, res       # no foot on the floor ever moves along it: not at a corner, a turn or a stop
    assert res["turn"] < 1e-6, res        # nor swivels: a foot turns while it is in the air
    assert res["both_up"] == 0, res       # walking is never a hop
    assert res["closest"] >= .019, res    # and the feet never touch or cross, stepping round corners or turning


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


def _feet_in(job: dict, tmp: Path) -> list[dict]:
    """Pose every drawing of a planned shot in Blender (nothing drawn, nothing measured) -> each shoe per drawing:
    {f, who, seat, L: [x, y, lowest z, pointing], R: [...]}."""
    exe = _blender()
    job = dict(job, mode="check", check_every=10 ** 6, trace_feet=True, device="CPU")
    p = tmp / "job.json"
    p.write_text(json.dumps(job), "utf-8")
    out = subprocess.run([exe, "-b", "--factory-startup", "-P", str(ENGINE / "film.py"), "--", str(p)],
                         capture_output=True, text=True, timeout=1800)
    rows = [json.loads(ln[5:]) for ln in out.stdout.splitlines() if ln.startswith("FEET ")]
    assert rows and "CHECKED" in out.stdout, out.stdout[-2000:] + out.stderr[-2000:]
    return rows


def test_sitting_down_and_getting_up_step_each_foot_once_and_a_foot_on_the_floor_never_slides_or_turns(tmp_path):
    """The sofa, the bench and the meeting room's chairs: on the way down and back up, a foot on the floor stays where
    it is and keeps pointing the way it points (it turns only while it is lifted), and each foot steps once, straight
    to where it goes: never part way and back, never one foot starting and the other taking over."""
    import math
    from concurrent.futures import ThreadPoolExecutor

    pytest.importorskip("skimage", reason="needs the clay extra: pip install -e '.[clay]'")
    _blender()
    from sastudio.project import load_project
    from sastudio.render import clay
    from sastudio.stopmotion import check as C

    if not clay.engine_included():
        pytest.skip("the clay engine is not in this installation")
    shutil.copytree(ROOT / "tests" / "data" / "staging", tmp_path / "staging")
    project = load_project(tmp_path / "staging")
    jobs = [j for j in C.planned_jobs(project, scene_ids=["sofa", "bench", "meeting"], log=lambda *_: None)]
    dirs = [tmp_path / f"t{i}" for i in range(len(jobs))]
    for d in dirs:
        d.mkdir()
    with ThreadPoolExecutor(2) as ex:
        traces = list(ex.map(lambda jd: (jd[0][0], _feet_in(jd[0][1], jd[1])), zip(jobs, dirs)))
    ON = .006           # a sole this close to the lowest it ever is in the shot is on the floor (3 mm)
    moves, slides, turns, backs = 0, [], [], []
    for label, rows in traces:
        for who in sorted({r["who"] for r in rows}):
            seq = [r for r in rows if r["who"] == who]
            floor = {s: min(r[s][2] for r in seq) for s in "LR"}
            for r0, r1 in zip(seq, seq[1:]):
                if not (0 < r0["seat"] and 0 < r1["seat"]):
                    continue                     # standing and walking are the other tests' business
                for s in "LR":
                    a, b = r0[s], r1[s]
                    if a[2] - floor[s] <= ON and b[2] - floor[s] <= ON:
                        slides.append((label, who, r1["f"], s, math.hypot(b[0] - a[0], b[1] - a[1])))
                        turns.append((label, who, r1["f"], s, abs((b[3] - a[3] + math.pi) % (2 * math.pi) - math.pi)))
            # each run of drawings between standing (0) and seated (1): every foot only ever gets nearer where it goes
            i = 0
            while i < len(seq):
                if not 0 < seq[i]["seat"] < 1:
                    i += 1
                    continue
                j = i
                while j + 1 < len(seq) and 0 < seq[j + 1]["seat"] < 1:
                    j += 1
                if i > 0 and j + 1 < len(seq):
                    moves += 1
                    end = seq[j + 1]
                    for s in "LR":
                        d = [math.hypot(r[s][0] - end[s][0], r[s][1] - end[s][1]) for r in seq[i - 1:j + 2]]
                        worst = max((d[k + 1] - min(d[:k + 1]) for k in range(len(d) - 1)), default=0.0)
                        backs.append((label, who, seq[i]["f"], s, worst))
                i = j + 1
    assert moves >= 3, moves                                     # the sofa, the bench and a chair, down and up
    assert max(x[4] for x in slides) < .002, max(slides, key=lambda x: x[4])      # 1 mm: a foot on the floor stays put
    assert max(x[4] for x in turns) < .01, max(turns, key=lambda x: x[4])         # and does not swivel
    assert max(x[4] for x in backs) < .02, max(backs, key=lambda x: x[4])         # each step goes one way (1 cm)


def test_the_body_faces_the_way_it_walks_after_a_turn_and_never_snaps_round():
    res = _engine("""
        import math, acting as A
        class P: pass
        out = {}
        # walk, come round on the spot, walk on the other way; then set off behind (a turn is put in first); then walk
        # up to somewhere and turn round there, the way people come to a seat
        a = A.Actor('x', P(), (0, 0))
        e1 = a.walk(0, (4.0, 0.0))
        t1 = a.turn(e1 + 2, 0.0)
        e2 = a.walk(t1 + 6, (-4.0, 0.0))
        t2 = a.turn(e2 + 2, 0.0)
        e3 = a.walk(t2 + 30, (-4.0, 3.0))          # straight behind them
        t3 = a.turn(e3 + 2, 0.0)
        a.finish()
        walks = [w for w in a.walks if w[8] == 'walk' and w[1] > w[0]]
        worst_mid, worst_step = 0.0, 0.0
        prev = None
        for f in range(-5, t3 + 40):
            y = a.heading(f, 0.0)
            if prev is not None:
                worst_step = max(worst_step, abs(A._ang(y - prev)))
            prev = y
            for w in walks:
                n = w[1] - w[0]
                if w[0] + .3 * n <= f <= w[0] + .7 * n:          # the middle of every walk: facing the way it goes
                    hd = math.atan2(w[3][0] - w[2][0], -(w[3][1] - w[2][1]))
                    worst_mid = max(worst_mid, abs(A._ang(y - hd)))
        out = dict(mid=worst_mid, step=worst_step, walks=len(walks), turns=sum(w[8] == 'turn' for w in a.walks))
        print(json.dumps(out))
    """)
    assert res["walks"] == 3 and res["turns"] == 4, res      # the walk that set off behind turned on the spot first
    assert res["mid"] < .06, res                              # walking, the body points the way it goes, never sideways
    assert res["step"] < .3, res                              # and it never snaps round from one frame to the next


def test_a_route_that_doubles_back_turns_on_the_spot_and_the_feet_never_touch():
    res = _engine("""
        import math, acting as A, body as Bd
        class P: pass
        a = A.Actor('x', P(), (0, 0))
        e1 = a.walk(0, (3.0, 0.0))                  # a route whose second leg doubles back past the first
        e2 = a.walk(e1, (0.0, 2.0))
        a.walk(e2, (-2.0, -1.0))
        a.finish()
        st = a.st['stance']
        prev, worst_slide, worst_turn, closest = None, 0.0, 0.0, 9.0
        for f in range(-2, a.walks[-1][1] + 20):
            pos, feet, _h, _m = a.locate(f)
            if feet:
                mv, sd, side, lift = feet[:4]
                yw = feet[5] if len(feet) > 5 else (None, None)
                foot = {side: (mv, lift, yw[0]), -side: (sd, 0.0, yw[1])}
            else:
                psi = a.stance(f)
                foot = {s: (A.standing_foot(pos, s, psi, st), 0.0, psi) for s in (-1, 1)}
            if foot[1][2] is not None and foot[-1][2] is not None:
                closest = min(closest, Bd.feet_gap(foot[1][0], foot[1][2], foot[-1][0], foot[-1][2])[0])
            if prev is not None:
                for s in (-1, 1):
                    (p0, l0, y0), (p1, l1, y1) = prev[s], foot[s]
                    if l0 < 1e-9 and l1 < 1e-9:
                        worst_slide = max(worst_slide, math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
                        if y0 is not None and y1 is not None:
                            worst_turn = max(worst_turn, abs(A._ang(y1 - y0)))
            prev = foot
        print(json.dumps(dict(slide=worst_slide, turn=worst_turn, closest=closest,
                              turns=sum(w[8] == 'turn' for w in a.walks))))
    """)
    assert res["turns"] >= 1, res             # a corner that sharp is turned on the spot, not stepped round
    assert res["closest"] >= .019, res        # so the shoes never touch or cross
    assert res["slide"] < 1e-6 and res["turn"] < 1e-6, res


_FEET_LOOP = """
        st = a.st['stance']
        prev, worst_slide, worst_turn, closest, jump, last = None, 0.0, 0.0, 9.0, 0.0, None
        for f in range(-2, a.walks[-1][1] + 20):
            pos, feet, _h, _m = a.locate(f)
            if last is not None:
                jump = max(jump, math.hypot(pos[0] - last[0], pos[1] - last[1]))
            last = pos
            if feet:
                mv, sd, side, lift = feet[:4]
                yw = feet[5] if len(feet) > 5 else (None, None)
                foot = {side: (mv, lift, yw[0]), -side: (sd, 0.0, yw[1])}
            else:
                psi = a.stance(f)
                foot = {s: (A.standing_foot(pos, s, psi, st), 0.0, psi) for s in (-1, 1)}
            if foot[1][2] is not None and foot[-1][2] is not None:
                closest = min(closest, Bd.feet_gap(foot[1][0], foot[1][2], foot[-1][0], foot[-1][2])[0])
            if prev is not None:
                for s in (-1, 1):
                    (p0, l0, y0), (p1, l1, y1) = prev[s], foot[s]
                    if l0 < 1e-9 and l1 < 1e-9:
                        worst_slide = max(worst_slide, math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
                        if y0 is not None and y1 is not None:
                            worst_turn = max(worst_turn, abs(A._ang(y1 - y0)))
            prev = foot
"""


def test_a_new_order_replaces_what_the_last_one_still_had_planned():
    """Told to go elsewhere before a route is walked: its later legs, the turn at its end and the sit that was to follow
    are dropped (nobody walks two plans at once, or sits down after being sent away); the direction's own keys stay."""
    res = _engine("""
        import math, acting as A, body as Bd
        class P: pass
        a = A.Actor('x', P(), (0, 0))
        e1 = a.walk(0, (3.0, 0.0))
        e2 = a.walk(e1, (3.0, 3.0))
        t = a.turn(e2 + 2, 0.0)
        a.plan(e2 - 10, dict(face=0.0))
        a.plan(t + 2, dict(seat=1.0, face=0.0))
        a.key(t + 5, dict(g='wave'))                # given by the direction itself: it stays
        f = e1 + 6                                  # a new order before the route is done
        gone_w, gone_k = a.supersede(f)
        a.walk(f, (-2.0, 0.0))
        a.finish()
    """ + _FEET_LOOP + """
        print(json.dumps(dict(gone_w=len(gone_w), gone_k=len(gone_k), seat=any(st_.get('seat') for _f, st_ in a.keys),
                              wave=any(st_.get('g') == 'wave' for _f, st_ in a.keys), jump=jump, closest=closest,
                              slide=worst_slide, turn=worst_turn, end=list(a.locate(a.walks[-1][1] + 12)[0][:2]))))
    """)
    # the turn not yet begun, and the face and the sit; the leg under way stays until the new walk takes it over
    assert res["gone_w"] == 1 and res["gone_k"] == 2, res
    assert not res["seat"] and res["wave"], res
    assert res["jump"] < .2, res                               # leaves from where the feet are: nothing jumps
    assert abs(res["end"][0] + 2.0) < .05 and abs(res["end"][1]) < .05, res
    assert res["closest"] >= .019 and res["slide"] < 1e-6 and res["turn"] < 1e-6, res


def test_sent_back_mid_stride_a_walker_stops_turns_round_and_walks_back():
    """Reversing in the air would swing one leg through the other: the foot that is up comes down, the other joins it,
    the body turns on the spot, and then walks back. The feet never touch, slide or swivel, and nothing jumps."""
    res = _engine("""
        import math, acting as A, body as Bd
        class P: pass
        a = A.Actor('x', P(), (0, 0))
        e = a.walk(0, (4.0, 0.0))
        mid = e // 2
        a.supersede(mid)
        a.walk(mid, (-2.0, 0.0))                    # back the way they came, mid-stride
        a.finish()
    """ + _FEET_LOOP + """
        print(json.dumps(dict(turns=sum(w[8] == 'turn' for w in a.walks), jump=jump, closest=closest, slide=worst_slide,
                              turn=worst_turn, end=list(a.locate(a.walks[-1][1] + 12)[0][:2]))))
    """)
    assert res["turns"] >= 1, res
    assert res["closest"] >= .019, res
    assert res["slide"] < 1e-6 and res["turn"] < 1e-6, res
    assert res["jump"] < .2, res
    assert abs(res["end"][0] + 2.0) < .05 and abs(res["end"][1]) < .05, res


def test_an_imported_model_in_the_shot_is_measured_without_breaking_the_check(tmp_path):
    """An imported model is measured whole against the set and the cast; the check (and so filming) must not stop at it."""
    pytest.importorskip("skimage", reason="needs the clay extra: pip install -e '.[clay]'")
    _blender()
    from sastudio.project import load_project
    from sastudio.render import clay
    from sastudio.stopmotion import check as C

    from .conftest import write_project

    if not clay.engine_included():
        pytest.skip("the clay engine is not in this installation")
    root = write_project(tmp_path / "guest")
    t = (root / "studio.yaml").read_text(encoding="utf-8")
    t = t.replace("  preset: draft", "  renderer: clay\n  preset: draft")
    t = t.replace("    voice: { provider: offline, settings: { rate: 200 } }",
                  '    voice: { provider: offline, settings: { rate: 200 } }\n'
                  '    look: { model: models/figure.glb, model_license: "made for the tests" }', 1)
    a, b = t.index("  - id: one\n"), t.index("  - id: two\n")
    t = t[:a] + ('  - id: one\n    title: "Scene One"\n    direction:\n      set: office\n'
                 '      blocking: { ana: standing_left, dev: standing_right }\n    lines:\n'
                 '      - { id: l1, who: ana, to: dev, say: "Morning. Did you see the email?" }\n'
                 '      - { id: l2, who: dev, to: ana, say: "I did. I reported it." }\n') + t[b:]
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    (root / "models").mkdir()
    shutil.copy(ROOT / "tests" / "data" / "rigged_figure.glb", root / "models" / "figure.glb")
    project = load_project(root)
    jobs = C.planned_jobs(project, scene_ids=["one"], log=lambda *_: None)
    assert jobs and any(any(c.get("model") for c in j["cast"]) for _l, j in jobs)
    rep = C.check(jobs, every=3, workers=2, log=lambda *_: None)
    assert not rep.failed, [(s.label, s.error) for s in rep.failed]
    assert rep.drawings > 0
