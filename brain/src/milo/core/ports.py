"""Interfaces between the brain's parts. Services depend on these, never on concrete adapters.

Every port has a fake in tests/fakes.py. Concrete implementations register themselves in
milo.core.registry and are picked by name from config.toml in milo.compose.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from .events import Event
from .types import Audio, Nudge, Reminder, Reply, Signals, Step, Usage

LevelCallback = Callable[[float], None]
"""Receives loudness in 0..1. May be called from an audio thread."""

StepCallback = Callable[[Step], None]
"""Receives each step of a harness turn as it starts and again when it ends. Called on the event loop."""


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...


@runtime_checkable
class Harness(Protocol):
    """An LLM agent harness (Codex CLI, Claude Code, ...). One call answers one user turn."""

    name: str

    async def reply(self, prompt: str, session_id: str | None, *, on_step: StepCallback | None = None) -> Reply:
        """Answer `prompt`, continuing `session_id` if given. Raises HarnessError.

        `on_step` hears about the commands, file edits and tool calls while the agent works.
        """
        ...


@runtime_checkable
class Transcriber(Protocol):
    def warm(self) -> None:
        """Load models so the first call is fast. Blocking; called on a worker thread."""
        ...

    def transcribe(self, audio: Audio) -> str:
        """16 kHz mono audio to text. Returns "" for silence or noise. Blocking."""
        ...


@runtime_checkable
class Voice(Protocol):
    sample_rate: int

    def warm(self) -> None: ...

    def synthesize(self, text: str) -> Audio:
        """Text to mono audio at `sample_rate`. Blocking; called on a worker thread."""
        ...

    def cancel(self) -> None:
        """Abort every synthesis already started, so barge-in frees the TTS thread at once.

        Safe from any thread. An aborted synthesize() raises; one started afterwards is unaffected.
        Engines that can't abort may do nothing.
        """
        ...


@runtime_checkable
class AudioInput(Protocol):
    @property
    def active(self) -> bool: ...

    def start(self, on_level: LevelCallback) -> None:
        """Open the mic and start buffering at 16 kHz. Raises on mic failure."""
        ...

    def stop(self) -> Audio:
        """Close the mic and return everything recorded since start()."""
        ...

    def peek(self, start: int = 0) -> Audio:
        """A copy of the samples recorded so far from index `start` on, while recording goes on. Empty when idle."""
        ...


@runtime_checkable
class AudioOutput(Protocol):
    """One continuous output stream per utterance, so chunks play back to back without gaps or clicks."""

    def begin(self, sample_rate: int, on_level: LevelCallback) -> None:
        """Open the stream; it plays silence until audio is fed. Interrupts a stream that is still open."""
        ...

    def feed(self, audio: Audio) -> None:
        """Queue audio after everything already queued. Safe to call from any thread."""
        ...

    async def drain(self) -> bool:
        """Wait until all fed audio has played, then close. Returns False if interrupt() cut it short."""
        ...

    def interrupt(self) -> None:
        """Stop now and drop queued audio. A pending drain() returns False."""
        ...


@runtime_checkable
class LiveModel(Protocol):
    """A fast conversational model that streams its reply and keeps the conversation in memory."""

    name: str
    last_usage: Usage

    async def start(self, system_prompt: str) -> None:
        """Begin a fresh conversation with this system prompt, replacing any running one."""
        ...

    def turn(self, text: str) -> AsyncIterator[str]:
        """Send one user message and yield the reply's text deltas as they arrive. Raises HarnessError.

        Starts a conversation with an empty system prompt if start() was never called.
        """
        ...

    async def interrupt(self) -> None:
        """Stop the reply in progress. The running turn() iterator ends early; the conversation survives."""
        ...

    async def close(self) -> None: ...


@runtime_checkable
class Confirmer(Protocol):
    """Asks the user before an action. Any tool or service that is about to do something it can't undo uses it."""

    async def confirm(self, summary: str) -> bool:
        """Ask `summary`, a plain yes-or-no question naming the thing and the consequence.

        True only for a yes. No, no answer before the timeout, or an error mean False.
        """
        ...


@runtime_checkable
class ProfileMemory(Protocol):
    """Durable facts about the user, kept as Markdown the user can read and edit."""

    def read(self) -> str:
        """The whole profile, for the live model's system prompt."""
        ...

    def remember(self, fact: str) -> None:
        """Append one fact (a single line). Ignores exact duplicates."""
        ...


@runtime_checkable
class TextCleaner(Protocol):
    def clean(self, text: str) -> str:
        """Turn a raw transcript into text ready to paste."""
        ...


@runtime_checkable
class EventSink(Protocol):
    """Where the brain sends UI events. Must be safe to call from the event loop thread only."""

    def emit(self, event: Event) -> None: ...


@runtime_checkable
class ReminderSource(Protocol):
    def all(self) -> list[Reminder]: ...


@runtime_checkable
class ReminderBook(ReminderSource, Protocol):
    def add(self, due: datetime, text: str) -> Reminder:
        """Append `- [ ] YYYY-MM-DD HH:MM text` to reminders.md and return the parsed reminder."""
        ...


@runtime_checkable
class UsageLedger(Protocol):
    def record(self, source: str, harness: str, usage: Usage) -> None: ...


@runtime_checkable
class TranscriptStore(Protocol):
    """The conversation as the Milo window shows it, kept across restarts. Entries are JSON objects."""

    def append(self, entry: dict) -> None: ...

    def tail(self, n: int) -> list[dict]:
        """The last `n` entries, oldest first. Reads only the end of the file."""
        ...


@runtime_checkable
class DictationHistory(Protocol):
    def append(self, text: str, app: str | None) -> None: ...


@runtime_checkable
class LlmBudget(Protocol):
    """Daily cap on harness calls the heartbeat may make."""

    def allow(self, today: date) -> bool: ...
    def spend(self, today: date) -> None: ...


@runtime_checkable
class ProactiveRule(Protocol):
    """One heartbeat rule. Reads signals and its own state; returns zero or more nudges. No I/O, no LLM.

    `state` is JSON-serializable. The engine restores it from heartbeat.json after creating the
    rule and saves it after each tick, so rules survive restarts without doing file I/O.
    """

    name: str
    state: dict
    # True for things the user asked for (reminders): checked even while the user is away or in a
    # quiet app, where they are shown silently. False rules only run while the user is active.
    user_requested: bool

    def check(self, signals: Signals, reminders: list[Reminder]) -> list[Nudge]: ...


@runtime_checkable
class ProactiveEngine(Protocol):
    """Runs the rules on each tick. Owns rate limits and persists its own state."""

    tick_s: float
    budget: LlmBudget

    def tick(self, signals: Signals) -> list[Nudge]: ...


# ---- app connections: what the worker reaches through Milo's MCP server (milo.connect)
#
# Every method blocks and raises ToolError with a plain-language message. Dates are naive local time.
# Results are JSON-ready dicts for the agent.


@runtime_checkable
class Calendar(Protocol):
    def events(self, start: datetime, end: datetime, query: str = "") -> list[dict]:
        """Events overlapping [start, end), optionally only those whose title, place or notes contain `query`."""
        ...

    def add_event(self, title: str, start: datetime, end: datetime, location: str = "", notes: str = "",
                  calendar: str = "") -> dict: ...


@runtime_checkable
class Reminders(Protocol):
    def list(self, query: str = "", include_done: bool = False) -> list[dict]: ...

    def add(self, title: str, due: datetime | None = None, notes: str = "", list_name: str = "") -> dict: ...

    def complete(self, id: str) -> dict: ...


@runtime_checkable
class Mail(Protocol):
    """Mail.app. There is deliberately no send: Milo writes drafts, the user sends them."""

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Newest first: id, from, subject, date, mailbox."""
        ...

    def read(self, id: str) -> dict: ...

    def draft(self, to: list[str], subject: str, body: str, reply_to: str = "") -> dict:
        """Save a draft and open it in Mail for the user to check. `reply_to` is a message id."""
        ...


@runtime_checkable
class Notes(Protocol):
    def search(self, query: str, limit: int = 20) -> list[dict]: ...

    def read(self, id: str) -> dict: ...

    def create(self, title: str, body: str, folder: str = "") -> dict: ...

    def append(self, id: str, text: str) -> dict: ...


@runtime_checkable
class Shortcuts(Protocol):
    def list(self) -> list[str]: ...

    def run(self, name: str, input_text: str = "") -> str:
        """Run the user's shortcut and return its text output."""
        ...


@runtime_checkable
class Files(Protocol):
    """The user's files inside one folder (home by default). ~/Library and hidden folders are out of reach."""

    def find(self, name: str, limit: int = 20) -> list[dict]:
        """Files whose name contains `name`, newest first: path, name, modified, size."""
        ...

    def search(self, text: str, limit: int = 20) -> list[dict]:
        """Files whose contents contain `text`."""
        ...

    def read(self, path: str, max_chars: int = 20000) -> dict:
        """The text of a file (txt, md, csv, pdf, docx, rtf, xlsx, ...): path, text, truncated."""
        ...


@dataclass(frozen=True)
class Connections:
    """One implementation of each connection. None: switched off in config.toml or not available."""

    calendar: Calendar | None = None
    reminders: Reminders | None = None
    mail: Mail | None = None
    notes: Notes | None = None
    shortcuts: Shortcuts | None = None
    files: Files | None = None
