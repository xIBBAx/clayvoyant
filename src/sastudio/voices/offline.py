"""Free, local speech for trying the pipeline without any account.

Two engines:

* `espeak-ng`, if it is installed: a real (robotic) synthetic voice in many languages,
  including Hindi. It runs as an external program; nothing is bundled.
* `silence`: no program needed. Produces silent audio timed like speech, so timing,
  subtitles and rendering can be tested anywhere. It is labelled as such in every report.

Neither engine says anything about whether Sarvam or ElevenLabs will work: those are
tested separately (see docs/VOICE_PROVIDERS.md).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from ..errors import ProviderError
from .base import Audio, PreparedRequest, Provider, check_wav, pcm_to_wav, repair_wav
from .common import spoken_text

ESPEAK_LANG = {"en": "en-us", "en-IN": "en-us", "en-GB": "en-gb", "en-US": "en-us", "hi": "hi", "hi-IN": "hi",
               "mr-IN": "mr", "ta-IN": "ta", "te-IN": "te", "kn-IN": "kn", "ml-IN": "ml", "bn-IN": "bn",
               "gu-IN": "gu", "pa-IN": "pa", "od-IN": "or"}


def find_espeak(config: dict | None = None) -> str | None:
    cfg = (config or {}).get("espeak_path") or os.environ.get("SASTUDIO_ESPEAK")
    if cfg:
        return cfg if Path(cfg).is_file() and os.access(cfg, os.X_OK) else None
    return shutil.which("espeak-ng")


def estimate_seconds(text: str, wpm: float = 150.0) -> float:
    words = max(1, len(re.findall(r"\w+", text)))
    pauses = len(re.findall(r"[,;:]", text)) * 0.15 + len(re.findall(r"[.!?]", text)) * 0.3
    return round(words * 60.0 / wpm + pauses + 0.2, 3)


class OfflineProvider(Provider):
    name = "offline"
    key_env = None
    billable = False

    def engine(self) -> str:
        want = self.config.get("engine", "auto")
        if want == "silence":
            return "silence"
        if find_espeak(self.config):
            return "espeak-ng"
        if want == "espeak-ng":
            raise ProviderError("espeak-ng is not installed.", "Install it (see docs/INSTALLATION.md) or set engine: silence.")
        return "silence"

    def validate(self, spec, lang):
        out = []
        for k, v in spec.settings.items():
            if k == "rate" and not (isinstance(v, (int, float)) and 80 <= v <= 400):
                out.append(("offline rate must be 80..400 words per minute.", None))
            elif k == "pitch" and not (isinstance(v, int) and 0 <= v <= 99):
                out.append(("offline pitch must be 0..99.", None))
            elif k not in ("rate", "pitch", "voice"):
                out.append((f"Unknown offline setting '{k}'.", "Known: rate, pitch, voice."))
        return out

    def prepare(self, utt, spec, rules):
        text = utt.override or spoken_text(utt.resolved, self.name, rules)
        engine = self.engine()
        voice = spec.settings.get("voice") or spec.speaker or ESPEAK_LANG.get(utt.language) or \
            ESPEAK_LANG.get(utt.language.split("-")[0], "en-us")
        fields = {"engine": engine, "voice": voice, "rate": spec.settings.get("rate", 160),
                  "pitch": spec.settings.get("pitch", 50), "language": utt.language}
        return PreparedRequest(self.name, text, fields, characters=0)

    def synthesize(self, req: PreparedRequest, *, key, transport, timeout) -> Audio:
        f = req.fields
        if f["engine"] == "silence":
            seconds = estimate_seconds(req.text, float(f["rate"]))
            return Audio(pcm_to_wav(b"\x00\x00" * int(seconds * 24000), 24000))
        exe = find_espeak(self.config)
        if not exe:
            raise ProviderError("espeak-ng disappeared between planning and generating.")
        # Arguments are passed as a list (no shell); the text goes through stdin, never argv,
        # so dialogue cannot be interpreted as options.
        cmd = [exe, "-v", str(f["voice"]), "-s", str(int(f["rate"])), "-p", str(int(f["pitch"])), "--stdout", "--stdin"]
        try:
            res = subprocess.run(cmd, input=req.text.encode("utf-8"), capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise ProviderError("espeak-ng timed out.")
        if res.returncode != 0:
            raise ProviderError(f"espeak-ng failed: {res.stderr.decode('utf-8', 'replace')[:200]}")
        wav = repair_wav(res.stdout)  # espeak-ng streams WAV with an unfinished header
        check_wav(wav)
        return Audio(wav)
