"""Rooms and the air in them: how long a room rings after a sound, and the quiet noise every place has.

A sound made in a room reaches the ear directly, then from the nearest walls a few milliseconds later, then as a
diffuse tail that dies away; the time it takes to fall by 60 dB is the room's reverberation time. Sabine's formula gives
it from the room's volume V and the absorption A of its surfaces (RT60 = 0.161 V / A, metres); the sets in
engine/clay/sets.py have real sizes and floors, so each one rings as long as a room that size and that soft would. High
frequencies die sooner than low ones (air and soft surfaces absorb them), so the tail darkens as it decays: a
stochastic impulse response with a decay time per band (as in Moorer's and Schroeder's work on artificial reverb).

The air of a place is its room tone: ventilation, the hum of the building, the city outside. A bed is made the length of
the scene from noise shaped like the real thing, never looped, so nothing in it repeats audibly. A bed holds only what
the set shows or implies: an office has its air conditioning, a cafe the murmur of other tables, a street its wind and
distant traffic. It never invents a crowd, weather or an event the picture does not have (docs/SOUND.md)."""

from __future__ import annotations

import math

import numpy as np

from . import dsp
from .dsp import RATE

# Each set's room, in metres: width, depth, height, the average absorption of its surfaces (0 hard, 1 open window),
# and the bed of air it has. 1 set unit = 0.5 m (engine/clay): the rooms are 9.5 m across, about 3.8 m high.
ROOMS = dict(
    office=dict(size=(9.5, 8.0, 3.8), alpha=.24, floor="wood", bed="office"),
    reception=dict(size=(9.5, 8.0, 3.8), alpha=.16, floor="tile", bed="office"),
    meeting_room=dict(size=(9.5, 8.0, 3.8), alpha=.32, floor="carpet", bed="quiet_office"),
    home_desk=dict(size=(9.5, 8.0, 3.8), alpha=.3, floor="wood", bed="home"),
    cafe=dict(size=(9.5, 8.0, 3.8), alpha=.18, floor="tile", bed="cafe"),
    corridor=dict(size=(6.2, 11.0, 3.8), alpha=.1, floor="stone", bed="corridor"),
    street=dict(size=None, alpha=1.0, floor="pavement", bed="street"),
    classroom=dict(size=(9.5, 8.0, 3.8), alpha=.22, floor="wood", bed="classroom"),
    studio=dict(size=(9.5, 8.0, 3.8), alpha=.45, floor="wood", bed="studio"),
)
BEDS = ("office", "quiet_office", "home", "cafe", "corridor", "street", "classroom", "studio")


def room_of(set_name: str | None) -> dict:
    return ROOMS.get(set_name or "", ROOMS["office"])


def rt60(room: dict) -> float:
    """Sabine reverberation time of a room (s); 0 outdoors."""
    if not room.get("size"):
        return 0.0
    w, d, h = room["size"]
    v = w * d * h
    s = 2 * (w * d + w * h + d * h)
    return max(.15, min(1.6, .161 * v / (s * room["alpha"])))


def impulse(room: dict, seed=0) -> np.ndarray:
    """The room's response to a click (mono, starts with the direct sound at sample 0): a few early reflections from the
    nearest surfaces, then a diffuse tail whose highs die faster than its lows. Outdoors: the direct sound, a faint slap
    back from the buildings, and nothing else.

    Indoors, everything after the direct sound (the room's answer) carries the direct sound's own energy, whatever the
    room's size and hardness: how much of it is heard is reverberate's `wet`, and a room that rings longer spreads the
    same energy over a longer time. The tail starts as one white noise split into bands, so it answers every frequency
    alike before the highs fade (made band by band, each band as loud as the next, the lows of a footstep or a door came
    back some 20 dB too strong)."""
    r = dsp.rng("room", seed)
    t60 = rt60(room)
    if t60 <= 0:
        ir = np.zeros(dsp.samples(.12))
        ir[0] = 1.0
        ir[dsp.samples(.045)] = .12
        ir[dsp.samples(.083)] = .06
        return ir
    n = dsp.samples(min(2.0, t60 * 1.1))
    t = np.arange(n) / RATE
    white = r.standard_normal(n)        # one noise for every band: each keeps its share of a flat spectrum
    tail = np.zeros(n)
    for lo, hi, k in ((20, 250, 1.15), (250, 1000, 1.0), (1000, 4000, .78), (4000, 20000, .5)):
        tail += dsp.shape(white, dsp.bandpass(lo, hi, 2)) * np.exp(-6.91 * t / (t60 * k))
    w, d, h = room["size"]
    gap = min(w, d, h) / 2 / 343.0           # the first reflection comes back from the nearest surface
    tail *= np.clip((t - gap) / .006, 0, 1)
    ir = np.zeros(n)
    ir[0] = 1.0
    for i, dist in enumerate(sorted((h, w / 2, d / 2, w, d))):
        k = dsp.samples(dist / 343.0)
        if 0 < k < n:
            ir[k] += .55 / (1 + i) * r.choice((-1.0, 1.0)) * (1 - room["alpha"]) ** .5
    # the diffuse part under the early reflections, a harder room's louder; then the whole answer at the direct sound's
    # energy (reverberate's `wet` says how much of it is heard)
    ir += tail * .09 * (1 - room["alpha"]) ** .5
    ir[0] = 0.0
    e = float(np.sum(ir * ir))
    if e > 0:
        ir /= math.sqrt(e)
    ir[0] = 1.0
    return ir


def reverberate(x: np.ndarray, room: dict, wet: float, seed=0) -> np.ndarray:
    """x (n,) or (n, 2) played in the room: the direct sound plus `wet` of the room's answer (decorrelated left and
    right, as two ears hear a room)."""
    if len(x) == 0 or wet <= 0:
        return x
    stereo = x.ndim == 2
    out = []
    for c in range(2 if stereo else 1):
        col = x[:, c] if stereo else x
        ir = impulse(room, seed=(seed, c))
        ir[0] = 0.0
        m = 1 << int(math.ceil(math.log2(len(col) + len(ir))))
        y = np.fft.irfft(np.fft.rfft(col, m) * np.fft.rfft(ir, m), m)[:len(col)]
        out.append(col + wet * y)
    return np.stack(out, axis=1) if stereo else out[0]


# ---------------------------------------------------------------- beds
def _hvac(n: int, r) -> np.ndarray:
    """Ventilation: a broadband rush of air, darker than white noise, and the low rumble of the fan behind it."""
    air = dsp.noise(n, r, lambda f: dsp.tilt(-4.0)(f) * dsp.bandpass(80, 6000, 2)(f))
    rumble = dsp.noise(n, r, dsp.bandpass(25, 140, 2))
    drift = 1 + .08 * dsp.noise(n, r, dsp.lowpass(.3, 1))
    return (air + .6 * rumble) * np.clip(drift, .7, 1.3)


def _mains(n: int, hz: float = 50.0, level: float = .03) -> np.ndarray:
    """The faint hum of lights and appliances at the mains frequency and its first harmonics."""
    t = np.arange(n) / RATE
    return level * (np.sin(2 * math.pi * hz * t) + .5 * np.sin(2 * math.pi * 2 * hz * t + .7) + .2 * np.sin(2 * math.pi * 3 * hz * t + 1.3))


def _murmur(n: int, r, voices: int = 7) -> np.ndarray:
    """Other tables talking, too far away to make out: noise shaped like the long-term spectrum of speech (strongest
    around 500 Hz, falling above), each voice coming and going in phrases, its syllables at 3 to 6 a second."""
    t = np.arange(n) / RATE
    out = np.zeros(n)
    def speechy(f):
        return dsp.bandpass(160, 3200, 2)(f) * dsp.peak_band(500, 1.2, 6)(f)

    for _v in range(voices):
        src = dsp.noise(n, r, speechy)
        syll = .55 + .45 * np.sin(2 * math.pi * r.uniform(3.0, 5.5) * t + r.uniform(0, 6.3)) ** 2
        phrase = (dsp.noise(n, r, dsp.lowpass(.35, 2)) > r.uniform(-.2, .3)).astype(float)
        phrase = dsp.smooth(phrase, dsp.samples(.25))
        out += src * syll * phrase * r.uniform(.5, 1.0)
    return out / math.sqrt(voices)


def _wind(n: int, r) -> np.ndarray:
    """Outdoor air: a soft rush that swells and falls in gusts a few seconds long."""
    gust = .65 + .35 * np.tanh(.8 * dsp.noise(n, r, dsp.lowpass(.15, 2)))
    return dsp.noise(n, r, lambda f: dsp.tilt(-5.0)(f) * dsp.bandpass(40, 2500, 2)(f)) * gust


def _traffic(n: int, r) -> np.ndarray:
    """Distant traffic: a low, slowly moving rumble with no single car standing out."""
    swell = .7 + .3 * np.tanh(dsp.noise(n, r, dsp.lowpass(.08, 2)))
    return dsp.noise(n, r, lambda f: dsp.tilt(-6.0)(f) * dsp.bandpass(30, 900, 2)(f)) * swell


def _clinks(n: int, r, rate_hz: float = .18) -> np.ndarray:
    """Now and then, across the room, a cup on a saucer or a spoon in a cup: far away, softened by the distance."""
    from .foley import modes, struck
    out = np.zeros(n)
    k = r.poisson(rate_hz * n / RATE)
    for _ in range(k):
        f0 = r.uniform(2400, 3600)
        hit = struck(modes([f0, f0 * 1.52, f0 * 2.31], [.15, .09, .05], [1, .6, .3], dsp.samples(.5), r), .0008)
        i = int(r.integers(0, max(1, n - len(hit))))
        out[i:i + len(hit)] += hit[:n - i] * r.uniform(.2, 1.0)
    return dsp.shape(out, dsp.lowpass(3500, 1))


def bed(kind: str, seconds: float, seed=0) -> np.ndarray:
    """The air of a place for `seconds`, stereo (n, 2), at a level near -40 dBFS RMS before the mixer sets it. Each
    channel is drawn separately so the bed is wide and does not sit in the middle of the dialogue."""
    n = dsp.samples(seconds)
    chans = []
    for c in range(2):
        r = dsp.rng("bed", kind, seed, c)
        if kind == "street":
            x = _wind(n, r) + .7 * _traffic(n, r)
        elif kind == "cafe":
            x = .55 * _hvac(n, r) + .9 * _murmur(n, r) + 3.0 * _clinks(n, r)
        elif kind in ("office", "corridor"):
            x = _hvac(n, r) + _mains(n)
        elif kind == "quiet_office":
            x = .7 * _hvac(n, r) + _mains(n, level=.02)
        elif kind == "classroom":
            x = .8 * _hvac(n, r)
        elif kind == "home":
            x = .45 * _hvac(n, r) + _mains(n, level=.04)
        else:                      # studio, or anything unknown: barely there
            x = .25 * _hvac(n, r)
        chans.append(x)
    y = np.stack(chans, axis=1)
    rms = float(np.sqrt(np.mean(y * y))) if n else 0.0
    return y * (dsp.gain(-40.0) / rms) if rms > 0 else y
