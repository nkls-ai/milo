"""The wire protocol between the macOS app and the brain: JSON objects, one per line.

protocol/messages.json at the repo root holds an example of every message. Both the Python
and the Swift test suites decode it, so a change here must change that file too.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, ClassVar

from .types import Emotion, ListenMode, MiloState, ScreenCapture


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

    hands_free_max_s caps a recording locked on by a double tap. whats_this_key is a combo such as
    "ctrl+option+m" for the "What's this?" shortcut; "" turns it off. character is "pip" or "classic".
    """

    type: ClassVar[str] = "ui_config"
    dictate_key: str
    talk_key: str
    hands_free_max_s: float = 300.0
    whats_this_key: str = ""
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


@dataclass(frozen=True)
class LookRequest(Event):
    """Capture the frontmost window and answer with look_result. mode "window": its text and a screenshot;
    "selection": the selected text, or the window if nothing is selected."""

    type: ClassVar[str] = "look_request"
    id: str
    mode: str = "window"


@dataclass(frozen=True)
class Looking(Event):
    """Milo is looking at the screen (an eye shows on him) until `on` is false."""

    type: ClassVar[str] = "looking"
    on: bool


@dataclass(frozen=True)
class HandsRequest(Event):
    """Run one computer-use action in the app (it holds the permissions) and answer with hands_result.

    `tool` is a milo-mac tool name, or "describe", which only reports what an action would touch.
    """

    type: ClassVar[str] = "hands_request"
    id: str
    tool: str
    args: dict


@dataclass(frozen=True)
class HandsSession(Event):
    """The worker is acting on screen: show the "Milo is working" frame and stop on real user input."""

    type: ClassVar[str] = "hands_session"
    on: bool


@dataclass(frozen=True)
class FlyTo(Event):
    """Where Milo is about to act, in global screen points with the origin top-left. None: back home."""

    type: ClassVar[str] = "fly_to"
    point: dict | None


@dataclass(frozen=True)
class Confirm(Event):
    """Milo asks a yes-or-no question before an action. Shown with Yes and No until `confirm_done` for this id."""

    type: ClassVar[str] = "confirm"
    id: str
    question: str


@dataclass(frozen=True)
class ConfirmDone(Event):
    """The question `id` is over. answer: "yes", "no" or "timeout" (which counts as no)."""

    type: ClassVar[str] = "confirm_done"
    id: str
    answer: str


@dataclass(frozen=True)
class AppRequest(Event):
    """Work only the app has permission for, such as Calendar and Reminders through EventKit.

    The app answers with `app_response` and the same id. Ops are listed in docs/ARCHITECTURE.md.
    """

    type: ClassVar[str] = "app_request"
    id: str
    op: str
    args: dict


@dataclass(frozen=True)
class Facts(Event):
    """What Milo knows, for the "What Milo knows" screen: every current fact as {id, text, topic, since, pinned}.

    Sent on `get_facts` and whenever a fact is added, edited or forgotten.
    """

    type: ClassVar[str] = "facts"
    facts: list[dict]


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


@dataclass(frozen=True)
class LookResult(Command):
    """What the app captured for look_request `id`."""

    type: ClassVar[str] = "look_result"
    id: str
    capture: ScreenCapture


@dataclass(frozen=True)
class WhatsThis(Command):
    """The "What's this?" shortcut: the selection, or the window if nothing was selected."""

    type: ClassVar[str] = "whats_this"
    capture: ScreenCapture


@dataclass(frozen=True)
class HandsResult(Command):
    """The outcome of hands_request `id`. `error` is plain words for the worker when ok is false."""

    type: ClassVar[str] = "hands_result"
    id: str
    ok: bool
    result: dict
    error: str = ""


@dataclass(frozen=True)
class HandsStop(Command):
    """The user took over the mouse or keyboard, or pressed esc, while the worker acted on screen."""

    type: ClassVar[str] = "hands_stop"
    reason: str


@dataclass(frozen=True)
class ConfirmAnswer(Command):
    """The user clicked Yes or No on the question `id`."""

    type: ClassVar[str] = "confirm_answer"
    id: str
    yes: bool


@dataclass(frozen=True)
class AppResponse(Command):
    """The answer to `app_request` `id`: `result` when ok, else a plain `error`."""

    type: ClassVar[str] = "app_response"
    id: str
    ok: bool
    result: Any = None
    error: str = ""


@dataclass(frozen=True)
class GetFacts(Command):
    """The "What Milo knows" screen opened: send `facts`."""

    type: ClassVar[str] = "get_facts"


@dataclass(frozen=True)
class ForgetFact(Command):
    """The user pressed Forget on fact `id`."""

    type: ClassVar[str] = "forget_fact"
    id: str


@dataclass(frozen=True)
class EditFact(Command):
    """The user rewrote fact `id` as `text`."""

    type: ClassVar[str] = "edit_fact"
    id: str
    text: str


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
            case "look_result":
                return LookResult(str(raw["id"]), ScreenCapture.from_dict(raw.get("capture") or {}))
            case "whats_this":
                return WhatsThis(ScreenCapture.from_dict(raw["capture"]))
            case "hands_result":
                result = raw.get("result")
                result = {} if result is None else result
                if not isinstance(result, dict):
                    raise ProtocolError("hands_result result must be an object")
                return HandsResult(str(raw["id"]), bool(raw["ok"]), result, str(raw.get("error") or ""))
            case "hands_stop":
                return HandsStop(str(raw.get("reason") or "user"))
            case "confirm_answer":
                if not isinstance(raw["yes"], bool):
                    raise ProtocolError("yes must be true or false")
                return ConfirmAnswer(str(raw["id"]), raw["yes"])
            case "app_response":
                return AppResponse(str(raw["id"]), raw["ok"] is True, raw.get("result"), str(raw.get("error") or ""))
            case "get_facts":
                return GetFacts()
            case "forget_fact":
                return ForgetFact(_required(raw, "id"))
            case "edit_fact":
                return EditFact(_required(raw, "id"), _required(raw, "text"))
    except (KeyError, TypeError, ValueError) as e:
        raise ProtocolError(f"bad {kind} message: {e}") from None
    raise ProtocolError(f"unknown message type {kind!r}")


def _required(raw: dict, key: str) -> str:
    value = " ".join(str(raw[key]).split())
    if not value:
        raise ProtocolError(f"{key} must not be empty")
    return value
