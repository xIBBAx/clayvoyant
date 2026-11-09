"""Shared helpers for building the text a provider is asked to say."""

from __future__ import annotations

import re

from ..text.speech import SpeechRules, normalize_literal
from ..text.template import Resolved


def spoken_text(resolved: Resolved, provider: str, rules: SpeechRules, *, name_hook=None) -> str:
    """Join resolved segments into speech text.

    Literal text gets email/URL/lexicon normalisation. Names use the provider's pronunciation
    hint when the character defines one, otherwise the character's spoken form.
    `name_hook(seg, hint)` lets a provider wrap a name (for example in a phoneme tag).
    """
    out = []
    for seg in resolved.segments:
        if seg.kind == "text":
            out.append(normalize_literal(seg.display, resolved.language, rules))
            continue
        hint = seg.hint(provider)
        if name_hook is not None:
            wrapped = name_hook(seg, hint)
            if wrapped is not None:
                out.append(wrapped)
                continue
        if hint and hint.get("text"):
            out.append(hint["text"])
        elif hint and hint.get("alias"):
            out.append(hint["alias"])
        else:
            out.append(seg.spoken)
    text = "".join(out)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text
