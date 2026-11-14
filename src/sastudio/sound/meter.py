"""Loudness as ITU-R BS.1770-4 defines it, in numpy, for the mixer's decisions (how loud the dialogue is, so the music
and the air can be set under it). The finished film is measured again by FFmpeg's EBU R128 meter (sound.master).

K-weighting is the standard's two filters (a high shelf for the head, a high-pass), given as biquads for 48 kHz; they
are applied here as their exact frequency response through the FFT. Mean square in 400 ms blocks every 100 ms, an
absolute gate at -70 LKFS, then a relative gate 10 LU under the mean of what passed it."""

from __future__ import annotations

import math

import numpy as np

from .dsp import RATE

# ITU-R BS.1770-4, Annex 1, at 48 kHz: stage 1 (the head's high shelf) and stage 2 (RLB high-pass)
_S1 = ((1.53512485958697, -2.69169618940638, 1.19839281085285), (1.0, -1.69065929318241, 0.73248077421585))
_S2 = ((1.0, -2.0, 1.0), (1.0, -1.99004745483398, 0.99007225036621))


def _biquad_response(b, a, n_fft: int) -> np.ndarray:
    z = np.exp(-1j * np.pi * np.arange(n_fft // 2 + 1) / (n_fft // 2))
    return (b[0] + b[1] * z + b[2] * z * z) / (a[0] + a[1] * z + a[2] * z * z)


def k_weight(x: np.ndarray) -> np.ndarray:
    """x (n,) through the K-weighting filters (causal, as the standard's biquads are)."""
    n = len(x)
    if n == 0:
        return x
    m = 1 << int(math.ceil(math.log2(n + 4800)))     # room for the filters' ringing so nothing wraps round
    h = _biquad_response(*_S1, m) * _biquad_response(*_S2, m)
    return np.fft.irfft(np.fft.rfft(x, m) * h, m)[:n]


def blocks(x: np.ndarray, size: float = .4, step: float = .1) -> np.ndarray:
    """Per-block K-weighted power summed over the channels (BS.1770's z), x (n,) or (n, ch)."""
    if x.ndim == 1:
        x = x[:, None]
    B, S = int(round(size * RATE)), int(round(step * RATE))
    if len(x) < B:
        return np.zeros(0)
    tot = None
    for c in range(x.shape[1]):
        y = k_weight(x[:, c].astype(float))
        cs = np.concatenate([[0.0], np.cumsum(y * y)])
        starts = np.arange(0, len(y) - B + 1, S)
        z = (cs[starts + B] - cs[starts]) / B
        tot = z if tot is None else tot + z
    return tot


def integrated(x: np.ndarray) -> float | None:
    """Integrated loudness in LUFS, or None for silence (nothing above the absolute gate) or a clip under 400 ms."""
    z = blocks(x)
    if len(z) == 0:
        return None
    L = -0.691 + 10 * np.log10(np.maximum(z, 1e-20))
    keep = L > -70.0
    if not keep.any():
        return None
    rel = -0.691 + 10 * math.log10(float(z[keep].mean())) - 10.0
    keep &= L > rel
    if not keep.any():
        return None
    return -0.691 + 10 * math.log10(float(z[keep].mean()))


def momentary(x: np.ndarray) -> np.ndarray:
    """Loudness of each 400 ms block, every 100 ms (LUFS, -inf for silence)."""
    z = blocks(x)
    return -0.691 + 10 * np.log10(np.maximum(z, 1e-20))
