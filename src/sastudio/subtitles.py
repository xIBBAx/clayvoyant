"""Subtitles (SRT, WebVTT) and transcripts.

Cues come from the real audio timing of each line. Long lines are split into several cues
at sentence or clause boundaries, each cue's time share proportional to its length, and each
cue is wrapped to at most two lines.
"""

from __future__ import annotations

import re
import textwrap
import unicodedata
from dataclasses import dataclass

MAX_CHARS_PER_LINE = 42
MAX_LINES = 2
MAX_CPS = 20.0  # characters per second; a warning, not an error


@dataclass
class Cue:
    start: float
    end: float
    text: str  # may contain one newline
    speaker: str | None = None
    line_id: str | None = None


def display_width(s: str) -> int:
    """Width in terminal-like cells; wide East Asian characters count as two."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def wrap(text: str, width: int = MAX_CHARS_PER_LINE) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= width:
        return [text]
    # Prefer a balanced two-line split near the middle at a space.
    words = text.split(" ")
    best, best_score = None, None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if len(a) > width or len(b) > width:
            continue
        score = abs(len(a) - len(b)) - (6 if a.endswith((",", ";", ":", ".", "?", "!")) else 0)
        if best_score is None or score < best_score:
            best, best_score = [a, b], score
    return best or textwrap.wrap(text, width, break_long_words=True, break_on_hyphens=False)


def chunk(text: str, width: int = MAX_CHARS_PER_LINE, lines: int = MAX_LINES) -> list[str]:
    """Split text into cue-sized chunks (each fits in `lines` wrapped lines)."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    limit = width * lines
    if len(text) <= limit and len(wrap(text, width)) <= lines:
        return [text]
    pieces = re.split(r"(?<=[.!?…।])\s+", text)
    out: list[str] = []
    for piece in pieces:
        if len(piece) <= limit and len(wrap(piece, width)) <= lines:
            out.append(piece)
            continue
        clauses = re.split(r"(?<=[,;:—–])\s+", piece)
        buf = ""
        for c in clauses:
            cand = f"{buf} {c}".strip()
            if len(cand) <= limit and len(wrap(cand, width)) <= lines:
                buf = cand
                continue
            if buf:
                out.append(buf)
            if len(c) <= limit and len(wrap(c, width)) <= lines:
                buf = c
            else:  # one very long clause: hard split by words
                words, cur = c.split(" "), ""
                for w in words:
                    cand = f"{cur} {w}".strip()
                    if len(cand) <= limit and len(wrap(cand, width)) <= lines:
                        cur = cand
                    else:
                        if cur:
                            out.append(cur)
                        cur = w
                buf = cur
        if buf:
            out.append(buf)
    # merge tiny trailing chunks into their neighbour when they fit
    merged: list[str] = []
    for c in out:
        if merged and len(c) < 12 and len(wrap(f"{merged[-1]} {c}", width)) <= lines:
            merged[-1] = f"{merged[-1]} {c}"
        else:
            merged.append(c)
    return merged


def cues_for_line(text: str, start: float, end: float, *, speaker: str | None, line_id: str | None,
                  min_cue: float = 0.8) -> list[Cue]:
    parts = chunk(text)
    if not parts:
        return []
    total = sum(len(p) for p in parts)
    span = max(end - start, min_cue * len(parts))
    cues, t = [], start
    for i, p in enumerate(parts):
        dur = span * len(p) / total
        e = end if i == len(parts) - 1 else t + dur
        cues.append(Cue(round(t, 3), round(max(e, t + 0.3), 3), "\n".join(wrap(p)), speaker, line_id))
        t = e
    return cues


def check(cues: list[Cue]) -> list[str]:
    warnings = []
    for c in cues:
        dur = c.end - c.start
        chars = len(c.text.replace("\n", ""))
        if dur > 0 and chars / dur > MAX_CPS:
            warnings.append(f"{c.line_id}: {chars / dur:.0f} characters per second is fast to read.")
        if any(display_width(ln) > MAX_CHARS_PER_LINE + 2 for ln in c.text.split("\n")):
            warnings.append(f"{c.line_id}: a subtitle line is wider than {MAX_CHARS_PER_LINE} characters.")
    for a, b in zip(cues, cues[1:], strict=False):
        if b.start < a.end - 1e-3:
            warnings.append(f"{a.line_id} and {b.line_id} overlap.")
    return warnings


def _ts(t: float, sep: str) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _clean(text: str) -> str:
    # Subtitle text is data: strip markup characters that players would interpret.
    return text.replace("<", "‹").replace(">", "›").replace("-->", "→")


def to_srt(cues: list[Cue], *, speaker_labels: bool = False) -> str:
    out = []
    for i, c in enumerate(cues, 1):
        text = _clean(c.text)
        if speaker_labels and c.speaker:
            text = f"{c.speaker.upper()}: {text}"
        out.append(f"{i}\n{_ts(c.start, ',')} --> {_ts(c.end, ',')}\n{text}\n")
    return "\n".join(out)


def to_vtt(cues: list[Cue], *, speaker_labels: bool = True, language: str | None = None) -> str:
    head = "WEBVTT" + (f"\nLanguage: {language}" if language else "") + "\n"
    out = [head]
    for c in cues:
        text = _clean(c.text)
        if speaker_labels and c.speaker:
            name = c.speaker.replace(">", "").replace("<", "")
            text = f"<v {name}>{text}"
        out.append(f"{_ts(c.start, '.')} --> {_ts(c.end, '.')}\n{text}\n")
    return "\n".join(out)


def to_transcript(rows: list[tuple[str | None, str | None, str]], title: str) -> str:
    """rows: (scene title or None, speaker or None, text)."""
    out = [title, "=" * len(title), ""]
    for scene, speaker, text in rows:
        if scene:
            out += ["", scene, "-" * len(scene)]
        elif speaker:
            out.append(f"{speaker}: {text}")
        else:
            out.append(f"[{text}]")
    return "\n".join(out).strip() + "\n"
