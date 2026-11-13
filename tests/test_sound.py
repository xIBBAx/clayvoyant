"""The sound engine (sastudio.sound): measured, not assumed. Synthetic signals only, so the tests are fast, the same
every run and free to redistribute. Levels are checked with the BS.1770 meter and, where FFmpeg is present, again in
the encoded film."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from sastudio.sound import ambience, dsp, events, foley, master, meter, mix
from sastudio.sound.events import Event
from sastudio.sound.kit import Kit, SoundFileError, decode

from .conftest import HAS_FFMPEG, write_project

R = dsp.RATE


def speechy(seconds: float, on: float = 1.0, off: float = 2.0, level_db: float = -20.0, seed: int = 1) -> np.ndarray:
    """A stand-in for dialogue: speech-shaped noise in phrases of `on` seconds with `off` seconds of silence between."""
    r = np.random.default_rng(seed)
    n = int(seconds * R)
    x = dsp.noise(n, r, dsp.bandpass(150, 4000)) * dsp.gain(level_db)
    t = np.arange(n) / R
    gate = ((t % (on + off)) < on).astype(float)
    return x * gate


# ---------------------------------------------------------------- the meter and the limiter
def test_the_loudness_meter_reads_a_reference_tone_as_bs1770_does():
    t = np.arange(10 * R) / R
    tone = np.stack([.1 * np.sin(2 * math.pi * 1000 * t)] * 2, axis=1)      # 1 kHz at -20 dBFS in both channels
    assert meter.integrated(tone) == pytest.approx(-20.0, abs=.05)
    assert meter.integrated(np.zeros((R, 2))) is None                          # silence has no loudness
    assert meter.integrated(np.zeros((R // 4, 2))) is None                     # nor does a clip under one block


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_the_loudness_meter_agrees_with_ffmpeg(tmp_path):
    x = np.stack([speechy(12.0, seed=2), speechy(12.0, seed=3)], axis=1)
    p = tmp_path / "x.wav"
    master.write_wav(p, x)
    assert meter.integrated(x) == pytest.approx(master.measure(p)["lufs"], abs=.15)


def test_the_limiter_never_lets_a_true_peak_over_the_ceiling():
    r = np.random.default_rng(4)
    loud_start = np.tile(1.4 * np.sin(2 * math.pi * 997 * np.arange(R) / R)[:, None], (1, 2))
    clicks = np.zeros((R, 2))
    clicks[::4801] = 1.8
    noise = r.standard_normal((5 * R, 2)) * .3
    for x in (loud_start, clicks, noise):
        y, red = dsp.limit(x, -1.5)
        assert dsp.true_peak_db(y) <= -1.5 + .02
        assert red < 0
    quiet = noise * .1
    y, red = dsp.limit(quiet, -1.5)
    assert red == 0.0 and np.array_equal(y, quiet)                             # nothing to do: nothing touched


def test_true_peaks_are_found_between_samples():
    t = np.arange(4800)
    s = np.sin(2 * math.pi * 12000 * t / R + math.pi / 4)        # samples at +-0.707, the wave itself reaches 1.0
    assert np.abs(s).max() == pytest.approx(.7071, abs=1e-3)
    assert dsp.true_peak_db(s[100:-100]) == pytest.approx(0.0, abs=.15)


def test_the_running_minimum_and_the_moving_average_are_exact():
    x = np.random.default_rng(5).standard_normal(3000)
    for w in (1, 2, 9, 240):
        assert np.allclose(dsp.running_min(x, w), [x[i:i + w].min() for i in range(len(x))])
    assert np.allclose(dsp.smooth(x, 9)[4:-4], [x[i - 4:i + 5].mean() for i in range(4, len(x) - 4)])


# ---------------------------------------------------------------- ducking, fades, crossfades
def test_music_dips_under_speech_recovers_in_pauses_and_never_jumps():
    d = speechy(16.0, on=2.0, off=3.0)
    g = mix.duck_curve(d, 11.0)
    gdb = 20 * np.log10(g)
    t = np.arange(len(d)) / R
    mid_speech = (t % 5.0 > .8) & (t % 5.0 < 1.6)
    mid_pause = (t % 5.0 > 3.9) & (t % 5.0 < 4.6)
    assert gdb[mid_speech].max() < -10.5                      # down by the depth asked while somebody speaks
    assert gdb[mid_pause].min() > -.5                         # and back up in a pause long enough to be one
    assert np.abs(np.diff(gdb)).max() * R * .01 < 1.6        # never more than about 1.5 dB in 10 ms: no pumping, no jump
    # it is already on its way down when the next phrase starts (look-ahead)
    assert gdb[5 * R] < -1.0 and gdb[int(4.7 * R)] > -.5


def test_a_pause_between_words_does_not_bring_the_music_up():
    d = speechy(8.0, on=.5, off=.3)               # short gaps, as between words
    gdb = 20 * np.log10(mix.duck_curve(d, 11.0))
    assert gdb[int(1.0 * R):int(7.0 * R)].max() < -10.5


def test_an_equal_power_crossfade_keeps_two_beds_at_the_same_level():
    n = 6 * R
    a = dsp.noise(n, np.random.default_rng(6))[:, None] * np.ones((1, 2)) * .1
    b = dsp.noise(n, np.random.default_rng(7))[:, None] * np.ones((1, 2)) * .1
    k = R
    out = np.concatenate([a[:3 * R - k // 2], a[3 * R - k // 2:3 * R + k // 2] * dsp.fade_out(k)[:, None]
                          + b[3 * R - k // 2:3 * R + k // 2] * dsp.fade_in(k)[:, None], b[3 * R + k // 2:]])
    w = int(.1 * R)
    lev = [20 * math.log10(np.sqrt(np.mean(out[i:i + w] ** 2))) for i in range(0, len(out) - w, w)]
    assert max(lev) - min(lev) < 1.2


def test_ambience_crosses_from_one_place_to_the_next_without_a_hole():
    n = 8 * R
    scenes = [mix.SceneMix(id="a", start=0, length=4 * R, room=ambience.ROOMS["office"], bed="office"),
              mix.SceneMix(id="b", start=4 * R, length=4 * R, room=ambience.ROOMS["cafe"], bed="cafe")]
    amb = mix.ambience_bus(scenes, n, -20.0, 0.0)
    w = int(.1 * R)
    lev = np.array([20 * math.log10(np.sqrt(np.mean(amb[i:i + w] ** 2)) + 1e-12) for i in range(0, n - w, w)])
    around_cut = lev[int(3.6 * 10):int(5.2 * 10)]
    assert around_cut.min() > min(lev[5:30].mean(), lev[55:75].mean()) - 3      # no dip into silence at the cut


# ---------------------------------------------------------------- events and placement
def test_a_sound_lands_on_the_drawing_that_first_shows_its_cause():
    beats = [(0, 20), (20, 30)]
    assert events.snap_to_drawings(7, beats) == 8           # on twos: the drawing at 8 is the first after frame 7
    assert events.snap_to_drawings(8, beats) == 8
    assert events.snap_to_drawings(19, beats) == 20         # past the beat's last drawing: the next beat's first
    assert events.snap_to_drawings(21, beats) == 22


def test_an_effect_is_placed_on_its_exact_sample():
    n = 3 * R
    e = Event(kind="laptop_close", t=1.234, scene="s")
    sc = mix.SceneMix(id="s", start=0, length=n, events=[e])
    rep = mix.MixReport()
    fx = mix.effects_bus([sc], n, Kit(), rep)
    on = int(np.argmax(np.abs(fx[:, 0]) > 1e-6))
    assert on == round(1.234 * R) or abs(on - round(1.234 * R)) <= 2       # the onset, not a frame early or late
    assert rep.events == 1 and rep.sources == {"made by code": 1}


def test_one_action_is_one_sound_and_a_cue_wins_over_the_motion():
    a = Event(kind="door_close", t=2.00, scene="s", thing="door", source="engine")
    b = Event(kind="door_close", t=2.08, scene="s", thing="door", source="cue")
    c = Event(kind="door_close", t=5.0, scene="s", thing="door")
    kept = events.dedupe([a, b, c])
    assert len(kept) == 2 and kept[0].source == "cue"
    steps = [Event(kind="footstep", t=1.0, scene="s", who="ana"), Event(kind="footstep", t=1.05, scene="s", who="ana")]
    assert len(events.dedupe(steps)) == 2                   # quick steps are each a step


def test_event_identities_are_stable():
    a = Event(kind="footstep", t=1.25, scene="s", who="ana", surface="wood")
    assert a.id == Event(kind="footstep", t=1.25, scene="s", who="ana", surface="wood").id
    assert a.id != Event(kind="footstep", t=1.30, scene="s", who="ana", surface="wood").id
    assert Event.from_json(json.loads(json.dumps(a.to_json()))) == a


def test_no_two_steps_sound_the_same_and_each_is_made_the_same_way_twice():
    s1 = foley.footstep("wood", seed="a")
    s2 = foley.footstep("wood", seed="b")
    assert not np.allclose(s1[:len(s2)], s2[:len(s1)])
    assert np.array_equal(s1, foley.footstep("wood", seed="a"))
    for surface in foley.FLOORS:
        x = foley.footstep(surface, seed=1)
        assert np.isfinite(x).all() and .5 < np.abs(x).max() <= 1.0


def test_every_sound_the_engine_places_can_be_made():
    kit = Kit()
    for kind in events.KINDS:
        if kind == "file":
            continue
        x, src = kit.clip(Event(kind=kind, t=0.0, scene="s", duration=1.0, surface="wood"))
        assert src == "made by code" and len(x) > 0 and np.isfinite(x).all() and np.abs(x).max() > .05, kind


def test_your_own_recordings_come_first_and_never_repeat_a_step(tmp_path):
    folder = tmp_path / "sounds" / "footstep" / "wood"
    folder.mkdir(parents=True)
    for i in range(3):
        click = np.zeros(int(.3 * R))
        click[int(.05 * R) + i * 10] = .8                     # each file a little different, with silence before it
        with wave.open(str(folder / f"step{i}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(R)
            w.writeframes((click * 32767).astype("<i2").tobytes())
    if not HAS_FFMPEG:
        pytest.skip("needs FFmpeg to read the recordings")
    kit = Kit([tmp_path / "sounds"])
    used = []
    for i in range(8):
        x, src = kit.clip(Event(kind="footstep", t=i * .5, scene="s", who="ana", surface="wood"))
        used.append(src)
        assert src.startswith("file:step") and np.argmax(np.abs(x)) < int(.01 * R)     # trimmed to its onset
    assert all(a != b for a, b in zip(used, used[1:], strict=False))
    x, src = kit.clip(Event(kind="door_close", t=0, scene="s"))
    assert src == "made by code"                              # nothing recorded for it: made by code


# ---------------------------------------------------------------- the mix and the master
def _film(seconds=12.0, music=None, scenes=None, cues=()):
    d = speechy(seconds)
    sc = scenes or [mix.SceneMix(id="s", start=0, length=len(d), room=ambience.ROOMS["office"], bed="office",
                                 events=[Event(kind="footstep", t=1.0 + i * .55, scene="s", who="ana", surface="wood")
                                         for i in range(6)])]
    return mix.mix(d, sc, list(cues), mix.Levels(), Kit())


def test_the_mix_is_dialogue_first_and_the_same_every_time():
    out1, buses, rep = _film()
    out2, _b, _r = _film()
    assert np.array_equal(out1, out2)
    assert rep.events == 6
    assert np.array_equal(buses["dialogue"][:, 0], speechy(12.0))                 # the dialogue itself is untouched
    assert rep.stems["ambience"] < rep.stems["dialogue"] - 20                       # the air sits well under the voices


def test_mastering_reaches_the_target_or_says_why():
    out, _b, _r = _film()
    y, info = master.master(out, master.Target())
    assert meter.integrated(y) == pytest.approx(-16.0, abs=.15)
    assert dsp.true_peak_db(y) <= -1.5 - master.codec_margin(192) + .02
    assert not info.get("warning")
    # a mix whose peaks sit far above its loudness: reaching the target would take heavy limiting, and it is said
    spiky = np.zeros((10 * R, 2))
    spiky[::R] = .99
    spiky += speechy(10.0, level_db=-55)[:, None]
    _y, info = master.master(spiky, master.Target())
    assert "limiting" in info.get("warning", "")


def test_a_silent_film_stays_silent():
    y, info = master.master(np.zeros((4 * R, 2)), master.Target())
    assert info["silent"] and not y.any()


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_music_of_any_rate_and_layout_is_matched_looped_and_faded(tmp_path):
    # a 44.1 kHz mono track, three seconds long, under a twelve-second film: looped, faded in and out
    t = np.arange(int(3 * 44100)) / 44100
    tone = .5 * np.sin(2 * math.pi * 220 * t) * (1 + .3 * np.sin(2 * math.pi * 1.5 * t))
    p = tmp_path / "theme.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes((tone * 32767).astype("<i2").tobytes())
    mp3 = tmp_path / "theme.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), str(mp3)], check=True)
    for f in (p, mp3):
        x = decode(f)
        assert x.shape[1] == 2 and abs(len(x) - 3 * R) < .06 * R
    d = speechy(12.0, on=1.0, off=4.0)
    cue = mix.MusicCue(file=mp3, fade_in=1.0, fade_out=2.0)
    out, buses, rep = mix.mix(d, [mix.SceneMix(id="s", start=0, length=len(d))], [cue], mix.Levels(), Kit())
    m = buses["music"][:, 0]
    w = int(.1 * R)
    lev = np.array([np.sqrt(np.mean(m[i:i + w] ** 2)) for i in range(0, len(m) - w, w)])
    assert lev[0] < lev[15] / 3                           # faded in
    assert lev[-1] < lev[-25] / 3                         # faded out at the end of the film
    assert (lev[10:-25] > 0).all()                        # never a hole where the track loops
    assert rep.music[0]["loop"] and rep.music[0]["lufs"] is not None


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_a_bad_sound_file_is_named_not_mixed(tmp_path):
    bad = tmp_path / "broken.wav"
    bad.write_bytes(b"RIFF\x00\x00\x00\x00WAVEnot really audio" * 10)
    with pytest.raises(SoundFileError, match="broken.wav"):
        decode(bad)
    with pytest.raises(SoundFileError, match="no such file"):
        decode(tmp_path / "missing.wav")


# ---------------------------------------------------------------- whole films
def _project(tmp_path, music: bool = True, extra_scene: str = "") -> Path:
    """A two-scene film with recorded (synthetic) voices, so the dialogue is audible, and optionally a music track."""
    root = write_project(tmp_path / "p")
    t = (root / "studio.yaml").read_text("utf-8")
    t = t.replace("voice: { provider: offline, settings: { rate: 200 } }", "voice: { provider: recorded }")
    t = t.replace("voice: { provider: offline  }", "voice: { provider: recorded }")
    t = t.replace("    offline: { engine: silence }", "    offline: { engine: silence }\n    recorded: {}")
    if music:
        t += "sound:\n  music:\n    - { file: music/theme.wav, fade_in: 1.0, fade_out: 1.5 }\n"
    t += extra_scene
    (root / "studio.yaml").write_text(t, "utf-8")
    rec = root / "recordings" / "en-IN"
    rec.mkdir(parents=True)
    for i, lid in enumerate(("l1", "l2", "l4")):
        x = speechy(2.2, on=2.2, off=.1, level_db=-24, seed=10 + i)
        with wave.open(str(rec / f"{lid}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(R)
            w.writeframes((x * 32767).astype("<i2").tobytes())
    (root / "music").mkdir()
    tt = np.arange(int(5 * R)) / R
    tone = .3 * np.sin(2 * math.pi * 196 * tt) * (1 + .4 * np.sin(2 * math.pi * .5 * tt))
    master.write_wav(root / "music" / "theme.wav", np.stack([tone, tone], 1))
    return root


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_the_encoded_film_measures_what_its_manifest_says_and_meets_its_targets(tmp_path):
    from sastudio.build import build
    from sastudio.project import load_project

    root = _project(tmp_path)
    res = build(load_project(root), log=lambda *_: None)
    man = json.loads(res.manifest.read_text("utf-8"))
    a = man["audio"]
    assert a["verdict"]["met"], a["verdict"]["said"]
    m = master.measure(res.video)
    assert m["lufs"] == pytest.approx(a["measured"]["lufs"], abs=.05)
    assert m["lufs"] == pytest.approx(-16.0, abs=1.0) and m["true_peak"] <= -1.5
    assert a["mix"]["music"] and a["mix"]["stems"]["music"] < a["mix"]["stems"]["dialogue"] - 6


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_changing_only_the_sound_renders_no_scene_again(tmp_path):
    from sastudio.build import build
    from sastudio.project import load_project

    root = _project(tmp_path)
    first = build(load_project(root), log=lambda *_: None)
    a1 = master.measure(first.video)
    y = root / "studio.yaml"
    y.write_text(y.read_text("utf-8").replace("fade_in: 1.0, fade_out: 1.5 }", "fade_in: 1.0, fade_out: 1.5, volume_db: -6 }"), "utf-8")
    second = build(load_project(root), log=lambda *_: None)
    assert not second.rendered and second.reused                           # every scene reused
    man = json.loads(second.manifest.read_text("utf-8"))
    assert man["audio"]["verdict"]["met"]
    assert master.measure(second.video) != a1                               # and the sound did change


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_a_cue_plays_at_its_line_and_a_scene_can_ask_for_quiet(tmp_path):
    from sastudio.build import build
    from sastudio.project import load_project

    root = _project(tmp_path, music=True)
    y = root / "studio.yaml"
    t = y.read_text("utf-8")
    t = t.replace('  - id: one\n    title: "Scene One"\n',
                  '  - id: one\n    title: "Scene One"\n    direction:\n      sound:\n        music: off\n'
                  '        cues:\n          - { sound: phone_ring, line: l1, at: 0, offset: -0.5, seconds: 2 }\n', 1)
    y.write_text(t, "utf-8")
    res = build(load_project(root), log=lambda *_: None)
    placed = json.loads((root / ".studio" / "work" / "en-IN" / "sound_events.json").read_text("utf-8"))
    rings = [e for e in placed if e["kind"] == "phone_ring"]
    assert len(rings) == 1 and rings[0]["source"] == "cue" and rings[0]["scene"] == "one"
    assert json.loads(res.manifest.read_text("utf-8"))["audio"]["verdict"]["met"]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_a_project_without_any_sound_settings_still_builds_a_mastered_film(tmp_path):
    from sastudio.build import build
    from sastudio.project import load_project

    root = _project(tmp_path, music=False)
    res = build(load_project(root), log=lambda *_: None)
    a = json.loads(res.manifest.read_text("utf-8"))["audio"]
    assert a["verdict"]["met"] and not a["mix"]["music"]


def test_wav_files_are_written_whole(tmp_path):
    p = tmp_path / "a.wav"
    master.write_wav(p, np.zeros((R, 2)))
    with wave.open(str(p)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (2, 3, R, R)
    assert not list(tmp_path.glob("*.part"))
    shutil.rmtree(tmp_path)
