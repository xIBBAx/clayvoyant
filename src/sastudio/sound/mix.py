"""The film's soundtrack, mixed the way a film is: dialogue first, everything else set under it.

Four buses, each a stereo track the length of the film at 48 kHz:

- dialogue: the spoken lines, in the middle, as the build timed them;
- effects: every sound event placed on the sample where the picture shows its cause (sound.events), panned toward
  where it happens, then played in the scene's room (sound.ambience): the direct sound and the room's answer;
- ambience: the air of each place, the length of its scene, never looped, crossfaded at a change of place;
- music: your tracks, loudness-matched, with fades and crossfades, dipping under speech.

Levels are set from what is measured, not guessed: the dialogue's loudness is the reference (BS.1770, sound.meter),
each bed sits a set number of loudness units under it, and each music file is measured and brought to its place.
The music dips by an envelope computed from the dialogue itself, with look-ahead (it starts to dip just before the
first syllable), hold (it stays down through the gaps between words) and slow release, so it never pumps.

Everything is placed by sample in numpy (no mixer that renormalises as inputs come and go), so a sound lands exactly
where it should, and the same project gives the same soundtrack every time."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import ambience, dsp, meter
from .dsp import RATE
from .events import Event
from .kit import Kit, decode

REFERENCE = -20.0   # the dialogue level assumed when a film has no audible dialogue (silent placeholder voices)
# How far each place's air sits under the dialogue (LU): a quiet home barely there, a cafe and a street more present.
BED_LU = dict(studio=-34.0, home=-30.0, classroom=-29.0, quiet_office=-30.0, office=-27.0, corridor=-27.0, cafe=-20.0,
              street=-22.0, file=-24.0)


@dataclass
class Levels:
    effects: float = -10.0    # dB: an ordinary action (a firm footstep) peaks about this far under the dialogue's peaks
    ambience: float = 0.0     # dB added to every place's air (BED_LU)
    music: float = -11.0      # LU: the music under the dialogue's loudness, while nobody speaks
    duck: float = 11.0        # dB the music dips further while somebody speaks


@dataclass
class MusicCue:
    file: Path
    scenes: tuple | None = None     # the scenes it plays under; None: the whole film
    start: float = 0.0              # seconds into the track where it starts
    level: float | None = None      # LU under the dialogue (None: Levels.music)
    fade_in: float = 1.5
    fade_out: float = 2.5
    loop: bool = True


@dataclass
class SceneMix:
    id: str
    start: int                      # the scene's first sample in the film
    length: int                     # samples
    room: dict | None = None        # ambience.ROOMS entry; None: no room (a title card)
    bed: str | None = None          # an ambience.BEDS kind, 'file', or None for no air
    bed_file: Path | None = None
    bed_db: float = 0.0             # added to the bed's level
    events: list = field(default_factory=list)
    music: bool = True              # False: no music under this scene
    effects: bool = True


@dataclass
class MixReport:
    dialogue_lufs: float | None = None
    stems: dict = field(default_factory=dict)        # bus -> integrated LUFS (None when silent)
    events: int = 0
    sources: dict = field(default_factory=dict)      # where the effects came from: 'made by code' / 'file:...' -> count
    music: list = field(default_factory=list)        # one row per cue: file, measured LUFS, gain dB, spans
    warnings: list = field(default_factory=list)


# ---------------------------------------------------------------- placing
def place(dst: np.ndarray, clip: np.ndarray, at: int, g: float = 1.0, pan: float = 0.0) -> None:
    """Add a clip (mono or stereo) into dst (n, 2) from sample `at`, at gain g, panned (mono clips only)."""
    if at >= len(dst) or g == 0 or len(clip) == 0:
        return
    st = dsp.pan(clip, pan) if clip.ndim == 1 else dsp.to_stereo(clip)
    i0 = max(0, at)
    j0 = i0 - at
    k = min(len(st) - j0, len(dst) - i0)
    if k > 0:
        dst[i0:i0 + k] += g * st[j0:j0 + k]


def pan_of(e: Event, room: dict | None) -> float:
    """Toward where it happens: across the room seen from the front, kept subtle (cuts change the view, not the room)."""
    if e.pos is None or not room or not room.get("size"):
        return 0.0
    half = room["size"][0] / 2
    return max(-1.0, min(1.0, float(e.pos[0]) / half)) * .35


# ---------------------------------------------------------------- the buses
def effects_bus(scenes: list[SceneMix], n: int, kit: Kit, rep: MixReport) -> np.ndarray:
    """Every scene's events in its own room."""
    out = np.zeros((n, 2))
    for sc in scenes:
        if not sc.effects or not sc.events:
            continue
        tail = dsp.samples(2.0)
        buf = np.zeros((sc.length + tail, 2))
        for e in sc.events:
            clip, src = kit.clip(e)
            rep.sources[src.split(":")[0] if src.startswith("file:") else src] = \
                rep.sources.get(src.split(":")[0] if src.startswith("file:") else src, 0) + 1
            place(buf, clip, dsp.samples(e.t), 1.0, pan_of(e, sc.room))
            rep.events += 1
        if sc.room is not None:
            t60 = ambience.rt60(sc.room)
            wet = .07 if t60 <= 0 else .12 + .12 * min(1.0, t60 / 1.0)
            buf = ambience.reverberate(buf, sc.room, wet, seed=sc.id)
        place(out, buf, sc.start)
    return out


def _bed_audio(sc: SceneMix, n_tail: int) -> np.ndarray:
    """A scene's air, n samples (its length plus the crossfade into the next), at the level BED_LU asks for when the
    dialogue sits at 0 LU (the mixer moves it with the dialogue)."""
    n = sc.length + n_tail
    if sc.bed == "file" and sc.bed_file is not None:
        src = decode(sc.bed_file)
        if len(src) == 0:
            return np.zeros((n, 2))
        x = _loop(src, n, xfade=min(2.0, len(src) / RATE / 4))
    elif sc.bed in ambience.BEDS:
        x = ambience.bed(sc.bed, n / RATE, seed=sc.id)[:n]
    else:
        return np.zeros((n, 2))
    lu = meter.integrated(x)
    if lu is None:
        return x
    return x * dsp.gain(BED_LU.get(sc.bed, BED_LU["file"]) + sc.bed_db - lu)


def ambience_bus(scenes: list[SceneMix], n: int, ref: float, extra_db: float) -> np.ndarray:
    """Each scene's bed. At a cut between two places the old air carries on a moment past the cut and fades as the new
    one comes in (an equal-power crossfade, up to a second, never more than a quarter of either scene); a bed with
    nothing before it rises over a quarter of a second, and with nothing after it falls away over half a second."""
    out = np.zeros((n, 2))
    xfs = []
    for a, b in zip(scenes, scenes[1:], strict=False):
        both = a.bed is not None and b.bed is not None
        xfs.append(dsp.samples(min(1.0, a.length / RATE / 4, b.length / RATE / 4)) if both else 0)
    for i, sc in enumerate(scenes):
        if sc.bed is None:
            continue
        tail = xfs[i] if i < len(xfs) else 0
        lead = xfs[i - 1] if i > 0 else 0
        x = _bed_audio(sc, tail) * dsp.gain(ref + extra_db)
        k = lead or min(len(x), dsp.samples(.25))
        x[:k] *= dsp.fade_in(k)[:, None]
        k = tail or min(len(x), dsp.samples(.5))
        x[len(x) - k:] *= dsp.fade_out(k)[:, None]
        place(out, x, sc.start)
    return out


def _loop(src: np.ndarray, n: int, xfade: float = 1.5) -> np.ndarray:
    """src repeated to n samples, each seam crossfaded (equal power) over xfade seconds."""
    if len(src) >= n:
        return src[:n].copy()
    k = max(1, min(dsp.samples(xfade), len(src) // 3))
    out = np.zeros((n, src.shape[1]))
    pos = 0
    fi, fo = dsp.fade_in(k)[:, None], dsp.fade_out(k)[:, None]
    while pos < n:
        seg = src.copy()
        if pos > 0:
            seg[:k] *= fi
        seg[-k:] *= fo
        m = min(len(seg), n - pos)
        out[pos:pos + m] += seg[:m]
        pos += len(seg) - k
    return out


def duck_curve(dialogue: np.ndarray, depth_db: float, lookahead: float = .15, attack: float = .12, hold: float = .45,
               release: float = .6, gate_db: float = -45.0) -> np.ndarray:
    """A gain for the music, sample by sample: 1 where nobody speaks, down to -depth_db while somebody does. Speech is
    found in 10 ms blocks of the dialogue; gaps shorter than `hold` count as speech (no rise between words); the dip
    starts `lookahead` before the first syllable; it goes down over `attack` and comes back up over `release`."""
    n = len(dialogue)
    if n == 0 or depth_db <= 0:
        return np.ones(n)
    B = dsp.samples(.01)
    nb = (n + B - 1) // B
    x = dialogue if dialogue.ndim == 1 else dialogue.mean(axis=1)
    pad = np.zeros(nb * B)
    pad[:n] = x
    rms = np.sqrt((pad.reshape(nb, B) ** 2).mean(axis=1))
    on = rms > dsp.gain(gate_db)
    # hold: fill short gaps
    h = int(round(hold / .01))
    idx = np.nonzero(on)[0]
    if len(idx):
        gaps = np.diff(idx)
        for a, g in zip(idx[:-1], gaps, strict=True):
            if 1 < g <= h:
                on[a:a + g] = True
    # look-ahead: begin before speech
    la = int(round(lookahead / .01))
    if la > 0 and on.any():
        on = on | np.concatenate([on[la:], np.zeros(la, bool)])
    # ease down and up at the speeds asked for
    down, up = .01 / max(attack, .01), .01 / max(release, .01)
    a = np.zeros(nb)
    v = 0.0
    for i in range(nb):
        v = min(1.0, v + down) if on[i] else max(0.0, v - up)
        a[i] = v
    a = a * a * (3 - 2 * a)            # a smoothstep on each ramp: no corners
    g = dsp.gain(-depth_db) ** a
    return np.interp(np.arange(n), np.arange(nb) * B + B / 2, g)


def music_bus(cues: list[MusicCue], scenes: list[SceneMix], n: int, ref: float, levels: Levels, rep: MixReport) -> np.ndarray:
    """Each cue under its scenes (or the whole film), at its level under the dialogue, faded in and out; where one cue
    hands over to the next the two cross (equal power) at the boundary. Scenes marked music: off are left quiet."""
    out = np.zeros((n, 2))
    by_id = {sc.id: sc for sc in scenes}
    for cue in cues:
        src = decode(cue.file)
        if len(src) == 0:
            rep.warnings.append(f"{cue.file.name}: no audio in it; left out")
            continue
        start = min(len(src) - 1, dsp.samples(cue.start))
        body = src[start:]
        lu = meter.integrated(body)
        if lu is None:
            rep.warnings.append(f"{cue.file.name}: silent; left out")
            continue
        g_db = ref + (cue.level if cue.level is not None else levels.music) - lu
        # where it plays: the whole film, or each run of consecutive listed scenes
        if cue.scenes is None:
            spans = [(0, n)]
        else:
            spans = []
            for sc in scenes:
                if sc.id not in cue.scenes:
                    continue
                if spans and spans[-1][1] == sc.start:
                    spans[-1] = (spans[-1][0], sc.start + sc.length)       # the next scene of a run: one span
                else:
                    spans.append((sc.start, sc.start + sc.length))
            missing = [s for s in cue.scenes if s not in by_id]
            if missing:
                rep.warnings.append(f"{cue.file.name}: no scene called {', '.join(missing)}")
        fi, fo = dsp.samples(cue.fade_in), dsp.samples(cue.fade_out)
        for s0, s1 in spans:
            a = max(0, s0 - (fi // 2 if s0 > 0 else 0))
            b = min(n, s1 + (fo // 2 if s1 < n else 0))
            want = b - a
            x = _loop(body, want) if cue.loop else body[:want].copy()
            if len(x) < want and not cue.loop:
                x = np.concatenate([x, np.zeros((want - len(x), 2))])
                end = len(body)
                k = min(fo, end)
                x[end - k:end] *= dsp.fade_out(k)[:, None]      # a track that ends before its scenes do fades as it ends
            k = min(fi, len(x))
            x[:k] *= dsp.fade_in(k)[:, None]
            k = min(fo, len(x))
            x[len(x) - k:] *= dsp.fade_out(k)[:, None]
            place(out, x, a, dsp.gain(g_db))
        rep.music.append(dict(file=cue.file.name, lufs=round(lu, 1), gain_db=round(g_db, 1),
                              spans=[(round(s0 / RATE, 2), round(s1 / RATE, 2)) for s0, s1 in spans], loop=cue.loop))
    # scenes that asked for no music: it fades out before them and back in after (a second each way)
    for sc in scenes:
        if sc.music:
            continue
        m = np.ones(n)
        k = dsp.samples(1.0)
        a, b = sc.start, sc.start + sc.length
        m[a:b] = 0.0
        lo = max(0, a - k)
        m[lo:a] = dsp.fade_out(a - lo)
        hi = min(n, b + k)
        m[b:hi] = dsp.fade_in(hi - b)
        out *= m[:, None]
    return out


# ---------------------------------------------------------------- the mix
def mix(dialogue: np.ndarray, scenes: list[SceneMix], cues: list[MusicCue], levels: Levels, kit: Kit) -> tuple[np.ndarray, dict, MixReport]:
    """dialogue (n,) mono -> (the mixed film (n, 2), the four buses by name, a report of what was measured and used)."""
    n = len(dialogue)
    rep = MixReport()
    d = dsp.to_stereo(dialogue.astype(float))
    rep.dialogue_lufs = meter.integrated(d)
    ref = rep.dialogue_lufs if rep.dialogue_lufs is not None else REFERENCE
    fx = effects_bus(scenes, n, kit, rep)
    # an ordinary action peaks `levels.effects` under the dialogue's peaks (lines are levelled to about -18 LUFS)
    fx *= dsp.gain(levels.effects + (ref + 18.0))
    amb = ambience_bus(scenes, n, ref, levels.ambience)
    mus = music_bus(cues, scenes, n, ref, levels, rep)
    if mus.any():
        mus *= duck_curve(dialogue, levels.duck)[:, None]
    buses = dict(dialogue=d, effects=fx, ambience=amb, music=mus)
    for k, v in buses.items():
        lu = meter.integrated(v) if v.any() else None
        rep.stems[k] = round(lu, 2) if lu is not None else None
    return d + fx + amb + mus, buses, rep
