"""Clay stop motion: turns a project's scenes into shots for the clay engine and films them in Blender.

The work is split in two. This module, in ordinary Python, reads the project, the shot plan (sastudio.direction) and
the timing of the voices, and writes a *job* for each shot: the set, the light, the cast, every spoken line with its
mouth shapes, every acting key and a camera. The engine (engine/clay/film.py), inside Blender, builds the scene and
films the frames. Acting is a pure function of the frame, so shots of one scene always agree, a changed line only
re-films the shots it can affect, and an interrupted shot resumes at its first missing frame.

Films are animated on twos (twelve drawings a second, each held for two frames), the cadence of stop motion.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .. import claydesign, lipsync
from .. import direction as D
from ..errors import ConfigError, RenderError, ToolMissing
from ..render import clay


class ContactError(RenderError):
    """A shot refused before filming: a body would pass through something (engine/clay/contacts.py)."""

FPS = 24
STEP = 2
ENGINE_NAME = "Sultan"   # the clay engine (engine/clay), named after Ibrahim Sultan, who made Clayvoyant
ENGINE_VERSION = "11"  # bump when the engine changes what it draws: every cached shot is filmed again
PRESETS = {"draft": (960, 540, 6), "preview": (1280, 720, 12), "final": (1920, 1080, 24)}
LEAD = 3              # frames of breath before a line when there is no recorded audio to time it
SPEAKER_UNTIL = "speaker_until"   # in a line's folder: the first frame of the line that does not show its speaker
TITLE_KEY = "title:"  # the opening shot of a scene, in the dict film_scene returns
# Gestures of the direction vocabulary and the engine's gesture each one plays.
HANDS = {"shrug": "shrug", "point": "point", "wave": "wave", "open_palms": "present", "thumbs_up": "thumb",
         "hand_on_chin": "chin", "arms_folded": "cross", "phone_to_ear": "phone", "typing": "typing", "hold_mug": "carry",
         "sip": "sip", "check_phone": "read"}
CARRIED = {"hold_mug": "mug", "sip": "mug", "check_phone": "phone", "phone_to_ear": "phone"}   # what the hand holds
OPENINGS = {"cut": "establish", "fade_from_black": "establish", "door_reveal": "door", "follow_object": "object", "match_cut": "match"}
MOODS = {"neutral": "neutral", "happy": "happy", "worried": "worry", "surprised": "surprise", "suspicious": "brow",
         "confident": "proud", "embarrassed": "oops", "relieved": "relief"}
ENGINE_MOODS = ("grin", "shock", "sad", "smug", "deadpan", "think", "annoyed", "recognise", "concern", "hesitate", "warm",
                "wince", "tender")


def find_blender() -> tuple[str, bool]:
    """Blender to run, and whether it is a Windows build used from WSL. SASTUDIO_BLENDER wins."""
    exe = os.environ.get("SASTUDIO_BLENDER") or shutil.which("blender") or shutil.which("blender.exe")
    if not exe:
        raise ToolMissing("The clay renderer needs Blender 4.2 or newer.",
                          "Install it from blender.org and put it on PATH, or set SASTUDIO_BLENDER to blender's path.")
    return exe, exe.lower().endswith(".exe") and os.name != "nt"


def _winpath(p: Path) -> str:
    return subprocess.run(["wslpath", "-w", str(p)], capture_output=True, text=True, check=True).stdout.strip()


# ----------------------------------------------------------------------------------------------- timing
@dataclass
class Span:
    """One beat of a scene on the scene's own clock (frames from the start of the scene's video)."""
    line: object            # the project's Line
    beat: int               # first frame of the beat
    frames: int             # frames the beat lasts
    lead: int = 0           # frames before the voice starts
    speech: int = 0         # frames the voice lasts
    env: list = field(default_factory=list)
    text: str = ""

    @property
    def start(self) -> int:
        return self.beat + self.lead

    @property
    def end(self) -> int:
        return self.start + self.speech


def spans_from_timeline(scene, tl) -> list[Span]:
    """The scene's spoken lines as the build timed them from the real audio."""
    by_id = {ln.id: ln for ln in scene.lines}
    out, at = [], 0
    for b in tl.beats:
        if b.kind == "line" and b.line_id in by_id:
            env = list(b.env[b.audio_offset:])
            out.append(Span(by_id[b.line_id], at, b.frames, b.audio_offset, max(1, len(env)), env, b.text))
        at += b.frames
    return out


def spans_estimated(project, scene) -> list[Span]:
    """Timing without audio, from the length of the words: for previews of the direction (`sastudio motion`)."""
    out, at = [], 0
    for ln in scene.lines:
        if ln.is_card:
            continue
        speech = max(12, math.ceil(D._estimate(ln) * FPS))
        frames = LEAD + speech + 8
        out.append(Span(ln, at, frames, LEAD, speech, [], project.display(ln.say or "", project.language)))
        at += frames
    return out


# ----------------------------------------------------------------------------------------------- the scene
def _mood(name: str | None) -> str | None:
    if not name:
        return None
    return MOODS.get(name) or (name if name in ENGINE_MOODS else None)


def _gesture_keys(who: str, g: str, f0: int, f1: int, to: str | None, set_info: dict, mood: str | None = None) -> tuple[list[dict], bool]:
    """Acting keys for one gesture of the direction vocabulary on a line from f0 to f1 -> (keys, uses the hands).
    mood: the face to come back to after a gesture that changes it (a laugh)."""
    info = D.GESTURES[g]
    k = lambda at, /, **d: dict(who=who, frame=int(at), **d)  # noqa: E731  (a key may set the face, `f`)
    if g == "laugh":
        # the face, the breath, the head and the shoulders, together (engine: acting.Actor.laugh_at)
        return [k(f0 + 2, laugh=1, f="grin"), k(f0 + 40, laugh=0, f=mood or "happy")], False
    if g == "nod":
        return [k(f0 + 2, nod=.2), k(f0 + 9, nod=0), k(f0 + 15, nod=.12), k(f0 + 22, nod=0)], False
    if g == "shake_head":
        return [k(f0 + 2, turn=.28), k(f0 + 8, turn=-.28), k(f0 + 14, turn=.2), k(f0 + 20, turn=0)], False
    if g == "tilt_head":
        return [k(f0 + 2, tilt=.17), k(max(f0 + 26, f1 - 6), tilt=0)], False
    if g == "lean_in":
        return [k(f0, lean=.1), k(f1 + 4, lean=0)], False
    if g == "turn_to":
        return ([k(f0 - 6, face=to), k(f1 + 10, face=None)] if to else []), False
    if g == "sit_down":
        return [k(f0, walk="seat")], False
    if g == "stand_up":
        return [k(f0, seat=False), k(f0 + 14, walk="home")], False
    if g == "walk_in":
        return [k(f0 + 10, walk="home", enter=True, speed=.095)], False
    if g == "walk_out":
        return [k(f1 - 6, walk="door" if set_info.get("door") else "offscreen", leave=True)], False
    hand = HANDS[g]
    if g == "sip":
        return [k(f0 - 6, g="carry", cR=1), k(f1 + 8, g="sip"), k(f1 + 8 + 30, g="carry"), k(f1 + 70, g="rest", cR=0)], True
    if g == "check_phone":
        return [k(f0 - 6, g=hand, look="hand", cR=1), k(f1 + 6, g="rest", look=to, cR=0)], True
    if info["kind"] == "once":
        hold = int(info["seconds"] * FPS) + 14
        return [k(f0 + 2, g=hand), k(min(f0 + 2 + hold, f1 + 4), g="talk" if f1 - (f0 + hold) > 20 else "rest")], True
    return [k(f0 - 4, g=hand, cR=1 if g in CARRIED else 0), k(f1 + 6, g="rest", cR=0)], True


def _cast_entry(project, cid: str) -> dict:
    """One character for a job: sculpted here, or a model somebody brought (look.model)."""
    look = project.characters[cid].look or {}
    c = {"id": cid, "style": claydesign.acting_style(project, cid)}
    if look.get("model"):
        path = project.path(look["model"], f"characters.{cid}.look.model")
        if not path.is_file():
            raise ConfigError(f"{cid}'s model {look['model']} is missing.", "Import it again with `sastudio model import`.")
        c.update(model=str(path), model_yaw=float(look.get("model_yaw") or 0.0),
                 model_sha=hashlib.sha256(path.read_bytes()).hexdigest()[:16])   # a changed file re-films its shots
    return c


def _aliases() -> dict:
    from .. import models

    return {"bones": models.BONES, "shapes": models.SHAPES}


def scene_job(project, scene, plan: D.ScenePlan, spans: list[Span], lang: str | None = None, phonemes: dict | None = None) -> dict:
    """Everything about a scene that every one of its shots shares: place, light, people, words, acting."""
    lang = lang or project.language
    set_info = D.SETS.get(plan.set, D.SETS["office"])
    d = scene.direction or {}
    blocking = d.get("blocking") or {}
    cast = []
    for cid in plan.sides:
        if cid not in project.characters:
            raise ConfigError(f"No character '{cid}'.", "List them with `sastudio characters`.")
        c = _cast_entry(project, cid)
        if blocking.get(cid):
            c["mark"] = blocking[cid]
        cast.append(c)
    lines, keys, doors, carry = [], [], [], []
    last_mood: dict[str, str] = {}
    first_line = {}
    for sp in spans:
        first_line.setdefault(sp.line.who, sp.start)
    for cid, g in (d.get("business") or {}).items():
        # what someone is busy with as the scene opens, until they first speak or are told otherwise
        if cid in plan.sides and g in HANDS:
            keys.append(dict(who=cid, frame=-500, g=HANDS[g], cR=1 if g in CARRIED else 0, **({"look": "hand"} if g == "check_phone" else {})))
            if g in CARRIED:
                carry.append({"who": cid, "prop": CARRIED[g], "use": g, "start": -10 ** 6, "end": first_line.get(cid, 10 ** 6) - 6,
                              "color": (project.org.get("palette") or {}).get("accent")})
    for sp in spans:
        ln = sp.line
        manual = set()
        for g in ln.act or []:
            ks, hands = _gesture_keys(ln.who, g, sp.start, sp.end, ln.to, set_info, _mood(ln.emotion) or last_mood.get(ln.who))
            keys += ks
            if hands:
                manual.add(ln.who)
            if g in CARRIED:
                carry.append({"who": ln.who, "prop": CARRIED[g], "use": g, "start": sp.start - 8, "end": sp.end + (72 if g == "sip" else 8),
                              "color": (project.org.get("palette") or {}).get("accent")})
            if g == "walk_in":
                c = next(x for x in cast if x["id"] == ln.who)
                c["enter_from"] = "door" if set_info.get("door") else "offscreen"
        for b in getattr(ln, "beats", None) or []:
            # business at a point inside the line, on the line's own clock: Odile nods at "fishing"
            who = b.get("who") or ln.who
            if who not in plan.sides:
                continue
            f = int(sp.start + float(b["at"]) * max(1, sp.end - sp.start))
            if b.get("feeling") and _mood(b["feeling"]):
                keys.append(dict(who=who, frame=f, f=_mood(b["feeling"])))
                last_mood[who] = _mood(b["feeling"])
            g = b.get("act")
            if g in D.GESTURES:
                to = ln.who if who != ln.who else ln.to
                ks, hands = _gesture_keys(who, g, f, max(f + 24, sp.end), to, set_info, _mood(b.get("feeling")) or last_mood.get(who))
                keys += ks
                if hands:
                    manual.add(who)
                if g in CARRIED:
                    carry.append({"who": who, "prop": CARRIED[g], "use": g, "start": f - 8, "end": max(f + 24, sp.end) + 8,
                                  "color": (project.org.get("palette") or {}).get("accent")})
        if ln.go:
            keys.append(dict(who=ln.who, frame=sp.start - 8, walk=ln.go))
        mood = _mood(ln.emotion)
        if mood and last_mood.get(ln.who) != mood:
            keys.append(dict(who=ln.who, frame=sp.start - 6, f=mood))
            last_mood[ln.who] = mood
        for cid, feeling in (getattr(ln, "reactions", None) or {}).items():
            m = _mood(feeling)
            if m and cid in plan.sides:
                keys.append(dict(who=cid, frame=sp.start + min(18, sp.speech // 3), f=m))
                last_mood[cid] = m
        marks = (phonemes or {}).get(ln.id)
        if marks:
            # the provider's own clock starts before the voice does; the prepared audio has that silence trimmed off
            t0 = next((m[1] for m in marks if m[0].strip()), 0.0) - 0.03
            cues = lipsync.cues_from_phonemes([(m[0], max(0.0, m[1] - t0), max(0.0, m[2] - t0)) for m in marks])
        else:
            cues = lipsync.cues_from_text(sp.text or project.display(ln.say or "", lang), sp.env, FPS) if sp.speech else []
        lines.append({"id": ln.id, "who": ln.who, "start": sp.start, "end": sp.end, "cues": cues, "to": ln.to,
                      "manual": sorted(manual), **({"feeling": mood} if mood else {})})
    org = project.org
    clock = D.clock_time(scene)
    tracks = []
    span_of = {sp.line.id: sp for sp in spans}
    for mv in d.get("props") or []:
        sp = span_of.get(mv.get("line"))
        if sp is None:
            continue
        tracks.append({"thing": mv["thing"], "do": mv["do"], "frame": int(sp.start + float(mv.get("at", 0)) * max(1, sp.end - sp.start)),
                       **({"by": list(mv["by"])} if mv.get("by") else {}), **({"deg": float(mv["deg"])} if mv.get("deg") is not None else {}),
                       "frames": int(mv.get("frames", 14))})
    return {"set": {"name": plan.set, "palette": org.get("palette") or {}, "org": org.get("short_name") or org.get("name"),
                    **({"clock": clock} if clock else {}),
                    **({"dressing": sorted(set(d["dressing"]))} if d.get("dressing") else {}),
                    "seed": int(hashlib.sha256(scene.id.encode()).hexdigest()[:6], 16) % 997 + 1,
                    "time": (scene.setting or {}).get("time_of_day", "day")},
            "lighting": dict(D.LIGHTING[plan.lighting], name=plan.lighting, **D.light_overrides(scene)),
            "cast": cast, "lines": lines, "keys": sorted(keys, key=lambda x: x["frame"]), "door": doors, "carry": carry, "fps": FPS,
            **({"props": sorted(tracks, key=lambda x: x["frame"])} if tracks else {}),
            **({"aliases": _aliases()} if any(c.get("model") for c in cast) else {})}


REST_SHAPES = ("X", "A")   # the mouth at rest, or closed on m/b/p: where an editor cuts inside a line


def cut_point(sp: Span, frac: float, cues: list | None) -> int:
    """Where inside a line a cut at `frac` of it really lands: the drawing (on twos, from the beat) nearest that point
    at which the speaker's mouth rests for at least two frames, between 35 and 80 % of the line; the plain fraction
    when no such moment exists. Both shots on either side of the cut ask this, so they always agree."""
    want = frac * sp.frames
    rests = []
    cues = list(cues or [])
    for (t, shape), nxt in zip(cues, cues[1:] + [(None, None)], strict=False):
        if shape in REST_SHAPES and (nxt[0] is None or (nxt[0] - t) * FPS >= 2):
            rests.append(sp.lead + t * FPS)
    near = [r for r in rests if .35 * sp.frames <= r <= .8 * sp.frames]
    k = int(round(min(near, key=lambda r: abs(r - want)) if near else want))
    k -= k % STEP
    return max(STEP, min(sp.frames - 1 - (sp.frames - 1) % STEP, k))


def shot_frames(shot: D.Shot, spans: list[Span], cues: dict | None = None) -> list[int]:
    """The scene frames a shot shows, on twos within each line's beat (the grid the cards compositor reads).
    A shot with `part` shows a piece of its one line, cut where `cut_point` says (`cues`: line id -> mouth cues)."""
    out: list[int] = []
    for sp in spans:
        if sp.line.id in shot.lines:
            fs = range(0, sp.frames, STEP)
            if shot.part:
                a, b = shot.part
                lo = 0 if a <= 0 else cut_point(sp, a, (cues or {}).get(sp.line.id))
                hi = sp.frames if b >= 1 else cut_point(sp, b, (cues or {}).get(sp.line.id))
                fs = [f for f in fs if lo <= f < hi]
            out += [sp.beat + f for f in fs]
    return sorted(set(out))


def line_cues(scene_part: dict) -> dict:
    return {ln["id"]: ln.get("cues") or [] for ln in scene_part.get("lines") or []}


def is_card(shot: D.Shot) -> bool:
    """An on-screen card (a line written as `card:`): drawn by the compositor, not filmed. An insert the director
    points at a prop of the set (`camera: insert, who: [laptop]`) is filmed: the prop, with the line heard over it."""
    return shot.camera == "insert" and not shot.who


def shot_job(scene_part: dict, shot: D.Shot, frames: list[int], preset: str) -> dict:
    """The job for one shot: the scene, trimmed to what can affect these frames, and a camera."""
    w, h, samples = PRESETS[preset]
    last = frames[-1] + 40
    job = dict(scene_part)
    job["lines"] = [ln for ln in scene_part["lines"] if ln["start"] <= last]
    job["keys"] = [k for k in scene_part["keys"] if k["frame"] <= last]
    job["door"] = [dr for dr in scene_part["door"] if dr[0] <= last]
    job["carry"] = [c for c in scene_part["carry"] if c["start"] <= last]
    job.pop("props", None)
    if [m for m in scene_part.get("props") or [] if m["frame"] <= last]:
        job["props"] = [m for m in scene_part["props"] if m["frame"] <= last]   # a later move does not refilm this shot
    job.update(mode="film", frames=frames, width=w, height=h, samples=samples,
               camera={"shot": shot.camera, "who": list(shot.who), "focus": shot.focus, "lens": shot.lens or D.SHOTS[shot.camera]["lens"],
                       "fstop": shot.fstop, "move": shot.move, "height": shot.height,
                       **({"position": shot.position, "aim": shot.aim} if shot.position and shot.aim else {}),
                       **({"fallback": shot.fallback} if shot.camera == "over_shoulder" and shot.fallback != "two_shot" else {})})
    return job


def opening_job(scene_part: dict, plan: D.ScenePlan, scene, frames: list[int], preset: str) -> dict:
    """The shot a scene opens on, in place of a title card: the place itself, entered the way the scene asks."""
    w, h, samples = PRESETS[preset]
    last = frames[-1] + 40
    d = scene.direction or {}
    job = dict(scene_part)
    job["lines"] = [ln for ln in scene_part["lines"] if ln["start"] <= last]
    job["keys"] = [k for k in scene_part["keys"] if k["frame"] <= last]
    job["door"] = [dr for dr in scene_part["door"] if dr[0] <= last]
    job["carry"] = [c for c in scene_part["carry"] if c["start"] <= last]
    job.pop("props", None)
    if [m for m in scene_part.get("props") or [] if m["frame"] <= last]:
        job["props"] = [m for m in scene_part["props"] if m["frame"] <= last]   # a later move does not refilm this shot
    style = OPENINGS.get(plan.transition_in, "establish")
    if style == "door":
        job["door"] = job["door"] + [[frames[0] + 6, frames[-1] + 30]]
    first = next((ln["who"] for ln in scene_part["lines"]), None)
    job.update(mode="film", frames=frames, width=w, height=h, samples=samples,
               camera={"shot": "opening", "style": style, "thing": d.get("object"), "who": [first] if first else [],
                       "lens": 28 if style in ("establish", "door") else 50, "fstop": 4.0})
    return job


_FINGERPRINT: list[str] = []
# the engine files whose code decides what a filmed shot looks like (contacts.py only measures: it draws nothing)
PICTURE_FILES = ("film.py", "acting.py", "body.py", "puppet.py", "handrig.py", "faceops.py", "claymat.py", "sets.py", "setkit.py",
                 "guest.py")


def engine_fingerprint() -> str:
    """A hash of the engine's code as Python reads it (comments and docstrings left out), so that any change to how a
    shot is posed or built films it again, even if nobody remembered to bump ENGINE_VERSION; a comment does not."""
    if not _FINGERPRINT:
        import ast

        def bare(src: str) -> str:
            tree = ast.parse(src)
            for node in ast.walk(tree):
                body = getattr(node, "body", None)
                if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                        and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
                    node.body = body[1:] or [ast.Pass()]
            return ast.dump(tree, annotate_fields=False)
        h = hashlib.sha256()
        for name in PICTURE_FILES:
            f = clay.ENGINE.joinpath("clay").joinpath(name)
            if f.is_file():
                h.update(name.encode() + b"\0" + bare(f.read_text("utf-8")).encode())
        _FINGERPRINT.append(h.hexdigest()[:16])
    return _FINGERPRINT[0]


def _digest(job: dict, rigs: dict) -> str:
    job = {k: v for k, v in job.items() if k != "contacts"}     # whether contact was checked does not change a drawing
    body = json.dumps({"job": job, "rigs": rigs, "v": ENGINE_VERSION, "engine": engine_fingerprint()}, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:20]


# ----------------------------------------------------------------------------------------------- Blender
def _font() -> Path:
    fonts = resources.files("sastudio").joinpath("data").joinpath("fonts")
    with resources.as_file(fonts) as fdir:
        return Path(fdir) / "AtkinsonHyperlegibleNext[wght].ttf"


STALL_MINUTES = 20    # no new drawing for this long and Blender is taken to be hung (SASTUDIO_CLAY_STALL_MINUTES)
RETRIES = 1           # a shot whose Blender dies or hangs is started once more, from its first missing drawing


def _env_number(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _stop(proc: subprocess.Popen, grace: float = 10.0) -> None:
    """End a child process and reap it: ask first, then insist. Nothing is left running behind a failed shot."""
    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:  # pragma: no cover - a process that survives SIGKILL is the kernel's problem
        pass


def watch(proc: subprocess.Popen, on_line, *, timeout: float, stall: float, progress=lambda line: True) -> int:
    """Read a child's output until it exits, enforcing two limits on the read itself (a hung child writes nothing,
    so a limit checked after the read loop would never be reached):

    timeout  seconds for the whole run
    stall    seconds without a line that `progress` accepts (for Blender: a finished drawing)

    On either limit, or any exception (Ctrl+C included), the child is terminated, killed if it does not stop, and reaped
    before this returns or raises. Returns the exit code; raises TimeoutError naming the limit that was hit."""
    import queue
    import threading
    import time

    lines: queue.Queue = queue.Queue()

    def pump():
        try:
            for ln in proc.stdout:
                lines.put(ln)
        finally:
            lines.put(None)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    start = last = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            if now - start > timeout:
                raise TimeoutError(f"ran past its limit of {timeout / 60:.0f} min")
            if now - last > stall:
                raise TimeoutError(f"wrote no new drawing for {stall / 60:.0f} min")
            try:
                ln = lines.get(timeout=min(1.0, max(.05, timeout - (now - start)), max(.05, stall - (now - last))))
            except queue.Empty:
                continue
            if ln is None:
                break
            ln = ln.rstrip()
            if progress(ln):
                last = time.monotonic()
            on_line(ln)
        try:
            return proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            raise TimeoutError("closed its output but did not exit") from None
    finally:
        _stop(proc)
        reader.join(timeout=5)


def blank_frames(paths) -> list[Path]:
    """Frames that came out as one flat colour (a black frame from a lost GPU context, an empty scene, a white flash).
    A real drawing always has light and shade in it, so a 32x18 thumbnail whose brightest and darkest pixels differ by
    under 6 levels is not a drawing. About 10 ms a frame."""
    from PIL import Image

    bad = []
    for p in paths:
        try:
            with Image.open(p) as im:
                lo, hi = im.convert("L").resize((32, 18)).getextrema()
        except (OSError, ValueError):
            bad.append(Path(p))   # unreadable or truncated: as bad as blank
            continue
        if hi - lo < 6:
            bad.append(Path(p))
    return bad


def _die_with_parent():  # pragma: no cover - runs in the child between fork and exec
    """Linux: ask the kernel to kill Blender if this process dies, even by SIGKILL, so no Blender outlives it."""
    import contextlib
    import ctypes
    import signal

    with contextlib.suppress(Exception):    # no libc prctl (musl, a sandbox): the watchdog still stops Blender
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGKILL)   # PR_SET_PDEATHSIG


def run_blender(job: dict, work: Path, log=print, timeout: float = 48 * 3600) -> None:
    """Run the engine on a job; paths are converted for a Windows Blender under WSL. Progress goes to `log`.

    The run is watched: past `timeout`, or with no new drawing for SASTUDIO_CLAY_STALL_MINUTES (default 20), Blender
    is stopped and RenderError is raised. Blender never outlives this call."""
    clay.require_engine()
    exe, wsl_win = find_blender()
    conv = _winpath if wsl_win else str
    job = dict(job)
    for key in ("rig", "out", "font", "export"):
        if job.get(key):
            job[key] = conv(Path(job[key]))
    job["cast"] = [dict(c, model=conv(Path(c["model"]))) if c.get("model") else c for c in job.get("cast") or []]
    job["device"] = clay.clay_device()
    if os.environ.get("SASTUDIO_ALLOW_INTERSECTIONS") == "1":
        job["contacts"] = "allow"      # sastudio film --allow-intersections: film it, and list what passes through what
    work.mkdir(parents=True, exist_ok=True)
    (work / "job.json").write_text(json.dumps(job), "utf-8")
    with resources.as_file(clay.ENGINE.joinpath("clay").joinpath("film.py")) as script:
        cmd = [exe, "-b", "--factory-startup", "-P", conv(Path(script)), "--", conv(work / "job.json")]
        linux = os.name == "posix" and os.uname().sysname == "Linux"
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                **({"preexec_fn": _die_with_parent} if linux else {}))
        tail: list[str] = []
        contacts: list[str] = []

        def on_line(line: str) -> None:
            nonlocal tail
            tail = (tail + [line])[-30:]
            if line.startswith("FILM contact ") or line.startswith("FILM refused"):
                contacts.append(line[5:])
            elif line.startswith("FILM contacts checked"):
                log("    " + line[5:])
            if line.startswith("FILM device"):
                cpu = job["device"] == "GPU" and line.startswith("FILM device CPU")
                log(("    warning: " if cpu else "    ") + line[5:]
                    + (" - rendering on the CPU is much slower; check your GPU driver" if cpu else ""))
            elif line.startswith("FILM frame "):
                n = line.split()[2]
                done, total = n.split("/")
                if int(done) % 12 == 0 or done == total:
                    log(f"    drawing {done} of {total} ({line.split()[-1]})")
            elif line.startswith("FILM over_shoulder"):
                log("    " + line[5:])

        stall = _env_number("SASTUDIO_CLAY_STALL_MINUTES", STALL_MINUTES) * 60
        try:
            # building the set and the puppets comes before the first drawing, and counts as progress too
            code = watch(proc, on_line, timeout=timeout, stall=stall, progress=lambda ln: ln.startswith("FILM"))
        except TimeoutError as e:
            raise RenderError(f"Blender {e} and was stopped. The drawings it finished are kept; run the same command "
                              "again to carry on from the first missing one.") from None
    for t in tail:
        if t.startswith("FILM guest"):
            log("    " + t[5:])
    if contacts and any(c.startswith("refused") for c in contacts):
        raise ContactError("This shot was not filmed: a body would pass through something.\n    "
                           + "\n    ".join(c[len("contact "):] if c.startswith("contact ") else c for c in contacts[:16]),
                           "Move someone (direction.blocking), change the gesture or the line's business, or give the people "
                           "more room; `sastudio check` shows every drawing without filming. To film it anyway: "
                           "sastudio film --allow-intersections.")
    if code != 0 or not any(t.startswith("FILM done") for t in tail):
        raise RenderError("Blender did not finish the shot:\n    " + "\n    ".join(tail[-14:]))


def rig_stamps(project, cast: list[str]) -> dict:
    rig = clay.rig_dir(project)
    return {cid: (rig / cid / ".params").read_text() if (rig / cid / ".params").exists() else "" for cid in cast}


def _film(project, job: dict, frames: list[int], label: str, what: str, log=print) -> Path:
    """Film a job (or reuse it): returns the folder holding its frames, named by scene frame number."""
    cast = [c["id"] for c in job["cast"]]
    key = _digest(job, rig_stamps(project, cast))
    out = project.root / ".studio" / "cache" / "clay" / f"{label}.{key}"
    if (out / ".done").exists() and all((out / f"{f:06d}.png").exists() for f in frames):
        log(f"  {label}: unchanged, reused")
        return out
    # the same job filmed under another label (a shot added earlier in the scene renumbers the ones after it):
    # reuse it when finished, carry on filming into it when it was interrupted
    for other in sorted(out.parent.glob(f"*.{key}")) if out.parent.is_dir() and not out.exists() else []:
        if (other / ".done").exists() and all((other / f"{f:06d}.png").exists() for f in frames):
            log(f"  {label}: unchanged, reused (filmed as {other.name.rsplit('.', 1)[0]})")
            return other
        out = other
        break
    job = dict(job, rig=str(clay.rig_dir(project)), out=str(out), font=str(_font()))
    left = sum(1 for f in frames if not (out / f"{f:06d}.png").exists())
    log(f"  {label}: {what}, {len(frames)} drawings" + (f" ({len(frames) - left} already done)" if left != len(frames) else ""))
    retries = int(_env_number("SASTUDIO_CLAY_RETRIES", RETRIES))
    for stale in out.glob("*.part.png") if out.is_dir() else []:
        stale.unlink(missing_ok=True)     # a drawing a stopped Blender was half way through writing
    for attempt in range(retries + 1):
        todo = [f for f in frames if not (out / f"{f:06d}.png").exists()]
        try:
            run_blender(job, project.root / ".studio" / "work" / "clay" / label, log)
            problem = None
        except RenderError as e:
            # an error in the engine's own code will not fix itself, nor will a shot refused for a contact; a crash, a
            # lost GPU or a hang might
            if isinstance(e, ContactError) or "Traceback" in str(e) or attempt == retries:
                raise
            problem = str(e).splitlines()[0]
        blank = blank_frames(out / f"{f:06d}.png" for f in todo if (out / f"{f:06d}.png").exists())
        for p in blank:
            p.unlink()      # a flat frame is not kept: the next attempt draws it again
        if blank:
            problem = f"{len(blank)} drawing(s) came out blank ({', '.join(p.stem for p in blank[:6])})"
            if attempt == retries:
                raise RenderError(f"{label}: {problem}.", "Check the GPU driver, or set SASTUDIO_CLAY_DEVICE=CPU.")
        if problem is None:
            break
        log(f"    {problem}; starting Blender once more from the first missing drawing")
    missing = [f for f in frames if not (out / f"{f:06d}.png").exists()]
    if missing:
        raise RenderError(f"{label}: Blender finished but {len(missing)} frame(s) are missing.")
    (out / ".done").write_text(key)
    return out


def film_shot(project, scene_part: dict, shot: D.Shot, frames: list[int], preset: str, label: str, log=print) -> Path:
    """Film one planned shot (or reuse it)."""
    return _film(project, shot_job(scene_part, shot, frames, preset), frames, label, shot.camera, log)


def film_scene(project, scene, plan: D.ScenePlan, spans: list[Span], preset: str, lang: str | None = None, log=print,
               phonemes: dict | None = None, title_frames: int = 0) -> dict[str, Path]:
    """Film every shot of a scene. Returns {line id: folder of that line's frames, numbered 00001.png on twos};
    with `title_frames`, also the opening shot that carries the scene's title, under TITLE_KEY + scene id."""
    if preset not in PRESETS:
        raise ConfigError(f"Unknown preset '{preset}'.", f"Use one of {', '.join(PRESETS)}.")
    clay.build_rigs(project, ids=list(plan.sides), log=log)
    part = scene_job(project, scene, plan, spans, lang, phonemes)
    by_line = {sp.line.id: sp for sp in spans}
    cues = line_cues(part)
    out: dict[str, Path] = {}
    sources: dict[str, list[tuple[Path, set[int]]]] = {}
    n = 0
    if title_frames:
        # the scene's title is laid over a real shot of the place: no card between scenes
        frames = list(range(0, title_frames, STEP))
        job = opening_job(part, plan, scene, frames, preset)
        folder = _film(project, job, frames, f"{scene.id}_open_{preset}", f"opening ({job['camera']['style']})", log)
        out[TITLE_KEY + scene.id] = _line_folder(project, folder, f"{scene.id}.title.{preset}", 0, title_frames)
    for i, shot in enumerate(plan.shots):
        ids = [lid for lid in shot.lines if lid in by_line]
        if is_card(shot) or not ids:
            continue
        n += 1
        frames = shot_frames(shot, spans, cues)
        folder = film_shot(project, part, shot, frames, preset, f"{scene.id}_s{i + 1:02d}_{preset}", log)
        for lid in ids:
            sources.setdefault(lid, []).append((folder, set(frames), by_line[lid].line.who in shot.who))
    for lid, src in sources.items():
        sp = by_line[lid]
        out[lid] = _line_folder(project, [(d, held) for d, held, _ in src], f"{scene.id}.{lid}.{preset}", sp.beat, sp.frames)
        # the speaker's name tag may only be on screen while the speaker is: a cut to the listener ends it
        away = [fr - sp.beat for _, held, shows in src if not shows for fr in held]
        (out[lid] / SPEAKER_UNTIL).write_text(str(min(away) if away else sp.frames))
    return out


def _line_folder(project, folder, name: str, beat: int, frames: int) -> Path:
    """A beat's own view of its shots: its drawings numbered 00001.png on twos, as the compositor reads them.
    `folder` is one shot's folder, or [(folder, scene frames it holds), ...] for a line cut between shots."""
    src_list = [(folder, None)] if isinstance(folder, Path) else list(folder)
    tag = src_list[0][0].name[-20:] if len(src_list) == 1 else \
        hashlib.sha256("|".join(f.name for f, _ in src_list).encode()).hexdigest()[:20]
    dest = project.root / ".studio" / "work" / "clay" / "lines" / f"{name}.{tag}"
    if not (dest / ".done").exists():
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        for f in range(0, frames, STEP):
            fr = beat + f
            home = next((d for d, held in src_list if held is None or fr in held), None)
            if home is None:
                raise RenderError(f"{name}: no shot films scene frame {fr}.", "Check the `part` pieces of this line.")
            src = home / f"{fr:06d}.png"
            try:
                os.link(src, dest / f"{f + 1:05d}.png")
            except OSError:
                shutil.copyfile(src, dest / f"{f + 1:05d}.png")
        (dest / ".done").write_text("ok")
    return dest


# ----------------------------------------------------------------------------------------------- stills
def render_portrait(project, cid: str, *, samples: int = 48, log=print, force: bool = True, feeling: str = "warm") -> Path:
    """A still of one character for the cards styles and the cast page: assets/characters/<id>_clay.png."""
    from PIL import Image

    if cid not in project.characters:
        raise ConfigError(f"No character '{cid}'.", "List them with `sastudio characters`.")
    rel = f"assets/characters/{cid}_clay.png"
    target = project.root / rel
    if target.exists() and not force:
        return target
    clay.build_rigs(project, ids=[cid], log=log)
    entry = dict(_cast_entry(project, cid), pos=[0, 0], face=0.14, feeling=feeling)
    work = project.root / ".studio" / "work" / "portraits" / cid
    shutil.rmtree(work, ignore_errors=True)
    job = {"mode": "portrait", "rig": str(clay.rig_dir(project)), "out": str(work / "frames"), "font": str(_font()),
           "width": 1200, "height": 1600, "samples": samples, "fps": FPS, "frames": [0], "transparent": True,
           "set": {"name": "studio", "palette": project.org.get("palette") or {}}, "lighting": dict(D.LIGHTING["soft_studio"], name="soft_studio"),
           "cast": [entry], "lines": [], "keys": [], "door": [], "aliases": _aliases(),
           "camera": {"shot": "portrait", "who": [cid], "lens": 50, "fstop": 8}}
    log(f"Rendering a portrait of {cid}...")
    run_blender(job, work, log)
    shots = sorted((work / "frames").glob("*.png"))
    if not shots:
        raise RenderError("Blender wrote no portrait.")
    im = Image.open(shots[0]).convert("RGBA")
    bb = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if not bb:
        raise RenderError(f"The portrait of {cid} is empty.")
    im = im.crop((max(0, bb[0] - 24), max(0, bb[1] - 24), min(im.width, bb[2] + 24), min(im.height, bb[3] + 24)))
    im = im.resize((max(1, int(im.width * 820 / im.height)), 820), Image.LANCZOS)
    target.parent.mkdir(parents=True, exist_ok=True)
    im.save(target, optimize=True)
    return target


EXPORT_FORMATS = (".glb", ".fbx", ".obj", ".blend")


def export_character(project, cid: str, out: Path, log=print) -> Path:
    """Write one character (sculpted, or a model as fitted to the cast) to GLB, FBX, OBJ or .blend."""
    out = Path(out).resolve()
    if out.suffix.lower() not in EXPORT_FORMATS:
        raise ConfigError(f"Cannot export to {out.suffix or 'a file without an extension'}.",
                          "Use .glb (most tools and the web), .fbx (game engines), .obj (any 3D tool) or .blend.")
    if cid not in project.characters:
        raise ConfigError(f"No character '{cid}'.", "List them with `sastudio characters`.")
    clay.build_rigs(project, ids=[cid], log=log)
    job = {"mode": "export", "rig": str(clay.rig_dir(project)), "out": str(out.parent), "export": str(out), "width": 64, "height": 64,
           "frames": [0], "set": {"name": "studio"}, "lighting": dict(D.LIGHTING["soft_studio"], name="soft_studio"),
           "cast": [dict(_cast_entry(project, cid), pos=[0, 0], face=0.0)], "lines": [], "keys": [], "door": [], "aliases": _aliases()}
    out.parent.mkdir(parents=True, exist_ok=True)
    log(f"Exporting {cid} to {out.name}...")
    run_blender(job, project.root / ".studio" / "work" / "export" / cid, log)
    if not out.is_file() or out.stat().st_size == 0:
        raise RenderError(f"Blender did not write {out}.")
    return out


# ----------------------------------------------------------------------------------------------- previews
def _plan_for(project, scene_id: str):
    plans = {p.scene: p for p in D.plan(project)}
    if scene_id not in plans:
        raise ConfigError(f"No enabled scene '{scene_id}'.", "List scenes with `sastudio scenes`.")
    return plans[scene_id], next(s for s in project.scenes if s.id == scene_id)


def _encode(folder_frames: list[Path], out: Path) -> None:
    from ..audio.ffmpeg import ffmpeg_exe

    out.parent.mkdir(parents=True, exist_ok=True)
    listing = out.with_suffix(".frames.txt")
    listing.write_text("".join(f"file '{p.as_posix()}'\nduration {STEP / FPS}\n" for p in folder_frames), "utf-8")
    subprocess.run([ffmpeg_exe(), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-vf", f"fps={FPS}",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-map_metadata", "-1", str(out)], check=True)
    listing.unlink(missing_ok=True)


def render_shot(project, scene_id: str, shot_index: int, preset: str, out: Path, log=print) -> Path:
    """Film one planned shot without voices (timed from the words) and encode it: a quick look at the direction."""
    plan, scene = _plan_for(project, scene_id)
    if not 0 <= shot_index < len(plan.shots):
        raise ConfigError(f"Scene {scene_id} has {len(plan.shots)} shots.", "See them with `sastudio direct`.")
    shot = plan.shots[shot_index]
    if is_card(shot):
        raise ConfigError("That shot is an on-screen card: the compositor draws it, it is not filmed.", "Choose another shot.")
    spans = spans_estimated(project, scene)
    clay.build_rigs(project, ids=list(plan.sides), log=log)
    part = scene_job(project, scene, plan, spans)
    frames = shot_frames(shot, spans, line_cues(part))
    folder = film_shot(project, part, shot, frames, preset, f"{scene_id}_s{shot_index + 1:02d}_{preset}_silent", log)
    _encode([folder / f"{f:06d}.png" for f in frames], out)
    log(f"Wrote {out} ({len(frames)} drawings)")
    return out


def render_scene(project, scene_id: str, preset: str, out: Path, log=print) -> Path:
    """Film every shot of a scene without voices and join them: a silent preview of the direction."""
    plan, scene = _plan_for(project, scene_id)
    spans = spans_estimated(project, scene)
    clay.build_rigs(project, ids=list(plan.sides), log=log)
    part = scene_job(project, scene, plan, spans)
    all_frames: list[Path] = []
    for i, shot in enumerate(plan.shots):
        frames = shot_frames(shot, spans, line_cues(part))
        if is_card(shot) or not frames:
            continue
        folder = film_shot(project, part, shot, frames, preset, f"{scene_id}_s{i + 1:02d}_{preset}_silent", log)
        all_frames += [folder / f"{f:06d}.png" for f in frames]
    if not all_frames:
        raise RenderError(f"Scene {scene_id} has no spoken lines to film.")
    _encode(all_frames, out)
    log(f"Wrote {out} ({len(all_frames)} drawings, {len(all_frames) * STEP / FPS:.1f} s, silent)")
    return out


# ----------------------------------------------------------------------------------------------- the shot cache
def cache_dir(project) -> Path:
    return project.root / ".studio" / "cache" / "clay"


def _size(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())


def stale_shots(project, *, everything: bool = False) -> list[tuple[Path, int, str]]:
    """Cached shots that can go: (folder, bytes, why). A shot is stored as `<label>.<hash>`; when a line, a look or
    the engine changes, the shot is filmed again under a new hash and the old folder is never read again. The newest
    folder of each label is kept (finished or not, so an interrupted shot can still resume); `everything` lists all."""
    root = cache_dir(project)
    if not root.is_dir():
        return []
    by_label: dict[str, list[Path]] = {}
    for d in root.iterdir():
        if d.is_dir() and "." in d.name:
            by_label.setdefault(d.name.rsplit(".", 1)[0], []).append(d)

    def age(d: Path) -> float:
        done = d / ".done"
        return (done if done.exists() else d).stat().st_mtime

    out = []
    for _label, dirs in sorted(by_label.items()):
        dirs.sort(key=age, reverse=True)
        for i, d in enumerate(dirs):
            if everything:
                out.append((d, _size(d), "all shots"))
            elif i > 0:
                out.append((d, _size(d), f"superseded by {dirs[0].name}"))
    return out
