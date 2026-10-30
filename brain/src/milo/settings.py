"""The settings the Settings window can change: what they are, which values they take, and how a change lands."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .config import KEY_NAMES, UPDATES, Config
from .core.events import SettingsReport
from .core.ports import EventSink
from .core.registry import ConfigError
from .core.types import LiveMode

log = logging.getLogger("milo.settings")

Value = str | bool | int | float


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
)

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

    def _report(self, config: Config, error: str = "") -> SettingsReport:
        rows = [{"section": s.section, "key": s.key, "value": _value(config, s), "options": list(s.options),
                 "labels": list(s.labels), "live": (s.section, s.key) in self._live} for s in SETTINGS]
        waiting = any(_value(config, s) != _value(self._running, s) for s in SETTINGS
                      if (s.section, s.key) not in self._live)
        return SettingsReport(rows, waiting, error)


BROKEN = "Milo couldn't open his settings file. If you edited it by hand, it may have a typo."


def _value(config: Config, setting: Setting) -> Value:
    return getattr(getattr(config, setting.section), setting.key)


def _plain(section: str, key: str, error: str) -> str:
    """ConfigError talks about config.toml; the window needs words for people."""
    if section == "ui" and key in ("dictate_key", "talk_key") and "same key" in error:
        return "The dictate key and the talk key need to be different keys."
    if "not valid TOML" in error:
        return BROKEN
    return "Milo couldn't use that. Try one of the choices."
