"""Foley made by code: the sounds of things the characters do, built from how those things make sound.

Most everyday sounds are a short push into something that rings. A hand, a heel or a lid presses into a surface for a
few milliseconds (the contact), and the surface and the thing answer at their own resonant frequencies, each dying away
at its own rate (the modes). That is modal synthesis (van den Doel, Kry and Pai, "FoleyAutomatic", SIGGRAPH 2001; Cook,
"Real Sound Synthesis for Interactive Applications", 2002): the response is a sum of damped sinusoids, excited by a
contact force whose duration sets the brightness (a hard heel on tile pushes for 2 ms and rings high; a soft sole on
carpet pushes for 15 ms and only thumps). Scrapes and creaks are friction: many small stick-slip impulses through the
same resonances. A footstep is a heel strike and, a moment later, the ball of the foot (Turchet, Serafin and others on
walking sounds; Cook's PhISEM for the granular part). Every call is deterministic in its seed, and no two steps of a
walk are the same: modes, timing, force and grit vary a little each time, as real ones do.

Each function returns mono float64 samples at dsp.RATE, scaled so that its loudest moment is near full scale for a
firm action; the mixer sets the level. What this module cannot make convincingly (voices, laughter, breathing) it does
not try to make: see docs/SOUND.md."""

from __future__ import annotations

import math

import numpy as np

from . import dsp
from .dsp import RATE


# ---------------------------------------------------------------- building blocks
def modes(freqs, decays, amps, n: int, r: np.random.Generator | None = None, detune: float = 0.0) -> np.ndarray:
    """An impulse response: sum of a * exp(-t / tau) * sin(2 pi f t + phase) over the modes (f Hz, tau s, a)."""
    t = np.arange(n) / RATE
    y = np.zeros(n)
    for f, tau, a in zip(freqs, decays, amps, strict=True):
        if f >= RATE * .45:
            continue
        if r is not None and detune:
            f = f * (1.0 + detune * r.uniform(-1, 1))
            tau = tau * (1.0 + .5 * detune * r.uniform(-1, 1))
        ph = r.uniform(0, 2 * math.pi) if r is not None else 0.0
        y += a * np.exp(-t / tau) * np.sin(2 * math.pi * f * t + ph)
    return y


def contact(tau: float) -> np.ndarray:
    """The force of a short contact (a raised half-sine, as Hertz's theory gives for two bodies meeting), duration tau s."""
    m = max(3, int(round(tau * RATE)))
    return np.sin(np.linspace(0, math.pi, m)) ** 1.5


def struck(ir: np.ndarray, tau: float) -> np.ndarray:
    """An impulse response struck with a contact of duration tau: the longer the contact, the darker the sound."""
    if len(ir) == 0:
        return ir
    f = contact(tau)
    n = len(ir) + len(f) - 1
    m = 1 << int(math.ceil(math.log2(n)))
    y = np.fft.irfft(np.fft.rfft(ir, m) * np.fft.rfft(f, m), m)[:len(ir)]
    return y / (f.sum() or 1.0)


def grains(n: int, rate_hz: float, r: np.random.Generator, width: float = .0015, env=None) -> np.ndarray:
    """A train of tiny random impulses (the stick-slip of friction, the crunch of grit): Poisson in time, rate_hz on
    average, each a decaying click of `width` seconds; env (n,) scales the rate and the size as the action goes on."""
    y = np.zeros(n)
    if n == 0 or rate_hz <= 0:
        return y
    expected = rate_hz * n / RATE
    k = r.poisson(max(1.0, expected * (float(np.mean(env)) if env is not None else 1.0)))
    if env is not None and env.max() > 0:
        p = env / env.sum()
        pos = r.choice(n, size=k, p=p)
    else:
        pos = r.integers(0, n, size=k)
    amp = r.uniform(.3, 1.0, size=k) * (env[pos] if env is not None else 1.0)
    np.add.at(y, pos, amp * r.choice((-1.0, 1.0), size=k))
    w = max(2, int(width * RATE))
    kern = np.exp(-np.arange(w) / (w / 4))
    return np.convolve(y, kern)[:n]


def norm(x: np.ndarray, peak: float = .9) -> np.ndarray:
    m = float(np.abs(x).max()) if len(x) else 0.0
    return x * (peak / m) if m > 0 else x


def _at(n_total: int, part: np.ndarray, t0: float) -> np.ndarray:
    out = np.zeros(n_total)
    i = dsp.samples(t0)
    if i < n_total:
        k = min(len(part), n_total - i)
        out[i:i + k] = part[:k]
    return out


# ---------------------------------------------------------------- surfaces
# What a floor does when a heel lands on it: its resonant modes (Hz, decay s, level), how stiff it is (a contact on it
# lasts this long, s), how much grit or fibre it adds, and how much it hides the high end.
FLOORS = dict(
    # boards on joists: a hollow, woody knock with a short ring in the low mids
    wood=dict(modes=([105, 182, 296, 451, 652, 905, 1290, 1820], [.06, .045, .035, .028, .02, .015, .011, .008],
                     [1.0, .8, .65, .5, .38, .28, .2, .12]), tau=.0035, grit=0.0, dark=5200, thump=.55),
    # ceramic tiles on a concrete screed: stiff and bright, a click with almost no ring below
    tile=dict(modes=([920, 1730, 2650, 3800, 5150, 6900], [.012, .009, .007, .005, .004, .003], [.5, .75, 1.0, .8, .55, .35]),
              tau=.0016, grit=.25, dark=11000, thump=.3),
    # stone flags: like tile, heavier and a little lower
    stone=dict(modes=([640, 1310, 2140, 3300, 4700], [.014, .01, .008, .006, .004], [.6, .9, 1.0, .7, .4]),
               tau=.002, grit=.35, dark=9000, thump=.4),
    # carpet over a floor: the pile soaks up the contact; a soft thump and the brush of fibres
    carpet=dict(modes=([88, 160, 280], [.03, .02, .012], [1.0, .45, .2]), tau=.014, grit=.12, dark=1500, thump=.8),
    # a rug on boards: between the two
    rug=dict(modes=([100, 175, 290, 445], [.04, .03, .02, .014], [1.0, .6, .35, .2]), tau=.009, grit=.1, dark=2600, thump=.7),
    # paving outside: gritty, dry, no room to ring in
    pavement=dict(modes=([520, 1150, 2300, 3700], [.008, .006, .004, .003], [.7, 1.0, .8, .45]), tau=.0022, grit=.8,
                  dark=9500, thump=.35),
)
SHOES = dict(hard=1.0, soft=1.9, heel=.7)     # how long a sole's contact lasts, relative to a leather sole's


def surface_of(name: str | None) -> str:
    """A floor's kind from a set's material name (engine/clay/sets.py): wood, tile, stone, carpet, rug or pavement."""
    n = (name or "").lower()
    for key in ("rug", "carpet", "tile", "stone", "pavement", "wood"):
        if key in n:
            return key
    if "plank" in n or "board" in n:
        return "wood"
    if "street" in n or "floor" in n:
        return "pavement"
    return "wood"


def footstep(surface: str = "wood", shoe: str = "hard", weight: float = 1.0, speed: float = 1.0, seed=0) -> np.ndarray:
    """One step: the heel strikes, the foot rolls, the ball comes down (sooner when walking quickly), and on a gritty
    surface the sole scuffs a little as it rolls. weight 1 is an average adult, speed 1 an ordinary walk."""
    fl = FLOORS.get(surface, FLOORS["wood"])
    r = dsp.rng("step", seed)
    n = dsp.samples(.42)
    fr, dc, am = fl["modes"]
    tau = fl["tau"] * SHOES.get(shoe, 1.0) * (1.0 + .25 * r.uniform(-1, 1))
    force = (.75 + .25 * min(2.0, weight)) * (.8 + .2 * min(1.6, speed)) * (1.0 + .12 * r.uniform(-1, 1))
    ir = modes(fr, dc, am, n, r, detune=.04)
    # the body of the step: the floor and the leg take the weight, a low thump under everything
    body = modes([62 + 10 * r.uniform(-1, 1), 118], [.035, .02], [1.0, .4], n, r) * fl["thump"]
    heel = struck(ir + body, tau)
    # a small slap of the sole itself, brighter on hard floors
    slap = dsp.noise(dsp.samples(.02), r, dsp.bandpass(900, fl["dark"])) * dsp.attack_decay(dsp.samples(.02), .0005, .004)
    heel[:len(slap)] += .35 * slap * (1.0 - min(1.0, fl["tau"] / .015))
    # the ball of the foot, 50 to 110 ms later, lighter, and the roll between them
    gap = (.105 - .03 * min(1.5, speed)) * (1.0 + .15 * r.uniform(-1, 1))
    ball = struck(modes(fr, dc, am, n, r, detune=.05) + .5 * body, tau * .8) * .42 * (1.0 + .2 * r.uniform(-1, 1))
    y = heel + _at(n, ball, gap)[:n]
    if fl["grit"] > 0:
        roll = dsp.attack_decay(n, gap * .6, .03, t0=.004)
        grit = grains(n, 2600, r, .0008, roll)
        y += fl["grit"] * .5 * dsp.shape(grit, dsp.bandpass(1400, fl["dark"]))
    y = dsp.shape(y, dsp.lowpass(fl["dark"], 2))
    return norm(y) * force


# ---------------------------------------------------------------- sitting, standing, chairs
def sit(soft: float = 0.0, weight: float = 1.0, wood: bool = True, seed=0) -> np.ndarray:
    """A body coming to rest on a seat. soft > 0 (a cushion's give, as engine/clay/setkit measures it): the air pushed
    out of the cushion and the cloth under the weight; soft == 0: a knock into a hard seat, and a creak if it is wood."""
    r = dsp.rng("sit", seed)
    n = dsp.samples(.9)
    w = min(2.0, max(.4, weight))
    thump = struck(modes([48 + 8 * r.uniform(-1, 1), 86, 140], [.09, .06, .03], [1.0, .5, .2], n, r), .02 + .03 * min(1.0, soft * 8))
    if soft > 0:
        # the cushion gives: a breath of air pushed out of it, low and soft, and the cover rubbing under the weight
        air = dsp.noise(n, r, dsp.bandpass(90, 700)) * dsp.attack_decay(n, .06, .2, t0=.01)
        cloth = grains(n, 900, r, .002, dsp.attack_decay(n, .05, .25)) * .6
        cloth = dsp.shape(cloth, dsp.bandpass(1200, 5500))
        y = .9 * thump + .5 * air + .22 * cloth
    else:
        frm = modes([170, 310, 520, 860, 1240], [.06, .05, .04, .03, .02], [1.0, .8, .6, .4, .25], n, r, detune=.05)
        y = .8 * thump + .55 * struck(frm, .006)
        if wood:
            y += .25 * _at(n, creak(.35, seed=seed), .03)
    return norm(y) * (.7 + .3 * w)


def stand(soft: float = 0.0, seed=0) -> np.ndarray:
    """Getting up: the weight leaving the seat (a cushion breathes back in), the cloth moving, a lighter knock."""
    r = dsp.rng("stand", seed)
    n = dsp.samples(.8)
    cloth = dsp.shape(grains(n, 700, r, .002, dsp.attack_decay(n, .15, .3)), dsp.bandpass(1000, 5000))
    if soft > 0:
        air = dsp.noise(n, r, dsp.bandpass(80, 600)) * dsp.attack_decay(n, .25, .25, t0=.05)
        y = .6 * air + .35 * cloth
    else:
        y = .45 * cloth + .3 * _at(n, creak(.3, seed=seed), .05)
    return norm(y) * .55


def creak(seconds: float = .4, pitch: float = 1.0, seed=0) -> np.ndarray:
    """Wood under strain: stick-slip, a run of tiny slips that speeds up and slows down, through the wood's resonances."""
    r = dsp.rng("creak", seed)
    n = dsp.samples(seconds)
    t = np.arange(n) / RATE
    env = np.sin(math.pi * np.clip(t / max(seconds, 1e-3), 0, 1)) ** 2
    rate_ = (180 + 260 * env) * pitch
    phase = np.cumsum(rate_ / RATE)
    pulses = np.diff(np.floor(phase), prepend=0.0) * (r.uniform(.6, 1.0, n))
    ir = modes([410 * pitch, 780 * pitch, 1330 * pitch, 2100 * pitch], [.012, .009, .006, .004], [1.0, .7, .45, .25], dsp.samples(.05), r)
    y = np.convolve(pulses, ir)[:n] * env
    return norm(y) * .5


def scrape(seconds: float, surface: str = "wood", seed=0, profile: np.ndarray | None = None) -> np.ndarray:
    """A chair or a table leg dragged across a floor: friction grains at a rate that follows how fast it moves (profile,
    0..1 per sample), through the legs' resonance; a carpet or a rug swallows most of it."""
    r = dsp.rng("scrape", seed)
    n = dsp.samples(seconds)
    if n == 0:
        return np.zeros(0)
    env = profile if profile is not None and len(profile) == n else np.sin(math.pi * np.linspace(0, 1, n)) ** 1.2
    soft = surface in ("carpet", "rug")
    g = grains(n, 5200 if not soft else 1800, r, .0006, env)
    legs = modes([620, 1150, 1900, 2800], [.01, .008, .006, .004], [1.0, .7, .5, .3], dsp.samples(.04), r)
    y = np.convolve(g, legs)[:n]
    y += .4 * dsp.noise(n, r, dsp.bandpass(300, 3000)) * env
    y = dsp.shape(y, dsp.lowpass(900 if soft else 6000, 2))
    return norm(y) * (.35 if soft else .8)


# ---------------------------------------------------------------- doors
def door_latch(seed=0) -> np.ndarray:
    """A handle turned and the latch bolt drawn back: two small metal clicks."""
    r = dsp.rng("latch", seed)
    n = dsp.samples(.35)
    def click():
        return struck(modes([2350, 3600, 5100, 7300], [.012, .009, .006, .004], [.7, 1.0, .7, .4], n, r, detune=.04), .0004)

    y = click() + .7 * _at(n, click(), .11 + .03 * r.uniform(-1, 1))
    return norm(y) * .45


def door_open(seconds: float = .8, seed=0) -> np.ndarray:
    """The latch, then the leaf swinging: a breath of moving air and, sometimes, a hinge that speaks."""
    r = dsp.rng("dooropen", seed)
    n = dsp.samples(max(.6, seconds))
    y = _at(n, door_latch(seed), 0.0)
    swing = dsp.noise(n, r, dsp.bandpass(60, 500)) * dsp.attack_decay(n, seconds * .4, seconds * .35, t0=.12)
    y += .25 * swing
    if r.uniform() < .5:
        y += _at(n, .35 * creak(min(.6, seconds * .6), pitch=1.6 + .3 * r.uniform(), seed=seed), .18)
    return norm(y) * .6


def door_close(seed=0) -> np.ndarray:
    """A door pushed to: the leaf meets the frame (a heavy panel ringing low), and the latch snaps home."""
    r = dsp.rng("doorclose", seed)
    n = dsp.samples(.6)
    panel = struck(modes([68, 104, 152, 236, 410, 690], [.12, .1, .07, .05, .03, .02], [1.0, .8, .6, .4, .25, .15], n, r, .04), .005)
    latch = struck(modes([1900, 3100, 4600, 6500], [.02, .014, .01, .006], [.8, 1.0, .7, .4], n, r, .04), .0005)
    rattle = grains(n, 400, r, .001, dsp.attack_decay(n, .002, .05)) * .3
    return norm(panel + .6 * latch + rattle) * .9


# ---------------------------------------------------------------- things on tables
def laptop_close(seed=0) -> np.ndarray:
    """A laptop's lid coming down onto its base: the hinge eases it the last centimetres, so it is a soft plastic knock
    and the click of the magnet that holds it."""
    r = dsp.rng("laptop", seed)
    n = dsp.samples(.35)
    shell = struck(modes([880, 1640, 2580, 3870, 5300], [.018, .014, .01, .007, .005], [.7, 1.0, .8, .5, .3], n, r, .03), .0025)
    body = struck(modes([140, 255, 420], [.035, .025, .015], [1.0, .6, .3], n, r), .004)
    magnet = struck(modes([4200, 6100], [.004, .003], [1.0, .6], n, r), .0003)
    return norm(shell + .7 * body + .25 * _at(n, magnet, .004)) * .6


def laptop_open(seed=0) -> np.ndarray:
    """A lid lifted: the magnet lets go, and the hinge turns stiffly."""
    r = dsp.rng("laptopopen", seed)
    n = dsp.samples(.5)
    release = struck(modes([3900, 5600], [.004, .003], [1.0, .5], n, r), .0004)
    hinge = dsp.shape(grains(n, 1600, r, .0007, dsp.attack_decay(n, .1, .15, t0=.03)), dsp.bandpass(900, 4500))
    return norm(.6 * release + .5 * hinge) * .3


def set_down(material: str = "ceramic", on: str = "wood", seed=0) -> np.ndarray:
    """A thing put down on a table: the thing rings (a ceramic mug high and pure, a phone dull) and the top knocks."""
    r = dsp.rng("setdown", material, on, seed)
    n = dsp.samples(.5)
    things = dict(ceramic=([1180, 2950, 4870, 6400], [.08, .05, .03, .02], [1.0, .6, .35, .2], .0012),
                  phone=([1450, 3300, 5200], [.012, .008, .005], [1.0, .6, .3], .0015),
                  paper=([400, 900], [.006, .004], [1.0, .5], .006))
    fr, dc, am, tau = things.get(material, things["ceramic"])
    thing = struck(modes(fr, dc, am, n, r, .03), tau)
    top = struck(modes([150, 260, 410, 640, 980], [.05, .04, .03, .02, .015], [1.0, .8, .6, .4, .25], n, r, .04), tau * 2)
    return norm(.6 * thing + .8 * top) * .55


# ---------------------------------------------------------------- keyboards and phones
def keystroke(space: bool = False, seed=0) -> np.ndarray:
    """One key of a laptop keyboard: the cap bottoms out with a plastic tick and a small knock into the deck, and on the
    way back up a fainter click. The space bar is lower and rattles on its stabiliser."""
    r = dsp.rng("key", seed)
    n = dsp.samples(.2)
    lo = .75 if space else 1.0
    down = struck(modes([2600 * lo, 3900 * lo, 5600 * lo], [.006, .004, .003], [1.0, .7, .4], n, r, .06), .0006)
    deck = struck(modes([420 * lo, 760 * lo, 1250 * lo], [.012, .008, .005], [1.0, .6, .3], n, r, .05), .0015)
    up = struck(modes([3100, 4700], [.004, .003], [1.0, .5], n, r, .06), .0005)
    y = down + .6 * deck + .25 * _at(n, up, .07 + .03 * r.uniform())
    if space:
        y += .3 * grains(n, 2000, r, .0005, dsp.attack_decay(n, .001, .02))
    return norm(y) * (.55 + .2 * r.uniform())


def typing_times(seconds: float, seed=0, rate: float = 4.2) -> list[tuple[float, bool]]:
    """When the keys go down while somebody types for `seconds`: words of three to nine letters at about `rate` keys a
    second, a space between words, now and then a longer pause to think. -> [(time s, is the space bar)]."""
    r = dsp.rng("typing", seed)
    t, out = r.uniform(.05, .25), []
    while t < seconds:
        for _ in range(int(r.integers(3, 10))):
            if t >= seconds:
                break
            out.append((t, False))
            t += float(np.exp(r.normal(math.log(1.0 / rate), .35)))
        if t < seconds:
            out.append((t, True))
            t += float(np.exp(r.normal(math.log(1.6 / rate), .3)))
        if r.uniform() < .12:
            t += r.uniform(.5, 1.4)
    return out


def phone_vibrate(seconds: float = 2.0, on_table: bool = True, seed=0) -> np.ndarray:
    """A phone's motor buzzing in bursts: on a table it rattles against the top; in a hand it is a muffled hum."""
    r = dsp.rng("vibrate", seed)
    n = dsp.samples(seconds)
    t = np.arange(n) / RATE
    f0 = 172 + 6 * r.uniform(-1, 1)
    motor = np.sin(2 * math.pi * f0 * t + .3 * np.sin(2 * math.pi * 3.1 * t))
    gate = ((t % 1.0) < .45).astype(float)
    gate = dsp.smooth(gate, dsp.samples(.012))
    if on_table:
        buzz = np.tanh(3.5 * motor) + .35 * np.sign(motor) * (np.abs(motor) > .92)
        y = dsp.shape(buzz, dsp.bandpass(120, 4200)) * gate
    else:
        y = dsp.shape(motor, dsp.lowpass(400)) * gate * .5
    return norm(y) * .45


# notes as frequencies (equal temperament from A4 = 440 Hz)
def _NOTE(k):
    return 440.0 * 2 ** ((k - 69) / 12)


def _mallet(f: float, n: int, r: np.random.Generator, decay: float = .35) -> np.ndarray:
    """A soft mallet on a tuned bar: the fundamental and the bar's overtones (about 4 and 10 times up, as on a marimba)."""
    return struck(modes([f, 3.98 * f, 9.9 * f], [decay, decay * .25, decay * .1], [1.0, .25, .06], n, r), .002)


def phone_ring(seconds: float = 4.0, seed=0) -> np.ndarray:
    """A phone ringing: an original four-note figure on a soft mallet, repeated every two seconds. Ring tones are
    synthetic by nature, so this one is made, not recorded."""
    r = dsp.rng("ring", seed)
    n = dsp.samples(seconds)
    y = np.zeros(n)
    figure = [(0.0, 79), (.16, 74), (.32, 77), (.48, 84)]
    t0 = 0.0
    while t0 < seconds:
        for dt, k in figure:
            y += _at(n, _mallet(_NOTE(k), dsp.samples(.7), r), t0 + dt)
        t0 += 2.0
    return norm(dsp.shape(y, dsp.highpass(250))) * .6


def notification(seed=0) -> np.ndarray:
    """A message arriving: two quick mallet notes, rising."""
    r = dsp.rng("notify", seed)
    n = dsp.samples(.6)
    y = _mallet(_NOTE(84), n, r, .25) + .9 * _at(n, _mallet(_NOTE(91), n, r, .3), .09)
    return norm(dsp.shape(y, dsp.highpass(300))) * .45


def cloth(seconds: float = .5, amount: float = 1.0, seed=0) -> np.ndarray:
    """Clothes moving with an arm or a turn: the fabric's grain brushing against itself, very quiet."""
    r = dsp.rng("cloth", seed)
    n = dsp.samples(seconds)
    env = dsp.attack_decay(n, seconds * .3, seconds * .3)
    y = dsp.shape(grains(n, 1400, r, .0015, env), dsp.bandpass(900, 6500))
    return norm(y) * .25 * amount


# every effect the engine can place, and the function that makes it (the mixer passes the event's parameters)
MAKERS = dict(footstep=footstep, sit=sit, stand=stand, creak=creak, scrape=scrape, door_latch=door_latch,
              door_open=door_open, door_close=door_close, laptop_close=laptop_close, laptop_open=laptop_open,
              set_down=set_down, keystroke=keystroke, phone_vibrate=phone_vibrate, phone_ring=phone_ring,
              notification=notification, cloth=cloth)
