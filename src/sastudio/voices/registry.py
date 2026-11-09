"""Provider lookup. Add a provider here (and to the schema enum) to support a new service."""

from __future__ import annotations

from .base import Provider
from .elevenlabs import ElevenLabsProvider
from .offline import OfflineProvider
from .sarvam import SarvamProvider

PROVIDERS: dict[str, type[Provider]] = {
    "sarvam": SarvamProvider,
    "elevenlabs": ElevenLabsProvider,
    "offline": OfflineProvider,
}


def get_provider(name: str, config: dict | None = None) -> Provider:
    try:
        return PROVIDERS[name](config or {})
    except KeyError:
        raise KeyError(f"Unknown provider '{name}'. Known: {', '.join(PROVIDERS)}")


_CONFIGS: dict[str, dict] = {}


def set_provider_configs(configs: dict[str, dict]) -> None:
    _CONFIGS.clear()
    _CONFIGS.update(configs or {})


def validate_voice(spec, lang: str) -> list[tuple[str, str | None]]:
    if spec.provider not in PROVIDERS:
        return [(f"Unknown provider '{spec.provider}'.", f"Use one of {', '.join(PROVIDERS)}.")]
    return get_provider(spec.provider, _CONFIGS.get(spec.provider)).validate(spec, lang)
