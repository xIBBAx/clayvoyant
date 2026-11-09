"""Error types. Every error carries a plain-language fix so the CLI can print it."""

from __future__ import annotations


class StudioError(Exception):
    """Base error. `hint` tells the user what to do next."""

    exit_code = 1

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return self.message if not self.hint else f"{self.message}\n  Fix: {self.hint}"


class ConfigError(StudioError):
    """The project file is missing, malformed or inconsistent."""

    exit_code = 2


class UnsafePathError(StudioError):
    """A configured path points outside the folder it must stay in."""

    exit_code = 2


class TemplateError(StudioError):
    """A dialogue template uses an unknown token or bad syntax."""

    exit_code = 2


class ProviderError(StudioError):
    """A speech provider refused or failed a request."""

    exit_code = 3

    def __init__(self, message: str, hint: str | None = None, *, retryable: bool = False,
                 status: int | None = None, code: str | None = None, retry_after: str | None = None):
        super().__init__(message, hint)
        self.retryable = retryable
        self.status = status
        self.code = code
        self.retry_after = retry_after


class BudgetExceeded(StudioError):
    """A live generation would exceed the configured limits."""

    exit_code = 4


class MissingCredential(StudioError):
    """An API key needed for the requested operation is not set."""

    exit_code = 5


class ToolMissing(StudioError):
    """An external program (FFmpeg, Blender) is not installed or too old."""

    exit_code = 6


class RenderError(StudioError):
    """A render step failed."""

    exit_code = 7
