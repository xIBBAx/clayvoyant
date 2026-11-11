"""Kokoro: a free neural voice that runs on this computer. No account, no key, no network once installed.

Kokoro-82M is a small open text-to-speech model (weights under Apache-2.0). This adapter uses it through the
`kokoro-onnx` package, which is not part of Security Awareness Studio: install it with

    pip install "security-awareness-studio[voices]"
    sastudio voices install kokoro          # downloads the model once (about 350 MB)

What it offers here: natural American and British English voices and four Hindi voices, on an ordinary CPU and
faster than real time. What it does not offer: an Indian-English accent (English lines are read in a British or
American voice) or voice cloning. It also reports when each sound is spoken, which the clay renderer uses for lip
sync. Its text front end (phonemizer, espeak-ng) is GPL-3.0 software that `kokoro-onnx` installs alongside itself.
"""

from __future__ import annotations

import hashlib
import io
import os
import wave
from pathlib import Path

from ..errors import ProviderError
from .base import Audio, PreparedRequest, Provider, check_wav
from .common import spoken_text

MODEL = "kokoro-v1.0"
FILES = {
    "kokoro-v1.0.onnx": ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx",
                         "beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a", 325_505_369),
    "voices-v1.0.bin": ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin",
                        "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d", 28_214_398),
}
# Voices this adapter has been run with. The first letter is the accent (a American, b British, h Hindi), the second
# the voice's gender (f, m).
VOICES = {"en-US": ["af_heart", "am_michael", "af_bella", "am_fenrir", "af_nicole", "am_puck", "af_sarah", "am_eric"],
          "en-GB": ["bf_emma", "bm_george", "bf_isabella", "bm_fable", "bf_alice", "bm_daniel", "bf_lily", "bm_lewis"],
          "hi-IN": ["hf_alpha", "hm_omega", "hf_beta", "hm_psi"]}
ACCENT = {"en": "en-GB", "en-IN": "en-GB", "en-GB": "en-GB", "en-US": "en-US", "hi": "hi-IN", "hi-IN": "hi-IN"}
ESPEAK = {"en-GB": "en-gb", "en-US": "en-us", "hi-IN": "hi"}
_engine = None


def model_dir(config: dict | None = None) -> Path:
    d = (config or {}).get("model_dir") or os.environ.get("SASTUDIO_KOKORO_DIR")
    return Path(d).expanduser() if d else Path.home() / ".cache" / "sastudio" / "kokoro"


def installed(config: dict | None = None) -> bool:
    d = model_dir(config)
    return all((d / name).is_file() and (d / name).stat().st_size == size for name, (_, _, size) in FILES.items())


def install(config: dict | None = None, log=print) -> Path:
    """Download the model files (once) and check them against their known SHA-256."""
    import urllib.request

    d = model_dir(config)
    d.mkdir(parents=True, exist_ok=True)
    for name, (url, sha, size) in FILES.items():
        dst = d / name
        if dst.is_file() and dst.stat().st_size == size:
            log(f"  {name}: already here")
            continue
        log(f"  {name}: downloading {size / 1e6:.0f} MB from {url.split('/')[2]} ...")
        tmp = dst.with_suffix(dst.suffix + ".part")
        h = hashlib.sha256()
        req = urllib.request.Request(url, headers={"User-Agent": "sastudio"})  # noqa: S310 (fixed https URL)
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as fh:  # noqa: S310
            while chunk := r.read(1 << 20):
                fh.write(chunk)
                h.update(chunk)
        if h.hexdigest() != sha:
            tmp.unlink(missing_ok=True)
            raise ProviderError(f"{name} did not match its expected checksum; nothing was installed.",
                                "Try again; if it keeps failing the download is being altered on the way.")
        tmp.replace(dst)
    return d


def _load(config: dict | None):
    global _engine
    if _engine is None:
        try:
            from kokoro_onnx import Kokoro
        except ImportError:
            raise ProviderError("The kokoro voice needs the kokoro-onnx package.",
                                'Install it: pip install "security-awareness-studio[voices]"')
        if not installed(config):
            raise ProviderError("The Kokoro model is not downloaded yet.", "Run: sastudio voices install kokoro  (about 350 MB, once)")
        d = model_dir(config)
        _engine = Kokoro(str(d / "kokoro-v1.0.onnx"), str(d / "voices-v1.0.bin"))
    return _engine


def default_voice(character_id: str, language: str, gender: str | None = None) -> str:
    """A voice for a character nobody chose one for: steady per character, matching their gender when it is known."""
    pool = VOICES[ACCENT.get(language) or ACCENT.get(language.split("-")[0], "en-GB")]
    g = {"feminine": "f", "masculine": "m"}.get((gender or "").lower())
    if g:
        pool = [v for v in pool if v[1] == g] or pool
    return pool[int(hashlib.sha256(character_id.encode()).hexdigest()[:6], 16) % len(pool)]


class KokoroProvider(Provider):
    name = "kokoro"
    key_env = None
    billable = False

    def validate(self, spec, lang):
        out = []
        if ACCENT.get(lang) is None and ACCENT.get(lang.split("-")[0]) is None:
            out.append((f"The kokoro voice has not been tested in {lang}.", "It is set up for en-IN, en-GB, en-US and hi-IN."))
        voice = spec.speaker or spec.settings.get("voice")
        if voice and voice not in {v for vs in VOICES.values() for v in vs}:
            out.append((f"'{voice}' is not a kokoro voice this adapter knows.",
                        "English: " + ", ".join(VOICES["en-GB"][:4] + VOICES["en-US"][:4]) + ". Hindi: " + ", ".join(VOICES["hi-IN"]) + "."))
        for k, v in spec.settings.items():
            if k == "speed" and not (isinstance(v, (int, float)) and 0.5 <= v <= 2.0):
                out.append(("kokoro speed must be 0.5..2.0.", None))
            elif k not in ("speed", "voice", "gender"):
                out.append((f"Unknown kokoro setting '{k}'.", "Known: speed, voice, gender."))
        return out

    def prepare(self, utt, spec, rules):
        text = utt.override or spoken_text(utt.resolved, self.name, rules)
        accent = ACCENT.get(utt.language) or ACCENT.get(utt.language.split("-")[0], "en-GB")
        gender = spec.settings.get("gender") or (self.config.get("_genders") or {}).get(utt.character_id)
        voice = spec.speaker or spec.settings.get("voice") or default_voice(utt.character_id, utt.language, gender)
        if voice[0] == "a" and accent == "en-GB":
            accent = "en-US"        # an American voice reads with American sounds
        elif voice[0] == "b" and accent == "en-US":
            accent = "en-GB"
        fields = {"model": MODEL, "voice": voice, "speed": float(spec.settings.get("speed", 1.0)), "accent": accent,
                  "language": utt.language}
        return PreparedRequest(self.name, text, fields, characters=0)

    def synthesize(self, req: PreparedRequest, *, key, transport, timeout) -> Audio:
        f = req.fields
        engine = _load(self.config)     # says what to install when the package or the model is missing
        import numpy as np
        try:
            samples, rate, timings = engine.create_timed(req.text, voice=f["voice"], speed=f["speed"], lang=ESPEAK[f["accent"]])
        except Exception as e:  # noqa: BLE001 (any failure inside the model is a provider failure)
            raise ProviderError(f"kokoro could not speak this line: {str(e)[:160]}")
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(int(rate))
            w.writeframes(pcm)
        data = buf.getvalue()
        check_wav(data)
        marks = [[t.phoneme, round(float(t.start), 3), round(float(t.end), 3)] for t in timings or []]
        return Audio(data, marks=marks or None)
