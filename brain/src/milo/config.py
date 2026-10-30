"""config.toml as sections. Swappable parts are picked by name; each adapter validates its own table."""

from __future__ import annotations

import dataclasses
import logging
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any

from .core.registry import ConfigError, options_from
from .core.types import LiveMode

log = logging.getLogger("milo.config")

KEY_NAMES = ("fn", "right_option", "right_command", "right_control")
CHARACTERS = ("milo",)
# Looks Milo used to have. Old config files still name them; they all mean the wren now.
RETIRED_CHARACTERS = ("pip", "classic", "dragon", "kit", "glow")
PLUGGABLE = ("chat", "harness", "stt", "tts", "audio", "dictation", "connections", "messages")
SECTIONS = (*PLUGGABLE, "ui", "heartbeat", "hands", "approvals", "logging", "memory", "routines", "meetings")
_COMBO = re.compile(r"^((ctrl|control|option|alt|shift|cmd|command)\+)+[a-z0-9]+$|^f([1-9]|1[0-9])$")

# `use` when a section leaves it out. Lets configs written before a section existed keep working.
DEFAULT_USE = {"chat": "claude_live", "connections": "mac", "messages": "telegram"}

# Keys older templates had. ~/Milo/config.toml is never overwritten, so they are skipped with a warning.
RETIRED = {("harness", "conversation_idle_reset_s"): "it moved to [chat]",
           ("hands", "confirm_timeout_s"): "questions wait [approvals] timeout_s"}


UPDATES = ("quiet", "bubble", "chatty")
MAX_HELPERS = 8


@dataclass(frozen=True)
class ChatSettings:
    conversation_idle_reset_s: float = 600.0
    updates: str = "bubble"
    """How Milo tells you about work in progress: "quiet" (only the small birds and the window), "bubble"
    (short notes in the bubble) or "chatty" (he also says them). Results and questions always come through."""
    voice_barge_in: bool = False
    """Listen while Milo speaks, and let the user stop him by talking. Opens the mic whenever he speaks."""
    backchannels: bool = True
    """A short "hm" when the answer is slow to come, so silence never feels like Milo didn't hear."""

    def __post_init__(self):
        if self.updates not in UPDATES:
            raise ConfigError(f"[chat] updates must be one of {', '.join(UPDATES)}")


@dataclass(frozen=True)
class HarnessSettings:
    max_helpers: int = 3
    """How many helpers work at the same time. Work on the screen always goes one at a time."""

    def __post_init__(self):
        if isinstance(self.max_helpers, bool) or not isinstance(self.max_helpers, int) \
                or not 1 <= self.max_helpers <= MAX_HELPERS:
            raise ConfigError(f"[harness] max_helpers must be a whole number from 1 to {MAX_HELPERS}")


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
    character: str = "milo"
    """How Milo looks. There is one Milo, a wren in a marigold scarf; the retired looks still load and mean him."""
    voice: bool = True
    """Say answers out loud. False: the bubble and the window only."""

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
        if self.character not in CHARACTERS + RETIRED_CHARACTERS:
            raise ConfigError('[ui] character must be "milo"')


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


MAX_ROUTINE_RUNS = 50


@dataclass(frozen=True)
class RoutineSettings:
    enabled: bool = True
    """Routines: recipes Milo keeps in ~/Milo/routines and runs again on request or on a schedule."""
    max_runs_per_day: int = 6
    """Scheduled runs a day, all routines together. Asking for one yourself is never capped."""
    grace_hours: float = 4.0
    """A scheduled run the Mac slept through runs at wake if it is at most this late; after that Milo says he
    missed it."""

    def __post_init__(self):
        if isinstance(self.max_runs_per_day, bool) or not isinstance(self.max_runs_per_day, int) \
                or not 0 <= self.max_runs_per_day <= MAX_ROUTINE_RUNS:
            raise ConfigError(f"[routines] max_runs_per_day must be a whole number from 0 to {MAX_ROUTINE_RUNS}")
        if isinstance(self.grace_hours, bool) or not isinstance(self.grace_hours, (int, float)) \
                or not 0 <= self.grace_hours <= 48:
            raise ConfigError("[routines] grace_hours must be from 0 to 48")


@dataclass(frozen=True)
class MessagesSettings:
    """Milo by message: reach Milo on the Mac from your phone (`use` picks the chat app). Off by default."""

    enabled: bool = False
    max_per_minute: int = 10
    """Messages from your phone Milo answers per minute. More are dropped, with one note."""
    away_after_min: float = 5.0
    """With no keyboard or mouse use for this long, Milo's questions go to your phone and only it can answer."""
    question_timeout_s: float = 150.0
    """How long a question sent to your phone waits. A helper's turn ends after [harness.*] timeout_s anyway."""
    brief_at: str = ""
    """A morning brief to your phone every day at this time, like "07:30". "" is off."""
    max_file_mb: float = 45.0
    """The biggest file Milo sends you (always after a yes). Telegram takes up to 50 MB from a bot."""

    def __post_init__(self):
        if isinstance(self.max_per_minute, bool) or not isinstance(self.max_per_minute, int) \
                or not 1 <= self.max_per_minute <= 60:
            raise ConfigError("[messages] max_per_minute must be a whole number from 1 to 60")
        if not 0 < self.away_after_min <= 24 * 60:
            raise ConfigError("[messages] away_after_min must be more than 0")
        if not 10 <= self.question_timeout_s <= 3600:
            raise ConfigError("[messages] question_timeout_s must be from 10 to 3600")
        if not 0 < self.max_file_mb <= 50:
            raise ConfigError("[messages] max_file_mb must be more than 0 and at most 50")
        try:
            brief_time(str(self.brief_at))
        except ValueError:
            raise ConfigError('[messages] brief_at must be a time like "07:30", or "" for no brief') from None


def brief_time(text: str) -> time | None:
    """"07:30" as a time, "" as None. Raises ValueError for anything else."""
    if not text:
        return None
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", text.strip())
    if match is None:
        raise ValueError(text)
    return time(int(match[1]), int(match[2]))


@dataclass(frozen=True)
class LoggingSettings:
    content: bool = False
    """Put what was said, replies, facts and reminder texts in brain.log. For debugging only."""
    max_mb: float = 2.0
    keep: int = 3
    """Old logs kept besides brain.log, each up to max_mb."""


MEETING_AUTO = ("ask", "calendar", "off")


@dataclass(frozen=True)
class MeetingSettings:
    """[meetings]. The diarizer's own options go in a table named after it, like [meetings.sherpa_onnx]."""

    auto: str = "ask"
    """When Milo notices a call: "ask" (he asks once whether to take notes), "calendar" (he takes notes without
    asking when your calendar has a meeting now, and asks otherwise) or "off" (he never asks; "Take meeting notes"
    in the menu bar still works)."""
    keep_audio: bool = False
    """Keep the recording after the notes are written. Off: it's deleted."""
    diarizer: str = "sherpa_onnx"
    """What tells the other people apart. "" labels everyone on the call as "Others"."""
    offer_reminders: bool = True
    """After the call, offer to put your to-dos into Reminders."""
    offer_mail: bool = True
    """After the call, offer a follow-up mail draft to the others."""
    end_after_s: float = 30.0
    """Notes stop this long after the call ends, so a dropped connection doesn't split a meeting in two."""

    def __post_init__(self):
        if self.auto not in MEETING_AUTO:
            raise ConfigError(f"[meetings] auto must be one of {', '.join(MEETING_AUTO)}")
        if self.end_after_s < 0:
            raise ConfigError("[meetings] end_after_s must be 0 or more")


@dataclass(frozen=True)
class SttSettings:
    talk: str = ""
    """A cloud service that listens along while you talk to Milo ("elevenlabs"), so his answer starts sooner.
    Empty: everything is transcribed on this Mac."""
    cloud_dictation: bool = False
    """Dictation goes to that service too. Off: dictation never leaves this Mac."""


@dataclass(frozen=True)
class AudioSettings:
    pass


@dataclass(frozen=True)
class MemorySettings:
    enabled: bool = True
    """Remember conversations, tasks and facts, and recall what matters with each turn."""
    recall_tokens: int = 800
    """How much memory goes along with each turn, at most (about 4 characters a token)."""
    embedder: str = "mlx_e5"
    """What turns text into numbers for search: "mlx_e5" (a small model, 140 MB) or "hash" (no model, words only)."""
    dictations: bool = False
    """Also remember what you dictate into other apps."""
    consolidate: bool = True
    """Once a night, while the Mac is idle and plugged in, summarize the day and update what Milo knows."""
    consolidate_calls_per_day: int = 2
    """Hard cap on worker calls for that. 0 turns it off."""

    def __post_init__(self):
        if not 0 <= self.recall_tokens <= 4000:
            raise ConfigError("[memory] recall_tokens must be between 0 and 4000")
        if self.consolidate_calls_per_day < 0:
            raise ConfigError("[memory] consolidate_calls_per_day can't be negative")


_PLUGGABLE_SETTINGS: dict[str, type] = {
    "chat": ChatSettings, "harness": HarnessSettings, "stt": SttSettings, "tts": TtsSettings,
    "audio": AudioSettings, "dictation": DictationSettings, "connections": ConnectionSettings,
    "messages": MessagesSettings,
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
        self.stt: SttSettings = settings["stt"]
        self.dictation: DictationSettings = settings["dictation"]
        self.connections: ConnectionSettings = settings["connections"]
        self.messages: MessagesSettings = settings["messages"]
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
        self.memory: MemorySettings = _pluggable_settings(MemorySettings, raw.get("memory", {}), "memory")
        self.routines = _typed(options_from(RoutineSettings, raw.get("routines", {}), "routines"), "routines")
        self.meetings: MeetingSettings = _pluggable_settings(MeetingSettings, raw.get("meetings", {}), "meetings")
        if self.meetings.diarizer and not isinstance(raw.get("meetings", {}).get(self.meetings.diarizer, {}), dict):
            raise ConfigError(f"[meetings.{self.meetings.diarizer}] must be a table")

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

    def embedder(self) -> tuple[str, dict[str, Any]]:
        """[memory] embedder and its `[memory.<name>]` table."""
        name = self.memory.embedder
        options = self.section("memory").get(name, {})
        if not isinstance(options, dict):
            raise ConfigError(f"[memory.{name}] must be a table")
        return name, options


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
