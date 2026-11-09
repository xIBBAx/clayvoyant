"""Export a project's pronunciations for upload to a provider (no network access here).

* elevenlabs-rules: body for POST /v1/pronunciation-dictionaries/add-from-rules
* elevenlabs-pls:   a W3C PLS 1.0 lexicon file for add-from-file
* sarvam-dict:      {"pronunciations": {"<language>": {"word": "replacement"}}} for Sarvam's
                    pronunciation-dictionary upload

After uploading, put the returned ids in studio.yaml (see docs/VOICE_PROVIDERS.md).
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

from ..safepath import atomic_write_text


def _entries(project):
    """Yield (grapheme, kind, value, language|None) from characters, the org and the lexicon."""
    for c in project.characters.values():
        el = c.pronunciation.get("elevenlabs") or {}
        if el.get("ipa"):
            yield c.name, "ipa", el["ipa"], None
        elif el.get("alias"):
            yield c.name, "alias", el["alias"], None
        sv = c.pronunciation.get("sarvam") or {}
        if sv.get("text"):
            yield c.name, "sarvam", sv["text"], None
        for lang, form in c.spoken.items():
            if form != c.name:
                yield c.name, "spoken", form, None if lang == "default" else lang
    org = project.org
    for lang, form in (org.get("spoken_name") or {}).items():
        if form != org["name"]:
            yield org["name"], "spoken", form, None if lang == "default" else lang
    for term, forms in project.speech.lexicon.items():
        for lang, form in forms.items():
            if form != term:
                yield term, "spoken", form, None if lang == "default" else lang


def export(project, fmt: str, out: Path) -> None:
    rows = list(_entries(project))
    if fmt == "elevenlabs-rules":
        rules, seen = [], set()
        for g, kind, value, lang in rows:
            if kind == "sarvam" or (lang and not lang.startswith("en")) or g in seen:
                continue
            seen.add(g)
            if kind == "ipa":
                rules.append({"type": "phoneme", "string_to_replace": g, "phoneme": value, "alphabet": "ipa"})
            else:
                rules.append({"type": "alias", "string_to_replace": g, "alias": value})
        body = {"name": f"{project.title[:60]} pronunciations", "rules": rules}
        atomic_write_text(out, json.dumps(body, ensure_ascii=False, indent=1))
    elif fmt == "elevenlabs-pls":
        lex, seen = [], set()
        for g, kind, value, lang in rows:
            if kind == "sarvam" or (lang and not lang.startswith("en")) or g in seen:
                continue
            seen.add(g)
            inner = f"<phoneme>{escape(value)}</phoneme>" if kind == "ipa" else f"<alias>{escape(value)}</alias>"
            lex.append(f"  <lexeme>\n    <grapheme>{escape(g)}</grapheme>\n    {inner}\n  </lexeme>")
        xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<lexicon version="1.0" '
               'xmlns="http://www.w3.org/2005/01/pronunciation-lexicon" alphabet="ipa" xml:lang="en-US">\n'
               + "\n".join(lex) + "\n</lexicon>\n")
        atomic_write_text(out, xml)
    elif fmt == "sarvam-dict":
        prons: dict[str, dict[str, str]] = {}
        for g, kind, value, lang in rows:
            if kind == "ipa":
                continue
            for target in ([lang] if lang else project.languages):
                prons.setdefault(target, {}).setdefault(g, value)
        atomic_write_text(out, json.dumps({"pronunciations": prons}, ensure_ascii=False, indent=1))
    else:
        raise ValueError(f"unknown format {fmt}")
