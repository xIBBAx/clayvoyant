"""Sarvam AI text-to-speech (Bulbul models).

Contract taken from docs.sarvam.ai (text-to-speech API reference, read 2026-11-09):
POST https://api.sarvam.ai/text-to-speech, header `api-subscription-key`, JSON body with
`text`, `language_code`, `model`, `speaker`, optional `pace`, `pitch`/`loudness` (bulbul:v2
only), `temperature` (v3 / v4-flash), `speech_sample_rate`, `output_audio_codec`, `dict_id`.
The response is JSON: {"request_id": ..., "audios": [<base64 WAV>, ...]}.
"""

from __future__ import annotations

import base64
import json
from importlib import resources

from ..errors import ProviderError
from ..text.speech import has_devanagari
from .base import Audio, PreparedRequest, Provider, check_wav, join_wavs, json_body, parse_json
from .common import spoken_text

URL = "https://api.sarvam.ai/text-to-speech"
_CATALOG = None


def catalog() -> dict:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = json.loads(resources.files("sastudio.data").joinpath("sarvam.json").read_text("utf-8"))
    return _CATALOG


SETTING_KEYS = {"pace", "pitch", "loudness", "temperature", "enable_preprocessing", "dict_id"}


class SarvamProvider(Provider):
    name = "sarvam"
    key_env = "SARVAM_API_KEY"

    @property
    def sample_rate(self) -> int:
        return int(self.config.get("sample_rate", 24000))

    def validate(self, spec, lang):
        cat = catalog()
        out = []
        model = spec.model or "bulbul:v3"
        info = cat["models"].get(model)
        if info is None:
            out.append((f"Sarvam model '{model}' is not one of {', '.join(cat['models'])}.",
                        "Use bulbul:v3 or bulbul:v4-flash."))
            return out
        if lang not in cat["languages"]:
            out.append((f"Sarvam does not list language '{lang}'.",
                        f"Supported: {', '.join(cat['languages'])}. Use another provider for this language."))
        if not spec.speaker:
            out.append(("A Sarvam voice needs `speaker`.", f"For {model}, for example: {', '.join(info['speakers'][:5])}."))
        elif spec.speaker not in info["speakers"] and not self.config.get("allow_unlisted"):
            hint = "Speaker names are case-sensitive and belong to one model."
            for other, oinfo in cat["models"].items():
                if spec.speaker in oinfo["speakers"]:
                    hint = f"'{spec.speaker}' is a {other} speaker; set model: {other}."
            out.append((f"'{spec.speaker}' is not a {model} speaker (list checked {cat['checked']}).",
                        hint + " If Sarvam added it recently, set voices.providers.sarvam.allow_unlisted: true."))
        for k, v in spec.settings.items():
            if k not in SETTING_KEYS:
                out.append((f"Unknown Sarvam setting '{k}'.", f"Known: {', '.join(sorted(SETTING_KEYS))}."))
                continue
            rng = info.get(k) if k in ("pace", "pitch", "loudness", "temperature") else "any"
            if rng is None:
                out.append((f"'{k}' is not supported by {model}.", "Remove it, or use bulbul:v2 for pitch/loudness."))
            elif isinstance(rng, list) and not (isinstance(v, (int, float)) and rng[0] <= v <= rng[1]):
                out.append((f"{k}={v!r} is outside {rng[0]}..{rng[1]} for {model}.", None))
        if self.sample_rate not in cat["sample_rates"]:
            out.append((f"Sample rate {self.sample_rate} is not supported.", f"Use one of {cat['sample_rates']}."))
        return out

    def prepare(self, utt, spec, rules):
        model = spec.model or "bulbul:v3"
        text = utt.override or spoken_text(utt.resolved, self.name, rules)
        limit = catalog()["models"][model]["max_characters"]
        if len(text) > limit:
            raise ProviderError(
                f"Line {utt.line_id} is {len(text)} characters; {model} accepts {limit}.",
                "Split the line into two lines.",
            )
        fields = {
            "model": model,
            "speaker": spec.speaker,
            "language_code": utt.language,
            "speech_sample_rate": self.sample_rate,
            "output_audio_codec": "wav",
        }
        for k in ("pace", "pitch", "loudness", "temperature", "enable_preprocessing", "dict_id"):
            if k in spec.settings:
                fields[k] = spec.settings[k]
        return PreparedRequest(self.name, text, fields, characters=len(text))

    def synthesize(self, req: PreparedRequest, *, key, transport, timeout) -> Audio:
        if not key:
            raise ProviderError("SARVAM_API_KEY is not set.", "Add it to your .env file (see docs/API_SETUP.md).")
        body = {"text": req.text, **req.fields}
        resp = transport("POST", URL, {"api-subscription-key": key, "Content-Type": "application/json",
                                       "Accept": "application/json"}, json_body(body), timeout)
        if resp.status != 200:
            raise map_error(resp.status, resp.body, resp.headers)
        data = parse_json(resp.body)
        if not isinstance(data, dict) or not isinstance(data.get("audios"), list) or not data["audios"]:
            raise ProviderError("Sarvam returned a response without audio.", retryable=True, code="empty_audio")
        parts = []
        for chunk in data["audios"]:
            if isinstance(chunk, dict):  # one documentation page shows {"audio": ...}
                chunk = chunk.get("audio", "")
            try:
                parts.append(base64.b64decode(chunk, validate=True))
            except (ValueError, TypeError):
                raise ProviderError("Sarvam returned audio that is not valid base64.", code="corrupt_audio",
                                    retryable=True)
        wav = join_wavs(parts)
        check_wav(wav)
        return Audio(wav, data.get("request_id"))


def map_error(status: int, body: bytes, headers: dict) -> ProviderError:
    data = parse_json(body) or {}
    err = data.get("error") if isinstance(data, dict) else None
    message = (err or {}).get("message") if isinstance(err, dict) else None
    code = (err or {}).get("code") if isinstance(err, dict) else None
    detail = f" ({message})" if message else ""
    if status == 403 or status == 401:
        return ProviderError(f"Sarvam rejected the API key{detail}.",
                             "Check SARVAM_API_KEY in your .env file. Run `sastudio credentials`.",
                             status=status, code=code or "invalid_api_key")
    if status == 402:
        return ProviderError(f"Sarvam says the account has no credits left{detail}.",
                             "Add credits in the Sarvam dashboard. Nothing was retried.", status=status,
                             code=code or "insufficient_quota")
    if status == 429:
        if code == "seat_budget_exhausted_error":
            return ProviderError(f"Sarvam budget exhausted{detail}.", "Check your Sarvam plan.", status=status, code=code)
        e = ProviderError(f"Sarvam rate limit{detail}.", "Wait and run again; finished lines are cached.",
                          retryable=True, status=status, code=code or "rate_limit")
        e.retry_after = headers.get("retry-after")
        return e
    if status in (500, 502, 503, 504):
        return ProviderError(f"Sarvam service error {status}{detail}.", "Try again later; finished lines are cached.",
                             retryable=True, status=status, code=code)
    if status in (400, 422):
        return ProviderError(f"Sarvam refused the request{detail}.",
                             "The model, speaker, language or a setting is not accepted. Run `sastudio validate`.",
                             status=status, code=code)
    return ProviderError(f"Sarvam returned HTTP {status}{detail}.", status=status, code=code)


def advice(text: str, lang: str) -> str | None:
    """Sarvam's documentation recommends writing Hindi in Devanagari, not Roman script."""
    if lang == "hi-IN" and not has_devanagari(text):
        return "Hindi text written in Roman script; Sarvam recommends Devanagari for better pronunciation."
    return None
