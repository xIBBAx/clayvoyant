"""Mouth shapes from words and audio, and the two free voice providers (Kokoro, recorded)."""

import wave

import pytest

from sastudio import lipsync
from sastudio.errors import ProviderError
from sastudio.project import VoiceSpec
from sastudio.voices import kokoro
from sastudio.voices.base import Utterance
from sastudio.voices.registry import PROVIDERS, get_provider


def test_lips_close_on_m_b_p_and_open_on_vowels():
    shapes = [s for s, _ in lipsync.shapes_for_text("map")]
    assert shapes == ["A", "D", "A"]
    assert [s for s, _ in lipsync.shapes_for_text("food")][:2] == ["G", "F"]
    assert lipsync.REST in [s for s, _ in lipsync.shapes_for_text("two words")]


@pytest.mark.parametrize("word", ["নমস্কার", "ਨਮਸਕਾਰ", "નમસ્કાર", "ନମସ୍କାର", "நமஸ்காரம்", "నమస్కారం", "ನಮಸ್ಕಾರ", "നമസ്കാരം"])
def test_every_indian_script_that_shares_devanagari_s_layout_moves_the_mouth(word):
    """'Namaskar' in Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada and Malayalam: a line in any of them
    reads like the Devanagari one: tongue for N, lips closed for M, open for the long A."""
    shapes = [s for s, _ in lipsync.shapes_for_text(word)]
    deva = [s for s, _ in lipsync.shapes_for_text("नमस्कार")]
    assert shapes[:2] == deva[:2] == ["H", "A"] and "D" in shapes


def test_cues_follow_the_voice_and_rest_in_its_pauses():
    env = [0.0] * 3 + [0.6] * 20 + [0.0] * 12 + [0.5] * 20 + [0.0] * 5
    cues = lipsync.cues_from_text("Hello there. Fine morning.", env, 24)
    times = [t for t, _ in cues]
    assert times == sorted(times) and times[0] >= 3 / 24 - 1e-6
    pause = [s for t, s in cues if 22 / 24 <= t < 34 / 24]
    assert lipsync.REST in pause                             # the mouth rests while the voice does
    assert cues[-1][1] == lipsync.REST and cues[-1][0] <= len(env) / 24


def test_silent_placeholder_audio_still_moves_the_mouth():
    cues = lipsync.cues_from_text("Report it to the security team.", [0.0] * 60, 24)
    assert len(cues) > 6 and len({s for _, s in cues}) >= 4


def test_hindi_text_gives_mouth_shapes():
    cues = lipsync.cues_from_text("बधाई हो। किसी competition में हिस्सा लिया था?", [0.5] * 80, 24)
    assert len(cues) > 8 and "A" in {s for _, s in cues}


def test_phoneme_tracks_map_to_the_nine_shapes():
    cues = lipsync.cues_from_phonemes([("m", 0.1, 0.2), ("ɑ", 0.2, 0.4), ("ˈ", 0.4, 0.4), (" ", 0.4, 0.7), ("f", 0.7, 0.8), ("u", 0.8, 1.0)])
    assert [s for _, s in cues] == ["A", "D", "X", "G", "F", "X"]
    assert {s for _, s in cues} <= set("ABCDEFGHX")


# ---------------------------------------------------------------------------------------------- kokoro
def _utt(cid="tara", lang="en-GB"):
    return Utterance("l1", "s1", lang, cid, None, override="Hello.")


def test_free_providers_are_registered_and_cost_nothing():
    for name in ("kokoro", "recorded", "offline"):
        assert name in PROVIDERS and get_provider(name).billable is False and get_provider(name).key_env is None


def test_kokoro_picks_a_steady_voice_that_suits_the_character():
    assert kokoro.default_voice("tara", "en-GB", "feminine")[:2] == "bf"
    assert kokoro.default_voice("bashir", "en-IN", "masculine")[:2] == "bm"   # Indian English is read in a British voice
    assert kokoro.default_voice("asha", "hi-IN", "feminine")[:2] == "hf"
    assert kokoro.default_voice("tara", "en-US", None) == kokoro.default_voice("tara", "en-US", None)


def test_kokoro_request_names_everything_that_changes_the_audio():
    p = get_provider("kokoro", {"_genders": {"tara": "feminine"}})
    req = p.prepare(_utt(), VoiceSpec(provider="kokoro", settings={"speed": 0.9}), None)
    assert req.characters == 0 and req.fields["model"] == kokoro.MODEL and req.fields["speed"] == 0.9
    assert req.fields["voice"][:2] == "bf" and req.fields["accent"] == "en-GB"
    us = p.prepare(_utt(), VoiceSpec(provider="kokoro", speaker="am_michael"), None)
    assert us.fields["accent"] == "en-US"                      # an American voice reads with American sounds
    assert "_genders" not in req.cache_payload()


def test_kokoro_validation_and_missing_model(tmp_path, monkeypatch):
    p = get_provider("kokoro")
    assert p.validate(VoiceSpec(provider="kokoro", speaker="bf_emma"), "en-GB") == []
    assert p.validate(VoiceSpec(provider="kokoro", speaker="nobody"), "en-GB")
    assert p.validate(VoiceSpec(provider="kokoro"), "ta-IN")       # not a language this adapter was tested in
    assert p.validate(VoiceSpec(provider="kokoro", settings={"speed": 9}), "en-GB")
    monkeypatch.setenv("SASTUDIO_KOKORO_DIR", str(tmp_path))
    monkeypatch.setattr(kokoro, "_engine", None)
    assert not kokoro.installed()
    req = p.prepare(_utt(), VoiceSpec(provider="kokoro"), None)
    with pytest.raises(ProviderError) as e:
        p.synthesize(req, key=None, transport=None, timeout=5)
    assert "sastudio voices install kokoro" in (e.value.hint or "") or "kokoro-onnx" in e.value.message


def test_kokoro_model_files_are_pinned_by_checksum():
    for name, (url, sha, size) in kokoro.FILES.items():
        assert url.startswith("https://") and url.endswith(name) and len(sha) == 64 and size > 1_000_000


# ---------------------------------------------------------------------------------------------- recorded
def test_recorded_voice_names_the_missing_file(tmp_path):
    p = get_provider("recorded", {"_project_root": str(tmp_path)})
    req = p.prepare(_utt(), VoiceSpec(provider="recorded"), None)
    with pytest.raises(ProviderError) as e:
        p.synthesize(req, key=None, transport=None, timeout=5)
    assert "recordings/en-GB/l1.wav" in e.value.hint


@pytest.mark.ffmpeg
def test_recorded_voice_reads_your_file_and_notices_when_it_changes(tmp_path):
    d = tmp_path / "recordings" / "en-GB"
    d.mkdir(parents=True)

    def write(seconds):
        with wave.open(str(d / "l1.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(b"\x10\x20" * int(22050 * seconds))
    write(0.5)
    p = get_provider("recorded", {"_project_root": str(tmp_path)})
    a = p.prepare(_utt(), VoiceSpec(provider="recorded"), None)
    audio = p.synthesize(a, key=None, transport=None, timeout=5)
    assert 0.4 < audio.duration() < 0.6
    write(0.8)
    b = p.prepare(_utt(), VoiceSpec(provider="recorded"), None)
    assert a.fields["sha"] != b.fields["sha"]                   # a new take is a new cache entry


def test_recorded_folder_cannot_leave_the_project(tmp_path):
    from sastudio.errors import StudioError

    p = get_provider("recorded", {"_project_root": str(tmp_path), "folder": "../elsewhere"})
    with pytest.raises(StudioError):
        p.prepare(_utt(), VoiceSpec(provider="recorded"), None)
