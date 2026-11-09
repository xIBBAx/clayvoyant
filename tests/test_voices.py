import base64
import json

import pytest

from sastudio.errors import BudgetExceeded, MissingCredential, ProviderError, StudioError
from sastudio.project import VoiceSpec, load_project
from sastudio.text import template as tpl
from sastudio.text.speech import SpeechRules
from sastudio.voices.base import HttpResponse, RetryPolicy, Utterance
from sastudio.voices.elevenlabs import ElevenLabsProvider
from sastudio.voices.engine import _Lock, build_plan, cache_key, generate, load_env_file
from sastudio.voices.sarvam import SarvamProvider

from .conftest import FakeTransport, ok_wav, wav_bytes, write_project

VOICE = "21m00Tcm4TlvDq8ikWAM"
NO_SLEEP = RetryPolicy(max_retries=2, sleep=lambda s: None)


def utt(text="Hello there.", lang="en-IN"):
    return Utterance("l1", "s1", lang, "ana", tpl.Resolved([tpl.Seg("text", text, text)], lang))


# ------------------------------------------------------------------ Sarvam validation
def test_sarvam_validation():
    p = SarvamProvider({"sample_rate": 24000})
    assert p.validate(VoiceSpec("sarvam", "bulbul:v3", "shubh"), "hi-IN") == []
    msgs = " ".join(m for m, _ in p.validate(VoiceSpec("sarvam", "bulbul:v9", "shubh"), "hi-IN"))
    assert "not one of" in msgs
    issues = p.validate(VoiceSpec("sarvam", "bulbul:v4-flash", "shubh"), "en-IN")
    assert issues and "bulbul:v3 speaker" in (issues[0][1] or "")
    assert p.validate(VoiceSpec("sarvam", "bulbul:v3", "shubh", settings={"pitch": 0.2}), "hi-IN")
    assert p.validate(VoiceSpec("sarvam", "bulbul:v3", "shubh", settings={"pace": 9}), "hi-IN")
    assert p.validate(VoiceSpec("sarvam", "bulbul:v3", "shubh"), "fr-FR")  # unsupported language
    assert SarvamProvider({"allow_unlisted": True}).validate(VoiceSpec("sarvam", "bulbul:v3", "newvoice"), "hi-IN") == []


def test_sarvam_request_and_response():
    p = SarvamProvider()
    req = p.prepare(utt(), VoiceSpec("sarvam", "bulbul:v3", "shubh", settings={"pace": 1.1}), SpeechRules())
    audio_b64 = base64.b64encode(wav_bytes()).decode()
    t = FakeTransport([HttpResponse(200, {}, json.dumps({"request_id": "r9", "audios": [audio_b64, audio_b64]}).encode())])
    a = p.synthesize(req, key="k-secret", transport=t, timeout=5)
    body = json.loads(t.calls[0]["body"])
    assert t.calls[0]["url"] == "https://api.sarvam.ai/text-to-speech"
    assert t.calls[0]["headers"]["api-subscription-key"] == "k-secret"
    assert body == {"text": "Hello there.", "model": "bulbul:v3", "speaker": "shubh", "language_code": "en-IN",
                    "speech_sample_rate": 24000, "output_audio_codec": "wav", "pace": 1.1}
    assert abs(a.duration() - 1.0) < 0.01 and a.request_id == "r9"  # two chunks joined


def test_sarvam_text_limit():
    p = SarvamProvider()
    with pytest.raises(ProviderError):
        p.prepare(utt("x" * 1600), VoiceSpec("sarvam", "bulbul:v2", "anushka"), SpeechRules())


@pytest.mark.parametrize("status,body,retry,code", [
    (403, {"error": {"message": "bad key", "code": "invalid_api_key_error"}}, False, "invalid_api_key_error"),
    (402, {"error": {"message": "No credits"}}, False, "insufficient_quota"),
    (429, {"error": {"message": "slow down"}}, True, "rate_limit"),
    (503, {}, True, None),
    (422, {"error": {"message": "too long"}}, False, None),
])
def test_sarvam_errors(status, body, retry, code):
    p = SarvamProvider()
    req = p.prepare(utt(), VoiceSpec("sarvam", "bulbul:v3", "shubh"), SpeechRules())
    t = FakeTransport([HttpResponse(status, {"retry-after": "2"}, json.dumps(body).encode())])
    with pytest.raises(ProviderError) as e:
        p.synthesize(req, key="k", transport=t, timeout=5)
    assert e.value.retryable is retry
    if code:
        assert e.value.code == code


def test_sarvam_empty_and_corrupt_audio():
    p = SarvamProvider()
    req = p.prepare(utt(), VoiceSpec("sarvam", "bulbul:v3", "shubh"), SpeechRules())
    for payload in ({"audios": []}, {"audios": ["!!!not-base64!!!"]}, {"audios": [base64.b64encode(b"RIFF....junk").decode()]}):
        with pytest.raises(ProviderError):
            p.synthesize(req, key="k", transport=FakeTransport([HttpResponse(200, {}, json.dumps(payload).encode())]), timeout=5)


# ------------------------------------------------------------------ ElevenLabs
def test_elevenlabs_validation():
    p = ElevenLabsProvider()
    assert p.validate(VoiceSpec("elevenlabs", "eleven_multilingual_v2", voice_id=VOICE), "hi-IN") == []
    assert p.validate(VoiceSpec("elevenlabs", "eleven_flash_v2", voice_id=VOICE), "hi-IN")  # English only
    assert p.validate(VoiceSpec("elevenlabs", "eleven_turbo_v2_5", voice_id=VOICE), "en-IN")  # deprecated
    assert p.validate(VoiceSpec("elevenlabs", "eleven_v3", voice_id="bad id!"), "en-IN")
    assert p.validate(VoiceSpec("elevenlabs", "eleven_v3", voice_id=VOICE, settings={"stability": 2}), "en-IN")
    assert p.validate(VoiceSpec("elevenlabs", "eleven_v3", voice_id=VOICE, settings={"speed": 1.5}), "en-IN")
    assert p.validate(VoiceSpec("elevenlabs", "made_up_model", voice_id=VOICE), "en-IN")
    many = ElevenLabsProvider({"pronunciation_dictionaries": [{"id": str(i)} for i in range(4)]})
    assert many.validate(VoiceSpec("elevenlabs", "eleven_v3", voice_id=VOICE), "en-IN")


def test_elevenlabs_request_shape():
    p = ElevenLabsProvider({"pronunciation_dictionaries": [{"id": "dict1", "version_id": "v2"}]})
    spec = VoiceSpec("elevenlabs", "eleven_multilingual_v2", voice_id=VOICE, settings={"stability": 0.4, "seed": 7})
    req = p.prepare(utt(), spec, SpeechRules())
    assert "language_code" not in req.fields  # not supported by multilingual_v2
    t = FakeTransport([ok_wav()])
    p.synthesize(req, key="xi-secret", transport=t, timeout=5)
    call = t.calls[0]
    assert call["url"] == f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}?output_format=wav_24000"
    assert call["headers"]["xi-api-key"] == "xi-secret"
    body = json.loads(call["body"])
    assert body["model_id"] == "eleven_multilingual_v2" and body["seed"] == 7
    assert body["voice_settings"] == {"stability": 0.4}
    assert body["pronunciation_dictionary_locators"] == [{"pronunciation_dictionary_id": "dict1", "version_id": "v2"}]
    req3 = p.prepare(utt(lang="hi-IN"), VoiceSpec("elevenlabs", "eleven_v3", voice_id=VOICE), SpeechRules())
    assert req3.fields["language_code"] == "hi"


def test_elevenlabs_phoneme_only_where_supported():
    c = tpl.TextContext({"x": tpl.CharacterText("x", "Aarav", pronunciation={"elevenlabs": {"ipa": "ˈɑːrəv", "alias": "Aa-ruv"}})},
                        tpl.OrgText(fields={}), lambda a, lang: a, lambda u, lang: u)
    r = tpl.resolve("Hi {x}", c, "en-US")
    u = Utterance("l", "s", "en-US", "x", r)
    flash = ElevenLabsProvider().prepare(u, VoiceSpec("elevenlabs", "eleven_flash_v2", voice_id=VOICE), SpeechRules())
    assert '<phoneme alphabet="ipa" ph="ˈɑːrəv">Aarav</phoneme>' in flash.text
    multi = ElevenLabsProvider().prepare(u, VoiceSpec("elevenlabs", "eleven_multilingual_v2", voice_id=VOICE), SpeechRules())
    assert multi.text == "Hi Aa-ruv"


def test_elevenlabs_pcm_is_wrapped():
    p = ElevenLabsProvider({"output_format": "pcm_16000"})
    req = p.prepare(utt(), VoiceSpec("elevenlabs", "eleven_v3", voice_id=VOICE), SpeechRules())
    a = p.synthesize(req, key="k", transport=FakeTransport([HttpResponse(200, {}, b"\x01\x00" * 16000)]), timeout=5)
    assert abs(a.duration() - 1.0) < 0.01


@pytest.mark.parametrize("status,body,retry,needle", [
    (401, {"detail": {"code": "invalid_api_key", "message": "Invalid"}}, False, "rejected the API key"),
    (402, {"detail": {"code": "insufficient_credits"}}, False, "out of credits"),
    (404, {"detail": {"code": "voice_not_found"}}, False, "could not find the voice"),
    (404, {"detail": {"code": "model_not_found"}}, False, "could not find the model"),
    (422, {"detail": [{"loc": ["body", "text"], "msg": "field required", "type": "missing"}]}, False, "field required"),
    (429, {"detail": {"code": "concurrent_limit_exceeded"}}, True, "limit"),
    (500, {}, True, "service error"),
])
def test_elevenlabs_errors(status, body, retry, needle):
    p = ElevenLabsProvider()
    req = p.prepare(utt(), VoiceSpec("elevenlabs", "eleven_v3", voice_id=VOICE), SpeechRules())
    with pytest.raises(ProviderError) as e:
        p.synthesize(req, key="k", transport=FakeTransport([HttpResponse(status, {}, json.dumps(body).encode())]), timeout=5)
    assert e.value.retryable is retry and needle in e.value.message


# ------------------------------------------------------------------ generation engine
def paid_project(tmp_path, budget=1000):
    return load_project(write_project(tmp_path / "p", dev_provider="sarvam",
                                      dev_extra=', model: "bulbul:v3", speaker: shubh', budget=budget))


def test_dry_run_never_calls_paid_provider(tmp_path):
    p = paid_project(tmp_path)
    plan = build_plan(p)
    t = FakeTransport([ok_wav()])
    rep = generate(p, plan, live=False, transport=t, env={"SARVAM_API_KEY": "k"}, log=lambda m: None)
    assert t.calls == [] and rep.skipped_paid == 1 and rep.generated == 2  # two free offline lines


def test_live_needs_budget_and_key(tmp_path):
    p = paid_project(tmp_path, budget=0)
    with pytest.raises(BudgetExceeded):
        generate(p, build_plan(p), live=True, transport=FakeTransport([ok_wav()]), env={"SARVAM_API_KEY": "k"}, log=lambda m: None)
    p = paid_project(tmp_path / "b", budget=1000)
    with pytest.raises(MissingCredential):
        generate(p, build_plan(p), live=True, transport=FakeTransport([ok_wav()]), env={}, log=lambda m: None)


def test_budget_stops_before_overspend(tmp_path):
    p = paid_project(tmp_path)
    plan = build_plan(p)
    with pytest.raises(BudgetExceeded):
        generate(p, plan, live=True, max_characters=5, transport=FakeTransport([ok_wav()]),
                 env={"SARVAM_API_KEY": "k"}, log=lambda m: None)


def test_live_generation_caches_and_is_idempotent(tmp_path):
    p = paid_project(tmp_path)
    t = FakeTransport([HttpResponse(200, {}, json.dumps({"audios": [base64.b64encode(wav_bytes()).decode()]}).encode())])
    rep = generate(p, build_plan(p), live=True, transport=t, env={"SARVAM_API_KEY": "k-secret"}, log=lambda m: None)
    assert len(t.calls) == 1 and rep.characters_billed > 0
    rep2 = generate(p, build_plan(p), live=True, transport=t, env={"SARVAM_API_KEY": "k-secret"}, log=lambda m: None)
    assert len(t.calls) == 1 and rep2.generated == 0  # nothing billed twice
    blob = "".join(f.read_text(errors="ignore") for f in (p.root / ".studio").rglob("*") if f.suffix in (".json", ".jsonl"))
    assert "k-secret" not in blob  # secrets never reach caches or the ledger


def test_retry_then_success_and_no_retry_on_402(tmp_path):
    p = paid_project(tmp_path)
    good = HttpResponse(200, {}, json.dumps({"audios": [base64.b64encode(wav_bytes()).decode()]}).encode())
    t = FakeTransport([HttpResponse(429, {"retry-after": "0"}, b"{}"), good])
    rep = generate(p, build_plan(p), live=True, transport=t, env={"SARVAM_API_KEY": "k"}, retry=NO_SLEEP, log=lambda m: None)
    assert len(t.calls) == 2 and rep.generated >= 1
    p2 = paid_project(tmp_path / "b")
    t2 = FakeTransport([HttpResponse(402, {}, b'{"error":{"message":"No credits"}}'), good])
    with pytest.raises(ProviderError):
        generate(p2, build_plan(p2), live=True, transport=t2, env={"SARVAM_API_KEY": "k"}, retry=NO_SLEEP, log=lambda m: None)
    assert len(t2.calls) == 1


def test_retry_exhaustion(tmp_path):
    p = paid_project(tmp_path)
    t = FakeTransport([HttpResponse(503, {}, b"{}")])
    with pytest.raises(ProviderError):
        generate(p, build_plan(p), live=True, transport=t, env={"SARVAM_API_KEY": "k"}, retry=NO_SLEEP, log=lambda m: None)
    assert len(t.calls) == 3  # first try + 2 retries


def test_timeout_counts_against_budget(tmp_path):
    p = paid_project(tmp_path)
    t = FakeTransport([ProviderError("timed out", retryable=True, code="timeout")])
    with pytest.raises((ProviderError, BudgetExceeded)):
        generate(p, build_plan(p), live=True, transport=t, env={"SARVAM_API_KEY": "k"}, retry=NO_SLEEP, log=lambda m: None)
    ledger = (p.root / ".studio" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(x)["counted"] for x in ledger)


def test_cache_key_rules(tmp_path):
    root = write_project(tmp_path / "p")
    p = load_project(root)
    k1 = {it.utt.line_id: it.key for it in build_plan(p).items}
    # logo change: no audio change
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    t = (root / "studio.yaml").read_text(encoding="utf-8").replace('  name: "Test Org"', '  name: "Test Org"\n  logo: logo.png')
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    assert {it.utt.line_id: it.key for it in build_plan(load_project(root)).items} == k1
    # spoken name change: only lines that say the name change
    t = (root / "studio.yaml").read_text(encoding="utf-8").replace("    name: Dev\n", "    name: Dev\n    spoken: { default: Devv }\n")
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    k2 = {it.utt.line_id: it.key for it in build_plan(load_project(root)).items}
    assert k2["l1"] != k1["l1"] and k2["l4"] != k1["l4"] and k2["l2"] == k1["l2"]


def test_identical_lines_requested_once(tmp_path):
    root = write_project(tmp_path / "p", dev_provider="sarvam", dev_extra=', model: "bulbul:v3", speaker: shubh', budget=500)
    t = (root / "studio.yaml").read_text(encoding="utf-8").replace(
        '      - { id: l4, who: ana, say: "Thanks, {dev}." }',
        '      - { id: l4, who: ana, say: "Thanks, {dev}." }\n      - { id: l5, who: dev, say: "Report to {org.security_email}." }')
    (root / "studio.yaml").write_text(t, encoding="utf-8")
    p = load_project(root)
    tr = FakeTransport([HttpResponse(200, {}, json.dumps({"audios": [base64.b64encode(wav_bytes()).decode()]}).encode())])
    generate(p, build_plan(p), live=True, transport=tr, env={"SARVAM_API_KEY": "k"}, log=lambda m: None)
    assert len(tr.calls) == 1


def test_lock_blocks_concurrent_runs(tmp_path):
    lock = tmp_path / "voices.lock"
    with _Lock(lock):
        with pytest.raises(StudioError):
            with _Lock(lock):
                pass
    assert not lock.exists()


def test_env_file_parsing(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# comment\nexport SARVAM_API_KEY='abc'\nELEVENLABS_API_KEY=\"x y\"\nBAD LINE\n$(rm -rf)=1\n", encoding="utf-8")
    env = load_env_file(f)
    assert env == {"SARVAM_API_KEY": "abc", "ELEVENLABS_API_KEY": "x y"}


def test_cache_key_is_stable():
    from sastudio.voices.base import PreparedRequest

    r = PreparedRequest("sarvam", "hi", {"a": 1, "b": 2}, 2)
    r2 = PreparedRequest("sarvam", "hi", {"b": 2, "a": 1}, 2)
    assert cache_key(r, "en-IN") == cache_key(r2, "en-IN") != cache_key(r, "hi-IN")


def test_streamed_wav_header_is_repaired_and_cache_validation_rejects_lies():
    from sastudio.voices.base import check_wav, repair_wav

    good = wav_bytes(0.5)
    streamed = good[:40] + (0xFFFFFFFF).to_bytes(4, "little") + good[44:]  # header claims 4 GB of audio
    with pytest.raises(ProviderError):
        check_wav(streamed)
    fixed = repair_wav(streamed)
    assert abs(check_wav(fixed) - 0.5) < 0.01
    truncated = good[:2000]  # header says 0.5 s, file holds far less
    with pytest.raises(ProviderError):
        check_wav(truncated)
