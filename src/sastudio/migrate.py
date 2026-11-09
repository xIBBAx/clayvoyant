"""Project format versions.

`schema_version` is required. When the format changes, a function here upgrades older
projects in memory (the file on disk is never rewritten silently), so existing projects keep
working. Version 1 is the first published format.
"""

from __future__ import annotations

from .errors import ConfigError

CURRENT = 1
MIGRATIONS: dict[int, callable] = {}  # from_version -> function(data) -> data (next version)


def migrate(data: dict) -> dict:
    version = data.get("schema_version")
    if version is None:
        raise ConfigError("studio.yaml has no schema_version.", "Add `schema_version: 1` at the top.")
    if not isinstance(version, int):
        raise ConfigError(f"schema_version must be a whole number, not {version!r}.")
    if version > CURRENT:
        raise ConfigError(f"This project uses format {version}; this tool understands up to {CURRENT}.",
                          "Update Security Awareness Studio.")
    while version < CURRENT:
        step = MIGRATIONS.get(version)
        if step is None:
            raise ConfigError(f"No upgrade path from format {version}.")
        data = step(data)
        version = data["schema_version"]
    return data
