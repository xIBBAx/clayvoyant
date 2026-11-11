"""The Blender launcher: a hung or dead Blender is stopped and reaped, a blank drawing is never kept, and a failed shot
is tried once more from its first missing drawing. No Blender is needed: a small Python child stands in for it."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from sastudio import stopmotion as SM
from sastudio.errors import RenderError


def _child(code: str) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:  # pragma: no cover - the pid was reused by someone else's process
        return True
    return False


def test_a_hung_child_is_stopped_at_the_deadline_and_reaped():
    proc = _child("import time; print('FILM start', flush=True); time.sleep(600)")
    t0 = time.monotonic()
    with pytest.raises(TimeoutError, match="limit"):
        SM.watch(proc, lambda ln: None, timeout=1.5, stall=600)
    assert time.monotonic() - t0 < 15
    assert proc.returncode is not None, "the child must be reaped, not left as a zombie"
    if os.name == "posix":
        assert _gone(proc.pid)


def test_a_child_that_stops_drawing_is_stopped_by_the_stall_watchdog():
    proc = _child("import time\nfor i in range(3): print('FILM frame', i, flush=True)\ntime.sleep(600)")
    seen: list[str] = []
    with pytest.raises(TimeoutError, match="no new drawing"):
        SM.watch(proc, seen.append, timeout=600, stall=1.5, progress=lambda ln: ln.startswith("FILM"))
    assert len(seen) == 3
    assert proc.returncode is not None


def test_a_child_that_finishes_returns_its_exit_code_and_every_line():
    proc = _child("print('FILM a'); print('FILM b'); raise SystemExit(3)")
    seen: list[str] = []
    assert SM.watch(proc, seen.append, timeout=60, stall=60) == 3
    assert seen == ["FILM a", "FILM b"]


def test_an_exception_while_reading_still_stops_the_child():
    proc = _child("import time; print('FILM x', flush=True); time.sleep(600)")

    def boom(_ln):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        SM.watch(proc, boom, timeout=600, stall=600)
    assert proc.returncode is not None


def test_blank_and_broken_frames_are_found(tmp_path):
    flat = tmp_path / "flat.png"
    Image.new("RGB", (320, 180), (12, 12, 12)).save(flat)
    white = tmp_path / "white.png"
    Image.new("RGB", (320, 180), (255, 255, 255)).save(white)
    real = tmp_path / "real.png"
    im = Image.new("RGB", (320, 180), (40, 30, 20))
    im.paste((220, 180, 140), (100, 40, 220, 160))     # a lit shape on a dark ground
    im.save(real)
    cut = tmp_path / "cut.png"
    cut.write_bytes(real.read_bytes()[:60])
    assert SM.blank_frames([flat, white, real, cut]) == [flat, white, cut]


def _project(tmp_path):
    return SimpleNamespace(root=tmp_path)


def _job():
    return {"cast": [{"id": "ana"}], "camera": {"shot": "medium"}}


def _drawing(path):
    im = Image.new("RGB", (64, 36), (30, 30, 30))
    im.paste((200, 160, 120), (10, 5, 40, 30))
    im.save(path)


@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setattr(SM, "rig_stamps", lambda project, cast: {})
    monkeypatch.setattr(SM, "_font", lambda: "font.ttf")


def test_a_blank_drawing_is_thrown_away_and_drawn_again(tmp_path, monkeypatch, fake_engine):
    calls = []

    def run(job, work, log):
        calls.append(sorted(p.name for p in Path(job["out"]).glob("*.png")))
        out = Path(job["out"])
        out.mkdir(parents=True, exist_ok=True)
        for f in (0, 2, 4):
            p = out / f"{f:06d}.png"
            if p.exists():
                continue
            if f == 2 and len(calls) == 1:
                Image.new("RGB", (64, 36), (0, 0, 0)).save(p)       # the first try draws frame 2 black
            else:
                _drawing(p)

    monkeypatch.setattr(SM, "run_blender", run)
    out = SM._film(_project(tmp_path), _job(), [0, 2, 4], "shot", "medium", log=lambda *_: None)
    assert len(calls) == 2
    assert calls[1] == ["000000.png", "000004.png"], "the second try starts with only the blank drawing missing"
    assert SM.blank_frames(sorted(out.glob("*.png"))) == []
    assert (out / ".done").exists()


def test_a_crash_is_retried_once_from_the_first_missing_drawing(tmp_path, monkeypatch, fake_engine):
    calls = []

    def run(job, work, log):
        out = Path(job["out"])
        out.mkdir(parents=True, exist_ok=True)
        calls.append(len(list(out.glob("*.png"))))
        if len(calls) == 1:
            _drawing(out / "000000.png")
            raise RenderError("Blender did not finish the shot:\n    CUDA error: an illegal memory access")
        for f in (0, 2, 4):
            if not (out / f"{f:06d}.png").exists():
                _drawing(out / f"{f:06d}.png")

    monkeypatch.setattr(SM, "run_blender", run)
    SM._film(_project(tmp_path), _job(), [0, 2, 4], "shot", "medium", log=lambda *_: None)
    assert calls == [0, 1], "the retry keeps the drawing the first run finished"


def test_an_engine_bug_is_not_retried(tmp_path, monkeypatch, fake_engine):
    calls = []

    def run(job, work, log):
        calls.append(1)
        raise RenderError("Blender did not finish the shot:\n    Traceback (most recent call last):\n    NameError: x")

    monkeypatch.setattr(SM, "run_blender", run)
    with pytest.raises(RenderError, match="Traceback"):
        SM._film(_project(tmp_path), _job(), [0, 2], "shot", "medium", log=lambda *_: None)
    assert calls == [1]


def test_a_shot_that_keeps_coming_out_blank_fails_loudly(tmp_path, monkeypatch, fake_engine):
    def run(job, work, log):
        out = Path(job["out"])
        out.mkdir(parents=True, exist_ok=True)
        for f in (0, 2):
            Image.new("RGB", (64, 36), (0, 0, 0)).save(out / f"{f:06d}.png")

    monkeypatch.setattr(SM, "run_blender", run)
    with pytest.raises(RenderError, match="blank"):
        SM._film(_project(tmp_path), _job(), [0, 2], "shot", "medium", log=lambda *_: None)
    assert not list((tmp_path / ".studio" / "cache" / "clay").glob("*/.done"))


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PR_SET_PDEATHSIG is Linux only")
def test_a_child_dies_with_its_parent_even_when_the_parent_is_killed_outright():
    """Blender is started this way: if sastudio is killed with SIGKILL (nothing of ours runs), the kernel kills it."""
    parent = subprocess.Popen([sys.executable, "-c", (
        "import subprocess, sys, time\n"
        "from sastudio.stopmotion import _die_with_parent\n"
        "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'], preexec_fn=_die_with_parent)\n"
        "print(c.pid, flush=True)\n"
        "time.sleep(600)\n")], stdout=subprocess.PIPE, text=True)
    child = int(parent.stdout.readline())
    assert not _gone(child)
    parent.kill()
    parent.wait(timeout=10)
    for _ in range(50):
        if _gone(child):
            break
        time.sleep(.1)
    assert _gone(child), "the child outlived a parent killed with SIGKILL"
