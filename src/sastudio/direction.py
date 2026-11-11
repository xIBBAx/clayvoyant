"""Scene direction: who is on screen, which camera, which light, which gesture, how a scene begins.

Direction is data. A scene may say nothing (the planner directs it with sensible, varied
defaults), name a few things (a lighting preset, a camera for one line), or spell out every shot.
Everything named is checked against the presets below; nothing unknown is silently ignored.

This module plans and validates; it does not render. The clay renderer (sastudio.stopmotion and the
engine in engine/clay) films the plan. `sastudio direct` prints it, so a plan can be read and
corrected before anything is rendered.
"""

from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- presets
# Shots: lens in mm (35 mm equivalent), what the frame holds, how many characters it needs.
SHOTS: dict[str, dict] = {
    "establishing": {"lens": 24, "framing": "the whole set", "min": 0, "max": 6, "fstop": 8.0},
    "wide": {"lens": 28, "framing": "full figures", "min": 1, "max": 6, "fstop": 5.6},
    "medium": {"lens": 40, "framing": "waist up", "min": 1, "max": 1, "fstop": 4.0},
    "two_shot": {"lens": 35, "framing": "two figures, waist up", "min": 2, "max": 2, "fstop": 4.0},
    "over_shoulder": {"lens": 50, "framing": "the speaker past the listener's shoulder", "min": 2, "max": 2,
                      "fstop": 2.8},
    "close_up": {"lens": 65, "framing": "head and shoulders", "min": 1, "max": 1, "fstop": 2.8},
    "extreme_close_up": {"lens": 100, "framing": "eyes and mouth", "min": 1, "max": 1, "fstop": 2.0},
    "reaction": {"lens": 65, "framing": "a listener's face while someone else speaks", "min": 1, "max": 1,
                 "fstop": 2.8},
    "insert": {"lens": 85, "framing": "a prop: a phone screen, a laptop, a badge", "min": 0, "max": 0, "fstop": 2.8},
}
MOVES: dict[str, str] = {
    "static": "the camera holds still",
    "push_in": "a slow move closer, for a line that matters",
    "pull_out": "a slow move back, to end a moment",
    "pan": "the camera turns to follow someone",
    "tilt": "the camera tilts up or down",
    "track": "the camera travels alongside someone walking",
    "orbit": "a small arc around the subject",
}
HEIGHTS = ("eye", "low", "high")
# Lighting: colour temperature of the key light, fill and rim as a share of the key, exposure in
# stops, shadow softness 0 (hard) to 1 (soft), and whether lamps in the set are lit.
LIGHTING: dict[str, dict] = {
    "warm_interior": {"key_k": 3200, "fill": 0.45, "rim": 0.30, "exposure": 0.0, "softness": 0.65, "practicals": True},
    "soft_studio": {"key_k": 5000, "fill": 0.70, "rim": 0.20, "exposure": 0.2, "softness": 0.90, "practicals": False},
    "daylight": {"key_k": 5600, "fill": 0.50, "rim": 0.25, "exposure": 0.1, "softness": 0.50, "practicals": False},
    "office": {"key_k": 4500, "fill": 0.60, "rim": 0.15, "exposure": 0.0, "softness": 0.80, "practicals": False},
    "night_practical": {"key_k": 2700, "fill": 0.15, "rim": 0.50, "exposure": -0.7, "softness": 0.40,
                        "practicals": True},
    "dramatic": {"key_k": 4300, "fill": 0.10, "rim": 0.60, "exposure": -0.2, "softness": 0.25, "practicals": False},
    "suspense": {"key_k": 3800, "fill": 0.20, "rim": 0.45, "exposure": -0.4, "softness": 0.35, "practicals": True},
}
# Gestures: the body parts they use (two gestures in one line may not share a part), seconds,
# and whether they play once, hold for the line, or loop.
GESTURES: dict[str, dict] = {
    "nod": {"parts": {"head"}, "seconds": 0.6, "kind": "once"},
    "shake_head": {"parts": {"head"}, "seconds": 0.8, "kind": "once"},
    "tilt_head": {"parts": {"head"}, "seconds": 0.7, "kind": "once"},
    "shrug": {"parts": {"shoulders", "left_arm", "right_arm"}, "seconds": 1.0, "kind": "once"},
    "point": {"parts": {"right_arm"}, "seconds": 0.9, "kind": "once"},
    "wave": {"parts": {"right_arm"}, "seconds": 1.2, "kind": "once"},
    "open_palms": {"parts": {"left_arm", "right_arm"}, "seconds": 0.9, "kind": "once"},
    "thumbs_up": {"parts": {"right_arm"}, "seconds": 0.8, "kind": "once"},
    "hand_on_chin": {"parts": {"right_arm"}, "seconds": 0.0, "kind": "hold"},
    "arms_folded": {"parts": {"left_arm", "right_arm"}, "seconds": 0.0, "kind": "hold"},
    "phone_to_ear": {"parts": {"right_arm"}, "seconds": 0.0, "kind": "hold", "prop": "phone"},
    "typing": {"parts": {"left_arm", "right_arm"}, "seconds": 0.0, "kind": "loop", "prop": "laptop"},
    "hold_mug": {"parts": {"right_arm"}, "seconds": 0.0, "kind": "hold", "prop": "mug"},
    "sip": {"parts": {"right_arm"}, "seconds": 1.6, "kind": "once", "prop": "mug"},
    "check_phone": {"parts": {"right_arm", "head"}, "seconds": 0.0, "kind": "hold", "prop": "phone"},
    "lean_in": {"parts": {"torso"}, "seconds": 0.8, "kind": "once"},
    "turn_to": {"parts": {"head", "torso"}, "seconds": 0.6, "kind": "once"},
    "sit_down": {"parts": {"torso", "legs"}, "seconds": 1.2, "kind": "once", "mark": "seat"},
    "stand_up": {"parts": {"torso", "legs"}, "seconds": 1.2, "kind": "once", "mark": "seat"},
    "walk_in": {"parts": {"legs", "torso"}, "seconds": 2.0, "kind": "once"},
    "walk_out": {"parts": {"legs", "torso"}, "seconds": 2.0, "kind": "once"},
}
EMOTIONS = ("neutral", "happy", "worried", "surprised", "suspicious", "confident", "embarrassed", "relieved",
            # the clay engine's finer shades
            "grin", "shock", "sad", "smug", "deadpan", "think", "annoyed", "recognise", "concern", "hesitate", "warm", "wince", "tender")
# Sets: the places a character can stand or sit, the props on hand, and whether there is a door.
SETS: dict[str, dict] = {
    "office": {"marks": ["desk", "desk_2", "standing_left", "standing_right", "window", "door"],
               "seats": ["desk", "desk_2"], "props": ["laptop", "laptop_2", "phone", "mug", "badge", "printer",
                                                      "plant", "poster"], "door": True},
    "reception": {"marks": ["counter", "visitor", "standing_left", "standing_right", "door"], "seats": [],
                  "props": ["badge", "badge_reader", "phone", "visitor_book", "plant", "poster", "monitor"],
                  "door": True},
    "meeting_room": {"marks": ["head_of_table", "left_seat", "right_seat", "screen", "door"],
                     "seats": ["head_of_table", "left_seat", "right_seat"],
                     "props": ["laptop", "phone", "mug", "screen", "poster"], "door": True},
    "home_desk": {"marks": ["desk", "sofa", "window"], "seats": ["desk", "sofa"],
                  "props": ["laptop", "phone", "mug", "plant", "router"], "door": False},
    "cafe": {"marks": ["table_left", "table_right", "table_left_2", "table_right_2", "counter", "door"],
             "seats": ["table_left", "table_right", "table_left_2", "table_right_2"],
             "props": ["laptop", "phone", "mug", "wifi_sign"], "door": True},
    "corridor": {"marks": ["left", "centre", "right", "door"], "seats": [],
                 "props": ["badge", "phone", "poster", "badge_reader"], "door": True},
    "street": {"marks": ["pavement_left", "pavement_right", "bench", "bus_stop", "shop_door", "far_left", "far_right"],
               "seats": ["bench"], "props": ["phone", "car", "bus_stop"], "door": False},
    "classroom": {"marks": ["teacher", "board", "teacher_desk", "front_desk_left", "front_desk_right", "standing_left",
                            "standing_right", "door"], "seats": ["teacher_desk", "front_desk_left", "front_desk_right"],
                  "props": ["board", "laptop", "map", "phone"], "door": True},
    "studio": {"marks": ["centre"], "seats": [], "props": [], "door": False},
}
# Transitions: a clean cut unless a story event motivates something else. No wipes or spins.
TRANSITIONS: dict[str, str] = {
    "cut": "a clean cut (the default)",
    "match_cut": "a cut that matches a shape or movement across the two shots",
    "follow_object": "the camera follows a named object into the new scene (needs `object`)",
    "door_reveal": "a door opens onto the new scene (the set needs a door)",
    "fade_from_black": "only to open the film, or after a jump in time (`time_jump: true`)",
}
WORDS_PER_SECOND = 2.6


@dataclass
class Problem:
    level: str  # error | warning
    where: str
    message: str
    hint: str | None = None


@dataclass
class Shot:
    lines: list[str]
    camera: str
    who: list[str]
    focus: str | None
    move: str = "static"
    seconds: float = 0.0
    lens: int = 0
    height: str = "eye"
    fstop: float = 4.0
    acts: dict[str, list[str]] = field(default_factory=dict)  # line id -> gestures
    reason: str = ""


@dataclass
class ScenePlan:
    scene: str
    set: str
    lighting: str
    transition_in: str
    sides: dict[str, str]
    shots: list[Shot]


def _suggest(value: str, choices) -> str:
    near = difflib.get_close_matches(str(value), list(choices), n=2, cutoff=0.5)
    return (f"Did you mean {' or '.join(near)}? " if near else "") + f"Choose from: {', '.join(sorted(choices))}."


def _estimate(line) -> float:
    if line.is_card:
        return float((line.card or {}).get("seconds") or 3.0)
    return round(0.4 + len((line.say or "").split()) / WORDS_PER_SECOND, 2)


def _on_list(value) -> list[str]:
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


# --------------------------------------------------------------------------- validation
def validate(project) -> list[Problem]:
    """Check every direction a project gives. Unknown names are errors, with the closest match."""
    out: list[Problem] = []
    scenes = [s for s in project.scenes if s.enabled]
    for idx, s in enumerate(scenes):
        d = s.direction or {}
        where = f"{s.id}.direction"
        set_name = d.get("set") or _default_set(s)
        if set_name not in SETS:
            out.append(Problem("error", f"{where}.set", f"Unknown set '{set_name}'.", _suggest(set_name, SETS)))
            set_info = {"marks": [], "seats": [], "props": [], "door": False}
        else:
            set_info = SETS[set_name]
        if d.get("lighting") and d["lighting"] not in LIGHTING:
            out.append(Problem("error", f"{where}.lighting", f"Unknown lighting '{d['lighting']}'.",
                               _suggest(d["lighting"], LIGHTING)))
        present = _present(s, d)
        for cid in present:
            if cid not in project.characters:
                out.append(Problem("error", f"{where}.extras", f"No character '{cid}' in the project.",
                                   _suggest(cid, project.characters)))
        for cid, mark in (d.get("blocking") or {}).items():
            if cid not in present:
                out.append(Problem("error", f"{where}.blocking.{cid}", f"'{cid}' is not in this scene.",
                                   "Add them to `extras`, or give them a line."))
            if set_info["marks"] and mark not in set_info["marks"]:
                out.append(Problem("error", f"{where}.blocking.{cid}", f"The {set_name} set has no mark '{mark}'.",
                                   _suggest(mark, set_info["marks"])))
        for cid, g in (d.get("business") or {}).items():
            if cid not in present:
                out.append(Problem("error", f"{where}.business.{cid}", f"'{cid}' is not in this scene.", "Add them to `extras`."))
            holds = sorted(k for k, v in GESTURES.items() if v["kind"] in ("hold", "loop"))
            if g not in holds:
                out.append(Problem("error", f"{where}.business.{cid}", f"'{g}' is not something to be doing as a scene opens.",
                                   _suggest(g, holds)))
        tr = d.get("transition_in", "cut")
        if tr not in TRANSITIONS:
            out.append(Problem("error", f"{where}.transition_in", f"Unknown transition '{tr}'.", _suggest(tr, TRANSITIONS)))
        elif tr == "door_reveal" and not set_info["door"]:
            out.append(Problem("error", f"{where}.transition_in", f"The {set_name} set has no door to open.",
                               "Use a cut, or a set with a door."))
        elif tr == "follow_object":
            obj = d.get("object")
            if not obj:
                out.append(Problem("error", f"{where}.object", "follow_object needs the `object` to follow."))
            elif obj not in set_info["props"]:
                out.append(Problem("error", f"{where}.object", f"The {set_name} set has no '{obj}'.",
                                   _suggest(obj, set_info["props"])))
        elif tr == "fade_from_black" and idx > 0 and not d.get("time_jump"):
            out.append(Problem("error", f"{where}.transition_in", "A fade from black is only for the first scene or a "
                               "jump in time.", "Add `time_jump: true` if time has passed, or use a cut."))
        if d.get("open_with") and d["open_with"] not in SHOTS:
            out.append(Problem("error", f"{where}.open_with", f"Unknown camera '{d['open_with']}'.",
                               _suggest(d["open_with"], SHOTS)))
        line_ids = [ln.id for ln in s.lines]
        covered: dict[str, int] = {}
        for n, shot in enumerate(d.get("shots") or [], 1):
            w = f"{where}.shots[{n}]"
            for lid in shot.get("lines") or []:
                if lid not in line_ids:
                    out.append(Problem("error", w, f"No line '{lid}' in this scene.", _suggest(lid, line_ids)))
                elif lid in covered:
                    out.append(Problem("error", w, f"Line '{lid}' is already in shot {covered[lid]}."))
                else:
                    covered[lid] = n
            out += _check_shot(shot, w, present, set_info, set_name)
            secs = shot.get("seconds")
            if secs:
                need = sum(_estimate(ln) for ln in s.lines if ln.id in (shot.get("lines") or []))
                if secs < need:
                    out.append(Problem("error", f"{w}.seconds", f"The dialogue in this shot needs about {need:.1f} s, "
                                       f"longer than {secs} s.", "Lengthen the shot or split the lines."))
        order = [covered[lid] for lid in line_ids if lid in covered]
        if order != sorted(order):
            out.append(Problem("error", f"{where}.shots", "Shots must follow the order of the lines."))
        for ln in s.lines:
            w = f"{s.id}.{ln.id}"
            if ln.camera and ln.camera not in SHOTS:
                out.append(Problem("error", f"{w}.camera", f"Unknown camera '{ln.camera}'.", _suggest(ln.camera, SHOTS)))
            used: dict[str, str] = {}
            for g in ln.act or []:
                if g not in GESTURES:
                    out.append(Problem("error", f"{w}.act", f"Unknown gesture '{g}'.", _suggest(g, GESTURES)))
                    continue
                info = GESTURES[g]
                for part in info["parts"]:
                    if part in used:
                        out.append(Problem("error", f"{w}.act", f"'{g}' and '{used[part]}' both need the {part.replace('_', ' ')}.",
                                           "Give them to different lines."))
                    used[part] = g
                if info.get("prop") and info["prop"] not in set_info["props"]:
                    out.append(Problem("error", f"{w}.act", f"'{g}' needs a {info['prop']}, and the {set_name} set has none.",
                                       f"Props here: {', '.join(set_info['props']) or 'none'}."))
                if info.get("mark") == "seat" and not set_info["seats"]:
                    out.append(Problem("error", f"{w}.act", f"'{g}' needs somewhere to sit; the {set_name} set has no seats."))
            if ln.emotion and ln.emotion not in EMOTIONS:
                out.append(Problem("warning", f"{w}.emotion", f"'{ln.emotion}' is not an expression the clay renderer "
                                   "knows; it will look neutral.", _suggest(ln.emotion, EMOTIONS)))
            if ln.go and set_info["marks"] and ln.go not in set_info["marks"]:
                out.append(Problem("error", f"{w}.go", f"The {set_name} set has no mark '{ln.go}'.", _suggest(ln.go, set_info["marks"])))
            if ln.to and ln.to not in present:
                out.append(Problem("error", f"{w}.to", f"'{ln.to}' is not in this scene.", "Add them to `extras`."))
    return out


def _check_shot(shot: dict, w: str, present: list[str], set_info: dict, set_name: str) -> list[Problem]:
    out = []
    cam = shot.get("camera", "medium")
    if cam not in SHOTS:
        return [Problem("error", f"{w}.camera", f"Unknown camera '{cam}'.", _suggest(cam, SHOTS))]
    on = _on_list(shot.get("who"))
    if cam == "insert":
        if len(on) != 1 or on[0] not in set_info["props"]:
            out.append(Problem("error", f"{w}.who", "An insert shot shows one prop of the set.",
                               f"Props here: {', '.join(set_info['props']) or 'none'}."))
    else:
        for cid in on:
            if cid not in present:
                out.append(Problem("error", f"{w}.who", f"'{cid}' is not in this scene.", _suggest(cid, present)))
        spec = SHOTS[cam]
        if on and not (spec["min"] <= len(on) <= spec["max"]):
            out.append(Problem("error", f"{w}.who", f"A {cam} shot shows {spec['min']}-{spec['max']} characters, "
                               f"not {len(on)}."))
    focus = shot.get("focus")
    if focus and focus not in on:
        out.append(Problem("error", f"{w}.focus", f"The focus '{focus}' is not in the shot.", "Focus on someone in `who`."))
    if shot.get("move", "static") not in MOVES:
        out.append(Problem("error", f"{w}.move", f"Unknown camera move '{shot['move']}'.", _suggest(shot["move"], MOVES)))
    if shot.get("height", "eye") not in HEIGHTS:
        out.append(Problem("error", f"{w}.height", f"Unknown camera height '{shot['height']}'.", _suggest(shot["height"], HEIGHTS)))
    return out


# --------------------------------------------------------------------------- planning
def _default_set(scene) -> str:
    backdrop = (scene.setting or {}).get("backdrop") or "office"
    return backdrop if backdrop in SETS else "office"


def _default_lighting(scene) -> str:
    return {"morning": "daylight", "day": "office", "evening": "warm_interior", "night": "night_practical"}.get(
        (scene.setting or {}).get("time_of_day", "day"), "office")


def _present(scene, d: dict) -> list[str]:
    seen: list[str] = []
    for ln in scene.lines:
        for cid in (ln.who, ln.to):
            if cid and cid not in seen:
                seen.append(cid)
    for cid in d.get("extras") or []:
        if cid not in seen:
            seen.append(cid)
    return seen


def plan(project) -> list[ScenePlan]:
    """Direct every enabled scene: explicit shots where given, varied defaults everywhere else."""
    plans: list[ScenePlan] = []
    prev_set = None
    for s in (x for x in project.scenes if x.enabled):
        d = s.direction or {}
        set_name = d.get("set") or _default_set(s)
        present = _present(s, d)
        sides = {cid: ("left" if i % 2 == 0 else "right") for i, cid in enumerate(present)}  # screen direction holds
        explicit = {lid: shot for shot in d.get("shots") or [] for lid in shot.get("lines") or []}
        seed = int(hashlib.sha256(s.id.encode()).hexdigest()[:8], 16)
        spoken = [ln for ln in s.lines if not ln.is_card]
        last_id = spoken[-1].id if spoken else None
        shots: list[Shot] = []
        done: set[str] = set()
        for i, ln in enumerate(s.lines):
            if ln.id in done:
                continue
            if ln.id in explicit:
                spec = explicit[ln.id]
                ids = list(spec.get("lines") or [])
                done.update(ids)
                cam = spec.get("camera", "medium")
                on = _on_list(spec.get("who")) or ([ln.who] if ln.who else [])
                shots.append(_shot(s, ids, cam, on, spec.get("focus") or (on[0] if on else None),
                                   spec.get("move", "static"), spec, "as written in the scene"))
                continue
            if ln.is_card:
                shots.append(_shot(s, [ln.id], "insert", [], None, "static", {}, "an on-screen card"))
                continue
            cam, on, move, reason = _choose(s, d, ln, i, shots, present, prev_set, set_name, last_id, seed)
            shots.append(_shot(s, [ln.id], cam, on, ln.who, move, {}, reason))
        shots = _merge_holds(shots)
        plans.append(ScenePlan(s.id, set_name, d.get("lighting") or _default_lighting(s),
                               d.get("transition_in", "cut"), sides, shots))
        prev_set = set_name
    return plans


def _choose(s, d, ln, i, shots, present, prev_set, set_name, last_id, seed):
    listener = ln.to or next((c for c in present if c != ln.who), None)
    if ln.camera:
        on = [ln.who, listener] if SHOTS[ln.camera]["min"] == 2 and listener else [ln.who]
        return ln.camera, on, "static", "the line asks for this camera"
    if not shots:
        if d.get("open_with"):
            opener, why = d["open_with"], "the scene asks to open this way"
        elif set_name != prev_set:
            # the opening shot (the scene's title) has shown the place: the first line shows the people in it
            opener, why = "wide", "a new place: everyone in it, full figure"
        else:  # the same place at a new moment: vary how we come back in
            words = len((ln.say or "").split())
            options = [("wide", "the same place, a new moment"), ("establishing", "time has moved on"),
                       ("medium", "straight into the conversation")]
            if words <= 8:
                options.append(("close_up", "a short first line: open on the face"))
            opener, why = options[seed % len(options)]
        on = present if opener in ("establishing", "wide") else [ln.who]
        return opener, on, "static", why
    if ln.id == last_id:
        return "close_up", [ln.who], "push_in", "the scene's last word: closer"
    spoken_before = {x.who for x in s.lines[:i]}
    if ln.who not in spoken_before:
        return ("wide" if len(present) > 2 else "medium"), (present if len(present) > 2 else [ln.who]), "static", \
            f"{ln.who} joins the conversation: seen in context"
    prev = s.lines[i - 1] if i else None
    if prev is not None and (prev.say or "").rstrip().endswith("?") and prev.who != ln.who:
        return "close_up", [ln.who], "static", "an answer to a question"
    if (ln.say or "").rstrip().endswith("?") and listener:
        return "over_shoulder", [ln.who, listener], "static", "a question, seen past the listener"
    words = len((ln.say or "").split())
    rotation = ["two_shot", "medium", "over_shoulder", "medium", "wide", "close_up"] if len(present) == 2 else \
               ["medium", "wide", "medium", "close_up", "two_shot", "medium"]
    cam = rotation[(seed + i) % len(rotation)]
    if words > 22 and cam in ("close_up", "extreme_close_up"):
        cam = "medium"  # room for the hands in a long explanation
    recent = [x.camera for x in shots[-2:]]
    if len(recent) == 2 and recent[0] == recent[1] == cam:
        cam = next(c for c in rotation if c != cam)  # never three of the same in a row
    if cam in ("two_shot", "over_shoulder"):
        on = [ln.who, listener] if listener else [ln.who]
        if len(on) < 2:
            cam = "medium"
    else:
        on = present if cam == "wide" else [ln.who]
    return cam, on, "static", "variety within the conversation"


def _shot(s, ids, cam, on, focus, move, spec, reason) -> Shot:
    lines = [ln for ln in s.lines if ln.id in ids]
    info = SHOTS.get(cam, SHOTS["medium"])
    secs = spec.get("seconds") or round(sum(_estimate(ln) for ln in lines), 2)
    return Shot(lines=list(ids), camera=cam, who=list(on), focus=focus, move=move, seconds=secs,
                lens=int(spec.get("lens_mm") or info["lens"]), height=spec.get("height", "eye"),
                fstop=float(spec.get("fstop") or info["fstop"]),
                acts={ln.id: list(ln.act) for ln in lines if ln.act}, reason=reason)


MAX_HOLD = 12.0  # seconds a held static shot may run before the planner cuts


def _merge_holds(shots: list[Shot]) -> list[Shot]:
    """Avoid jump cuts: consecutive shots with the same framing of the same people become one shot.

    A static hold is cut after about 12 seconds (the next line gets another angle); a framing that
    ends in a push-in is one continuous move, so it always joins.
    """
    out: list[Shot] = []
    for sh in shots:
        last = out[-1] if out else None
        same = (last is not None and last.camera == sh.camera and last.who == sh.who and last.camera != "insert"
                and "as written in the scene" not in (last.reason, sh.reason))
        if same and (sh.move == "push_in" or last.seconds + sh.seconds <= MAX_HOLD):
            last.lines += sh.lines
            last.seconds = round(last.seconds + sh.seconds, 2)
            last.acts.update(sh.acts)
            if sh.move != "static":
                last.move, last.reason = sh.move, sh.reason
        elif same:  # too long to hold: same people, another angle
            alt = {"close_up": "medium", "medium": "close_up", "two_shot": "over_shoulder", "over_shoulder": "two_shot",
                   "wide": "medium", "establishing": "wide"}.get(sh.camera, "medium")
            info = SHOTS[alt]
            sh.camera, sh.lens, sh.fstop = alt, info["lens"], info["fstop"]
            if not info["min"] <= len(sh.who) <= max(info["max"], 1):
                sh.who = sh.who[:1]
            sh.reason = "a long hold: another angle on the same moment"
            out.append(sh)
        else:
            out.append(sh)
    return out


def describe(plans: list[ScenePlan]) -> str:
    """A readable shot list: what a director would hand the camera crew."""
    rows = []
    for p in plans:
        lt = LIGHTING[p.lighting] if p.lighting in LIGHTING else {}
        rows.append(f"{p.scene}: {p.set} set, {p.lighting} light ({lt.get('key_k', '?')} K), enters by {p.transition_in}")
        rows.append("   ".join(f"{c} {side}" for c, side in p.sides.items()) and
                    "   screen sides: " + ", ".join(f"{c} {side}" for c, side in p.sides.items()))
        for n, sh in enumerate(p.shots, 1):
            who = ", ".join(sh.who) or "-"
            acts = "; ".join(f"{k}: {'+'.join(v)}" for k, v in sh.acts.items())
            rows.append(f"  {n:>2}. {sh.camera:<16} {sh.lens:>3} mm  {sh.move:<8} {sh.seconds:>5.1f} s  on {who:<18}"
                        f" lines {','.join(sh.lines)}" + (f"  [{acts}]" if acts else "") + f"  ({sh.reason})")
    return "\n".join(r for r in rows if r)
