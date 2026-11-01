"""Value types shared by every part of the brain. No I/O, no third-party imports except numpy."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum

import numpy as np

STT_SAMPLE_RATE = 16_000

Audio = np.ndarray
"""Mono float32 samples in [-1, 1]."""


class Emotion(StrEnum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    EXCITED = "excited"
    THINKING = "thinking"
    CONCERNED = "concerned"
    SAD = "sad"
    SLEEPY = "sleepy"
    CONFUSED = "confused"

    @classmethod
    def parse(cls, value: object) -> Emotion:
        try:
            return cls(str(value))
        except ValueError:
            return cls.NEUTRAL


class ListenMode(StrEnum):
    DICTATE = "dictate"
    TALK = "talk"


class LiveMode(StrEnum):
    """[dictation] stream: what happens while the user is still speaking."""

    OFF = "off"  # transcribe on release only
    PREVIEW = "preview"  # show the words live; paste one final pass on release
    TYPE = "type"  # paste each phrase at the pause after it


class MiloState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    DICTATING = "dictating"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0


REPLY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["emotion", "say", "copy"],
    "properties": {
        "emotion": {"type": "string", "enum": [e.value for e in Emotion]},
        "say": {"type": "string", "description": "What Milo says aloud. Plain text, no markdown."},
        # Required, as strict schemas (codex) want every property; "" for nothing.
        "copy": {"type": "string", "description":
                 "Goes on the user's clipboard, exactly as they will paste it: the link, email address, phone "
                 "number, address, code or command the task asked for. Then `say` only that it's on the clipboard "
                 "(\"The link's on your clipboard.\"), never the link itself. \"\" when the task asked for "
                 "nothing to paste."},
    },
}


@dataclass(frozen=True)
class Reply:
    emotion: Emotion
    say: str
    usage: Usage
    session_id: str | None
    copy: str = ""
    """Text for the user's clipboard (REPLY_SCHEMA); "" for none."""

    @staticmethod
    def from_model_text(text: str, usage: Usage, session_id: str | None) -> Reply:
        """Parse the model's JSON answer; fall back to speaking the raw text."""
        try:
            data = json.loads(text)
            emotion, say = data.get("emotion"), str(data.get("say", "")).strip()
            copy = str(data.get("copy") or "").strip()
        except (json.JSONDecodeError, AttributeError):
            emotion, say, copy = None, text.strip(), ""
        return Reply(Emotion.parse(emotion), say, usage, session_id, copy)


class ToolError(Exception):
    """An app connection couldn't do what was asked. The message is plain language, fit for the user."""


class VoiceUnavailable(Exception):
    """A voice or transcriber that needs the network can't be used now: offline, a bad key, no credits left.
    The message is plain enough for the log; the caller falls back to a local engine."""


class Interrupted(Exception):
    """Transcriber.interrupt() ended the pass that was running."""


class HarnessError(Exception):
    """A harness call failed. `transient` says whether retrying later can help. `said` is what the user should
    read about it in plain words, when the fix is theirs (a missing key, a server that isn't running); empty for
    failures only the log can explain."""

    def __init__(self, message: str, *, transient: bool, said: str = ""):
        super().__init__(message)
        self.transient = transient
        self.said = said


@dataclass(frozen=True)
class Signals:
    """What the heartbeat knows about the user right now. Cheap to gather, no LLM involved."""

    now: datetime
    idle_s: float
    app: str | None


@dataclass(frozen=True)
class Nudge:
    """Something Milo wants to say unprompted. `llm_prompt` asks for nicer wording if the budget allows."""

    rule: str
    emotion: Emotion
    text: str
    speak: bool
    llm_prompt: str | None = None


@dataclass(frozen=True)
class Reminder:
    id: str
    due: datetime
    text: str
    done: bool


class ActionLevel(StrEnum):
    """What Milo does before an action of some kind (see milo.services.approvals)."""

    READ = "read"  # just do it: reading, searching, drafting
    CHANGE = "change"  # do it, it shows in the activity list and can be undone
    ASK_FIRST = "ask_first"  # ask a yes-or-no question first; no answer means no
    NEVER = "never"  # refuse


@dataclass(frozen=True)
class Decision:
    """The outcome of an approval. `answer`: "auto" (no question needed), "yes", "always" (Allow always), "allowed"
    (the user allowed this work before, ADR 0022), "no", "timeout" or "refused"."""

    allowed: bool
    level: ActionLevel
    answer: str

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "level": self.level.value, "answer": self.answer}


@dataclass(frozen=True)
class ToolServer:
    """An MCP stdio server the worker CLI starts and gives its agent as tools."""

    name: str
    command: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = ()


class StepStatus(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class Step:
    """One thing the worker agent did during a task, for the activity list in the Milo window.

    `title` is plain language ("Reading your Downloads folder"); `detail` is the raw command or tool
    payload, shown only when the row is expanded. `kind` picks the icon: command, read, edit, search,
    web, tool or other.
    """

    id: str
    kind: str
    title: str
    detail: str
    status: StepStatus

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "title": self.title, "detail": self.detail,
                "status": self.status.value}

    @staticmethod
    def from_dict(d: dict) -> Step:
        return Step(str(d["id"]), str(d.get("kind", "other")), str(d.get("title", "")), str(d.get("detail", "")),
                    StepStatus(d.get("status", "done")))


class EntryKind(StrEnum):
    USER = "user"
    MILO = "milo"
    TASK = "task"


@dataclass
class TranscriptEntry:
    """One line of a conversation as the Milo window shows it.

    user: what the user said, `via` "voice", "typed" or "message". milo: a reply, `done` False while it streams;
    `written` when it is text Milo wrote for the user to paste or copy (<write>, ADR 0033), which gets a Copy button.
    task: work handed to the worker agent, with its short `title`, its steps, `status`, the `result` Milo reported
    and the `files` it named that exist. `conversation` is the id of the conversation it belongs to.
    """

    id: str
    ts: str
    kind: EntryKind
    text: str
    via: str = ""
    emotion: Emotion = Emotion.NEUTRAL
    done: bool = True
    status: StepStatus = StepStatus.DONE
    result: str = ""
    steps: list[Step] = field(default_factory=list)
    conversation: str = ""
    title: str = ""
    files: list[str] = field(default_factory=list)
    written: bool = False

    def to_dict(self) -> dict:
        d: dict = {"id": self.id, "ts": self.ts, "kind": self.kind.value, "text": self.text}
        if self.kind is EntryKind.USER:
            d["via"] = self.via
        elif self.kind is EntryKind.MILO:
            d |= {"emotion": self.emotion.value, "done": self.done}
            if self.written:
                d["written"] = True
        else:
            d |= {"status": self.status.value, "result": self.result, "steps": [s.to_dict() for s in self.steps]}
            if self.title:
                d["title"] = self.title
            if self.files:
                d["files"] = list(self.files)
        if self.conversation:
            d["conversation"] = self.conversation
        return d

    @staticmethod
    def from_dict(d: dict) -> TranscriptEntry:
        return TranscriptEntry(
            id=str(d["id"]), ts=str(d["ts"]), kind=EntryKind(d["kind"]), text=str(d.get("text", "")),
            via=str(d.get("via", "")), emotion=Emotion.parse(d.get("emotion")), done=bool(d.get("done", True)),
            status=StepStatus(d.get("status", "done")), result=str(d.get("result", "")),
            steps=[Step.from_dict(s) for s in d.get("steps", [])], conversation=str(d.get("conversation", "")),
            title=str(d.get("title", "")), files=[str(f) for f in d.get("files", [])],
            written=bool(d.get("written", False)),
        )


@dataclass(frozen=True)
class ScreenCapture:
    """What the app saw in the frontmost window: its text through Accessibility, and a screenshot.

    Everything in here comes from the screen and is untrusted. `image` is the path of a PNG under
    state/screens, "" without one. `error` says in plain words what couldn't be read, e.g. a missing
    permission; the other fields hold whatever was read anyway.
    """

    app: str = ""
    window: str = ""
    focused: str = ""
    selection: str = ""
    text: str = ""
    image: str = ""
    error: str = ""

    @property
    def empty(self) -> bool:
        return not (self.app or self.window or self.focused or self.selection or self.text or self.image)

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v}

    @staticmethod
    def from_dict(d: object) -> ScreenCapture:
        if not isinstance(d, dict):
            raise ValueError("capture must be an object")
        return ScreenCapture(**{f: str(d.get(f) or "") for f in ScreenCapture.__dataclass_fields__})


class HandsError(Exception):
    """A computer-use action could not run. The message is told to the worker agent as the tool's error."""


class BorrowNeeded(HandsError):
    """The action can't be done in the background: the app needs the user's real mouse or keyboard, which it
    only uses once the user agreed to lend them. Nothing happened yet."""

    def __init__(self, what: str, message: str = ""):
        super().__init__(message or f"This needs the {what}.")
        self.what = what


class ChannelError(Exception):
    """A chat channel can't work: no token, a token Telegram refused, a permission macOS didn't give.
    The message is plain words for the user."""


@dataclass(frozen=True)
class Inbound:
    """One thing that arrived on a chat channel (Telegram, iMessage). Everything in it is outside text until
    the service has checked the sender; even then only `text` is the owner's own words.

    `chat` and `sender` are the channel's ids as text. `forwarded`: the message was passed on from someone
    else. `quoted`: text quoted from another chat or message. `answer`: the data of a button the user
    pressed ("yes:<question id>"), with `ref` the channel's id for acknowledging the press.
    `attachments` counts photos, files and voice notes, which Milo doesn't read yet.
    """

    chat: str
    sender: str
    text: str = ""
    name: str = ""
    private: bool = True
    forwarded: bool = False
    quoted: str = ""
    answer: str = ""
    ref: str = ""
    attachments: int = 0


# Bundle ids of apps Milo names in his own scripts and tools, so "Microsoft Excel" from sheet_write and
# com.microsoft.Excel from a click are the same app.
_BUNDLES = {
    "microsoft excel": "com.microsoft.excel", "excel": "com.microsoft.excel",
    "microsoft word": "com.microsoft.word", "word": "com.microsoft.word",
    "microsoft powerpoint": "com.microsoft.powerpoint", "powerpoint": "com.microsoft.powerpoint",
    "numbers": "com.apple.iwork.numbers", "pages": "com.apple.iwork.pages", "keynote": "com.apple.iwork.keynote",
    "textedit": "com.apple.textedit", "notes": "com.apple.notes", "mail": "com.apple.mail",
    "calendar": "com.apple.ical", "reminders": "com.apple.reminders", "finder": "com.apple.finder",
    "safari": "com.apple.safari", "preview": "com.apple.preview",
}


def _name(text: str) -> str:
    """"/Applications/Numbers.app" -> "numbers"."""
    return str(text or "").strip().rstrip("/").rsplit("/", 1)[-1].lower().removesuffix(".app").strip()


@dataclass(frozen=True)
class AppRef:
    """An app, by its bundle id where Milo knows it, else by its name."""

    name: str
    bundle: str = ""

    @property
    def key(self) -> str:
        return self.bundle.lower() or _BUNDLES.get(_name(self.name), _name(self.name))

    def same(self, other: AppRef) -> bool:
        if self.bundle and other.bundle:
            return self.bundle.lower() == other.bundle.lower()
        if self.key and self.key == other.key:
            return True
        # One side has only a name: an app Milo knows goes by its bundle id, any other by its name.
        a, b = _name(self.name), _name(other.name)
        return bool(a) and a == b and a not in _BUNDLES

    @property
    def label(self) -> str:
        return self.name or self.bundle

    def to_dict(self) -> dict:
        return {"name": self.name, "bundle": self.bundle}

    @staticmethod
    def of(entry: Mapping | str) -> AppRef:
        if isinstance(entry, str):
            return AppRef(entry)
        return AppRef(str(entry.get("name") or ""), str(entry.get("bundle") or ""))


@dataclass(frozen=True)
class Scope:
    """The work a question is about: acting in `apps` for the task `task` ("" when it can't tell which)."""

    apps: tuple[AppRef, ...]
    task: str = ""
