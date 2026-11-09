"""ElevenLabs text-to-speech.

Contract taken from elevenlabs.io/docs (create speech API reference, models, best practices,
errors; read 2026-11-09): POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
?output_format=..., header `xi-api-key`, JSON body with `text`, `model_id`, optional
`language_code`, `voice_settings`, `pronunciation_dictionary_locators` (max 3), `seed`,
`apply_text_normalization`. The response body is the audio file.
"""

from __future__ import annotations

import json
import re
from html import escape
from importlib import resources
from urllib.parse import quote

from ..errors import ProviderError
from .base import Audio, PreparedRequest, Provider, check_wav, json_body, parse_json, pcm_to_wav, sniff_audio
from .common import spoken_text

BASE = "https://api.elevenlabs.io/v1/text-to-speech/"
_CATALOG = None
_VOICE_ID = re.compile(r"^[A-Za-z0-9]{8,40}$")
VOICE_SETTING_KEYS = {"stability", "similarity_boost", "style", "use_speaker_boost", "speed"}
OTHER_KEYS = {"seed", "apply_text_normalization"}


def catalog() -> dict:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = json.loads(resources.files("sastudio.data").joinpath("elevenlabs.json").read_text("utf-8"))
    return _CATALOG


class ElevenLabsProvider(Provider):
    name = "elevenlabs"
    key_env = "ELEVENLABS_API_KEY"

    @property
    def output_format(self) -> str:
        return self.config.get("output_format", "wav_24000")

    @property
    def dictionaries(self) -> list[dict]:
        return list(self.config.get("pronunciation_dictionaries") or [])

    def validate(self, spec, lang):
        cat = catalog()
        out = []
        model = spec.model or "eleven_multilingual_v2"
        info = cat["models"].get(model)
        if info is None and not self.config.get("allow_unlisted_model"):
            out.append((f"ElevenLabs model '{model}' is not in this tool's model list (checked {cat['checked']}).",
                        f"Use one of {', '.join(m for m, i in cat['models'].items() if not i.get('deprecated'))}, "
                        "or set voices.providers.elevenlabs.allow_unlisted_model: true."))
        if info and info.get("deprecated"):
            out.append((f"ElevenLabs lists '{model}' as deprecated.", f"Switch: {info['deprecated']}."))
        if info and info.get("english_only") and not lang.startswith("en"):
            out.append((f"'{model}' only speaks English, but this line is {lang}.", "Use eleven_multilingual_v2 or eleven_v3."))
        if info and lang.startswith("hi") and not info.get("hindi"):
            out.append((f"'{model}' does not list Hindi.", "Use eleven_multilingual_v2, eleven_v3 or eleven_flash_v2_5."))
        if not spec.voice_id:
            out.append(("An ElevenLabs voice needs `voice_id`.", "Copy the voice ID from your ElevenLabs voice library."))
        elif not _VOICE_ID.match(spec.voice_id):
            out.append((f"'{spec.voice_id}' does not look like an ElevenLabs voice ID.", "Voice IDs are letters and digits only."))
        ranges = cat["voice_settings"]
        for k, v in spec.settings.items():
            if k in VOICE_SETTING_KEYS:
                rng = ranges[k]
                if rng == "bool":
                    if not isinstance(v, bool):
                        out.append((f"{k} must be true or false.", None))
                elif not (isinstance(v, (int, float)) and not isinstance(v, bool) and rng[0] <= v <= rng[1]):
                    out.append((f"{k}={v!r} is outside {rng[0]}..{rng[1]}.", None))
            elif k == "seed":
                if not (isinstance(v, int) and 0 <= v <= 4294967295):
                    out.append(("seed must be a whole number from 0 to 4294967295.", None))
            elif k == "apply_text_normalization":
                if v not in ("auto", "on", "off"):
                    out.append(("apply_text_normalization must be auto, on or off.", None))
            else:
                out.append((f"Unknown ElevenLabs setting '{k}'.",
                            f"Known: {', '.join(sorted(VOICE_SETTING_KEYS | OTHER_KEYS))}."))
        if self.output_format not in cat["output_formats"]:
            out.append((f"output_format '{self.output_format}' is not supported.", "Use wav_24000 (default) or pcm_24000."))
        if len(self.dictionaries) > cat["max_dictionaries"]:
            out.append((f"ElevenLabs accepts at most {cat['max_dictionaries']} pronunciation dictionaries per request.", None))
        for d in self.dictionaries:
            if not isinstance(d, dict) or not d.get("id"):
                out.append(("Each pronunciation dictionary needs an `id` (and optionally `version_id`).", None))
        return out

    def _phoneme_ok(self, model: str) -> bool:
        info = catalog()["models"].get(model) or {}
        return bool(info.get("phoneme_tags"))

    def prepare(self, utt, spec, rules):
        model = spec.model or "eleven_multilingual_v2"
        use_tags = self._phoneme_ok(model)

        def hook(seg, hint):
            if not hint:
                return None
            if use_tags and hint.get("ipa"):
                return f'<phoneme alphabet="ipa" ph="{escape(hint["ipa"], quote=True)}">{escape(seg.spoken)}</phoneme>'
            if use_tags and hint.get("cmu"):
                return f'<phoneme alphabet="cmu-arpabet" ph="{escape(hint["cmu"], quote=True)}">{escape(seg.spoken)}</phoneme>'
            if hint.get("alias"):
                return hint["alias"]
            return None

        text = utt.override or spoken_text(utt.resolved, self.name, rules, name_hook=hook)
        info = catalog()["models"].get(model) or {}
        limit = info.get("max_characters")
        if limit and len(text) > limit:
            raise ProviderError(f"Line {utt.line_id} is {len(text)} characters; {model} accepts {limit}.",
                                "Split the line into two lines.")
        vs = {k: v for k, v in spec.settings.items() if k in VOICE_SETTING_KEYS}
        fields = {"voice_id": spec.voice_id, "model_id": model, "output_format": self.output_format}
        if vs:
            fields["voice_settings"] = dict(sorted(vs.items()))
        if info.get("language_code", True):
            fields["language_code"] = utt.language.split("-")[0]
        for k in OTHER_KEYS:
            if k in spec.settings:
                fields[k] = spec.settings[k]
        if self.dictionaries:
            fields["pronunciation_dictionary_locators"] = [
                {"pronunciation_dictionary_id": d["id"], **({"version_id": d["version_id"]} if d.get("version_id") else {})}
                for d in self.dictionaries
            ]
        return PreparedRequest(self.name, text, fields, characters=len(text))

    def synthesize(self, req: PreparedRequest, *, key, transport, timeout) -> Audio:
        if not key:
            raise ProviderError("ELEVENLABS_API_KEY is not set.", "Add it to your .env file (see docs/API_SETUP.md).")
        f = dict(req.fields)
        voice_id = f.pop("voice_id")
        fmt = f.pop("output_format")
        url = f"{BASE}{quote(voice_id, safe='')}?output_format={quote(fmt, safe='')}"
        body = {"text": req.text, **f}
        resp = transport("POST", url, {"xi-api-key": key, "Content-Type": "application/json",
                                       "Accept": "audio/*"}, json_body(body), timeout)
        if resp.status != 200:
            raise map_error(resp.status, resp.body, resp.headers)
        data = resp.body
        if fmt.startswith("pcm_"):
            data = pcm_to_wav(data, int(fmt.split("_")[1]))
        elif sniff_audio(data) == "mp3":
            from ..audio.ffmpeg import decode_to_wav  # needs FFmpeg

            data = decode_to_wav(data)
        check_wav(data)
        return Audio(data, resp.headers.get("request-id"))


def map_error(status: int, body: bytes, headers: dict) -> ProviderError:
    data = parse_json(body)
    code = message = None
    if isinstance(data, dict):
        d = data.get("detail")
        if isinstance(d, dict):
            code = d.get("code") or d.get("status")
            message = d.get("message")
        elif isinstance(d, list) and d:  # 422 validation shape: [{loc, msg, type}]
            message = "; ".join(str(x.get("msg")) for x in d if isinstance(x, dict))[:300]
            code = "validation_error"
        elif isinstance(d, str):
            message = d
    detail = f" ({message})" if message else ""
    if status == 401:
        return ProviderError(f"ElevenLabs rejected the API key{detail}.", "Check ELEVENLABS_API_KEY. Run `sastudio credentials`.",
                             status=status, code=code or "invalid_api_key")
    if status == 402:
        return ProviderError(f"ElevenLabs says the account is out of credits{detail}.",
                             "Top up or upgrade your ElevenLabs plan. Nothing was retried.", status=status,
                             code=code or "insufficient_credits")
    if status == 403:
        return ProviderError(f"ElevenLabs refused access{detail}.", "Your plan or key permissions may not allow this voice/model.",
                             status=status, code=code)
    if status == 404:
        what = "voice" if code == "voice_not_found" else ("model" if code == "model_not_found" else "voice or model")
        return ProviderError(f"ElevenLabs could not find the {what}{detail}.",
                             "Check voice_id and model in studio.yaml. A removed voice must be replaced; it is never swapped silently.",
                             status=status, code=code)
    if status == 429:
        e = ProviderError(f"ElevenLabs rate or concurrency limit{detail}.", "Run again later; finished lines are cached.",
                          retryable=True, status=status, code=code or "rate_limit_exceeded")
        e.retry_after = headers.get("retry-after")
        return e
    if status in (500, 502, 503, 504):
        return ProviderError(f"ElevenLabs service error {status}{detail}.", "Try again later; finished lines are cached.",
                             retryable=True, status=status, code=code)
    if status in (400, 422):
        return ProviderError(f"ElevenLabs refused the request{detail}.", "Run `sastudio validate`; check model, settings and text length.",
                             status=status, code=code)
    return ProviderError(f"ElevenLabs returned HTTP {status}{detail}.", status=status, code=code)
