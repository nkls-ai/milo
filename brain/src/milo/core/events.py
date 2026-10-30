"""The wire protocol between the macOS app and the brain: JSON objects, one per line.

protocol/messages.json at the repo root holds an example of every message. Both the Python
and the Swift test suites decode it, so a change here must change that file too.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, ClassVar

from .types import Emotion, ListenMode, MiloState


class ProtocolError(ValueError):
    """An inbound message was malformed. The connection stays open; the message is dropped."""


# ---- brain -> app


@dataclass(frozen=True)
class Event:
    type: ClassVar[str]

    def to_wire(self) -> dict[str, Any]:
        body = {k: (v.value if hasattr(v, "value") else v) for k, v in asdict(self).items()}
        return {"type": self.type, **body}


@dataclass(frozen=True)
class StateChanged(Event):
    type: ClassVar[str] = "state"
    state: MiloState


@dataclass(frozen=True)
class EmotionChanged(Event):
    type: ClassVar[str] = "emotion"
    emotion: Emotion


@dataclass(frozen=True)
class Bubble(Event):
    """Replace the speech bubble text. Grows sentence by sentence while Milo speaks."""

    type: ClassVar[str] = "bubble"
    text: str


@dataclass(frozen=True)
class Heard(Event):
    """What the user said, shown small above Milo's answer."""

    type: ClassVar[str] = "heard"
    text: str


@dataclass(frozen=True)
class Level(Event):
    """Mic loudness while listening, voice loudness while speaking. 0..1, about 20 per second."""

    type: ClassVar[str] = "level"
    value: float


@dataclass(frozen=True)
class Dictation(Event):
    """Final dictated text. The app inserts it into the focused app."""

    type: ClassVar[str] = "dictation"
    text: str


@dataclass(frozen=True)
class Status(Event):
    """A short notice for the user, e.g. a mic error. Shown in the bubble."""

    type: ClassVar[str] = "status"
    text: str


@dataclass(frozen=True)
class Partial(Event):
    """The words heard so far in the recording in progress, shown live next to Milo. Empty clears it."""

    type: ClassVar[str] = "partial"
    text: str


@dataclass(frozen=True)
class UiConfig(Event):
    """Sent once per connection. Key names: "fn", "right_option", "right_command", "right_control".

    hands_free_max_s caps a recording locked on by a double tap. character is "pip" or "classic".
    """

    type: ClassVar[str] = "ui_config"
    dictate_key: str
    talk_key: str
    hands_free_max_s: float = 300.0
    character: str = "pip"


@dataclass(frozen=True)
class History(Event):
    """The recent conversation for the Milo window, oldest first. Sent on connect and on `get_history`."""

    type: ClassVar[str] = "history"
    entries: list[dict]


@dataclass(frozen=True)
class EntryChanged(Event):
    """A transcript entry was added or changed. The app replaces the entry with the same id."""

    type: ClassVar[str] = "entry"
    entry: dict


@dataclass(frozen=True)
class ReplyDelta(Event):
    """More text of the Milo reply `id` while it streams."""

    type: ClassVar[str] = "reply_delta"
    id: str
    text: str


@dataclass(frozen=True)
class Activity(Event):
    """A step of the running task `task_id` started or ended. The app replaces the step with the same id."""

    type: ClassVar[str] = "activity"
    task_id: str
    step: dict


# ---- app -> brain


@dataclass(frozen=True)
class Command:
    type: ClassVar[str]


@dataclass(frozen=True)
class ListenStart(Command):
    """`tentative`: record, but show nothing until listen_confirm or listen_stop. The key press may be a tap."""

    type: ClassVar[str] = "listen_start"
    mode: ListenMode
    tentative: bool = False


@dataclass(frozen=True)
class ListenConfirm(Command):
    """A tentative recording is real (held long enough, or locked on by a double tap): show it."""

    type: ClassVar[str] = "listen_confirm"


@dataclass(frozen=True)
class ListenStop(Command):
    type: ClassVar[str] = "listen_stop"


@dataclass(frozen=True)
class ListenCancel(Command):
    type: ClassVar[str] = "listen_cancel"


@dataclass(frozen=True)
class TextInput(Command):
    """Typed chat, same path as a spoken turn after transcription."""

    type: ClassVar[str] = "text"
    text: str
    speak: bool = True
    """False: answer in the bubble and the window only, without audio."""


@dataclass(frozen=True)
class GetHistory(Command):
    """The Milo window opened: send the recent conversation again."""

    type: ClassVar[str] = "get_history"


@dataclass(frozen=True)
class ContextUpdate(Command):
    """Sent every 15 s and on app switch. idle_s is seconds since the last keyboard or mouse input."""

    type: ClassVar[str] = "context"
    app: str | None
    idle_s: float


@dataclass(frozen=True)
class Mute(Command):
    """Mute or unmute proactive nudges. Reminders still show, silently."""

    type: ClassVar[str] = "mute"
    on: bool


def parse_command(raw: object) -> Command:
    if not isinstance(raw, dict):
        raise ProtocolError("message must be a JSON object")
    kind = raw.get("type")
    try:
        match kind:
            case "listen_start":
                return ListenStart(ListenMode(raw.get("mode", "talk")), bool(raw.get("tentative", False)))
            case "listen_confirm":
                return ListenConfirm()
            case "listen_stop":
                return ListenStop()
            case "listen_cancel":
                return ListenCancel()
            case "text":
                text = str(raw["text"]).strip()
                if not text:
                    raise ProtocolError("text must not be empty")
                return TextInput(text, bool(raw.get("speak", True)))
            case "get_history":
                return GetHistory()
            case "context":
                app = raw.get("app") or None
                return ContextUpdate(str(app) if app else None, max(0.0, float(raw.get("idle_s", 0))))
            case "mute":
                return Mute(bool(raw["on"]))
    except (KeyError, TypeError, ValueError) as e:
        raise ProtocolError(f"bad {kind} message: {e}") from None
    raise ProtocolError(f"unknown message type {kind!r}")
