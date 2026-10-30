"""config.toml as sections. Swappable parts are picked by name; each adapter validates its own table."""

from __future__ import annotations

import dataclasses
import logging
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core.registry import ConfigError, options_from
from .core.types import LiveMode

log = logging.getLogger("milo.config")

KEY_NAMES = ("fn", "right_option", "right_command", "right_control")
CHARACTERS = ("pip", "classic")
PLUGGABLE = ("chat", "harness", "stt", "tts", "audio", "dictation", "connections")
SECTIONS = (*PLUGGABLE, "ui", "heartbeat", "hands", "approvals", "logging")
_COMBO = re.compile(r"^((ctrl|control|option|alt|shift|cmd|command)\+)+[a-z0-9]+$|^f([1-9]|1[0-9])$")

# `use` when a section leaves it out. Lets configs written before a section existed keep working.
DEFAULT_USE = {"chat": "claude_live", "connections": "mac"}

# Keys older templates had. ~/Milo/config.toml is never overwritten, so they are skipped with a warning.
RETIRED = {("harness", "conversation_idle_reset_s"): "it moved to [chat]",
           ("hands", "confirm_timeout_s"): "questions wait [approvals] timeout_s"}


@dataclass(frozen=True)
class ChatSettings:
    conversation_idle_reset_s: float = 600.0


@dataclass(frozen=True)
class HarnessSettings:
    pass


@dataclass(frozen=True)
class TtsSettings:
    fallback: str = "say"
    """Engine to use if `use` fails to load. Empty: none."""


@dataclass(frozen=True)
class DictationSettings:
    keep_history: bool = True
    stream: str = "preview"
    """While speaking: "off" (transcribe on release), "preview" (show the words live) or "type" (paste at pauses)."""

    def __post_init__(self):
        if self.stream not in {m.value for m in LiveMode}:
            raise ConfigError(f"[dictation] stream must be one of {', '.join(m.value for m in LiveMode)}")


@dataclass(frozen=True)
class UiSettings:
    dictate_key: str = "fn"
    talk_key: str = "right_option"
    whats_this_key: str = "ctrl+option+m"
    """A shortcut with at least one modifier (or an F key), held by nobody else. "" turns it off."""
    hands_free_max_s: float = 300.0
    """A recording locked on by a double tap stops by itself after this long."""
    character: str = "pip"
    """How Milo looks: "pip" (the bird) or "classic" (the purple robot)."""

    def __post_init__(self):
        if self.whats_this_key and not _COMBO.match(str(self.whats_this_key).lower().replace(" ", "")):
            raise ConfigError('[ui] whats_this_key must look like "ctrl+option+m" (modifiers joined with +) or be ""')
        for name in ("dictate_key", "talk_key"):
            if getattr(self, name) not in KEY_NAMES:
                raise ConfigError(f"[ui] {name} must be one of {', '.join(KEY_NAMES)}")
        if self.dictate_key == self.talk_key:
            # The app ignores a ui_config that puts both modes on one key, so fail here instead.
            raise ConfigError(f"[ui] dictate_key and talk_key can't be the same key ({self.talk_key!r})")
        if self.hands_free_max_s <= 0:
            raise ConfigError("[ui] hands_free_max_s must be more than 0")
        if self.character not in CHARACTERS:
            raise ConfigError(f"[ui] character must be one of {', '.join(CHARACTERS)}")


@dataclass(frozen=True)
class HandsSettings:
    enabled: bool = True
    """Give the worker agent the milo-mac tools: read windows, press buttons, type, click."""
    applescript: bool = True


@dataclass(frozen=True)
class HeartbeatSettings:
    enabled: bool = True


@dataclass(frozen=True)
class ConnectionSettings:
    """What the worker may reach through Milo's app connections. Each switch turns one off."""

    enabled: bool = True
    calendar: bool = True
    reminders: bool = True
    mail: bool = True
    notes: bool = True
    shortcuts: bool = True
    files: bool = True


@dataclass(frozen=True)
class ApprovalSettings:
    timeout_s: float = 60.0
    """How long Milo waits for a yes. No answer means no."""
    speak: bool = True
    """Say the question aloud, besides showing it."""


@dataclass(frozen=True)
class LoggingSettings:
    content: bool = False
    """Put what was said, replies, facts and reminder texts in brain.log. For debugging only."""
    max_mb: float = 2.0
    keep: int = 3
    """Old logs kept besides brain.log, each up to max_mb."""


@dataclass(frozen=True)
class SttSettings:
    pass


@dataclass(frozen=True)
class AudioSettings:
    pass


_PLUGGABLE_SETTINGS: dict[str, type] = {
    "chat": ChatSettings, "harness": HarnessSettings, "stt": SttSettings, "tts": TtsSettings,
    "audio": AudioSettings, "dictation": DictationSettings, "connections": ConnectionSettings,
}


class Config:
    def __init__(self, raw: Mapping[str, Any]):
        unknown = sorted(set(raw) - set(SECTIONS))
        if unknown:
            raise ConfigError(f"unknown section(s) in config.toml: {', '.join(unknown)}")
        for name in SECTIONS:
            if not isinstance(raw.get(name, {}), dict):
                raise ConfigError(f"[{name}] must be a table")
        self._raw = raw
        settings = {name: _pluggable_settings(cls, raw.get(name, {}), name)
                    for name, cls in _PLUGGABLE_SETTINGS.items()}
        self.chat: ChatSettings = settings["chat"]
        self.harness: HarnessSettings = settings["harness"]
        self.tts: TtsSettings = settings["tts"]
        self.dictation: DictationSettings = settings["dictation"]
        self.connections: ConnectionSettings = settings["connections"]
        approvals = raw.get("approvals", {})
        self.approvals = _pluggable_settings(ApprovalSettings, approvals, "approvals")
        if not isinstance(approvals.get("levels", {}), dict):
            raise ConfigError("[approvals.levels] must be a table")
        self.approval_levels: dict[str, Any] = dict(approvals.get("levels", {}))
        self.logging = _typed(options_from(LoggingSettings, raw.get("logging", {}), "logging"), "logging")
        self.ui = _typed(options_from(UiSettings, raw.get("ui", {}), "ui"), "ui")
        heartbeat = {k: v for k, v in raw.get("heartbeat", {}).items() if k == "enabled"}
        self.heartbeat = _typed(HeartbeatSettings(**heartbeat), "heartbeat")
        self.hands = _typed(options_from(HandsSettings, _current(raw.get("hands", {}), "hands"), "hands"), "hands")

    @classmethod
    def load(cls, path: Path) -> Config:
        return cls.parse(path.read_text(), str(path))

    @classmethod
    def parse(cls, text: str, source: str = "config.toml") -> Config:
        try:
            return cls(tomllib.loads(text))
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{source} is not valid TOML: {e}") from None

    def pluggable(self, section: str) -> tuple[str, dict[str, Any]]:
        """`use = "<name>"` and that implementation's `[section.<name>]` table (empty if absent)."""
        table = self.section(section)
        name = table.get("use", DEFAULT_USE.get(section))
        if not isinstance(name, str) or not name:
            raise ConfigError(f"[{section}] needs use = \"<name>\"")
        options = table.get(name, {})
        if not isinstance(options, dict):
            raise ConfigError(f"[{section}.{name}] must be a table")
        return name, options

    def section(self, name: str) -> dict[str, Any]:
        return self._raw.get(name, {})


def _pluggable_settings(cls: type, table: Mapping[str, Any], section: str):
    """Top-level keys other than `use` and implementation tables belong to the settings dataclass."""
    own = {k: v for k, v in table.items() if k != "use" and not isinstance(v, dict)}
    return _typed(options_from(cls, _current(own, section), section), section)


def _current(table: Mapping[str, Any], section: str) -> dict[str, Any]:
    """`table` without RETIRED keys, each skipped with a warning."""
    current = dict(table)
    for key in [k for k in current if (section, k) in RETIRED]:
        log.warning("ignoring [%s] %s in config.toml: %s", section, key, RETIRED[section, key])
        del current[key]
    return current


def _typed(settings, section: str):
    """Reject `enabled = "no"` and friends: a value must have its default's type (ints pass as floats)."""
    for f in dataclasses.fields(settings):
        value, expected = getattr(settings, f.name), type(f.default)
        allowed = (int, float) if expected is float else expected
        if isinstance(value, bool) != (expected is bool) or not isinstance(value, allowed):
            raise ConfigError(f"[{section}] {f.name} must be {expected.__name__}, got {value!r}")
    return settings
