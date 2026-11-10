"""Clay stop-motion renderer: the parts that run without Blender (jobs, cameras, acting, safety)."""

import json
import math
import py_compile
from pathlib import Path

import pytest

from sastudio import direction as D
from sastudio import stopmotion as SM
from sastudio.cli import main
from sastudio.errors import ConfigError, ToolMissing
from sastudio.project import load_project

HAIR_TOP = 0.365  # the top of the tallest bundled hair, in metres (figures are 0.30 m)


@pytest.fixture(scope="module")
def film(tmp_path_factory):
    root = tmp_path_factory.mktemp("m") / "film"
    assert main(["init", str(root), "--org", "Acme Ltd", "--email", "sec@acme.co.in"]) == 0
    return load_project(root)


def _plan(project, scene):
    return next(p for p in D.plan(project) if p.scene == scene)


def test_job_is_complete_and_deterministic(film, tmp_path):
    plan = _plan(film, "helpful_caller")
    a = SM.build_job(film, plan, 0, "draft", tmp_path)
    b = SM.build_job(film, plan, 0, "draft", tmp_path)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    assert {c["id"] for c in a["characters"]} == set(plan.sides)
    assert (a["width"], a["height"], a["step"]) == (960, 540, 2)
    assert a["frame_end"] >= int(plan.shots[0].seconds * SM.FPS)
    drawings = sorted(next(iter(a["tracks"].values())))
    assert drawings[0] == 1 and all(y - x == 2 for x, y in zip(drawings, drawings[1:], strict=False))  # on twos
    assert a["logo"] and Path(a["logo"]).name == "logo.png"
    assert a["lighting"] == D.LIGHTING[plan.lighting]


def test_only_the_speaker_talks(film, tmp_path):
    plan = _plan(film, "helpful_caller")
    shot = plan.shots[0]
    job = SM.build_job(film, plan, 0, "draft", tmp_path)
    speaker = next(ln.who for ln in film.scenes[[s.id for s in film.scenes].index("helpful_caller")].lines
                   if ln.id == shot.lines[0])
    assert any(st["mouth"] > 0 for st in job["tracks"][speaker].values())
    for cid, tr in job["tracks"].items():
        if cid != speaker:
            assert all(st["mouth"] == 0 for st in tr.values()), cid
    assert any(st["blink"] for tr in job["tracks"].values() for st in tr.values())


@pytest.mark.parametrize("camera", ["medium", "two_shot", "close_up", "over_shoulder"])
def test_framing_leaves_headroom(camera):
    assert SM.AIM_Z[camera] + SM.FRAME_H[camera] / 2 > HAIR_TOP


def test_push_in_moves_closer():
    shot = D.Shot(lines=["x"], camera="close_up", who=["a"], focus="a", move="push_in", lens=65, fstop=2.8)
    pos = {"a": ((0.0, 0.18, 0.0), 0.0)}
    keys = SM.camera_keys(shot, pos, 48)["keys"]
    (start, aim), (end, _) = keys[1], keys[48]
    assert math.dist(end, aim) < math.dist(start, aim)


def test_unfilmable_gestures_are_refused_not_faked(film, tmp_path):
    root = Path(film.root)
    scene = root / "scenes" / "04_helpful_caller.yaml"
    text = scene.read_text(encoding="utf-8")
    try:
        scene.write_text(text.replace('  - { id: hc_01, who: rook, say:', '  - { id: hc_01, who: rook, act: [walk_in], say:', 1),
                         encoding="utf-8")
        proj = load_project(root)
        with pytest.raises(ConfigError, match="cannot film 'walk_in' yet"):
            SM.build_job(proj, _plan(proj, "helpful_caller"), 0, "draft", tmp_path)
    finally:
        scene.write_text(text, encoding="utf-8")


def test_missing_blender_says_how_to_fix_it(monkeypatch):
    monkeypatch.delenv("SASTUDIO_BLENDER", raising=False)
    monkeypatch.setattr(SM.shutil, "which", lambda _name: None)
    with pytest.raises(ToolMissing) as e:
        SM.find_blender()
    assert "SASTUDIO_BLENDER" in e.value.hint and "blender.org" in e.value.hint


def test_blender_scene_script_compiles(tmp_path):
    script = Path(SM.__file__).with_name("blender_scene.py")
    py_compile.compile(str(script), cfile=str(tmp_path / "x.pyc"), doraise=True)


def test_motion_command_is_listed(capsys):
    with pytest.raises(SystemExit):
        main(["motion", "--help"])
    assert "--scene" in capsys.readouterr().out


def test_close_up_camera_sits_on_the_eyeline_side():
    """A character on the left looks right: their close-up camera is to the right of them, and vice versa."""
    for side_x, yaw in ((-0.13, 0.42), (0.13, -0.42)):
        shot = D.Shot(lines=["x"], camera="close_up", who=["a"], focus="a", lens=65, fstop=2.8)
        cam, aim = SM.camera_keys(shot, {"a": ((side_x, 0.18, 0.0), yaw)}, 24)["keys"][1]
        assert (cam[0] - side_x) * yaw > 0


def test_mouth_stays_above_the_subtitles():
    for camera in ("close_up", "medium", "two_shot", "over_shoulder"):
        bottom = SM.AIM_Z[camera] - SM.FRAME_H[camera] / 2
        mouth = 0.282
        assert (mouth - bottom) / SM.FRAME_H[camera] > 0.30, camera  # subtitles use the bottom ~20 %
