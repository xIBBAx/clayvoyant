"""Recorded voices: your own recordings, one audio file per line. Free, and the only way to get a real person.

Put a file for each line in `recordings/<language>/<line id>.<wav|flac|mp3|m4a|ogg>` inside the project (or name the
folder with `voices.providers.recorded.folder`) and give the character `voice: { provider: recorded }`. The line ids
are the ones in the scene files; `sastudio voices plan` lists them with the words to say. A line with no recording
is reported by name, never skipped silently. Record people only with their agreement.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..audio.ffmpeg import decode_to_wav
from ..errors import ProviderError
from ..safepath import resolve_inside
from .base import Audio, PreparedRequest, Provider, check_wav, repair_wav
from .common import spoken_text

EXTS = (".wav", ".flac", ".mp3", ".m4a", ".ogg")
MAX_BYTES = 200 * 1024 * 1024


class RecordedProvider(Provider):
    name = "recorded"
    key_env = None
    billable = False

    def _file(self, line_id: str, language: str) -> Path | None:
        root = Path(self.config.get("_project_root", "."))
        folder = resolve_inside(root, str(self.config.get("folder", "recordings")), what="recordings folder")
        for base in (folder / language, folder):
            for ext in EXTS:
                p = base / f"{line_id}{ext}"
                if p.is_file():
                    return p
        return None

    def validate(self, spec, lang):
        return [(f"Unknown recorded setting '{k}'.", "The recorded provider has no settings.") for k in spec.settings]

    def prepare(self, utt, spec, rules):
        text = utt.override or spoken_text(utt.resolved, self.name, rules)
        p = self._file(utt.line_id, utt.language)
        digest = hashlib.sha256(p.read_bytes()).hexdigest()[:20] if p and p.stat().st_size <= MAX_BYTES else None
        return PreparedRequest(self.name, text, {"line": utt.line_id, "language": utt.language, "file": str(p) if p else None,
                                                 "sha": digest}, characters=0)

    def synthesize(self, req: PreparedRequest, *, key, transport, timeout) -> Audio:
        f = req.fields
        if not f.get("file"):
            raise ProviderError(f"No recording for line {f['line']} [{f['language']}].",
                                f"Save it as recordings/{f['language']}/{f['line']}.wav (the words: \"{req.text[:80]}\").")
        p = Path(f["file"])
        if p.stat().st_size > MAX_BYTES:
            raise ProviderError(f"{p.name} is larger than 200 MB.", "Export the line on its own.")
        data = repair_wav(decode_to_wav(p.read_bytes()))  # FFmpeg streams a WAV with an unfinished header
        check_wav(data)
        return Audio(data)
