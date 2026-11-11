"""A real clay render: two drawings of one shot of the sample film, through Blender. Skipped without Blender.

Slow (it sculpts two characters and starts Blender): about two minutes on a laptop GPU."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.blender

ROOT = Path(__file__).resolve().parents[1]


def test_a_two_drawing_clay_shot_renders_and_is_reused(tmp_path):
    pytest.importorskip("skimage", reason="needs the clay extra: pip install -e '.[clay]'")
    from sastudio import stopmotion as SM
    from sastudio.project import load_project
    from sastudio.render import clay

    if not clay.engine_included():
        pytest.skip("the clay engine is not in this installation")
    shutil.copytree(ROOT / "examples" / "the-fast-one", tmp_path / "film")
    project = load_project(tmp_path / "film")
    plan, scene = SM._plan_for(project, "the_fast_one")
    shot = plan.shots[1]                                   # a medium on one person
    spans = SM.spans_estimated(project, scene)
    clay.build_rigs(project, ids=list(plan.sides), log=lambda *_: None)
    part = SM.scene_job(project, scene, plan, spans)
    frames = SM.shot_frames(shot, spans)[:2]
    log: list[str] = []
    folder = SM.film_shot(project, part, shot, frames, "draft", "smoke", log=log.append)
    pngs = [folder / f"{f:06d}.png" for f in frames]
    assert all(p.exists() and p.stat().st_size > 10_000 for p in pngs)
    assert SM.blank_frames(pngs) == []
    assert (folder / ".done").exists()
    again: list[str] = []
    assert SM.film_shot(project, part, shot, frames, "draft", "smoke", log=again.append) == folder
    assert any("unchanged, reused" in ln for ln in again)
