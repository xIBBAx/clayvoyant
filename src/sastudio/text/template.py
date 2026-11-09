"""Dialogue templates.

Dialogue never contains a character's name as plain text. It contains a token that points at
the character's stable ID, and the token is resolved when the film is built:

    "{leo}, did {org.name} really send you this?"

Resolution happens twice, for two audiences:

* display: what people read (subtitles, on-screen text, transcripts, credits)
* spoken:  what a speech engine is asked to say (spoken name, pronunciation hints)

Because a name is resolved from its ID, renaming a character can never corrupt an unrelated word
that happens to contain the old name ("Dev" inside "device", "Ana" inside "banana").

Token syntax (inside braces):

    {leo}                      the character's name
    {leo.full_name}            any field from the character's `forms` or the built-ins below
    {leo.they} {leo.Their}     pronouns (a capital first letter capitalises the result)
    {org.name}                 organisation fields and `organization.terms` entries
    {leo.gender?feminine=gayi|masculine=gaya|other=gaye}
                               choose text by a character attribute (for gendered grammar)
    {{ and }}                  literal braces
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..errors import TemplateError

PRONOUN_KEYS = ("they", "them", "their", "theirs", "themself")
PRONOUN_SETS = {
    "he": {"they": "he", "them": "him", "their": "his", "theirs": "his", "themself": "himself"},
    "she": {"they": "she", "them": "her", "their": "her", "theirs": "hers", "themself": "herself"},
    "they": {"they": "they", "them": "them", "their": "their", "theirs": "theirs", "themself": "themself"},
}
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_TOKEN_BODY = re.compile(
    r"^(?P<path>[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_\-]*)?)"
    r"(?:\?(?P<choices>.*))?$",
    re.S,
)


# --------------------------------------------------------------------------- segments
@dataclass(frozen=True)
class Seg:
    """A piece of resolved dialogue."""

    kind: str  # "text" | "name" | "email" | "url"
    display: str
    spoken: str
    ref: str | None = None  # "char:leo", "org:name", ...
    hints: tuple = ()  # provider pronunciation hints, as (provider, dict) pairs

    def hint(self, provider: str) -> dict | None:
        for p, h in self.hints:
            if p == provider:
                return h
        return None


@dataclass
class Resolved:
    segments: list[Seg]
    language: str

    @property
    def display(self) -> str:
        return _tidy("".join(s.display for s in self.segments))

    @property
    def spoken(self) -> str:
        return _tidy("".join(s.spoken for s in self.segments))


def _tidy(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


# --------------------------------------------------------------------------- context
@dataclass
class CharacterText:
    id: str
    name: str
    pronouns: str = "they"
    gender: str = "other"
    forms: dict[str, str] = field(default_factory=dict)  # "full_name" or "hi-IN.full_name"
    spoken: dict[str, str] = field(default_factory=dict)  # "default" or a language code
    pronunciation: dict[str, dict] = field(default_factory=dict)  # provider -> hint
    attrs: dict[str, str] = field(default_factory=dict)  # extra select attributes

    def spoken_name(self, lang: str) -> str:
        return self.spoken.get(lang) or self.spoken.get(lang.split("-")[0]) or self.spoken.get("default") or self.name

    def form(self, key: str, lang: str) -> str | None:
        for k in (f"{lang}.{key}", f"{lang.split('-')[0]}.{key}", key):
            if k in self.forms:
                return self.forms[k]
        if key == "name":
            return self.name
        return None

    def attr(self, key: str) -> str | None:
        if key == "gender":
            return self.gender
        if key == "pronouns":
            return self.pronouns
        return self.attrs.get(key)


@dataclass
class OrgText:
    fields: dict[str, str]  # name, short_name, security_team, it_team, training_title, ...
    spoken: dict[str, dict[str, str]] = field(default_factory=dict)  # field -> {lang|default: text}
    emails: set[str] = field(default_factory=set)  # field names that hold email addresses
    urls: set[str] = field(default_factory=set)
    pronunciation: dict[str, dict[str, dict]] = field(default_factory=dict)  # field -> provider -> hint
    localized: dict[str, dict[str, str]] = field(default_factory=dict)  # lang -> field -> text

    def value(self, key: str, lang: str) -> str:
        for k in (lang, lang.split("-")[0]):
            if key in self.localized.get(k, {}):
                return self.localized[k][key]
        if key in self.fields:
            return self.fields[key]
        raise TemplateError(f"Organisation field '{key}' has no {lang} value.",
                            f"Add it under organization.translations.{lang} or as a base field.")

    def spoken_field(self, key: str, lang: str) -> str | None:
        forms = self.spoken.get(key) or {}
        return forms.get(lang) or forms.get(lang.split("-")[0]) or forms.get("default")


@dataclass
class TextContext:
    characters: dict[str, CharacterText]
    org: OrgText
    speak_email: callable  # (address, lang) -> spoken text
    speak_url: callable  # (url, lang) -> spoken text


# --------------------------------------------------------------------------- parsing
def _split(template: str) -> list[tuple[str, str]]:
    """Split into ('text', s) and ('token', body) parts. Raises on unbalanced braces."""
    out: list[tuple[str, str]] = []
    buf: list[str] = []
    i, n = 0, len(template)
    while i < n:
        c = template[i]
        if c == "{":
            if i + 1 < n and template[i + 1] == "{":
                buf.append("{")
                i += 2
                continue
            j = template.find("}", i + 1)
            nested = template.find("{", i + 1)
            if j == -1 or (nested != -1 and nested < j):
                raise TemplateError(
                    f"Unclosed '{{' at position {i} in: {template!r}",
                    "Close every token with '}', or write '{{' for a literal brace.",
                )
            if buf:
                out.append(("text", "".join(buf)))
                buf = []
            out.append(("token", template[i + 1 : j].strip()))
            i = j + 1
            continue
        if c == "}":
            if i + 1 < n and template[i + 1] == "}":
                buf.append("}")
                i += 2
                continue
            raise TemplateError(
                f"Stray '}}' at position {i} in: {template!r}",
                "Write '}}' for a literal closing brace.",
            )
        buf.append(c)
        i += 1
    if buf:
        out.append(("text", "".join(buf)))
    return out


def tokens_in(template: str) -> list[str]:
    return [body for kind, body in _split(template) if kind == "token"]


def referenced_characters(template: str, known: Iterable[str]) -> set[str]:
    known = set(known)
    refs = set()
    for body in tokens_in(template):
        m = _TOKEN_BODY.match(body)
        if m:
            head = m.group("path").split(".")[0]
            if head in known:
                refs.add(head)
    return refs


def _parse_choices(raw: str, body: str) -> dict[str, str]:
    choices: dict[str, str] = {}
    for part in raw.split("|"):
        if "=" not in part:
            raise TemplateError(
                f"Choice '{part}' in token {{{body}}} has no '='.",
                "Write choices as key=text, for example {leo.gender?feminine=gayi|masculine=gaya|other=gaye}.",
            )
        k, v = part.split("=", 1)
        k = k.strip()
        if not k:
            raise TemplateError(f"Empty choice key in token {{{body}}}.")
        if k in choices:
            raise TemplateError(f"Choice '{k}' appears twice in token {{{body}}}.")
        choices[k] = v
    if "other" not in choices:
        raise TemplateError(
            f"Token {{{body}}} has no 'other' choice.",
            "Add other=... so every character value has text.",
        )
    return choices


def _cap(word: str, like: str) -> str:
    if like[:1].isupper() and word:
        return word[0].upper() + word[1:]
    return word


# --------------------------------------------------------------------------- resolve
def resolve(template: str, ctx: TextContext, lang: str) -> Resolved:
    segs: list[Seg] = []
    for kind, body in _split(template):
        if kind == "text":
            segs.append(Seg("text", body, body))
            continue
        segs.append(_resolve_token(body, ctx, lang, template))
    return Resolved(segs, lang)


def _resolve_token(body: str, ctx: TextContext, lang: str, template: str) -> Seg:
    m = _TOKEN_BODY.match(body)
    if not m:
        raise TemplateError(f"Token {{{body}}} is not valid in: {template!r}",
                            "Tokens look like {character_id}, {character_id.field} or {org.field}.")
    path = m.group("path")
    head, _, key = path.partition(".")
    choices_raw = m.group("choices")

    if head == "org":
        if not key:
            raise TemplateError("Token {org} needs a field, for example {org.name}.")
        if choices_raw is not None:
            raise TemplateError(f"Token {{{body}}}: choices only work on character attributes.")
        if key not in ctx.org.fields and not any(key in d for d in ctx.org.localized.values()):
            raise TemplateError(
                f"Unknown organisation field '{key}' in: {template!r}",
                f"Known fields: {', '.join(sorted(ctx.org.fields))}. Add custom ones under organization.terms.",
            )
        value = ctx.org.value(key, lang)
        hints = tuple(sorted((ctx.org.pronunciation.get(key) or {}).items()))
        if key in ctx.org.emails:
            return Seg("email", value, ctx.speak_email(value, lang), f"org:{key}", hints)
        if key in ctx.org.urls:
            return Seg("url", value, ctx.speak_url(value, lang), f"org:{key}", hints)
        spoken = ctx.org.spoken_field(key, lang) or value
        return Seg("name", value, spoken, f"org:{key}", hints)

    char = ctx.characters.get(head)
    if char is None:
        raise TemplateError(
            f"Unknown character or token '{head}' in: {template!r}",
            f"Known character IDs: {', '.join(sorted(ctx.characters)) or '(none)'}.",
        )

    if choices_raw is not None:
        attr = key or "gender"
        value = char.attr(attr)
        if value is None:
            raise TemplateError(f"Character '{head}' has no attribute '{attr}' (token {{{body}}}).")
        choices = _parse_choices(choices_raw, body)
        text = choices.get(value, choices["other"])
        return Seg("text", text, text)

    hints = tuple(sorted(char.pronunciation.items()))
    if not key or key == "name":
        return Seg("name", char.form("name", lang) or char.name, char.spoken_name(lang), f"char:{head}", hints)
    if key.lower() in PRONOUN_KEYS:
        word = PRONOUN_SETS.get(char.pronouns, PRONOUN_SETS["they"])[key.lower()]
        word = _cap(word, key)
        return Seg("text", word, word)
    form = char.form(key, lang)
    if form is None:
        raise TemplateError(
            f"Character '{head}' has no form '{key}' (token {{{body}}}).",
            f"Add it under characters.{head}.forms, or use one of: name, they, them, their.",
        )
    spoken_form = char.forms.get(f"spoken.{lang}.{key}") or char.forms.get(f"spoken.{key}") or form
    return Seg("name", form, spoken_form, f"char:{head}.{key}", hints)


# --------------------------------------------------------------------------- hardcoded-name lint
def find_literal_names(text: str, names: dict[str, str]) -> list[tuple[str, str]]:
    """Find character names written as plain text instead of tokens.

    Matching is whole-word and Unicode-aware, so 'Dev' is found in 'Dev, look' but not in
    'device'. Returns (character_id, matched_text) pairs.
    """
    plain = "".join(body for kind, body in _split(text) if kind == "text")
    norm = unicodedata.normalize("NFC", plain)
    hits = []
    for cid, name in names.items():
        name = unicodedata.normalize("NFC", name).strip()
        if not name:
            continue
        pat = re.compile(r"(?<![\w])" + re.escape(name) + r"(?![\w])", re.IGNORECASE)
        for mm in pat.finditer(norm):
            hits.append((cid, mm.group(0)))
    return hits


def valid_id(value: str) -> bool:
    return bool(_ID_RE.match(value or ""))
