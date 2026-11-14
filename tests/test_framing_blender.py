"""Where the camera stands for a shot on one person (engine/clay/film.py, frame_shot), measured in Blender on the Held
Door sample, as `sastudio check` poses it: the face the shot is for can be seen."""

from __future__ import annotations

import math
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.blender

ROOT = Path(__file__).resolve().parents[1]


def _blender():
    from sastudio import stopmotion as SM

    try:
        return SM.find_blender()[0]
    except Exception:
        pytest.skip("Blender is not installed")


def _clearance(cam: dict, subject: str, other: str) -> float:
    """How far the line of sight from the lens to the subject's face passes from the other person's head (in set units,
    50 cm each), less the face's own half-width as perspective shrinks it towards the lens: under a head's half-width
    (.42), part of the face is behind that head."""
    p, f, h = cam["pos"], cam["heads"][subject], cam["heads"][other]
    gaps = []
    for k in range(1, 40):
        t = k / 40
        q = [p[i] + (f[i] - p[i]) * t for i in range(3)]
        if q[2] <= h[2] + .5:
            gaps.append(math.hypot(q[0] - h[0], q[1] - h[1]) - .3 * t)
    return min(gaps)


def test_a_shot_on_one_person_sees_their_face_past_everyone_else(tmp_path):
    """At reception Nadia stands at the counter, facing Sana across it. The shot on Sana used to stand straight out
    from Sana's face, which put Nadia's head in front of the lens: Held Door showed the back of her neck, out of focus,
    for most of Sana's question. The camera now walks round Sana until her face is clear.

    By Kofi's line he has turned round more than half a circle since he walked in, so his yaw counts past pi, and the
    camera, which stands on the side a face is turned to, stood behind him. It now stands in front of his face."""
    pytest.importorskip("skimage", reason="needs the clay extra: pip install -e '.[clay]'")
    _blender()
    from sastudio.project import load_project
    from sastudio.render import clay
    from sastudio.stopmotion import check as C

    if not clay.engine_included():
        pytest.skip("the clay engine is not in this installation")
    shutil.copytree(ROOT / "examples" / "held-door", tmp_path / "held-door", ignore=shutil.ignore_patterns(".studio", "build"))
    jobs = dict(C.planned_jobs(load_project(tmp_path / "held-door"), log=lambda *_: None))

    sana = jobs["reception_s02"]
    assert sana["camera"]["shot"] == "medium" and sana["camera"]["who"] == ["sana"]
    r = C.run_check("reception_s02", sana, every=10 ** 6)
    assert r.finished, r.error
    assert any(n.startswith("camera medium on sana: nadia stood between the lens and their face") for n in r.notes), r.notes
    assert _clearance(r.camera, "sana", "nadia") > .42, r.camera

    # a shot with nobody in the way is placed as it always was
    nadia = C.run_check("reception_s04", jobs["reception_s04"], every=10 ** 6)
    assert nadia.finished, nadia.error
    assert not [n for n in nadia.notes if n.startswith("camera")], nadia.notes

    kofi = jobs["held_door_s06"]
    assert kofi["camera"]["who"] == ["kofi"]
    r = C.run_check("held_door_s06", kofi, every=10 ** 6)
    assert r.finished, r.error
    cam = r.camera
    to_cam = [cam["pos"][i] - cam["heads"]["kofi"][i] for i in (0, 1)]
    n = math.hypot(*to_cam)
    assert (to_cam[0] * cam["facing"][0] + to_cam[1] * cam["facing"][1]) / n > .3, cam
