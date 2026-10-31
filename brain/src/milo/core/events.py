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
    "ctrl+option+m" for the "What's this?" shortcut, meeting_key the one that starts or stops meeting notes;
    "" turns either off. character is "milo"; an old config may
    name a retired look, and the app shows Milo either way.
    """

    type: ClassVar[str] = "ui_config"
    dictate_key: str
    talk_key: str
    hands_free_max_s: float = 300.0
    whats_this_key: str = ""
    character: str = "milo"
    meeting_key: str = ""


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
    """Milo asks a yes-or-no question before an action. Shown with Yes and No until `confirm_done` for this id.
    `always`: the question is about working in an app, so it also offers Allow always (ADR 0022). `money`: it buys
    or pays, so it shows as a money question and only a click on Yes answers it (ADR 0023)."""

    type: ClassVar[str] = "confirm"
    id: str
    question: str
    always: bool = False
    money: bool = False


@dataclass(frozen=True)
class ConfirmDone(Event):
    """The question `id` is over. answer: "yes", "always" (Allow always), "no" or "timeout" (which counts as no)."""

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
class Helpers(Event):
    """The helpers working for Milo, oldest first: each {id, title, status, step, progress?}.

    status is queued, working, needs_you, done, failed or stopped; `step` says what it does now in plain
    words; `progress` (0..1) is there only while the worker keeps a to-do list. `id` is the transcript entry
    of its task. Sent whenever one changes; a finished helper stays in the list for a few seconds.
    """

    type: ClassVar[str] = "helpers"
    helpers: list[dict]


@dataclass(frozen=True)
class HandsBorrow(Event):
    """The user lent Milo the real mouse and keyboard for actions that can't be done in the background.

    The app shows the frame around the screen and stops on any touch while it holds them, and hands them back on
    its own a while after the last such action or when the session ends.
    """

    type: ClassVar[str] = "hands_borrow"
    on: bool
    what: str = ""


@dataclass(frozen=True)
class Facts(Event):
    """What Milo knows, for the "What Milo knows" screen: every current fact as {id, text, topic, since, pinned}.

    Sent on `get_facts` and whenever a fact is added, edited or forgotten.
    """

    type: ClassVar[str] = "facts"
    facts: list[dict]


@dataclass(frozen=True)
class Routines(Event):
    """The user's routines for the Milo window, by name, and the recipe drafts waiting for a look.

    Each routine: {id, name, description, schedule, paused, last_run, next_run?, inputs, problem?}. `id` is the
    file name without .md; `next_run` is a local time like "2026-11-02T09:00" while a schedule is on; a file
    that doesn't read has only id, name and `problem`. Each draft: {id, name, recipe, schedule}, where `recipe`
    is the whole file the user can save or ask to change. Sent on connect, on get_history and on every change.
    """

    type: ClassVar[str] = "routines"
    routines: list[dict]
    drafts: list[dict]


@dataclass(frozen=True)
class SettingsReport(Event):
    """What the Settings window shows. Sent on `get_settings` and after every `set_setting`.

    Each setting is {section, key, value, options, labels, live}: `options` lists the allowed values (empty
    for free text or a switch) and `labels` names them in plain words. `live` false: a change applies after
    a restart. `restart`: a saved change is waiting for one. `error`: why the last change was not saved.
    """

    type: ClassVar[str] = "settings"
    settings: list[dict]
    restart: bool = False
    error: str = ""


@dataclass(frozen=True)
class UsageReport(Event):
    """What the Usage page shows, after `get_usage`. `span` days ending `today` (both YYYY-MM-DD); `since` is the
    first day anything was recorded, or "" before that.

    `daily`: every day of the span, oldest first, each {day, calls, input_tokens, cached_input_tokens,
    output_tokens, dictations, words}; input_tokens includes the cached ones. `sources`: tokens per kind of work
    over the span, {source, calls, tokens}, most first ("chat", "task", "memory", "proactive"). `apps`: where
    dictations went, {app, dictations, words}, most words first, at most 6. `accounts`: {service, uses, state,
    plan, who, detail}, see milo.core.usage.Account. No dictated text is sent."""

    type: ClassVar[str] = "usage"
    span: int
    today: str
    since: str
    daily: list[dict]
    sources: list[dict]
    apps: list[dict]
    accounts: list[dict]


@dataclass(frozen=True)
class Remote(Event):
    """Milo by message, for the menu. `channel` is the chat app's name ("telegram"), `label` what the user calls
    it. state: "starting", "unpaired" (no phone yet; `detail` says how to connect), "paired" (`detail`: the
    owner's name in the chat app) or "error" (`detail`: what is wrong, in plain words). Sent on connect when
    messages are on, and on every change."""

    type: ClassVar[str] = "remote"
    channel: str
    label: str
    state: str
    paused: bool = False
    detail: str = ""


@dataclass(frozen=True)
class MeetingRecord(Event):
    """Record the meeting `id`: the microphone and the call's audio, each in 30 s WAV chunks (16 kHz mono) into
    `dir`, named `me-0001.wav` and `them-0001.wav`. on=false stops it. A red dot shows while the app records."""

    type: ClassVar[str] = "meeting_record"
    id: str
    dir: str
    on: bool


@dataclass(frozen=True)
class Conversations(Event):
    """The Milo window's list: conversation headers, the latest first (core.conversations.ConversationInfo),
    `current` the one going on ("" for none) and `more` whether older ones exist. Sent on connect, on
    get_conversations and after changes."""

    type: ClassVar[str] = "conversations"
    conversations: list[dict]
    current: str = ""
    more: bool = False


@dataclass(frozen=True)
class ConversationOpened(Event):
    """One conversation for the window, on open_conversation: its header and its entries, oldest first."""

    type: ClassVar[str] = "conversation"
    id: str
    info: dict
    entries: list[dict]


@dataclass(frozen=True)
class SearchResults(Event):
    """What search_conversations found: each {conversation, title, kind, at, snippet, via}, best first."""

    type: ClassVar[str] = "search_results"
    query: str
    results: list[dict]


@dataclass(frozen=True)
class RemindersList(Event):
    """Open reminders of today and tomorrow for the window's Today view: each {due, text}, soonest first."""

    type: ClassVar[str] = "reminders"
    reminders: list[dict]


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
    conversation: str = ""
    """Typed into this earlier conversation: pick it up again. "" goes on with the current one."""


@dataclass(frozen=True)
class GetHistory(Command):
    """The Milo window opened: send the recent conversation again."""

    type: ClassVar[str] = "get_history"


@dataclass(frozen=True)
class GetConversations(Command):
    """The window wants its list: the latest page, or the page of conversations older than `before`."""

    type: ClassVar[str] = "get_conversations"
    before: str = ""


@dataclass(frozen=True)
class OpenConversation(Command):
    """The user opened conversation `id`: send `conversation`."""

    type: ClassVar[str] = "open_conversation"
    id: str


@dataclass(frozen=True)
class SearchConversations(Command):
    type: ClassVar[str] = "search_conversations"
    query: str


@dataclass(frozen=True)
class RenameConversation(Command):
    type: ClassVar[str] = "rename_conversation"
    id: str
    title: str


@dataclass(frozen=True)
class NewConversation(Command):
    """⌘N: the next turn starts a new conversation, with a fresh chat model."""

    type: ClassVar[str] = "new_conversation"


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
    """The user clicked Yes or No on the question `id`, or Allow always (`always`, with yes) where it was offered."""

    type: ClassVar[str] = "confirm_answer"
    id: str
    yes: bool
    always: bool = False


@dataclass(frozen=True)
class AppResponse(Command):
    """The answer to `app_request` `id`: `result` when ok, else a plain `error`."""

    type: ClassVar[str] = "app_response"
    id: str
    ok: bool
    result: Any = None
    error: str = ""


@dataclass(frozen=True)
class StopHelper(Command):
    """The user clicked Stop on the helper `id` (an id from `helpers`)."""

    type: ClassVar[str] = "stop_helper"
    id: str


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


ROUTINE_ACTIONS = ("run", "pause", "resume", "delete")


@dataclass(frozen=True)
class RoutineAction(Command):
    """A button in the Routines section of the Milo window: run, pause, resume or delete the routine `id`."""

    type: ClassVar[str] = "routine"
    id: str
    action: str


@dataclass(frozen=True)
class RoutineDraftAnswer(Command):
    """Save on a recipe draft (`save` true), or throw it away (false)."""

    type: ClassVar[str] = "routine_draft_answer"
    id: str
    save: bool


@dataclass(frozen=True)
class GetSettings(Command):
    """The Settings window opened: send `settings`."""

    type: ClassVar[str] = "get_settings"


@dataclass(frozen=True)
class GetUsage(Command):
    """The Usage page opened or changed its range: send `usage` for the last `span` days (1 to 366)."""

    type: ClassVar[str] = "get_usage"
    span: int = 30


@dataclass(frozen=True)
class SetSetting(Command):
    """Change one setting in config.toml, e.g. section "ui", key "voice", value false."""

    type: ClassVar[str] = "set_setting"
    section: str
    key: str
    value: Any


@dataclass(frozen=True)
class RemotePause(Command):
    """The menu's "Pause messages from your phone": Milo ignores the phone until it is switched off again."""

    type: ClassVar[str] = "remote_pause"
    on: bool


@dataclass(frozen=True)
class RemoteForget(Command):
    """The menu's "Disconnect phone": unpair it. Connecting again needs a new code shown on the Mac."""

    type: ClassVar[str] = "remote_forget"


@dataclass(frozen=True)
class CallStarted(Command):
    """The app saw a call start: a call app or a browser tab with a call uses the microphone."""

    type: ClassVar[str] = "call_started"
    app: str
    bundle: str = ""
    title: str = ""


@dataclass(frozen=True)
class CallEnded(Command):
    type: ClassVar[str] = "call_ended"
    app: str


@dataclass(frozen=True)
class MeetingChunk(Command):
    """The app finished chunk `index` (from 1) of `track` ("me" or "them") of the meeting `id`.

    `start` is seconds since recording started, `seconds` how much audio the chunk holds.
    """

    type: ClassVar[str] = "meeting_chunk"
    id: str
    track: str
    index: int
    path: str
    start: float
    seconds: float


@dataclass(frozen=True)
class MeetingRecording(Command):
    """What the app's recorder is doing: sent when it starts or stops, and on every connect. `tracks` are the
    tracks it records; `error` says in plain words what it can't record (the call's audio without permission)."""

    type: ClassVar[str] = "meeting_recording"
    id: str
    on: bool
    tracks: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class DictationFixed(Command):
    """The user changed words Milo had pasted: each pair is (heard, meant), a few words each (ADR 21). Only these
    pairs come from the app, never the field's text."""

    type: ClassVar[str] = "dictation_fixed"
    fixes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class MeetingToggle(Command):
    """The user asked from the menu bar to start (on) or stop taking meeting notes."""

    type: ClassVar[str] = "meeting_toggle"
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
                return TextInput(text, bool(raw.get("speak", True)), str(raw.get("conversation") or ""))
            case "get_history":
                return GetHistory()
            case "get_conversations":
                return GetConversations(str(raw.get("before") or ""))
            case "open_conversation":
                return OpenConversation(_required(raw, "id"))
            case "search_conversations":
                return SearchConversations(" ".join(str(raw["query"]).split()))
            case "rename_conversation":
                return RenameConversation(_required(raw, "id"), _required(raw, "title"))
            case "new_conversation":
                return NewConversation()
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
                return ConfirmAnswer(str(raw["id"]), raw["yes"], raw.get("always") is True)
            case "app_response":
                return AppResponse(str(raw["id"]), raw["ok"] is True, raw.get("result"), str(raw.get("error") or ""))
            case "remote_pause":
                if not isinstance(raw["on"], bool):
                    raise ProtocolError("on must be true or false")
                return RemotePause(raw["on"])
            case "remote_forget":
                return RemoteForget()
            case "stop_helper":
                id = str(raw["id"]).strip()
                if not id:
                    raise ProtocolError("id must not be empty")
                return StopHelper(id)
            case "get_facts":
                return GetFacts()
            case "forget_fact":
                return ForgetFact(_required(raw, "id"))
            case "edit_fact":
                return EditFact(_required(raw, "id"), _required(raw, "text"))
            case "routine":
                action = str(raw["action"])
                if action not in ROUTINE_ACTIONS:
                    raise ProtocolError(f"action must be one of {', '.join(ROUTINE_ACTIONS)}")
                return RoutineAction(str(raw["id"]), action)
            case "routine_draft_answer":
                if not isinstance(raw["save"], bool):
                    raise ProtocolError("save must be true or false")
                return RoutineDraftAnswer(str(raw["id"]), raw["save"])
            case "get_settings":
                return GetSettings()
            case "get_usage":
                span = raw.get("span", 30)
                if isinstance(span, bool) or not isinstance(span, int) or not 1 <= span <= 366:
                    raise ProtocolError("span must be a whole number of days from 1 to 366")
                return GetUsage(span)
            case "set_setting":
                value = raw["value"]
                if not isinstance(value, str | bool | int | float):
                    raise ProtocolError("value must be text, a number or true/false")
                return SetSetting(str(raw["section"]), str(raw["key"]), value)
            case "call_started":
                return CallStarted(str(raw.get("app") or ""), str(raw.get("bundle") or ""), str(raw.get("title") or ""))
            case "call_ended":
                return CallEnded(str(raw.get("app") or ""))
            case "meeting_chunk":
                if raw["track"] not in ("me", "them"):
                    raise ProtocolError("track must be me or them")
                index = int(raw["index"])
                if index < 1:
                    raise ProtocolError("index starts at 1")
                return MeetingChunk(str(raw["id"]), raw["track"], index, str(raw["path"]),
                                    max(0.0, float(raw["start"])), max(0.0, float(raw["seconds"])))
            case "meeting_recording":
                tracks = raw.get("tracks") or ()
                if not isinstance(tracks, list | tuple):
                    raise ProtocolError("tracks must be a list")
                return MeetingRecording(str(raw.get("id") or ""), raw["on"] is True,
                                        tuple(str(t) for t in tracks if t in ("me", "them")),
                                        str(raw.get("error") or ""))
            case "meeting_toggle":
                return MeetingToggle(raw["on"] is True)
            case "dictation_fixed":
                fixes = raw["fixes"]
                if not isinstance(fixes, list) or not all(isinstance(f, dict) for f in fixes):
                    raise ProtocolError("fixes must be a list of {heard, meant}")
                return DictationFixed(tuple((str(f["heard"]), str(f["meant"])) for f in fixes))
    except (KeyError, TypeError, ValueError) as e:
        raise ProtocolError(f"bad {kind} message: {e}") from None
    raise ProtocolError(f"unknown message type {kind!r}")


def _required(raw: dict, key: str) -> str:
    value = " ".join(str(raw[key]).split())
    if not value:
        raise ProtocolError(f"{key} must not be empty")
    return value
