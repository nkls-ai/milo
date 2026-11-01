"""The settings the Settings window can change: what they are, which values they take, and how a change lands."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .config import ASK, KEY_NAMES, MEETING_AUTO, UPDATES, Config
from .core.events import SettingsReport
from .core.key_names import KeyNames
from .core.ports import EventSink
from .core.registry import ConfigError
from .core.types import LiveMode

log = logging.getLogger("milo.settings")

Value = str | bool | int | float | list


@dataclass(frozen=True)
class Setting:
    """One key of config.toml the window shows. `options` empty: a switch or free text. Labels name the options."""

    section: str
    key: str
    options: tuple[Value, ...] = ()
    labels: tuple[str, ...] = ()


KEY_LABELS = {"fn": "fn", "right_option": "Right Option", "right_command": "Right Command",
              "right_control": "Right Control"}

SETTINGS = (
    Setting("chat", "use", ("claude_live", "codex_live", "openai_compat", "none"),
            ("Claude CLI", "Codex CLI", "OpenAI-compatible", "Dictation only")),
    Setting("chat", "updates", UPDATES, ("Only the answer", "Short notes in his bubble", "Tells you each step")),
    Setting("dictation", "stream", tuple(m.value for m in LiveMode),
            ("When you let go", "Show the words as you speak", "Type as you speak")),
    Setting("dictation", "learn"),
    Setting("ui", "dictate_key", KEY_NAMES, tuple(KEY_LABELS[k] for k in KEY_NAMES)),
    Setting("ui", "talk_key", KEY_NAMES, tuple(KEY_LABELS[k] for k in KEY_NAMES)),
    Setting("ui", "whats_this_key", ("ctrl+option+m", "ctrl+option+w", "ctrl+shift+m", ""),
            ("Control-Option-M", "Control-Option-W", "Control-Shift-M", "Off")),
    Setting("ui", "meeting_key", ("ctrl+option+n", "ctrl+shift+n", "ctrl+option+r", ""),
            ("Control-Option-N", "Control-Shift-N", "Control-Option-R", "Off")),
    Setting("ui", "voice"),
    Setting("ui", "hide_after_s", (15, 30, 60, 300, 0), ("After 15 seconds", "After 30 seconds", "After a minute", "After 5 minutes", "Never")),
    Setting("hands", "show_window"),
    Setting("approvals", "ask", ASK, ("Every step", "Once per task", "Only when it matters (auto)")),
    Setting("approvals", "allowed_apps"),
    Setting("meetings", "auto", MEETING_AUTO,
            ("Ask me", "Without asking when my calendar has a meeting", "Never ask")),
    Setting("meetings", "always"),
    Setting("meetings", "never"),
)
ALLOWED_APPS = ("approvals", "allowed_apps")
"""Only Allow always adds an app (`keep`); the window can only take them away."""

assert all(len(s.options) == len(s.labels) for s in SETTINGS)


class ConfigFile(Protocol):
    def read(self) -> Config: ...

    def write(self, section: str, key: str, value: Value) -> Config:
        """Save one key and return the whole config as saved. Raises ConfigError and saves nothing if invalid."""
        ...


Apply = Callable[[Config], None]


class Settings:
    """Reads and writes the settings in SETTINGS. A change with an entry in `live` applies at once; the
    others wait for a restart, and the report says so until the file matches what is running again."""

    def __init__(self, file: ConfigFile, running: Config, ui: EventSink, live: Mapping[tuple[str, str], Apply]):
        self._file = file
        self._running = running
        self._ui = ui
        self._live = live

    def send(self, error: str = "") -> None:
        self._ui.emit(self.report(error))

    def report(self, error: str = "") -> SettingsReport:
        """The settings as config.toml has them now. No rows if the file can't be read."""
        try:
            config = self._file.read()
        except (OSError, ConfigError) as e:
            log.warning("settings: could not read config.toml: %s", e)
            return SettingsReport([], False, BROKEN)
        return self._report(config, error)

    def change(self, section: str, key: str, value: Value) -> None:
        if not any(s.section == section and s.key == key for s in SETTINGS):
            log.warning("settings: refused to change [%s] %s", section, key)
            self.send("That one can't be changed here.")
            return
        if (section, key) == ("chat", "use"):
            # Config leaves adapter names to the registry at composition time.
            # The settings selector can validate its closed set without starting
            # a CLI, checking credentials, or loading a model to save a choice.
            choices = next(s.options for s in SETTINGS if (s.section, s.key) == (section, key))
            if not isinstance(value, str) or value not in choices:
                self.send("Milo couldn't use that. Try one of the choices.")
                return
        if (section, key) == ALLOWED_APPS and not self._only_removes(value):
            log.warning("settings: refused to add to the always-allowed apps from the window")
            self.send("Apps are added with Allow always, when Milo asks.")
            return
        self.keep(section, key, value)

    def keep(self, section: str, key: str, value: Value) -> None:
        """Save `[section] key = value`, apply it if it is live, and report. For the window's changes after
        their checks, and for Milo's own (Allow always adds an app)."""
        try:
            config = self._file.write(section, key, value)
        except ConfigError as e:
            log.warning("settings: [%s] %s = %r not saved: %s", section, key, value, e)
            self.send(_plain(section, key, str(e)))
            return
        except OSError as e:
            log.warning("settings: could not write config.toml: %s", e)
            self.send(BROKEN)
            return
        log.info("settings: [%s] %s = %r", section, key, value)
        apply = self._live.get((section, key))
        if apply is not None:
            apply(config)
        self._ui.emit(self._report(config))

    def _only_removes(self, value: object) -> bool:
        try:
            now = self._file.read().approvals.allowed_apps
        except (OSError, ConfigError):
            return False
        return isinstance(value, list) and all(isinstance(v, dict) and v in now for v in value)

    def _report(self, config: Config, error: str = "") -> SettingsReport:
        names = self._running.platform.key_names
        rows = [{"section": s.section, "key": s.key, "value": _value(config, s), "options": list(s.options),
                 "labels": _labels(s, names), "live": (s.section, s.key) in self._live} for s in SETTINGS]
        waiting = any(_value(config, s) != _value(self._running, s) for s in SETTINGS
                      if (s.section, s.key) not in self._live)
        return SettingsReport(rows, waiting, error)


def _labels(setting: Setting, names: KeyNames) -> list[str]:
    """Key choices in the words of this computer's keyboard ("Right Alt", "Ctrl+Alt+M" on a PC)."""
    if (setting.section, setting.key) in (("ui", "dictate_key"), ("ui", "talk_key")):
        return [names.key(str(o)) for o in setting.options]
    if (setting.section, setting.key) in (("ui", "whats_this_key"), ("ui", "meeting_key")):
        return [names.combo(str(o)) for o in setting.options]
    return list(setting.labels)


BROKEN = "Milo couldn't open his settings file. If you edited it by hand, it may have a typo."


def _value(config: Config, setting: Setting) -> Value:
    if setting.key == "use":
        return config.pluggable(setting.section)[0]
    value = getattr(getattr(config, setting.section), setting.key)
    return [dict(v) for v in value] if isinstance(value, tuple) else value


def _plain(section: str, key: str, error: str) -> str:
    """ConfigError talks about config.toml; the window needs words for people."""
    if section == "ui" and key in ("dictate_key", "talk_key") and "same key" in error:
        return "The dictate key and the talk key need to be different keys."
    if "not valid TOML" in error:
        return BROKEN
    return "Milo couldn't use that. Try one of the choices."
