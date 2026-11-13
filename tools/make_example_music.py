"""Make the placeholder theme of examples/held-door: a gentle four-chord loop of soft mallet notes over a pad.

    python tools/make_example_music.py [out.ogg]

Made entirely by this code (numpy and FFmpeg), so it is part of the repository under its MIT licence. It is a
placeholder to show how music sits in a film's mix (sastudio.sound), not a score: bring your own music for a real film.
"""

import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

RATE = 48000
BPM = 84
BEAT = 60 / BPM
# D major: D - A - Bm - G, two bars each
CHORDS = [(62, 66, 69), (61, 64, 69), (59, 62, 66), (59, 62, 67)]


def hz(k):
    return 440.0 * 2 ** ((k - 69) / 12)


def mallet(f, n, r):
    t = np.arange(n) / RATE
    y = np.zeros(n)
    for mult, amp, dec in ((1.0, 1.0, 1.4), (2.0, .25, .5), (3.01, .08, .25), (4.2, .04, .12)):
        y += amp * np.exp(-t / dec) * np.sin(2 * math.pi * f * mult * t + r.uniform(0, 6.28))
    att = np.clip(t / .006, 0, 1)
    return y * att


def pad(freqs, n):
    t = np.arange(n) / RATE
    env = np.sin(math.pi * np.clip(t / (n / RATE), 0, 1)) ** .8
    y = sum(np.sin(2 * math.pi * f * t) + .3 * np.sin(2 * math.pi * f * 2.003 * t) for f in freqs)
    return y * env / len(freqs)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("examples/held-door/assets/music/theme.ogg")
    r = np.random.default_rng(84)
    bar = 4 * BEAT
    total = len(CHORDS) * 2 * bar
    n = int(total * RATE) + RATE
    L, R = np.zeros(n), np.zeros(n)
    for ci, chord in enumerate(CHORDS):
        t0 = ci * 2 * bar
        i0 = int(t0 * RATE)
        p = pad([hz(k - 12) for k in chord], int(2 * bar * RATE))
        L[i0:i0 + len(p)] += .22 * p
        R[i0:i0 + len(p)] += .22 * p
        for b in range(8):                      # an arpeggio on the beats, the top note a little later
            k = chord[b % 3] + (12 if b in (3, 7) else 0)
            j = int((t0 + b * BEAT + (.02 if b % 2 else 0)) * RATE)
            m = mallet(hz(k), int(2.5 * RATE), r) * (.5 if b % 2 else .62)
            pan = .35 * math.sin(b)
            seg = min(len(m), n - j)
            L[j:j + seg] += m[:seg] * (1 - pan)
            R[j:j + seg] += m[:seg] * (1 + pan)
    y = np.stack([L, R], 1)
    y *= .5 / np.abs(y).max()
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        w = Path(tmp) / "theme.wav"
        with wave.open(str(w), "wb") as f:
            f.setnchannels(2)
            f.setsampwidth(2)
            f.setframerate(RATE)
            f.writeframes((y * 32767).astype("<i2").tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(w), "-c:a", "libvorbis", "-q:a", "4", str(out)], check=True)
    print(f"Wrote {out} ({total:.1f} s)")


if __name__ == "__main__":
    main()
