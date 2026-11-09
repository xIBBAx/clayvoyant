"""Frame-exact timelines.

Every beat lasts a whole number of frames, and every scene's audio has exactly
frames * (48000 / fps) samples, so scenes can be cut, re-rendered and joined without drift.
"""

from __future__ import annotations

import array
import math
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .audio.ffmpeg import RATE, read_pcm, silence_pcm
from .subtitles import Cue, chunk, cues_for_line

INTRO_S = 4.5
TITLE_S = 2.4
OUTRO_S = 6.0
MIN_LINE_S = 1.0
LEAD_IN_S = 0.12  # small breath before a line starts


@dataclass
class Beat:
    kind: str  # intro | title | line | card | takeaway | outro
    frames: int
    text: str = ""
    speaker: str | None = None
    speaker_name: str | None = None
    audio: str | None = None
    audio_offset: int = 0  # frames of lead-in before the audio starts
    env: list[float] = field(default_factory=list)
    cues: list[tuple[float, float, str]] = field(default_factory=list)  # seconds, relative to the beat
    line_id: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class SceneTimeline:
    id: str
    title: str
    language: str
    fps: int
    beats: list[Beat]
    cast: list[str]
    headline: str = ""
    setting: dict = field(default_factory=dict)

    @property
    def frames(self) -> int:
        return sum(b.frames for b in self.beats)

    @property
    def seconds(self) -> float:
        return self.frames / self.fps

    def to_json(self) -> dict:
        return asdict(self)


def frames_for(seconds: float, fps: int) -> int:
    return max(1, int(math.ceil(seconds * fps - 1e-9)))


def reading_seconds(text: str, minimum: float = 3.0) -> float:
    return max(minimum, 1.4 + len(text) / 14.0)


def envelope(wav_path: Path, fps: int, smooth: int = 2) -> list[float]:
    """Per-frame speech energy in 0..1 (used for a gentle 'talking' motion)."""
    with wave.open(str(wav_path)) as w:
        data = array.array("h")
        data.frombytes(w.readframes(w.getnframes()))
    step = RATE // fps
    vals = []
    for i in range(0, len(data), step):
        seg = data[i:i + step]
        if not seg:
            break
        vals.append(math.sqrt(sum(x * x for x in seg[::4]) / max(1, len(seg[::4]))))
    peak = max(vals) if vals else 0
    if peak <= 0:
        return [0.0] * len(vals)
    vals = [v / peak for v in vals]
    out = []
    for i in range(len(vals)):
        window = vals[max(0, i - smooth): i + smooth + 1]
        out.append(round(sum(window) / len(window), 3))
    return out


def line_beat(*, text: str, speaker: str, speaker_name: str, wav: Path, seconds: float, pause: float,
              fps: int, line_id: str) -> Beat:
    lead = frames_for(LEAD_IN_S, fps)
    body = frames_for(max(seconds + pause, MIN_LINE_S), fps)
    end_s = (lead / fps) + seconds
    cues = [(c.start, c.end, c.text) for c in
            cues_for_line(text, lead / fps, min(end_s + 0.25, (lead + body) / fps), speaker=speaker_name, line_id=line_id)]
    return Beat("line", lead + body, text, speaker, speaker_name, str(wav), lead,
                [0.0] * lead + envelope(wav, fps), cues, line_id)


def scene_audio(tl: SceneTimeline) -> bytes:
    """Exactly frames * RATE / fps samples of 16-bit mono PCM."""
    per_frame = RATE // tl.fps
    out = bytearray()
    for b in tl.beats:
        want = b.frames * per_frame * 2
        chunk_bytes = bytearray(silence_pcm(b.audio_offset / tl.fps))
        if b.audio:
            chunk_bytes += read_pcm(Path(b.audio))
        if len(chunk_bytes) > want:
            chunk_bytes = chunk_bytes[:want]
        chunk_bytes += b"\x00" * (want - len(chunk_bytes))
        out += chunk_bytes
    return bytes(out)


def film_cues(timelines: list[SceneTimeline]) -> list[Cue]:
    cues, t0 = [], 0.0
    for tl in timelines:
        t = t0
        for b in tl.beats:
            for (s, e, text) in b.cues:
                cues.append(Cue(round(t + s, 3), round(t + e, 3), text, b.speaker_name, b.line_id))
            t += b.frames / tl.fps
        t0 += tl.frames / tl.fps
    return cues


__all__ = ["Beat", "SceneTimeline", "frames_for", "reading_seconds", "envelope", "line_beat", "scene_audio",
           "film_cues", "chunk", "INTRO_S", "TITLE_S", "OUTRO_S"]
