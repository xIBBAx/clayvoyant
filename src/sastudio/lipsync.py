"""Mouth shapes for a spoken line, from its words and the loudness of its audio.

The clay puppets speak with the nine mouth shapes of the Rhubarb alphabet (A closed, B teeth, C open, D wide open,
E rounded, F pucker, G lip on teeth, H tongue up, X rest). The best source is a phoneme track: a voice provider
that reports phoneme times (`cues_from_phonemes`), or Rhubarb Lip Sync when it is installed. Without either, the
shapes are read from the spelling and laid over the parts of the audio where someone is actually speaking, so the
mouth closes in every pause and opens on the vowels. That is an approximation, and it is honest work for a puppet:
stop-motion mouths are replacement shapes on twos, not a phonetic transcription.
"""

from __future__ import annotations

import re

REST = "X"
# Latin letters. Digraphs first.
_DIGRAPHS = {"th": "H", "sh": "B", "ch": "B", "ph": "G", "wh": "F", "oo": "F", "ou": "E", "ow": "E", "ee": "B",
             "ea": "B", "ai": "C", "ay": "C", "oa": "E", "au": "E", "aw": "E", "qu": "F", "ng": "B", "ck": "B"}
_LETTERS = {**dict.fromkeys("a", "D"), **dict.fromkeys("e", "C"), **dict.fromkeys("iy", "B"), **dict.fromkeys("o", "E"),
            **dict.fromkeys("u", "F"), **dict.fromkeys("mbp", "A"), **dict.fromkeys("fv", "G"), **dict.fromkeys("ltdn", "H"),
            **dict.fromkeys("w", "F"), **dict.fromkeys("cgjkqrsxzh", "B")}
# Devanagari: independent vowels, vowel signs and consonants.
_DEVA = {**dict.fromkeys("अआाॅ", "D"), **dict.fromkeys("इईिी", "B"), **dict.fromkeys("उऊुू", "F"), **dict.fromkeys("एऐेै", "C"),
         **dict.fromkeys("ओऔोौऑॉ", "E"), **dict.fromkeys("पफबभम", "A"), **dict.fromkeys("व", "G"),
         **dict.fromkeys("तथदधनलटठडढणरड़ढ़", "H"), **dict.fromkeys("कखगघङचछजझञशषसहयक़ख़ग़ज़फ़", "B")}
_VOWELS = set("DCEF")
# Phonemes (IPA and ARPAbet-like symbols, as text-to-speech engines report them) to mouth shapes.
_PHONEMES = {**dict.fromkeys(["m", "b", "p"], "A"), **dict.fromkeys(["f", "v"], "G"),
             **dict.fromkeys(["l", "t", "d", "n", "θ", "ð", "ɾ", "ʈ", "ɖ", "ɳ", "ɭ", "th", "dh"], "H"),
             **dict.fromkeys(["a", "ɑ", "æ", "ʌ", "aɪ", "aʊ", "aa", "ae", "ah", "ay", "aw", "ɐ", "A", "W"], "D"),
             **dict.fromkeys(["e", "ɛ", "ə", "ɜ", "eɪ", "eh", "er", "ey", "ɚ", "ɝ"], "C"),
             **dict.fromkeys(["i", "ɪ", "iː", "j", "iy", "ih", "y", "s", "z", "k", "g", "ɡ", "ŋ", "ʃ", "ʒ", "tʃ", "dʒ", "h", "ɹ", "r",
                              "x", "ʤ", "ʧ", "I"], "B"),
             **dict.fromkeys(["o", "ɔ", "ɒ", "oʊ", "ɔɪ", "ao", "ow", "oy", "O", "Y"], "E"),
             **dict.fromkeys(["u", "ʊ", "uː", "w", "uw", "uh"], "F")}


def shapes_for_text(text: str) -> list[tuple[str, float]]:
    """The mouth shapes a line passes through, with a weight for how long each is held. Words are separated by REST."""
    out: list[tuple[str, float]] = []
    for word in re.findall(r"[^\W\d_]+|\d+", text or "", flags=re.UNICODE):
        w = word.lower()
        shapes: list[str] = []
        i = 0
        while i < len(w):
            two = w[i:i + 2]
            if two in _DIGRAPHS:
                shapes.append(_DIGRAPHS[two])
                i += 2
                continue
            ch = w[i]
            s = _LETTERS.get(ch) or _DEVA.get(ch)
            if s is None and ch.isdigit():
                s = "C"
            if s and not (shapes and shapes[-1] == s and s not in _VOWELS):
                shapes.append(s)
            i += 1
        if w.endswith("e") and len(shapes) > 2 and w[-1] in _LETTERS:   # a silent final e
            shapes.pop()
        if not shapes:
            continue
        if out:
            out.append((REST, 0.35))
        out += [(s, 1.3 if s in _VOWELS else 0.75) for s in shapes]
    return out


def _voiced(env: list[float], floor: float = 0.07) -> list[bool]:
    if not env or max(env) <= 0.02:      # a silent placeholder voice: the whole line counts as spoken
        return [True] * max(1, len(env))
    v = [e > floor for e in env]
    for i in range(1, len(v) - 1):       # a single quiet frame inside speech is not a pause
        if not v[i] and v[i - 1] and v[i + 1]:
            v[i] = True
    return v


def cues_from_text(text: str, env: list[float], fps: int = 24) -> list[list]:
    """[[seconds, shape], ...] from the start of the audio: the line's shapes spread over its spoken frames."""
    shapes = shapes_for_text(text)
    if not shapes:
        return []
    voiced = _voiced(env)
    spoken = [i for i, v in enumerate(voiced) if v]
    if not spoken:
        return []
    total = sum(w for _, w in shapes)
    cues: list[list] = []
    acc = 0.0
    last_frame = -1
    for shape, w in shapes:
        k = min(len(spoken) - 1, int(acc / total * len(spoken)))
        frame = spoken[k]
        if frame > last_frame + 1 and last_frame >= 0 and not all(voiced[last_frame + 1:frame]):
            # a real pause in the voice between these two sounds: the mouth rests through it
            gap = next(i for i in range(last_frame + 1, frame) if not voiced[i])
            cues.append([round(gap / fps, 3), REST])
        if not cues or cues[-1][1] != shape or frame - last_frame > 2:
            cues.append([round(frame / fps, 3), shape])
        last_frame = frame
        acc += w
    end = spoken[-1] + 1
    cues.append([round(end / fps, 3), REST])
    out = [cues[0]]
    for c in cues[1:]:
        if c[0] > out[-1][0]:
            out.append(c)
        else:
            out[-1] = [out[-1][0], c[1]] if c[1] != REST else out[-1]
    return out


def cues_from_phonemes(phonemes: list[tuple[str, float, float]]) -> list[list]:
    """[[seconds, shape], ...] from a phoneme track [(symbol, start, end), ...] in seconds."""
    cues: list[list] = []
    t_end = 0.0
    for sym, start, end in phonemes:
        s = (sym or "").strip().strip("ˈˌː")
        if not s:
            continue
        shape = _PHONEMES.get(s) or _PHONEMES.get(s.lower()) or _PHONEMES.get(s[:1]) or _PHONEMES.get(s[:1].lower())
        if shape is None:
            shape = REST if not s.isalpha() else "B"
        if start - t_end > 0.12 and cues:
            cues.append([round(t_end, 3), REST])
        if not cues or cues[-1][1] != shape:
            cues.append([round(start, 3), shape])
        t_end = max(t_end, end)
    if cues:
        cues.append([round(t_end, 3), REST])
    return cues
