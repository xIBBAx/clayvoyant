"""Where each sound comes from: recordings first, Foley made by code otherwise.

A project can bring its own recordings (`sound.library: sounds`), laid out by what they are:

    sounds/footstep/wood/*.wav      footsteps on boards (and footstep/tile, footstep/carpet, ...)
    sounds/footstep/*.wav           footsteps on anything without a folder of its own
    sounds/door_close/*.wav         any kind in sound.events.KINDS, the same way

An installed pack (`sastudio sounds install kenney`) is a folder laid out the same way. For each event the first
folder that has a recording of its kind (and surface) gives it; which recording is chosen follows the event's stable id,
and a footstep never repeats the step before it. With no recording, the sound is made by code (sound.foley).
A recording is trimmed to where it starts, so its onset lands on the frame the picture shows the action."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import numpy as np

from . import dsp, foley
from .dsp import RATE
from .events import Event

AUDIO_EXTS = (".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aac", ".opus")


class SoundFileError(Exception):
    """A sound file that cannot be read: it names the file and why."""


_DECODED: dict = {}


def decode(path: Path, channels: int = 2) -> np.ndarray:
    """Any audio file FFmpeg reads, as float64 at 48 kHz: (n, channels). Cached for the build."""
    from ..audio import ffmpeg as ff

    key = (str(Path(path).resolve()), channels, Path(path).stat().st_mtime if Path(path).exists() else 0)
    if key in _DECODED:
        return _DECODED[key]
    if not Path(path).is_file():
        raise SoundFileError(f"{path}: no such file")
    rs = "aresample=48000:resampler=soxr" if ff._has_soxr() else "aresample=48000"
    try:
        r = subprocess.run([ff.ffmpeg_exe(), "-v", "error", "-nostdin", "-i", str(path), "-vn", "-af", rs, "-ac", str(channels),
                            "-ar", str(RATE), "-f", "f32le", "-"], capture_output=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise SoundFileError(f"{path}: FFmpeg took more than ten minutes to read it")
    if r.returncode != 0 or not r.stdout:
        why = r.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["no audio in it"]
        raise SoundFileError(f"{path}: cannot be read as audio ({why[0][:160]})")
    x = np.frombuffer(r.stdout, dtype="<f4").astype(np.float64).reshape(-1, channels)
    if not np.isfinite(x).all():
        raise SoundFileError(f"{path}: the audio holds invalid samples (NaN or infinity)")
    _DECODED[key] = x
    return x


def onset(x: np.ndarray, threshold_db: float = -45.0) -> int:
    """The first sample where a recording's level comes within 45 dB of its peak (its silence before it is cut)."""
    a = np.abs(x).max(axis=1) if x.ndim == 2 else np.abs(x)
    pk = float(a.max()) if len(a) else 0.0
    if pk <= 0:
        return 0
    idx = np.nonzero(a >= pk * dsp.gain(threshold_db))[0]
    return max(0, int(idx[0]) - dsp.samples(.002)) if len(idx) else 0


class Kit:
    """Recordings found in folders (the project's own, then installed packs), and code for everything else."""

    def __init__(self, folders: list[Path] | None = None):
        self.folders = [Path(f) for f in (folders or []) if Path(f).is_dir()]
        self._last: dict = {}
        self.used: dict[str, str] = {}      # event id -> where its sound came from

    def files(self, kind: str, surface: str | None) -> list[Path]:
        for root in self.folders:
            for sub in ([root / kind / surface] if surface else []) + [root / kind]:
                if sub.is_dir():
                    found = sorted(p for p in sub.iterdir() if p.suffix.lower() in AUDIO_EXTS and p.is_file())
                    if found:
                        return found
        return []

    def recording(self, e: Event) -> tuple[np.ndarray, str] | None:
        files = self.files(e.kind, e.surface)
        if not files:
            return None
        h = int(hashlib.sha256(e.id.encode()).hexdigest()[:8], 16)
        k = h % len(files)
        last = self._last.get((e.kind, e.who))
        if len(files) > 1 and last == k:          # never the same step twice running
            k = (k + 1) % len(files)
        self._last[(e.kind, e.who)] = k
        x = decode(files[k], 1)[:, 0]
        x = x[onset(x):]
        return foley.norm(x), f"file:{files[k].name}"

    def clip(self, e: Event) -> tuple[np.ndarray, str]:
        """The sound of one event (mono, its loudest moment near full scale for intensity 1) and where it came from."""
        got = self.recording(e)
        if got is None:
            got = (_made(e), "made by code")
        x, src = got
        self.used[e.id] = src
        return x * max(0.0, min(2.0, e.intensity)), src


def _made(e: Event) -> np.ndarray:
    """An event's sound made by code (sound.foley), from what the event says about it."""
    p, seed = e.params or {}, e.id
    k = e.kind
    if k == "footstep":
        return foley.footstep(foley.surface_of(e.surface), p.get("shoe", "hard"), float(p.get("weight", 1.0)),
                              float(p.get("speed", 1.0)), seed=seed)
    if k == "sit":
        return foley.sit(float(p.get("soft", 0.0)), float(p.get("weight", 1.0)), bool(p.get("wood", True)), seed=seed)
    if k == "stand":
        return foley.stand(float(p.get("soft", 0.0)), seed=seed)
    if k == "scrape":
        return foley.scrape(max(.1, e.duration or .6), foley.surface_of(e.surface), seed=seed)
    if k == "door_open":
        return foley.door_open(max(.4, e.duration or .8), seed=seed)
    if k == "door_close":
        return foley.door_close(seed=seed)
    if k == "knock":
        n = dsp.samples(.7)
        y = np.zeros(n)
        for i, t in enumerate((0.0, .19, .36)):
            hit = foley.door_close(seed=(seed, i))[: dsp.samples(.25)] * (.9 - .15 * i)
            j = dsp.samples(t)
            y[j:j + len(hit)] += hit[: n - j]
        return foley.norm(y) * .8
    if k == "laptop_close":
        return foley.laptop_close(seed=seed)
    if k == "laptop_open":
        return foley.laptop_open(seed=seed)
    if k == "set_down":
        return foley.set_down(p.get("material", "ceramic"), foley.surface_of(e.surface), seed=seed)
    if k == "phone_ring":
        return foley.phone_ring(max(.5, e.duration or 4.0), seed=seed)
    if k == "phone_vibrate":
        return foley.phone_vibrate(max(.5, e.duration or 2.0), bool(p.get("on_table", True)), seed=seed)
    if k == "notification":
        return foley.notification(seed=seed)
    if k == "typing":
        dur = max(.3, e.duration or 2.0)
        n = dsp.samples(dur + .3)
        y = np.zeros(n)
        for t, space in foley.typing_times(dur, seed=seed):
            hit = foley.keystroke(space, seed=(seed, round(t, 3)))
            j = dsp.samples(t)
            y[j:j + len(hit)] += hit[: n - j]
        return y * .8
    raise ValueError(f"no way to make a '{k}' sound")
