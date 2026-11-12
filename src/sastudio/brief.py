"""A writing brief: everything a writer who has never seen this project needs to write its scenes.

Films here are plain text, so the writing can be done by anyone, or by any chat assistant: writing a
script costs a page of text, not minutes of video. `sastudio brief` prints the brief; paste it into
the assistant you already use, save what comes back under scenes/, and film it on your own computer.

Every list in the brief is read from the same tables the validator uses, so it cannot ask for a set,
a gesture or a camera that does not exist.
"""
from __future__ import annotations

from . import direction as D

EXAMPLE = """\
id: late_bus
title: The late bus
summary: Mina is sure she has missed the last bus. Joss has checked.
setting: { time_of_day: evening }
direction:
  set: street
  lighting: night_practical
  blocking: { mina: bus_stop, joss: bench }
  business: { joss: check_phone }
lines:
  - id: lb_01
    who: mina
    to: joss
    emotion: worried
    act: [point]
    say: "That was the last one. That was the last bus, {joss}."
  - id: lb_02
    who: joss
    to: mina
    emotion: deadpan
    act: [check_phone]
    reactions: { mina: surprised }
    say: "It was the one before the last one. Four minutes."
  - id: lb_03
    who: mina
    to: joss
    go: bench
    emotion: relieved
    say: "Then I am sitting down. Wake me in three."
"""


def _words(items) -> str:
    return ", ".join(f"`{x}`" for x in items)


def _cast(project) -> str:
    rows = []
    for c in project.characters.values():
        about = ". ".join(x.strip().rstrip(".") for x in (c.role, c.description) if x and x.strip())
        rows.append(f"- `{c.id}`: {c.name}" + (f". {about}." if about else ""))
    return "\n".join(rows)


def _sets() -> str:
    rows = []
    for name, s in D.SETS.items():
        seats = set(s.get("seats") or [])
        marks = ", ".join(f"`{m}`" + (" (a seat)" if m in seats else "") for m in s["marks"])
        props = f" Things on it: {_words(s['props'])}." if s.get("props") else ""
        rows.append(f"- `{name}`. Places to stand or sit: {marks}.{props}")
    return "\n".join(rows)


def _gestures() -> str:
    held = sorted(k for k, v in D.GESTURES.items() if v["kind"] in ("hold", "loop"))
    once = sorted(k for k, v in D.GESTURES.items() if v["kind"] == "once")
    return (f"Done once: {_words(once)}.\nKept up for the whole line (also allowed in `business`, for what "
            f"someone is doing as the scene opens): {_words(held)}.")


def brief(project, idea: str | None = None, scenes: int = 2, seconds: int = 40) -> str:
    """The brief as Markdown. `idea` is what the film should be about; without it the writer is asked to ask."""
    cast_ids = list(project.characters)
    lines_each = max(4, round(seconds * D.WORDS_PER_SECOND / 14))
    parts = [
        "# Writing brief: a short clay stop-motion film",
        "You are writing the script of a short stop-motion film. The film is made from plain text files: "
        "a program reads them, sculpts the characters in clay, builds the room, plans the camera, voices the "
        "lines and films it. Your whole job is the text. Write it like a screenwriter: people who want "
        "something, short lines, one clear turn in each scene, and an ending that lands.",
        "## The film",
        (f"What it is about: {idea.strip()}" if idea and idea.strip() else
         "What it is about: ask me before you write anything, in one question."),
        (f"Length: one scene of about {seconds} seconds" if scenes == 1 else
         f"Length: {scenes} scenes of about {seconds} seconds each") + f", which is "
        f"{lines_each - 1} to {lines_each + 2} spoken lines a scene. People speak about "
        f"{D.WORDS_PER_SECOND:g} words a second. No line longer than 22 words.",
        "## The cast (use only these ids)",
        _cast(project),
        "Two or three of them in a scene works best. Write each one so they could not be mistaken for another.",
        "## What a scene file looks like",
        "One YAML file per scene. This example is complete and valid (its cast is not yours):",
        "```yaml\n" + EXAMPLE + "```",
        "## The rules of the format",
        "\n".join([
            "- `id`: lower-case letters, digits and underscores; unique in the film. Line ids are unique too.",
            "- `direction.set`: one of the places below. `direction.blocking` puts each character on one of "
            "that place's marks as the scene opens; everyone in the scene must be placed, on different marks.",
            "- `lines[].who` speaks `say` to `to`. Both are cast ids. `{id}` inside `say` becomes that "
            "character's name, so write `{" + (cast_ids[0] if cast_ids else "id") + "}` and never the name itself.",
            "- `emotion`: how the line is said. `reactions`: how a listener takes it, as `{ id: emotion }`.",
            "- `act`: up to two gestures for the line. `go`: a mark the speaker walks to as they speak "
            "(to a seat, they sit).",
            "- `camera`: only when a line needs one; left out, the film is cut for you (an answer gets a "
            "close-up, a long line cuts away to the listener, no two scenes end alike).",
            "- Spoken text is plain: no stage directions in brackets, no emoji, no markdown. Write numbers "
            "the way they are said.",
            "- Anything not listed here is not available. Do not invent places, gestures, emotions or keys.",
        ]),
        "## Places (`direction.set`)",
        _sets(),
        f"Light (`direction.lighting`): {_words(D.LIGHTING)}. Time of day (`setting.time_of_day`): "
        f"{_words(D.CLOCK_AT)}.",
        "How a scene begins (`direction.transition_in`): "
        + "; ".join(f"`{k}` ({v.split(' (')[0]})" for k, v in D.TRANSITIONS.items()) + ".",
        "Background life (`direction.dressing`, a list): "
        + "; ".join(f"`{k}` ({v})" for k, v in D.DRESSING.items()) + ".",
        "## Acting",
        f"Emotions: {_words(D.EMOTIONS)}.",
        _gestures(),
        "Cameras (`camera`): " + "; ".join(f"`{k}` ({v['framing']})" for k, v in D.SHOTS.items()
                                            if k not in ("establishing", "insert")) + ".",
        "## What to send back",
        f"Exactly {scenes} YAML file{'s' if scenes != 1 else ''}, each in its own code block, with its file "
        "name on the line above it (`scenes/01_some_id.yaml`). Then, in one more code block, the lines to add "
        "under `scenes:` in `studio.yaml`, in order:",
        "```yaml\nscenes:\n  - file: scenes/01_some_id.yaml\n```",
        "Nothing else: no explanation before or after.",
    ]
    return "\n\n".join(parts) + "\n"
