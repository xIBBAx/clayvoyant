"""Clay stop motion: everything that runs without Blender (jobs, timing, acting keys, caching, safety),
and the contracts between the Python side and the engine scripts that Blender runs."""

import json
import py_compile
import re
from pathlib import Path

import pytest

from sastudio import direction as D
from sastudio import stopmotion as SM
from sastudio.cli import main
from sastudio.errors import ToolMissing
from sastudio.project import load_project
from sastudio.render import clay

ENGINE = Path(clay.__file__).resolve().parents[1] / "engine"


@pytest.fixture(scope="module")
def film(tmp_path_factory):
    root = tmp_path_factory.mktemp("m") / "film"
    assert main(["init", str(root), "--org", "Acme Ltd", "--email", "sec@acme.co.in"]) == 0
    return load_project(root)


def _scene(project, scene_id):
    plan = next(p for p in D.plan(project) if p.scene == scene_id)
    scene = next(s for s in project.scenes if s.id == scene_id)
    return scene, plan, SM.spans_estimated(project, scene)


def _edit(root: Path, name: str, old: str, new: str):
    f = root / "scenes" / name
    text = f.read_text(encoding="utf-8")
    assert old in text
    f.write_text(text.replace(old, new, 1), encoding="utf-8")
    return f, text


def test_scene_job_is_complete_and_deterministic(film):
    scene, plan, spans = _scene(film, "helpful_caller")
    a = SM.scene_job(film, scene, plan, spans)
    b = SM.scene_job(film, scene, plan, spans)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert [c["id"] for c in a["cast"]] == list(plan.sides)
    assert [ln["id"] for ln in a["lines"]] == [ln.id for ln in scene.lines if not ln.is_card]
    assert a["set"]["name"] == plan.set and a["set"]["org"].startswith("Acme")
    assert a["lighting"]["key_k"] == D.LIGHTING[plan.lighting]["key_k"]
    for ln in a["lines"]:
        assert ln["end"] > ln["start"] and ln["cues"], ln["id"]
        assert all(0 <= t <= (ln["end"] - ln["start"]) / SM.FPS + 0.1 for t, _ in ln["cues"])
        assert {s for _, s in ln["cues"]} <= set("ABCDEFGHX")


def test_shots_cover_every_line_once_on_twos(film):
    scene, plan, spans = _scene(film, "too_good_email")
    seen: list[int] = []
    for shot in plan.shots:
        frames = SM.shot_frames(shot, spans)
        if shot.camera == "insert":
            continue
        assert frames == sorted(frames)
        seen += frames
    assert len(seen) == len(set(seen))  # no frame is filmed by two shots
    want = {sp.beat + f for sp in spans for f in range(0, sp.frames, SM.STEP)}
    assert set(seen) == want            # and every drawing of every line is filmed


def test_a_later_line_does_not_refilm_an_earlier_shot(film):
    """Shots are cached by what can affect them: changing the last line leaves the first shot's job alone."""
    root = Path(film.root)
    scene, plan, spans = _scene(film, "helpful_caller")
    first = plan.shots[0]
    before = SM.shot_job(SM.scene_job(film, scene, plan, spans), first, SM.shot_frames(first, spans), "draft")
    last = [ln for ln in scene.lines if not ln.is_card][-1]
    f, text = _edit(root, "04_helpful_caller.yaml", last.say[:24], "Hm. " + last.say[:24])
    try:
        proj = load_project(root)
        scene2, plan2, spans2 = _scene(proj, "helpful_caller")
        first2 = plan2.shots[0]
        after = SM.shot_job(SM.scene_job(proj, scene2, plan2, spans2), first2, SM.shot_frames(first2, spans2), "draft")
        last_shot = plan2.shots[-1]
        end_before = SM.shot_job(SM.scene_job(film, scene, plan, spans), plan.shots[-1], SM.shot_frames(plan.shots[-1], spans), "draft")
        end_after = SM.shot_job(SM.scene_job(proj, scene2, plan2, spans2), last_shot, SM.shot_frames(last_shot, spans2), "draft")
    finally:
        f.write_text(text, encoding="utf-8")
    assert SM._digest(before, {}) == SM._digest(after, {})
    assert SM._digest(end_before, {}) != SM._digest(end_after, {})


def test_presets_match_the_compositor():
    from sastudio.render import cards

    assert set(SM.PRESETS) == set(cards.PRESETS)
    for name, (w, h, samples) in SM.PRESETS.items():
        assert (w, h) == cards.PRESETS[name]["size"] and samples > 0


def test_walking_in_is_filmed_not_refused(film):
    root = Path(film.root)
    f, text = _edit(root, "04_helpful_caller.yaml", "  - { id: hc_01, who: rook, say:", "  - { id: hc_01, who: rook, act: [walk_in, wave], say:")
    try:
        proj = load_project(root)
        scene, plan, spans = _scene(proj, "helpful_caller")
        job = SM.scene_job(proj, scene, plan, spans)
    finally:
        f.write_text(text, encoding="utf-8")
    walk = [k for k in job["keys"] if k.get("walk")]
    assert walk and walk[0]["who"] == "rook" and walk[0]["walk"] == "home" and walk[0]["enter"]
    assert next(c for c in job["cast"] if c["id"] == "rook")["enter_from"] in ("door", "offscreen")
    assert "rook" in next(ln for ln in job["lines"] if ln["id"] == "hc_01")["manual"]  # the wave is theirs, not the default


def test_things_in_hands_and_business(film):
    root = Path(film.root)
    f, text = _edit(root, "04_helpful_caller.yaml", "  - { id: hc_01, who: rook, say:", "  - { id: hc_01, who: rook, act: [check_phone], say:")
    try:
        proj = load_project(root)
        scene, plan, spans = _scene(proj, "helpful_caller")
        scene.direction = dict(scene.direction or {}, business={plan.shots[0].who[0]: "hold_mug"})
        job = SM.scene_job(proj, scene, plan, spans)
    finally:
        f.write_text(text, encoding="utf-8")
    props = {(c["who"], c["prop"]) for c in job["carry"]}
    assert ("rook", "phone") in props and (plan.shots[0].who[0], "mug") in props
    assert any(k.get("look") == "hand" for k in job["keys"] if k["who"] == "rook")


def test_every_gesture_and_feeling_has_an_engine_counterpart():
    acting = (ENGINE / "clay" / "acting.py").read_text(encoding="utf-8")
    gest = set(re.findall(r"^    (\w+)=dict\(", acting[acting.index("GEST = dict("):acting.index("TALK = [")], re.M))
    moods = set(re.findall(r"(\w+)=M_\(", acting))
    joints = (ENGINE / "clay" / "handrig.py").read_text(encoding="utf-8")
    gj = set(re.findall(r"(\w+)=dict\(", joints[joints.index("GJ = dict("):joints.index("FACE = dict(")]))
    assert set(SM.HANDS.values()) <= gest, set(SM.HANDS.values()) - gest
    assert set(SM.HANDS.values()) <= gj | {"rest"}, set(SM.HANDS.values()) - gj
    assert set(SM.MOODS.values()) | set(SM.ENGINE_MOODS) <= moods
    assert set(SM.HANDS) | {"nod", "shake_head", "tilt_head", "lean_in", "turn_to", "sit_down", "stand_up", "walk_in", "walk_out"} == set(D.GESTURES)
    assert set(D.EMOTIONS) == set(SM.MOODS) | set(SM.ENGINE_MOODS)
    assert set(SM.OPENINGS) == set(D.TRANSITIONS)


def test_sets_the_engine_builds_are_the_sets_direction_knows():
    src = (ENGINE / "clay" / "sets.py").read_text(encoding="utf-8")
    built = set(re.findall(r"(\w+)=\1[,)]", src[src.index("SETS = dict("):]))
    assert built == set(D.SETS)
    for name, info in D.SETS.items():
        body = src[src.index(f"def {name}(C):"):]
        body = body[:body.index("\ndef ", 10)] if "\ndef " in body[10:] else body
        marks = set(re.findall(r"(\w+)=mark\(", body))
        assert set(info["marks"]) <= marks, (name, set(info["marks"]) - marks)
        assert set(info["seats"]) <= marks, name
        assert bool(re.search(r"\bdoor=mark\(", body)) == info["door"], name


def test_missing_blender_says_how_to_fix_it(monkeypatch):
    monkeypatch.delenv("SASTUDIO_BLENDER", raising=False)
    monkeypatch.setattr(SM.shutil, "which", lambda _name: None)
    with pytest.raises(ToolMissing) as e:
        SM.find_blender()
    assert "SASTUDIO_BLENDER" in e.value.hint and "blender.org" in e.value.hint


def test_engine_scripts_compile_and_are_all_listed(tmp_path):
    files = sorted(p.relative_to(ENGINE).as_posix() for p in ENGINE.rglob("*.py") if p.name != "__init__.py")
    assert set(files) == set(clay.ENGINE_FILES)
    for rel in files:
        py_compile.compile(str(ENGINE / rel), cfile=str(tmp_path / "x.pyc"), doraise=True)


def test_engine_reads_no_code_and_no_private_paths_from_a_job():
    """The scripts Blender runs take numbers, names and paths from the job: never eval/exec, never an absolute path of ours."""
    for rel in clay.ENGINE_FILES:
        src = (ENGINE / rel).read_text(encoding="utf-8")
        assert not re.search(r"\b(eval|exec|__import__|pickle|subprocess|os\.system)\s*\(", src), rel
        assert not re.search(r"/mnt/|/home/|[A-Z]:\\\\", src), rel


def test_film_and_motion_commands_are_listed(capsys):
    for cmd, flag in (("film", "--voices"), ("motion", "--scene")):
        with pytest.raises(SystemExit):
            main([cmd, "--help"])
        assert flag in capsys.readouterr().out


def test_phoneme_marks_drive_the_mouth_when_a_voice_reports_them(film):
    scene, plan, spans = _scene(film, "helpful_caller")
    lid = spans[0].line.id
    marks = [["m", 0.20, 0.26], ["ɑ", 0.26, 0.40], [" ", 0.40, 0.44], ["f", 0.44, 0.52], ["u", 0.52, 0.70]]
    job = SM.scene_job(film, scene, plan, spans, phonemes={lid: marks})
    cues = next(ln for ln in job["lines"] if ln["id"] == lid)["cues"]
    assert [s for _, s in cues][:4] == ["A", "D", "G", "F"]
    assert cues[0][0] == pytest.approx(0.03, abs=0.01)   # the provider's leading silence is trimmed off, as in the audio


def test_a_prop_insert_is_filmed_and_a_card_is_left_to_the_compositor(monkeypatch):
    """A line under `camera: insert, who: [laptop]` used to be skipped silently, so a clay film fell back to the
    drawn style for it. Now the prop is filmed and the line is heard over it; a `card:` line is still drawn as a card."""
    from types import SimpleNamespace as NS

    filmed: list[str] = []
    monkeypatch.setattr(SM.clay, "build_rigs", lambda *a, **k: None)
    monkeypatch.setattr(SM, "scene_job", lambda *a, **k: {})
    monkeypatch.setattr(SM, "film_shot", lambda project, part, shot, frames, preset, label, log: filmed.append(label) or Path(label))
    monkeypatch.setattr(SM, "_line_folder", lambda project, folder, name, beat, frames: folder)
    card = D.Shot(lines=["c1"], camera="insert", who=[], focus=None)
    prop = D.Shot(lines=["l2"], camera="insert", who=["laptop"], focus=None)
    talk = D.Shot(lines=["l3"], camera="medium", who=["ana"], focus="ana")
    spans = [NS(line=NS(id=i), beat=b, frames=24, start=b, end=b + 24) for i, b in (("c1", 0), ("l2", 24), ("l3", 48))]
    plan = NS(sides={"ana": "left"}, shots=[card, prop, talk])
    monkeypatch.setattr(SM, "shot_frames", lambda shot, sp: [0, 2])
    out = SM.film_scene(NS(), NS(id="s"), plan, spans, "draft", log=lambda *_: None)
    assert filmed == ["s_s02_draft", "s_s03_draft"]
    assert set(out) == {"l2", "l3"}
    assert SM.is_card(card) and not SM.is_card(prop) and not SM.is_card(talk)

