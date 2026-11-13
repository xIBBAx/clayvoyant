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
    assert set(SM.HANDS) | {"nod", "shake_head", "tilt_head", "lean_in", "laugh", "turn_to", "sit_down", "stand_up", "walk_in",
                            "walk_out"} == set(D.GESTURES)
    assert set(D.EMOTIONS) == set(SM.MOODS) | set(SM.ENGINE_MOODS)
    assert set(SM.OPENINGS) == set(D.TRANSITIONS)


def test_every_gesture_becomes_acting_keys_and_a_laugh_comes_back_to_the_face_it_left():
    for g in D.GESTURES:
        keys, _hands = SM._gesture_keys("ana", g, 100, 160, "ben", {"door": True}, mood="worry")
        assert all(k["who"] == "ana" and isinstance(k["frame"], int) for k in keys), g
    keys, hands = SM._gesture_keys("ana", "laugh", 100, 160, "ben", {}, mood="worry")
    assert not hands and (keys[0]["laugh"], keys[0]["f"]) == (1, "grin") and (keys[-1]["laugh"], keys[-1]["f"]) == (0, "worry")


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


def test_a_prop_insert_is_filmed_and_a_card_is_left_to_the_compositor(monkeypatch, tmp_path):
    """A line under `camera: insert, who: [laptop]` used to be skipped silently, so a clay film fell back to the
    drawn style for it. Now the prop is filmed and the line is heard over it; a `card:` line is still drawn as a card."""
    from types import SimpleNamespace as NS

    filmed: list[str] = []
    monkeypatch.setattr(SM.clay, "build_rigs", lambda *a, **k: None)
    monkeypatch.setattr(SM, "scene_job", lambda *a, **k: {})
    def fake_film(project, part, shot, frames, preset, label, log):
        filmed.append(label)
        (tmp_path / label).mkdir(exist_ok=True)
        return tmp_path / label

    monkeypatch.setattr(SM, "film_shot", fake_film)
    monkeypatch.setattr(SM, "_line_folder", lambda project, src, name, beat, frames: src[0][0])
    card = D.Shot(lines=["c1"], camera="insert", who=[], focus=None)
    prop = D.Shot(lines=["l2"], camera="insert", who=["laptop"], focus=None)
    talk = D.Shot(lines=["l3"], camera="medium", who=["ana"], focus="ana")
    spans = [NS(line=NS(id=i, who="ana"), beat=b, frames=24, start=b, end=b + 24) for i, b in (("c1", 0), ("l2", 24), ("l3", 48))]
    plan = NS(sides={"ana": "left"}, shots=[card, prop, talk])
    monkeypatch.setattr(SM, "shot_frames", lambda shot, sp, cues=None: [0, 2])
    out = SM.film_scene(NS(), NS(id="s"), plan, spans, "draft", log=lambda *_: None)
    assert filmed == ["s_s02_draft", "s_s03_draft"]
    assert set(out) == {"l2", "l3"}
    assert SM.is_card(card) and not SM.is_card(prop) and not SM.is_card(talk)


def test_clean_shots_is_a_dry_run_until_yes_and_keeps_the_newest_of_each_shot(project_dir, capsys):
    import os
    import time

    cache = Path(project_dir) / ".studio" / "cache" / "clay"
    old, new, other = cache / "s_s01_draft.aaaa", cache / "s_s01_draft.bbbb", cache / "s_s02_draft.cccc"
    for i, d in enumerate((old, new, other)):
        d.mkdir(parents=True)
        (d / "000000.png").write_bytes(b"x" * 1000)
        (d / ".done").write_text("k")
        t = time.time() - 1000 + i * 100
        os.utime(d / ".done", (t, t))
    assert main(["clean", str(project_dir), "--shots"]) == 0
    out = capsys.readouterr().out
    assert "s_s01_draft.aaaa" in out and "superseded by s_s01_draft.bbbb" in out and "Nothing was deleted" in out
    assert old.exists() and new.exists() and other.exists()
    assert main(["clean", str(project_dir), "--shots", "--yes"]) == 0
    assert not old.exists() and new.exists() and other.exists()
    assert main(["clean", str(project_dir), "--shots", "--all"]) == 0
    assert "Would free" in capsys.readouterr().out and new.exists()


def test_a_cut_inside_a_line_lands_where_the_mouth_rests_and_the_pieces_tile_the_line():
    from types import SimpleNamespace as NS

    sp = SM.Span(line=NS(id="l1"), beat=100, frames=96, lead=6, speech=84)
    # speech cues in seconds from the voice's start: the mouth rests ('X') at 1.5 s, i.e. frame 6 + 36 = 42 of the beat
    cues = [(0.0, "B"), (0.6, "C"), (1.5, "X"), (1.75, "E"), (3.2, "X")]
    assert SM.cut_point(sp, .55, cues) == 42          # 52.8 wanted, 42 is the nearest rest inside 35-80 %
    assert SM.cut_point(sp, .55, []) == 52            # no rest known: the plain fraction, on twos
    a = D.Shot(lines=["l1"], camera="close_up", who=["ana"], focus="ana", part=[0, .55])
    b = D.Shot(lines=["l1"], camera="reaction", who=["dev"], focus="dev", part=[.55, 1])
    fa, fb = SM.shot_frames(a, [sp], {"l1": cues}), SM.shot_frames(b, [sp], {"l1": cues})
    assert fa[-1] < fb[0] == 142 and sorted(fa + fb) == list(range(100, 196, SM.STEP))


def test_a_line_cut_between_two_shots_takes_each_drawing_from_its_own_shot(tmp_path):
    from types import SimpleNamespace as NS

    one, two = tmp_path / "shotA.aaaa", tmp_path / "shotB.bbbb"
    for d, frames in ((one, (10, 12)), (two, (14, 16))):
        d.mkdir()
        for f in frames:
            (d / f"{f:06d}.png").write_text(d.name)
    dest = SM._line_folder(NS(root=tmp_path), [(one, {10, 12}), (two, {14, 16})], "s.l1.draft", 10, 8)
    assert [(dest / f"{i:05d}.png").read_text() for i in (1, 3, 5, 7)] == [one.name, one.name, two.name, two.name]


def test_a_shot_renumbered_by_an_earlier_cut_is_reused_not_filmed_again(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS

    monkeypatch.setattr(SM, "rig_stamps", lambda project, cast: {})
    monkeypatch.setattr(SM, "_font", lambda: "font.ttf")
    monkeypatch.setattr(SM, "run_blender", lambda *a, **k: pytest.fail("filmed again"))
    job = {"cast": [{"id": "ana"}], "camera": {"shot": "medium"}}
    key = SM._digest(job, {})
    old = tmp_path / ".studio" / "cache" / "clay" / f"s_s03_draft.{key}"
    old.mkdir(parents=True)
    (old / "000000.png").write_bytes(b"x")
    (old / ".done").write_text(key)
    log: list[str] = []
    assert SM._film(NS(root=tmp_path), job, [0], "s_s04_draft", "medium", log=log.append) == old
    assert "filmed as s_s03_draft" in log[0]


def test_an_over_the_shoulder_next_to_a_two_shot_of_the_same_pair_falls_back_to_a_medium():
    root = Path(__file__).resolve().parents[1] / "examples" / "the-fast-one"
    plan = next(p for p in D.plan(load_project(root)) if p.scene == "nearly")
    ots = next(s for s in plan.shots if s.camera == "over_shoulder")
    assert ots.fallback == "medium"
    scene = next(s for s in load_project(root).scenes if s.id == "nearly")
    spans = SM.spans_estimated(load_project(root), scene)
    part = SM.scene_job(load_project(root), scene, plan, spans)
    assert SM.shot_job(part, ots, SM.shot_frames(ots, spans), "draft")["camera"]["fallback"] == "medium"


def test_a_name_tag_never_sits_on_the_listener_s_face(monkeypatch, tmp_path):
    """A line cut to the listener records where the cut lands; the compositor ends the speaker's name tag there."""
    from types import SimpleNamespace as NS

    from sastudio.render.cards import SceneRenderer

    monkeypatch.setattr(SM.clay, "build_rigs", lambda *a, **k: None)
    monkeypatch.setattr(SM, "scene_job", lambda *a, **k: {"lines": []})

    def fake_film(project, part, shot, frames, preset, label, log):
        d = tmp_path / label
        d.mkdir(exist_ok=True)
        for f in frames:
            (d / f"{f:06d}.png").write_bytes(b"x")
        return d

    monkeypatch.setattr(SM, "film_shot", fake_film)
    speak = D.Shot(lines=["l1"], camera="medium", who=["ana"], focus="ana", part=[0, .5])
    react = D.Shot(lines=["l1"], camera="reaction", who=["dev"], focus="dev", part=[.5, 1])
    sp = SM.Span(line=NS(id="l1", who="ana"), beat=0, frames=40, lead=0, speech=40)
    plan = NS(sides={"ana": "left", "dev": "right"}, shots=[speak, react])
    out = SM.film_scene(NS(root=tmp_path), NS(id="s"), plan, [sp], "draft", log=lambda *_: None)
    until = int((out["l1"] / SM.SPEAKER_UNTIL).read_text())
    assert until == 20
    r = SceneRenderer.__new__(SceneRenderer)
    r.vis = NS(clay_name_until={"l1": until})
    assert r.name_end(NS(line_id="l1")) == 20 and r.name_end(NS(line_id="other")) == 66


def test_a_change_to_the_engine_s_code_films_again_and_a_comment_does_not(monkeypatch, tmp_path):
    """The shot cache is keyed by the engine's code as Python reads it, so a forgotten ENGINE_VERSION bump cannot keep
    stale shots; a comment or a docstring changes nothing a drawing shows, so it refilms nothing."""
    import shutil as sh

    eng = tmp_path / "engine"
    sh.copytree(ENGINE, eng)
    monkeypatch.setattr(clay, "ENGINE", eng)
    job = {"frames": [0, 2], "set": {"name": "office"}}

    def key():
        SM._FINGERPRINT.clear()
        return SM._digest(job, {})
    base = key()
    acting = eng / "clay" / "acting.py"
    src = acting.read_text("utf-8")
    acting.write_text(src.replace("# Mouth shapes", "# A comment that changes nothing. Mouth shapes", 1), "utf-8")
    assert key() == base
    acting.write_text(src.replace("SIT_FRAMES = 22", "SIT_FRAMES = 23", 1), "utf-8")
    assert key() != base
    acting.write_text(src, "utf-8")
    assert key() == base
    contacts = eng / "clay" / "contacts.py"
    csrc = contacts.read_text("utf-8")
    contacts.write_text(csrc.replace("FOOT = .01", "FOOT = .02", 1), "utf-8")   # settling measures with it: it can change a drawing
    assert key() != base
    contacts.write_text(csrc, "utf-8")
    assert key() == base
    assert SM._digest(dict(job, contacts="allow"), {}) == base
    SM._FINGERPRINT.clear()


def test_a_shot_filmed_with_intersections_allowed_is_not_quietly_reused_by_a_plain_film(tmp_path, monkeypatch):
    import json as js

    shot = tmp_path / "the_call_s01.abc"
    shot.mkdir()
    (shot / "contacts.json").write_text(js.dumps([dict(frame=4, actor="ana", what="left leg", other="cush", kind="set",
                                                       pairs=12, depth=.02)]), "utf-8")
    monkeypatch.delenv("SASTUDIO_ALLOW_INTERSECTIONS", raising=False)
    with pytest.raises(SM.ContactError, match="allow-intersections"):
        SM._reusable(shot, "the_call_s01")
    monkeypatch.setenv("SASTUDIO_ALLOW_INTERSECTIONS", "1")
    SM._reusable(shot, "the_call_s01")                    # allowed again: reused, as it was filmed
    monkeypatch.delenv("SASTUDIO_ALLOW_INTERSECTIONS")
    (shot / "contacts.json").write_text("[]", "utf-8")
    SM._reusable(shot, "the_call_s01")                    # checked and clean
    (shot / "contacts.json").unlink()
    SM._reusable(shot, "the_call_s01")                    # filmed before shots kept their check


def test_a_check_that_did_not_finish_is_never_a_pass():
    from sastudio.stopmotion import check as C

    ok = C.ShotResult("a_s01", drawings=10)
    hit = C.ShotResult("a_s02", drawings=8, contacts=[dict(frame=4, actor="ana", what="left leg", other="cush", kind="set",
                                                            pairs=12, depth=.02)])
    crashed = C.ShotResult("a_s03", error="Blender stopped before the check was done")
    assert C.Report([ok]).exit_code() == 0
    assert C.Report([ok, hit]).exit_code() == 1
    assert C.Report([ok, crashed]).exit_code() == 2 and C.Report([hit, crashed]).exit_code() == 2
    words = C.said(dict(hit.contacts[0], shot="a_s02"))
    assert "a_s02 frame 4: ana's left leg inside cush" in words and "1.0 cm deep" in words


def test_a_refused_shot_says_what_passes_through_what_and_is_not_retried(monkeypatch, tmp_path):
    """The engine refuses to film a shot with a contact; the film command says who, where, and how to fix it."""
    calls = []

    class FakeProc:
        stdout = iter(["FILM frames 2 of 2 to do\n", "FILM contacts checked in 3.0s: 1\n",
                       "FILM contact frame 4: ana's left leg inside cush (set, 12 crossing faces, 1.0 cm deep)\n",
                       "FILM refused: 1 contact(s) in 2 drawings; every one is in /x/contacts.json\n"])

        def poll(self):
            return 3

        def wait(self, timeout=None):
            return 3

    monkeypatch.setattr(SM, "find_blender", lambda: ("blender", False))
    monkeypatch.setattr(SM.subprocess, "Popen", lambda *a, **k: calls.append(a) or FakeProc())
    with pytest.raises(SM.ContactError) as e:
        SM.run_blender({"rig": str(tmp_path), "out": str(tmp_path / "o"), "cast": []}, tmp_path / "w", log=lambda *_: None)
    assert "ana's left leg inside cush" in str(e.value) and "--allow-intersections" in e.value.hint
