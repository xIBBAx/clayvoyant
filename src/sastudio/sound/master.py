"""Mastering: the mix brought to its loudness, held under its true-peak ceiling, and measured as people will hear it.

The default suits a short film watched online, mostly speech: -16 LUFS integrated (Apple's spoken-word target, inside
AES TD1008's -18 to -16 for speech and mixed content, a little under what YouTube and Spotify turn things down to), and
-1.5 dBTP for the true peak of the encoded film (EBU R 128 allows -1; lossy codecs push peaks up, more at lower bit
rates, so the ceiling is set below that). Both can be changed (sound.master).

How: one gain to reach the loudness (a linear change, as FFmpeg's two-pass loudnorm in linear mode makes), then a
look-ahead true-peak limiter (sound.dsp.limit) for the few transients above the ceiling. Limiting lowers the loudness a
little, so the two are repeated until both hold. The film is then encoded (AAC), decoded and measured again by FFmpeg's
EBU R 128 meter: if the codec pushed a peak over the ceiling, the ceiling comes down by that much and the audio is
encoded again. What is reported is what the encoded film measures. If the targets cannot both be met (a mix whose peaks
sit far above its loudness would need heavy limiting), the report says so rather than claiming them."""

from __future__ import annotations

import io
import os
import re
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import dsp, meter
from .dsp import RATE

MAX_LIMIT_DB = 6.0      # deeper limiting than this squashes transients audibly: the target is reported as not met


@dataclass
class Target:
    loudness: float = -16.0      # LUFS, integrated (ITU-R BS.1770)
    true_peak: float = -1.5      # dBTP, of the encoded film
    bitrate: int = 192           # kb/s, AAC-LC
    tolerance: float = 1.0       # LU either side of the loudness that counts as on target


def codec_margin(bitrate: int) -> float:
    """How far under the ceiling to limit before encoding, so the codec's overshoot fits (it grows as the bit rate falls:
    AES TD1008 section 7B; EBU Tech 3343)."""
    return .3 if bitrate >= 256 else .5 if bitrate >= 160 else 1.0


def master(mix: np.ndarray, t: Target, margin: float | None = None) -> tuple[np.ndarray, dict]:
    """-> (mastered (n, 2), what was done and measured before encoding)."""
    info = dict(target_lufs=t.loudness, target_dbtp=t.true_peak)
    lu = meter.integrated(mix)
    info["mix_lufs"] = None if lu is None else round(lu, 2)
    if lu is None:
        info.update(silent=True, gain_db=0.0, limiter_db=0.0)
        return mix, info
    ceiling = t.true_peak - (codec_margin(t.bitrate) if margin is None else margin)
    g = t.loudness - lu
    y, red = mix, 0.0
    for _ in range(4):
        y, red = dsp.limit(mix * dsp.gain(g), ceiling)
        now = meter.integrated(y)
        if now is None or abs(now - t.loudness) < .05 or red < -MAX_LIMIT_DB:
            break
        g += t.loudness - now
    info.update(silent=False, gain_db=round(g, 2), limiter_db=round(red, 2), ceiling_dbtp=round(ceiling, 2),
                lufs_before_encoding=round(meter.integrated(y), 2), true_peak_before_encoding=round(dsp.true_peak_db(y), 2))
    if red < -MAX_LIMIT_DB:
        info["warning"] = (f"reaching {t.loudness:g} LUFS needs {-red:.1f} dB of limiting: the mix's peaks sit far above its "
                           "loudness (effects or music too loud against the dialogue?)")
    return y, info


def write_wav(path: Path, x: np.ndarray) -> None:
    """24-bit stereo WAV, written whole to a temporary name and moved into place (never a half-written file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    y = np.clip(x, -1.0, 1.0 - 1.0 / 8388608)
    q = np.round(y * 8388607).astype(np.int32)
    b = q.astype("<i4").view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2 if x.ndim == 2 else 1)
        w.setsampwidth(3)
        w.setframerate(RATE)
        w.writeframes(b)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(buf.getvalue())
    os.replace(tmp, path)


_I = re.compile(r"I:\s+(-?[\d.]+|-inf)\s+LUFS")
_LRA = re.compile(r"LRA:\s+(-?[\d.]+)\s+LU")
_TP = re.compile(r"Peak:\s+(-?[\d.]+|-inf)\s+dBFS")


def measure(path: Path) -> dict:
    """FFmpeg's EBU R 128 meter on a file's audio, as decoded (a film's AAC included): integrated loudness, loudness
    range and true peak (BS.1770 Annex 2, four times oversampled)."""
    from ..audio import ffmpeg as ff

    res = ff.run([ff.ffmpeg_exe(), "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af",
                  "ebur128=peak=true:framelog=quiet", "-f", "null", "-"], what="Loudness measurement")
    err = res.stderr.decode("utf-8", "replace")
    s = err[err.rfind("Summary:"):] if "Summary:" in err else err

    def num(rx):
        m = rx.search(s)
        return None if not m or m.group(1) == "-inf" else float(m.group(1))

    i = num(_I)
    return dict(lufs=None if i is None or i <= -69.0 else i, lra=num(_LRA), true_peak=num(_TP))


def verdict(m: dict, t: Target, info: dict) -> dict:
    """Whether the encoded film meets its targets, in plain words for the manifest and the log."""
    if m.get("lufs") is None:
        return dict(met=None, said="silent: nothing to measure")
    ok_l = abs(m["lufs"] - t.loudness) <= t.tolerance
    ok_p = m["true_peak"] is not None and m["true_peak"] <= t.true_peak + 1e-6
    said = (f"{m['lufs']:.1f} LUFS (target {t.loudness:g}), true peak {m['true_peak']:.1f} dBTP (ceiling {t.true_peak:g}), "
            f"loudness range {m['lra']:.1f} LU")
    if not ok_l:
        said += f"; loudness off target by {m['lufs'] - t.loudness:+.1f} LU"
    if not ok_p:
        said += "; true peak over the ceiling"
    if info.get("warning"):
        said += "; " + info["warning"]
    return dict(met=ok_l and ok_p and not info.get("warning"), said=said)
