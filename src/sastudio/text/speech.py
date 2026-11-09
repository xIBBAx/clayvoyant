"""Turn display text into text a speech engine should read.

Only literal dialogue text is rewritten here. Names arrive as separate segments from the
template resolver, so a lexicon entry such as "IT" -> "I T" can never change a name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Built-in pronunciations for common security vocabulary. Projects can override or remove any
# of them in `speech.lexicon`. Matching is whole-word and case-sensitive so "IT" (the
# department) is spelled out but "it" is left alone.
DEFAULT_LEXICON: dict[str, dict[str, str]] = {
    "MFA": {"default": "M F A"},
    "2FA": {"default": "two F A"},
    "OTP": {"default": "O T P"},
    "VPN": {"default": "V P N"},
    "USB": {"default": "U S B"},
    "IT": {"default": "I T"},
    "PIN": {"default": "pin"},
    "URL": {"default": "U R L"},
    "SMS": {"default": "S M S"},
    "QR": {"default": "Q R"},
    "Wi-Fi": {"default": "Wi-Fi"},
}

DEFAULT_EMAIL_WORDS = {"at": "at", "dot": "dot", "dash": "dash", "underscore": "underscore"}

_EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)(?![\w-])")
_URL_RE = re.compile(r"\bhttps?://[^\s<>\"']+|\bwww\.[^\s<>\"']+", re.IGNORECASE)


@dataclass
class SpeechRules:
    lexicon: dict[str, dict[str, str]] = field(default_factory=lambda: dict(DEFAULT_LEXICON))
    email_words: dict[str, dict[str, str]] = field(default_factory=lambda: {"default": dict(DEFAULT_EMAIL_WORDS)})
    _compiled: list[tuple[re.Pattern, dict[str, str]]] | None = None

    def words(self, lang: str) -> dict[str, str]:
        base = dict(DEFAULT_EMAIL_WORDS)
        for key in ("default", lang.split("-")[0], lang):
            base.update(self.email_words.get(key, {}))
        return base

    def compiled(self) -> list[tuple[re.Pattern, dict[str, str]]]:
        if self._compiled is None:
            items = sorted(self.lexicon.items(), key=lambda kv: -len(kv[0]))  # longest first
            self._compiled = [
                (re.compile(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])"), forms)
                for term, forms in items if term
            ]
        return self._compiled


def _spell_part(part: str, w: dict[str, str]) -> str:
    out = []
    for token in re.split(r"([.\-_])", part):
        if token == ".":  # noqa: S105 - a text token, not a password
            out.append(f" {w['dot']} ")
        elif token == "-":  # noqa: S105
            out.append(f" {w['dash']} ")
        elif token == "_":  # noqa: S105
            out.append(f" {w['underscore']} ")
        elif token:
            out.append(token)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def speak_email(address: str, lang: str, rules: SpeechRules | None = None) -> str:
    rules = rules or SpeechRules()
    w = rules.words(lang)
    user, _, domain = address.partition("@")
    return f"{_spell_part(user, w)} {w['at']} {_spell_part(domain, w)}"


def speak_url(url: str, lang: str, rules: SpeechRules | None = None) -> str:
    rules = rules or SpeechRules()
    w = rules.words(lang)
    bare = re.sub(r"^https?://", "", url, flags=re.IGNORECASE).rstrip("/")
    host, _, path = bare.partition("/")
    spoken = _spell_part(host, w)
    if path:
        spoken += " slash " + " slash ".join(_spell_part(p, w) for p in path.split("/") if p)
    return spoken


def apply_lexicon(text: str, lang: str, rules: SpeechRules) -> str:
    def pick(forms: dict[str, str]) -> str | None:
        return forms.get(lang) or forms.get(lang.split("-")[0]) or forms.get("default")

    for pat, forms in rules.compiled():
        rep = pick(forms)
        if rep is None:
            continue
        text = pat.sub(lambda _m, r=rep: r, text)
    return text


def normalize_literal(text: str, lang: str, rules: SpeechRules) -> str:
    """Rewrite emails, URLs and lexicon terms inside literal dialogue text."""
    text = _EMAIL_RE.sub(lambda m: speak_email(m.group(0), lang, rules), text)
    text = _URL_RE.sub(lambda m: speak_url(m.group(0), lang, rules), text)
    return apply_lexicon(text, lang, rules)


def has_devanagari(text: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in text)
