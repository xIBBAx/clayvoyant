"""Sound events: what happens in a scene that makes a sound, when, where, and who or what makes it.

Events come from two places. The engine reports what its characters and props actually do (engine/clay/sounds.py
reads the scene's own plan: every footfall where a foot comes down, every sit and stand, a door's swing, a laptop's
lid, a chair drawn in, typing hands on a keyboard), so a footstep is heard only where a foot lands. The scene's
direction adds cues for sounds no motion makes (a phone ringing, a message arriving, a knock). Nothing is ever added
because of a word in the dialogue.

Events are found once per scene, on the scene's own clock, not per shot: two shots that both show a footstep can never
both play it, and a sound runs on across a cut as the action does. Each event has a stable identity, so the same film
gives the same events and a changed one is easy to find."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field

# every kind of event the engine or a cue can place, and what each needs
KINDS = {
    "footstep": "a foot coming down (surface, shoe, weight, speed)",
    "sit": "a body coming to rest on a seat (soft: the cushion's give)",
    "stand": "a body leaving a seat",
    "scrape": "a chair drawn in or pushed back across the floor (duration)",
    "door_open": "a door opened: latch and swing",
    "door_close": "a door pushed to: panel and latch",
    "laptop_close": "a laptop's lid coming down",
    "laptop_open": "a laptop's lid lifted",
    "typing": "hands typing on a keyboard (duration)",
    "set_down": "something put down on a table (material)",
    "phone_ring": "a phone ringing (duration)",
    "phone_vibrate": "a phone vibrating (duration, on_table)",
    "notification": "a message arriving on a phone",
    "knock": "a knock on a door",
    "file": "a sound file of your own",
}
ENGINE_KINDS = ("footstep", "sit", "stand", "scrape", "door_open", "door_close", "laptop_close", "laptop_open", "typing")
CUE_KINDS = ("phone_ring", "phone_vibrate", "notification", "knock", "door_open", "door_close", "laptop_close",
             "laptop_open", "set_down", "typing", "file")
DEDUPE_S = .15      # the same kind of sound from the same thing within this long is one sound


@dataclass(frozen=True)
class Event:
    kind: str
    t: float                          # seconds on the scene's clock (its first frame is 0), when the sound begins
    scene: str
    who: str | None = None            # the character who makes it, if one does
    thing: str | None = None          # the object that makes it (door, laptop, chair, phone...)
    surface: str | None = None        # what it happens on (wood, tile, carpet, rug, stone, pavement)
    intensity: float = 1.0            # 1 is ordinary; a hurried step or a slammed door is more
    duration: float = 0.0             # seconds, for sounds that last (typing, a scrape, a ring)
    pos: tuple | None = None          # where in the set (metres from the set's centre, floor height 0)
    params: dict = field(default_factory=dict, hash=False, compare=False)
    source: str = "engine"            # 'engine' (from motion), 'cue' (the direction asked for it)
    frame: float | None = None        # the scene frame it comes from (engine events)

    @property
    def id(self) -> str:
        """Stable: the same event of the same scene always has the same id (and the same sound)."""
        key = json.dumps([self.scene, self.kind, self.who, self.thing, round(self.t, 3), self.source], sort_keys=True)
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_json(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d

    @staticmethod
    def from_json(d: dict) -> Event:
        d = {k: v for k, v in d.items() if k != "id"}
        if d.get("pos") is not None:
            d["pos"] = tuple(d["pos"])
        return Event(**d)


def snap_to_drawings(frame: float, beats: list[tuple[int, int]], step: int = 2) -> float:
    """The scene frame at which a drawing first shows something that happens at `frame`. Clay is drawn on twos: each
    drawing is held for `step` frames, and the drawings of a beat (start, length) are at start, start + step, ... A
    sound must not come before the picture shows its cause, nor wait longer than one drawing for it."""
    for b0, n in beats:
        if b0 <= frame < b0 + n:
            k = math.ceil((frame - b0) / step - 1e-9)
            # past the beat's last drawing: the next drawing is the first of the next beat, which starts where this ends
            return float(min(b0 + k * step, b0 + n))
    return float(frame)


def dedupe(events: list[Event]) -> list[Event]:
    """One sound per action: events of the same kind from the same thing (or person) closer than DEDUPE_S are one, and
    a cue the direction asked for wins over the same sound found in the motion (it says what the director wants)."""
    out: list[Event] = []
    for e in sorted(events, key=lambda e: (e.source != "cue", e.t)):       # the director's cues first
        if e.kind != "footstep":
            twin = next((o for o in out if o.kind == e.kind and (o.thing or o.who) == (e.thing or e.who)
                         and abs(o.t - e.t) < DEDUPE_S), None)
            if twin is not None:
                continue
        out.append(e)
    return sorted(out, key=lambda e: e.t)


def load(path) -> list[Event]:
    return [Event.from_json(d) for d in json.loads(open(path, encoding="utf-8").read())]


def save(path, events: list[Event]) -> None:
    from ..safepath import atomic_write_text
    atomic_write_text(path, json.dumps([e.to_json() for e in events], indent=1, ensure_ascii=False))
