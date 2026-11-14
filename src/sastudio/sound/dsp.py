"""Signal tools for the sound engine. numpy only, float64, 48 kHz, and deterministic: the same inputs and the same seed
always give the same samples, so a soundtrack can be rebuilt bit for bit and its parts cached.

Levels are measured by FFmpeg's EBU R128 meter (sastudio.sound.master); what is here shapes and places sound."""

from __future__ import annotations

import hashlib
import math

import numpy as np

RATE = 48000


def db(g: float) -> float:
    """A linear gain in decibels (silence is -200 dB)."""
    return 20.0 * math.log10(max(float(g), 1e-10))


def gain(d: float) -> float:
    """Decibels as a linear gain."""
    return 10.0 ** (float(d) / 20.0)


def rng(*keys) -> np.random.Generator:
    """A random source fixed by its keys: the same event of the same film always sounds the same."""
    h = hashlib.sha256("\x1f".join(str(k) for k in keys).encode()).digest()
    return np.random.default_rng(int.from_bytes(h[:8], "little"))


def seconds(n: int) -> float:
    return n / RATE


def samples(s: float) -> int:
    return max(0, int(round(s * RATE)))


# ---------------------------------------------------------------- spectra
def freqs(n: int) -> np.ndarray:
    return np.fft.rfftfreq(n, 1.0 / RATE)


def shape(x: np.ndarray, mag) -> np.ndarray:
    """x through a zero-phase filter whose gain at each frequency is mag(f) (an array function of frequency in Hz)."""
    n = len(x)
    if n == 0:
        return x
    m = 1 << max(1, int(math.ceil(math.log2(n + 1))))
    spec = np.fft.rfft(x, m)
    spec *= mag(freqs(m))
    return np.fft.irfft(spec, m)[:n]


def lowpass(fc: float, order: int = 2):
    return lambda f: 1.0 / np.sqrt(1.0 + (f / max(fc, 1.0)) ** (2 * order))


def highpass(fc: float, order: int = 2):
    return lambda f: 1.0 / np.sqrt(1.0 + (max(fc, 1.0) / np.maximum(f, 1e-3)) ** (2 * order))


def bandpass(lo: float, hi: float, order: int = 2):
    lp, hp = lowpass(hi, order), highpass(lo, order)
    return lambda f: lp(f) * hp(f)


def peak_band(fc: float, q: float, gain_db: float):
    """A bell around fc: +gain_db at fc, falling off with bandwidth fc / q (a resonance in a body or a room)."""
    g = gain(gain_db) - 1.0
    return lambda f: 1.0 + g / (1.0 + ((f - fc) * q / max(fc, 1.0)) ** 2)


def tilt(db_per_octave: float, ref: float = 1000.0):
    """A straight slope in dB per octave about ref: -3 is pink noise from white, -6 is brown."""
    return lambda f: (np.maximum(f, 20.0) / ref) ** (db_per_octave / 6.0206)


def noise(n: int, r: np.random.Generator, mag=None) -> np.ndarray:
    """n samples of noise, white or shaped by mag(f), scaled to an RMS of 1."""
    x = r.standard_normal(n)
    if mag is not None:
        x = shape(x, mag)
    s = float(np.sqrt(np.mean(x * x))) if n else 0.0
    return x / s if s > 0 else x


# ---------------------------------------------------------------- envelopes and fades
def fade_in(n: int) -> np.ndarray:
    """Equal-power fade in: sin over a quarter turn, so a fade out of cos beside it keeps the power constant."""
    if n <= 0:
        return np.ones(0)
    return np.sin(np.linspace(0.0, math.pi / 2, n, endpoint=False) + math.pi / (4 * n))


def fade_out(n: int) -> np.ndarray:
    return fade_in(n)[::-1]


def attack_decay(n: int, attack: float, decay: float, t0: float = 0.0) -> np.ndarray:
    """A sharp rise over `attack` seconds from t0, then an exponential fall with time constant `decay` seconds."""
    t = np.arange(n) / RATE - t0
    a = np.clip(t / max(attack, 1e-5), 0.0, 1.0)
    a = np.where(t < 0, 0.0, a)
    return a * np.exp(-np.maximum(t - attack, 0.0) / max(decay, 1e-5))


def smooth(x: np.ndarray, width: int) -> np.ndarray:
    """A moving average of width samples (centred), in O(n) whatever the width."""
    if width <= 1 or len(x) == 0:
        return x
    c = np.concatenate([[0.0], np.cumsum(x, dtype=float)])
    i = np.arange(len(x))
    lo = np.clip(i - width // 2, 0, len(x))
    hi = np.clip(i - width // 2 + width, 0, len(x))
    return (c[hi] - c[lo]) / np.maximum(hi - lo, 1)


def running_min(x: np.ndarray, width: int) -> np.ndarray:
    """out[i] = min(x[i:i + width]) (the window looks ahead, and past the end it holds only what is there), in O(n):
    van Herk and Gil-Werman's block prefix and suffix minima."""
    n = len(x)
    if width <= 1 or n == 0:
        return x.copy()
    m = -(-(n + width) // width) * width
    p = np.full(m, np.inf)
    p[:n] = x
    blocks = p.reshape(-1, width)
    pre = np.minimum.accumulate(blocks, axis=1).ravel()
    suf = np.minimum.accumulate(blocks[:, ::-1], axis=1)[:, ::-1].ravel()
    i = np.arange(n)
    return np.minimum(suf[i], pre[np.minimum(i + width - 1, m - 1)])


def convolve(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Linear convolution through the FFT, cut to len(x) (a filter or a room applied to a signal)."""
    if len(x) == 0 or len(h) == 0:
        return np.zeros(len(x))
    m = 1 << int(math.ceil(math.log2(len(x) + len(h) - 1)))
    return np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(h, m), m)[:len(x)]


# ---------------------------------------------------------------- stereo
def pan(mono: np.ndarray, p: float) -> np.ndarray:
    """Constant-power pan of a mono signal: p from -1 (left) to 1 (right). -> (n, 2)."""
    th = (max(-1.0, min(1.0, p)) + 1.0) * math.pi / 4
    return np.stack([mono * math.cos(th), mono * math.sin(th)], axis=1) * math.sqrt(2.0)


def to_stereo(x: np.ndarray) -> np.ndarray:
    if x.ndim == 1:
        return np.stack([x, x], axis=1)
    if x.shape[1] == 1:
        return np.repeat(x, 2, axis=1)
    return x[:, :2]


# ---------------------------------------------------------------- true peak and limiting
def _upsampler(factor: int, taps: int = 32) -> np.ndarray:
    """Polyphase windowed-sinc interpolator: (factor, 2 * taps) coefficients, one row per phase."""
    k = np.arange(-taps + 1, taps + 1, dtype=float)
    rows = []
    for p in range(factor):
        t = k - p / factor
        h = np.sinc(t) * np.kaiser(len(t), 8.0)
        rows.append(h / h.sum())
    return np.array(rows)


_UP = {}


def true_peaks(x: np.ndarray, factor: int = 4) -> np.ndarray:
    """Per sample, the largest absolute value the signal reaches between that sample and the next once reconstructed
    (inter-sample peaks: ITU-R BS.1770 Annex 2 measures true peak at four times the sample rate). x: (n,) or (n, ch);
    the result is (n,), the largest over the channels."""
    if x.ndim == 1:
        x = x[:, None]
    if factor not in _UP:
        _UP[factor] = _upsampler(factor)
    h = _UP[factor]
    out = np.abs(x).max(axis=1)
    half = h.shape[1] // 2
    for c in range(x.shape[1]):
        col = x[:, c]
        for p in range(1, factor):
            # the value a quarter, a half, three quarters of the way to the next sample
            y = convolve(np.concatenate([col, np.zeros(half)]), h[p][::-1])[half:half + len(col)]
            np.maximum(out, np.abs(y), out=out)
    return out


def true_peak_db(x: np.ndarray) -> float:
    if len(x) == 0:
        return -200.0
    return db(float(true_peaks(x).max()))


def limit(x: np.ndarray, ceiling_db: float, lookahead: float = .005, release: float = .12) -> tuple[np.ndarray, float]:
    """A look-ahead true-peak limiter, linked across channels: the gain starts coming down `lookahead` seconds before a
    peak, so it is never late, and recovers with a `release` time constant, so it never pumps on a single transient.
    -> (limited signal, deepest gain reduction in dB, 0 when nothing was touched)."""
    if len(x) == 0:
        return x, 0.0
    ceil_ = gain(ceiling_db)
    pk = true_peaks(x)
    need = np.minimum(1.0, ceil_ / np.maximum(pk, 1e-12))
    if need.min() >= 1.0:
        return x, 0.0
    L = max(2, samples(lookahead))
    # the gain each sample must be at or below so that every peak in the next L samples is under the ceiling
    ahead = running_min(need, L)
    # eased in over the look-ahead: the average of L of these is never above the gain a peak inside the window needs
    # (before the first sample the ramp is already at the first window's gain: a film that starts loud is caught too)
    c = np.concatenate([[0.0], np.cumsum(np.concatenate([np.full(L - 1, ahead[0]), ahead]))])
    att = (c[L:] - c[:-L]) / L
    # recovery, a block at a time
    B = 32
    nb = (len(att) + B - 1) // B
    blocks = np.minimum.reduceat(att, np.arange(0, len(att), B))
    k = 1.0 - math.exp(-B / (release * RATE))
    g = np.empty(nb)
    prev = 1.0
    for i in range(nb):
        prev = min(blocks[i], prev + (1.0 - prev) * k)
        g[i] = prev
    # back to samples: each block's gain from its start, eased into the next; never above the attack curve
    gs = np.interp(np.arange(len(att)), np.arange(nb) * B, g)
    gs = np.minimum(gs, att)
    y = x * (gs[:, None] if x.ndim == 2 else gs)
    return y, db(float(gs.min()))
