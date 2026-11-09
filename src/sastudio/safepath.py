"""Path safety.

Project files are treated as untrusted input: a project downloaded from someone else must not
be able to read or overwrite files outside its own folder. Every path that comes from a project
file goes through `resolve_inside`, which rejects absolute paths, drive letters, `..` escapes
and symlinks that leave the allowed folder.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from .errors import UnsafePathError

# Characters that are unsafe in file names on at least one supported OS.
_BAD_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
MAX_NAME_LEN = 120


def _looks_absolute(raw: str) -> bool:
    return (
        PurePosixPath(raw).is_absolute()
        or PureWindowsPath(raw).is_absolute()
        or bool(PureWindowsPath(raw).drive)
        or raw.startswith(("\\\\", "//"))
        or raw.startswith("~")
    )


def resolve_inside(base: Path, raw: str, *, what: str = "path", must_exist: bool = False) -> Path:
    """Resolve `raw` relative to `base` and guarantee the result stays inside `base`.

    Accepts forward or back slashes so a project written on Windows works on Linux and the
    other way round.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise UnsafePathError(f"The {what} is empty.", "Give a path relative to the project folder.")
    if "\x00" in raw:
        raise UnsafePathError(f"The {what} contains a NUL byte.", "Remove the invisible character.")
    if _looks_absolute(raw):
        raise UnsafePathError(
            f"The {what} '{raw}' is an absolute path.",
            "Use a path relative to the project folder, for example 'assets/logo.png'.",
        )
    parts = [p for p in re.split(r"[\\/]+", raw) if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise UnsafePathError(
            f"The {what} '{raw}' uses '..' to leave the project folder.",
            "Copy the file into the project folder and point to the copy.",
        )
    base_real = Path(os.path.realpath(base))
    candidate = base_real.joinpath(*parts)
    real = Path(os.path.realpath(candidate))
    if real != base_real and base_real not in real.parents:
        raise UnsafePathError(
            f"The {what} '{raw}' resolves outside the project folder (through a symbolic link).",
            "Replace the link with a real file inside the project folder.",
        )
    if must_exist and not real.exists():
        raise UnsafePathError(f"The {what} '{raw}' does not exist.", f"Check the file is at {candidate}.")
    return real


def ensure_output_dir(base: Path, raw: str, *, protected: list[Path] | None = None) -> Path:
    """Resolve an output folder inside `base`, refusing protected locations."""
    out = resolve_inside(base, raw, what="output folder")
    for p in protected or []:
        p_real = Path(os.path.realpath(p))
        if out == p_real or p_real in out.parents:
            raise UnsafePathError(
                f"The output folder {out} is inside a protected folder {p_real}.",
                "Choose an output folder inside your own project.",
            )
    out.mkdir(parents=True, exist_ok=True)
    return out


def safe_name(name: str, *, fallback: str = "untitled") -> str:
    """Turn any string (a scene title, an org name) into a portable file name.

    Letters and digits in any script are kept (a Hindi title stays readable); punctuation and
    symbols become underscores.
    """
    import unicodedata

    name = unicodedata.normalize("NFC", name)
    name = "".join(ch if (unicodedata.category(ch)[0] in "LNM" or ch in "-_. ") else "_" for ch in name)
    cleaned = _BAD_NAME_CHARS.sub("_", name).strip(" .")
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_").lstrip(".")
    if not cleaned:
        cleaned = fallback
    if cleaned.split(".")[0].upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    if len(cleaned) > MAX_NAME_LEN:
        cleaned = cleaned[:MAX_NAME_LEN].rstrip(" ._")
    return cleaned


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write a file so readers never see half of it, even if the process is killed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))
