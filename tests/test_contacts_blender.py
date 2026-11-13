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
            mv, st, side, lift, fr = feet
            if last is not None and last[0] == side:      # the same foot carries the weight: it must not move
                slide = max(slide, math.hypot(st[0] - last[1][0], st[1] - last[1][1]))
            gap = min(gap, math.hypot(mv[0] - st[0], mv[1] - st[1]))
            last = (side, st)
        print(json.dumps(dict(slide=slide, gap=gap, end=end, done=done, stance=a.stance(done + 1))))
    """)
    assert res["slide"] < 1e-6                  # a planted foot never skates
    assert res["gap"] > .12                     # the feet never cross through each other, walking or turning
    assert res["done"] > res["end"] + 10 and abs(res["stance"]) < 1e-6


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
