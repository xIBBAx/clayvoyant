"""Hindi in Roman letters, the way people type it on a phone: "Papa, ek minute ke liye phone neeche rakhiye."

A great many people who speak Hindi read it more easily, and forward it more readily, in Roman letters than in
Devanagari. So a project can list `hi-Latn` among its languages. That film is the Hindi film (the same lines, the same
voices, the same filmed shots) with every word on screen written in Roman letters: subtitles, titles, key points,
posters, phone captions. Nothing is written twice: the Hindi lines stay in Devanagari, which is what a voice reads
best, and this module spells them out.

    languages: [en-IN, hi-IN, hi-Latn]

How a word is spelled, in order:
1. A line can carry its own Roman text (`translations: { hi-Latn: "..." }`); then nothing here runs for that line.
2. Words in `data/romanize_hi.json` are spelled as listed. That file holds English words Hindi has borrowed
   ("वीडियो कॉल" is "video call", not "veediyo kol") and the handful of Hindi words everybody spells one way
   ("नहीं" is "nahin").
3. Everything else goes letter by letter, dropping the vowel Hindi itself leaves unspoken ("करना" is "karna", not
   "karanaa"; "समझना" is "samajhna").

This is everyday spelling, not a scholar's transliteration: it has no accents or dots, and it cannot be turned back
into Devanagari.
"""

from __future__ import annotations

import json
import re
from functools import cache
from importlib import resources

# A language shown in Roman letters -> the language it is written and spoken in.
ROMAN_OF = {"hi-Latn": "hi-IN"}


def spoken_language(lang: str) -> str:
    """The language whose lines and voices a film in `lang` uses: itself, unless `lang` is a Roman-letter rendering."""
    return ROMAN_OF.get(lang, lang)


def romanize(text: str, lang: str) -> str:
    """`text` as people of `lang` read it: unchanged unless `lang` is a Roman-letter rendering."""
    return hindi(text) if lang == "hi-Latn" else text


# --------------------------------------------------------------------------- the letters
_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "ळ": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}
_NUKTA = {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "ड": "d", "ढ": "dh", "फ": "f", "य": "y"}   # the dotted letters
_PRECOMPOSED = dict(zip(map(chr, range(0x958, 0x960)), "कखगजडढफय", strict=True))     # the same letters as single characters
_VOWELS = {"अ": "a", "आ": "A", "इ": "i", "ई": "I", "उ": "u", "ऊ": "U", "ऋ": "ri", "ए": "e", "ऐ": "ai", "ऍ": "e",
           "ऑ": "o", "ओ": "o", "औ": "au"}
_SIGNS = {"ा": "A", "ि": "i", "ी": "I", "ु": "u", "ू": "U", "ृ": "ri", "े": "e", "ै": "ai", "ॅ": "e", "ॉ": "o",
          "ो": "o", "ौ": "au"}
_VIRAMA, _NUKTA_SIGN, _ANUSVARA, _CHANDRABINDU, _VISARGA = "्", "़", "ं", "ँ", "ः"
_LABIALS = {"p", "ph", "f", "b", "bh", "m"}
_LONG = {"A": ("aa", "a"), "I": ("ee", "i"), "U": ("oo", "u")}        # inside a word, at its end
_WORD = re.compile(r"[\u0900-\u0963\u0971-\u097F]+")
_PUNCTUATION = str.maketrans({"।": ".", "॥": ".", **{chr(0x966 + d): str(d) for d in range(10)}})


@cache
def _listed() -> dict[str, str]:
    data = json.loads(resources.files("sastudio").joinpath("data", "romanize_hi.json").read_text("utf-8"))
    return {word: roman for group in data["words"].values() for word, roman in group.items()}


class _Syllable:
    """One written syllable: its consonants, its vowel ('' when it has none, 'a' for the unwritten one), its nasal."""

    def __init__(self):
        self.onset: list[str] = []
        self.vowel = ""
        self.unwritten = False      # the vowel is the one Devanagari does not write, which speech often drops
        self.nasal = False
        self.breath = False


def _syllables(word: str) -> list[_Syllable]:
    out: list[_Syllable] = []
    cur: _Syllable | None = None
    letter = ""                     # the consonant just read, for a dot that follows it
    joining = False                 # that consonant carried a virama: the next one joins its cluster
    for ch in word:
        dotted = ch in _PRECOMPOSED
        ch = _PRECOMPOSED.get(ch, ch)
        if ch in _CONSONANTS:
            if cur is None or not joining:
                cur = _Syllable()
                out.append(cur)
            cur.onset.append(_NUKTA[ch] if dotted else _CONSONANTS[ch])
            cur.vowel, cur.unwritten, joining, letter = "a", True, False, ch
        elif ch in _VOWELS:
            cur = _Syllable()
            cur.vowel = _VOWELS[ch]
            out.append(cur)
            joining, letter = False, ""
        elif cur is None:
            continue                # a sign with nothing to sit on
        elif ch == _NUKTA_SIGN:
            if letter in _NUKTA and cur.onset:
                cur.onset[-1] = _NUKTA[letter]
        elif ch == _VIRAMA:
            cur.vowel, cur.unwritten, joining = "", False, True
        elif ch in _SIGNS:
            cur.vowel, cur.unwritten, joining = _SIGNS[ch], False, False
        elif ch in (_ANUSVARA, _CHANDRABINDU):
            cur.nasal = True
        elif ch == _VISARGA:
            cur.breath = True
    return out


def _drop_unspoken(syl: list[_Syllable]) -> None:
    """Hindi does not say every vowel it leaves unwritten: not at the end of a word (कल is "kal"), and not in the
    middle when the syllables on both sides can carry it (करना is "kar-na")."""
    def droppable(s: _Syllable) -> bool:
        return s.unwritten and not s.nasal and not s.breath

    last = syl[-1]
    if len(syl) > 1 and droppable(last):
        # after a cluster that ends in y, r or v the vowel is heard: सत्य "satya", मित्र "mitra", तत्व "tatva"
        if not (len(last.onset) > 1 and last.onset[-1] in ("y", "r", "v")):
            last.vowel = ""
    for i in range(len(syl) - 2, 0, -1):
        s, after = syl[i], syl[i + 1]
        if droppable(s) and len(s.onset) == 1 and len(after.onset) == 1 and after.vowel and syl[i - 1].vowel:
            s.vowel = ""


def _spell(word: str) -> str:
    syl = _syllables(word)
    if not syl:
        return word
    _drop_unspoken(syl)
    out = []
    for i, s in enumerate(syl):
        after = syl[i + 1] if i + 1 < len(syl) else None
        final = after is None
        onset = "".join(s.onset)
        if len(s.onset) == 2 and s.onset[1].startswith(s.onset[0]) and s.onset[1] != s.onset[0]:
            onset = s.onset[1]                              # च्छ is "chh", not "chchh"
        v = s.vowel
        if v in _LONG:
            inside, at_end = _LONG[v]
            if v == "A" and not s.onset and i == 0:
                v = "aa"                                    # आप "aap", आज "aaj"
            elif after is not None and not after.onset:
                v = at_end                                  # before another vowel: बताओ "batao"
            elif final and not (s.nasal and v == "U"):
                v = at_end                                  # का "ka", यहाँ "yahan", but हूँ "hoon"
            else:
                v = inside
        if after is not None and not after.onset and after.vowel in ("e", "I"):
            if v == "i" or s.vowel in ("a", "A"):
                v += "y"                                    # रखिए "rakhiye", गए "gaye", गई "gayi", डराए "daraye"
        nasal = ""
        if s.nasal:
            nasal = "m" if after is not None and after.onset and after.onset[0] in _LABIALS else "n"
            if final and v == "e":
                v = "ei"                                    # में "mein", करें "karein"
        out.append(onset + v + nasal + ("h" if s.breath else ""))
    return "".join(out)


def hindi(text: str) -> str:
    """Hindi written in Devanagari, in everyday Roman spelling. Anything not in Devanagari is left exactly as it is."""
    listed = _listed()

    def one(m: re.Match) -> str:
        word = m.group(0)
        roman = listed.get(word) or _spell(word)
        before = text[:m.start()].rstrip(" \"'“‘(")
        starts_sentence = not before or before[-1] in ".?!।॥\n"
        return roman[:1].upper() + roman[1:] if starts_sentence and roman[:1].islower() else roman

    return _WORD.sub(one, text).translate(_PUNCTUATION)
