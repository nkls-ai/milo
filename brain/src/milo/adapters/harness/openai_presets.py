"""The OpenAI-style APIs Milo knows by name, for `[chat] use = "openai_compat"`: one table, read by Setup's
Connections & models (desktop/viewmodels/setup.py) and quoted in docs/setup/windows-linux.md.

Any other server works through "custom": an address that ends where `/chat/completions` would begin.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    base_url: str
    """Up to and without /chat/completions. Empty for "custom": the user types it."""
    key_ref: str
    """The key's file in ~/Milo/secrets; empty for a local server that needs none."""
    local: bool
    """Runs on this computer: Setup looks for it by itself and needs no key."""
    keys_url: str = ""
    """Where the user makes a key."""
    model: str = ""
    """A sensible first choice when the server can't list its models."""


PRESETS: tuple[Preset, ...] = (
    Preset("ollama", "Ollama", "http://localhost:11434/v1", "", True),
    Preset("lmstudio", "LM Studio", "http://localhost:1234/v1", "", True),
    Preset("openai", "OpenAI", "https://api.openai.com/v1", "openai.key", False,
           "https://platform.openai.com/api-keys", "gpt-5-mini"),
    Preset("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "openrouter.key", False,
           "https://openrouter.ai/keys"),
    Preset("groq", "Groq", "https://api.groq.com/openai/v1", "groq.key", False,
           "https://console.groq.com/keys"),
    Preset("custom", "Custom", "", "", False),
)


def as_dicts() -> list[dict]:
    return [asdict(p) for p in PRESETS]


def by_id(preset_id: str) -> Preset | None:
    return next((p for p in PRESETS if p.id == preset_id), None)


def matching(base_url: str) -> Preset:
    """The preset an address belongs to, by host and port; "custom" for any other."""
    def where(url: str) -> tuple[str, int | None]:
        try:
            parts = urlsplit(url.strip().rstrip("/"))
            return (parts.hostname or "").replace("127.0.0.1", "localhost"), parts.port
        except ValueError:
            return "", None
    target = where(base_url)
    return next((p for p in PRESETS if p.base_url and where(p.base_url) == target), PRESETS[-1])
