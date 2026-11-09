"""Speech provider interface.

A provider turns one utterance (spoken text + voice + language) into audio bytes. Providers do
not share parameters: each one validates its own settings against its own documented limits
before any request is sent, so a mistake costs nothing.
"""

from __future__ import annotations

import io
import json
import random
import time
import urllib.error
import urllib.request
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..errors import ProviderError
from ..text.template import Resolved

ADAPTER_VERSION = "1"  # bump when a change alters the audio a provider would return


# --------------------------------------------------------------------------- HTTP
@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class Transport(Protocol):
    def __call__(self, method: str, url: str, headers: dict[str, str], body: bytes | None,
                 timeout: float) -> HttpResponse: ...


def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None,
                     timeout: float) -> HttpResponse:
    """Default transport (standard library only). HTTPS with certificate checks."""
    if not url.startswith("https://"):
        raise ProviderError(f"Refusing a non-HTTPS request to {url.split('?')[0]}.")
    req = urllib.request.Request(url, data=body, method=method, headers=headers)  # noqa: S310 - https only
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - only https:// reaches here (checked above)
            return HttpResponse(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(50_000_000))
    except urllib.error.HTTPError as e:
        return HttpResponse(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read(1_000_000))
    except urllib.error.URLError as e:
        raise ProviderError(f"Network error: {e.reason}", "Check your connection and try again.", retryable=True)
    except TimeoutError:
        raise ProviderError("The request timed out.", "Try again, or raise voices.budget.timeout_seconds.",
                            retryable=True, code="timeout")


# --------------------------------------------------------------------------- audio
@dataclass
class Audio:
    data: bytes  # always a WAV file
    request_id: str | None = None

    def duration(self) -> float:
        with wave.open(io.BytesIO(self.data)) as w:
            return w.getnframes() / float(w.getframerate())


def pcm_to_wav(pcm: bytes, rate: int, channels: int = 1, width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def join_wavs(parts: list[bytes]) -> bytes:
    """Concatenate WAV files with identical formats into one WAV file."""
    if len(parts) == 1:
        return parts[0]
    frames, params = [], None
    for p in parts:
        with wave.open(io.BytesIO(p)) as w:
            cur = (w.getnchannels(), w.getsampwidth(), w.getframerate())
            if params is None:
                params = cur
            elif cur != params:
                raise ProviderError("The provider returned audio chunks in different formats.")
            frames.append(w.readframes(w.getnframes()))
    nch, width, rate = params
    return pcm_to_wav(b"".join(frames), rate, nch, width)


def sniff_audio(data: bytes) -> str:
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "mp3"
    if data[:4] == b"OggS":
        return "ogg"
    if data[:4] == b"fLaC":
        return "flac"
    return "unknown"


def repair_wav(data: bytes) -> bytes:
    """Rewrite a WAV header from the bytes actually present.

    Programs that stream WAV to a pipe (espeak-ng --stdout, some APIs) cannot go back and fill
    in the length, so the header claims a huge or zero size. Only PCM is repaired.
    """
    if sniff_audio(data) != "wav":
        return data
    pos, fmt, payload = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], int.from_bytes(data[pos + 4:pos + 8], "little")
        body = pos + 8
        if cid == b"fmt " and size >= 16:
            fmt = data[body:body + 16]
        if cid == b"data":
            end = len(data) if size in (0, 0xFFFFFFFF) or body + size > len(data) else body + size
            payload = data[body:end]
            break
        pos = body + size + (size & 1)
    if fmt is None or payload is None or int.from_bytes(fmt[0:2], "little") != 1:
        return data
    channels = int.from_bytes(fmt[2:4], "little")
    rate = int.from_bytes(fmt[4:8], "little")
    width = int.from_bytes(fmt[14:16], "little") // 8
    block = max(1, channels * width)
    payload = payload[: len(payload) - len(payload) % block]
    return pcm_to_wav(payload, rate, channels, width)


def check_wav(data: bytes, min_seconds: float = 0.05) -> float:
    """Raise ProviderError unless `data` is a readable, non-empty WAV. Returns its duration."""
    if not data:
        raise ProviderError("The provider returned empty audio.", retryable=True, code="empty_audio")
    if sniff_audio(data) != "wav":
        raise ProviderError("The provider returned audio that is not a WAV file.", code="bad_audio")
    try:
        with wave.open(io.BytesIO(data)) as w:
            n, rate = w.getnframes(), w.getframerate()
            needed = n * w.getnchannels() * w.getsampwidth()
        if needed > len(data):
            raise ProviderError("The audio file is shorter than its header says (truncated or streamed).",
                                retryable=True, code="corrupt_audio")
    except (wave.Error, EOFError) as e:
        raise ProviderError(f"The provider returned corrupted audio ({e}).", retryable=True, code="corrupt_audio")
    if rate <= 0 or n / rate < min_seconds:
        raise ProviderError("The provider returned audio that is too short to be speech.", retryable=True,
                            code="empty_audio")
    return n / rate


# --------------------------------------------------------------------------- provider
@dataclass
class Utterance:
    """One line in one language, ready for a provider."""

    line_id: str
    scene_id: str
    language: str
    character_id: str
    resolved: Resolved
    override: str | None = None  # exact spoken text from the project file, if any


@dataclass
class PreparedRequest:
    provider: str
    text: str  # exactly what the provider will be asked to say
    fields: dict[str, Any]  # every non-secret input that changes the audio
    characters: int  # billable characters

    def cache_payload(self) -> dict[str, Any]:
        return {"adapter": ADAPTER_VERSION, "provider": self.provider, "text": self.text, **self.fields}


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.5
    max_delay: float = 30.0
    sleep: Callable[[float], None] = time.sleep

    def delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.max_delay)
            except ValueError:
                pass
        return min(self.max_delay, self.base_delay * (2 ** attempt)) * (0.75 + random.random() * 0.5)


class Provider:
    name = "base"
    key_env: str | None = None  # environment variable holding the API key
    billable = True

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    # -- validation (no network)
    def validate(self, spec, lang: str) -> list[tuple[str, str | None]]:
        return []

    # -- request building (no network)
    def prepare(self, utt: Utterance, spec, rules) -> PreparedRequest:
        raise NotImplementedError

    # -- network
    def synthesize(self, req: PreparedRequest, *, key: str | None, transport: Transport,
                   timeout: float) -> Audio:
        raise NotImplementedError


def json_body(obj: dict) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def parse_json(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


@dataclass
class Issue:
    message: str
    hint: str | None = None
    extra: dict = field(default_factory=dict)
