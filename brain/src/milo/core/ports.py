"""Interfaces between the brain's parts. Services depend on these, never on concrete adapters.

Every port has a fake in tests/fakes.py. Concrete implementations register themselves in
milo.core.registry and are picked by name from config.toml in milo.compose.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from .events import Event
from .meetings import Chunk, MeetingInfo, MeetingNotes, TimedWord, Track, TranscriptLine, Turn
from .memory import ConsolidationReport, Document, Episode, Fact, Hit, IndexItem, Recall, TurnContext
from .routines import Routine
from .types import Audio, Inbound, Nudge, Reminder, Reply, ScreenCapture, Signals, Step, Usage

LevelCallback = Callable[[float], None]
"""Receives loudness in 0..1. May be called from an audio thread."""

StepCallback = Callable[[Step], None]
"""Receives each step of a harness turn as it starts and again when it ends. Called on the event loop."""

SessionCallback = Callable[[str], None]
"""Receives the session id of a harness turn as soon as the CLI names it, long before the reply."""

PlanCallback = Callable[[int, int], None]
"""Receives (done, total) whenever the worker's own to-do list changes."""


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...


@runtime_checkable
class Harness(Protocol):
    """An LLM agent harness (Codex CLI, Claude Code, ...). One call answers one user turn."""

    name: str

    async def reply(self, prompt: str, session_id: str | None, *, on_step: StepCallback | None = None,
                    on_session: SessionCallback | None = None, on_plan: PlanCallback | None = None) -> Reply:
        """Answer `prompt`, continuing `session_id` if given. Raises HarnessError.

        `on_step` hears about the commands, file edits and tool calls while the agent works, `on_session`
        the session id once the CLI has one (so a stopped turn can be resumed), and `on_plan` how far the
        agent is through its to-do list. Cancelling the call ends the CLI.
        """
        ...


@runtime_checkable
class Transcriber(Protocol):
    def warm(self) -> None:
        """Load models so the first call is fast. Blocking; called on a worker thread."""
        ...

    def wake(self) -> None:
        """The user pressed a key to speak. Bring loaded models back into memory, which macOS pages out
        while the brain idles, so the passes that follow aren't slowed by that. Blocking and cheap; runs
        on the STT thread ahead of them. An engine with nothing to page in does nothing."""
        ...

    def transcribe(self, audio: Audio, before: str = "", *, quick: bool = False) -> str:
        """16 kHz mono audio to text. Returns "" for silence or noise. Blocking.

        `before` is what the user said just before this audio in the same recording, when it is one
        phrase of a longer one; the engine may keep that phrase's language. `quick`: someone is waiting,
        so trade a little accuracy for speed. Raises Interrupted if interrupt() ended it."""
        ...

    def preview(self, audio: Audio) -> str:
        """Like transcribe(), but fast and rougher: live words while the user still speaks. Never pasted.
        An engine without a fast mode returns transcribe(audio)."""
        ...

    def interrupt(self) -> None:
        """End the pass running now as soon as possible, with Interrupted. Safe from any thread; does
        nothing if no pass runs or the engine can't stop one."""
        ...


@runtime_checkable
class TranscriptionSession(Protocol):
    """One recording streamed to a transcriber while it is made, so the text is ready right after it ends."""

    def feed(self, audio: Audio) -> None:
        """More 16 kHz mono samples, straight after the last. Doesn't block."""
        ...

    async def finish(self) -> str:
        """The recording is over: the whole text ("" for silence). Raises VoiceUnavailable if the engine can't
        say; then the caller transcribes the recording another way."""
        ...

    def cancel(self) -> None:
        """Drop the recording. Nothing more is sent."""
        ...


@runtime_checkable
class StreamingTranscriber(Protocol):
    """A transcriber that listens along while the user speaks (a cloud service). Used only where config.toml
    allows audio to leave the Mac."""

    def session(self, on_partial: Callable[[str], None] | None = None) -> TranscriptionSession:
        """Start a recording's session now (it connects while the user speaks). On the event loop.
        `on_partial` gets the words so far whenever the service has a new guess, for the live words."""
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
class VoiceStream(Protocol):
    """One reply spoken as one continuous delivery: pieces go in as they are written, audio comes out as it is
    made, and every piece is spoken with the earlier ones as context, so pitch and pace carry across them.

    Used on the event loop. Iterating yields (piece, audio): the index of the piece the samples belong to, in the
    order send() got them, and mono samples at the voice's `sample_rate`. Empty audio says all of that piece has
    come. It ends once finish() was called and all audio has come, and raises VoiceUnavailable if the engine
    can't go on (the caller says the rest another way).
    """

    def send(self, text: str) -> None:
        """Queue the next piece. The engine starts on it at once; doesn't block."""
        ...

    def finish(self) -> None:
        """No more pieces are coming."""
        ...

    def cancel(self) -> None:
        """Stop now and drop audio not yet yielded. Iteration ends."""
        ...

    def __aiter__(self) -> AsyncIterator[tuple[int, Audio]]: ...


@runtime_checkable
class StreamingVoice(Voice, Protocol):
    """A Voice that can also speak text while it is still being written (see VoiceStream)."""

    first_audio_s: float
    """About how long from send() to the first audio, from recent streams. Tells a backchannel to wait."""

    def stream(self) -> VoiceStream | None:
        """A new delivery, or None when streaming isn't available now: then synthesize() piece by piece."""
        ...

    def prepare(self) -> None:
        """The user started talking: make the next stream fast (open the connection). Never blocks or raises."""
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
class PlaybackTap(Protocol):
    """What an AudioOutput has actually played, with timestamps, so a listener can tell Milo's own voice in the
    microphone from the user's (barge-in). Optional: outputs that can't say leave voice barge-in off."""

    def played(self, since: float) -> tuple[int, list[tuple[float, Audio]]]:
        """(sample rate, blocks) played from `since` on: each block is the time its first sample reached the
        speaker, on the clock of AudioInput.started_at, and its samples."""
        ...


@runtime_checkable
class LiveModel(Protocol):
    """A fast conversational model that streams its reply and keeps the conversation in memory."""

    name: str
    last_usage: Usage

    async def start(self, system_prompt: str) -> None:
        """Begin a fresh conversation with this system prompt, replacing any running one."""
        ...

    def turn(self, text: str, images: Sequence[Path] = ()) -> AsyncIterator[str]:
        """Send one user message and yield the reply's text deltas as they arrive. Raises HarnessError.

        `images` are PNG files sent with the message (a screenshot). Starts a conversation with an empty
        system prompt if start() was never called.
        """
        ...

    async def interrupt(self) -> None:
        """Stop the reply in progress. The running turn() iterator ends early; the conversation survives."""
        ...

    async def close(self) -> None: ...


@runtime_checkable
class ScreenEyes(Protocol):
    """Reads the frontmost window through the app, which holds the Accessibility and Screen Recording
    permissions."""

    async def look(self, mode: str = "window") -> ScreenCapture:
        """mode "window" or "selection". Never raises: a capture that failed has `error` set."""
        ...


@runtime_checkable
class AppHands(Protocol):
    """Runs one computer-use action inside the app."""

    async def act(self, tool: str, args: dict) -> dict:
        """The action's result. Raises HandsError with plain words the worker can act on."""
        ...

    def cancel(self) -> None:
        """Give up on every action still waiting for the app; each raises HandsError."""
        ...


@runtime_checkable
class Confirmer(Protocol):
    """Asks the user before an action. Any tool or service that is about to do something it can't undo uses it."""

    async def confirm(self, summary: str) -> bool:
        """Ask `summary`, a plain yes-or-no question naming the thing and the consequence.

        True only for a yes. No, no answer before the timeout, or an error mean False.
        """
        ...


@runtime_checkable
class Channel(Protocol):
    """A chat app the owner reaches Milo through from their phone (Telegram, iMessage). It only moves
    messages: who counts as the owner, what Milo answers and what may be sent is the MessageService's job."""

    name: str
    """The registry name, e.g. "telegram"."""
    label: str
    """What the user calls it, e.g. "Telegram"."""

    async def start(self) -> None:
        """Check the token or permissions and get ready. Raises ChannelError with plain words."""
        ...

    async def receive(self) -> list[Inbound]:
        """Wait for what arrived since the last call, for up to a poll's length. [] when nothing came.
        Raises ChannelError when the channel stopped working; the caller waits and tries again."""
        ...

    async def send(self, chat: str, text: str) -> None:
        """Send a text message to `chat`. Raises ChannelError."""
        ...

    async def ask(self, chat: str, id: str, question: str) -> None:
        """Send a yes-or-no question. Buttons, where the app has them, answer with `yes:<id>` or `no:<id>`."""
        ...

    async def typing(self, chat: str) -> None:
        """Show that Milo is writing, for a few seconds. Never raises."""
        ...

    async def send_file(self, chat: str, name: str, data: bytes, caption: str = "") -> None:
        """Send one file's bytes under `name`. The caller has read and checked them. Raises ChannelError."""
        ...

    async def acknowledge(self, inbound: Inbound, text: str = "") -> None:
        """Confirm a button press, with a short note the app may show. Never raises."""
        ...

    async def close(self) -> None: ...


@runtime_checkable
class QuestionRelay(Protocol):
    """Somewhere else Approvals can ask its questions, like the owner's phone."""

    def asked(self, id: str, question: str, detail: str) -> Relayed | None:
        """A question started. None: not passed on. Never raises."""
        ...

    def closed(self, id: str, answer: str) -> None:
        """The question is over: "yes", "no" or "timeout"."""
        ...


@dataclass(frozen=True)
class Relayed:
    """A question was passed on. `wait_s`: how long to wait for its answer at most. `only`: only the relay may
    answer it (the user is away, so whoever sits at the Mac must not)."""

    wait_s: float
    only: bool = False


@runtime_checkable
class RemoteState(Protocol):
    """Where the MessageService keeps whose phone is paired and whether remote is paused."""

    def load(self) -> dict: ...

    def save(self, data: dict) -> None: ...


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
class RoutineBook(Protocol):
    """The user's routines, one Markdown recipe each (milo.core.routines), plus a short log of their runs."""

    def all(self) -> list[Routine]:
        """Every routine that reads, by name. Re-reads only files that changed."""
        ...

    def problems(self) -> dict[str, str]:
        """Files that don't read, by slug, with what is wrong in plain words."""
        ...

    def get(self, slug: str) -> Routine | None: ...

    def save(self, routine: Routine) -> Routine:
        """Write the routine to its file, whole or not at all."""
        ...

    def rename(self, slug: str, name: str) -> Routine:
        """Give it a new name and the file a matching slug. Raises ValueError if that name is taken."""
        ...

    def update(self, slug: str, fields: dict[str, str]) -> Routine:
        """Set front matter fields (`paused`, `schedule`, `last_run`) in place, keeping the rest of the file as
        the user wrote it. Raises ValueError if there is no such routine or the result wouldn't read."""
        ...

    def delete(self, slug: str) -> bool:
        """Move the file aside (not gone: it can be put back by hand). False if there was none."""
        ...

    def draft_path(self, draft: str) -> Path:
        """Where a worker writes the recipe draft `draft` for the user to look at."""
        ...

    def read_draft(self, draft: str) -> str | None: ...

    def write_draft(self, draft: str, text: str) -> None: ...

    def drop_draft(self, draft: str) -> None: ...

    def record_run(self, slug: str, run: dict) -> None:
        """Append one run ({"at", "outcome", "inputs", "result", ...}) to the run log."""
        ...

    def runs(self, slug: str, n: int = 5) -> list[dict]:
        """The last `n` runs of a routine, oldest first."""
        ...


@runtime_checkable
class StateFile(Protocol):
    """A small JSON object kept across restarts, for a service's own bookkeeping."""

    def load(self) -> dict: ...

    def save(self, data: dict) -> None: ...


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

    def forward(self, id: str, to: list[str]) -> dict:
        """Save a draft passing email `id` on to `to`, attachments and all, and open it in Mail."""
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

    def list(self, folder: str, name: str = "", limit: int = 20) -> list[dict]:
        """The files right inside `folder` whose name contains `name`, newest first."""
        ...

    def move(self, paths: list[str], folder: str) -> dict:
        """Move files into `folder` (made if missing), never replacing one: moved (path, name, ...), folder."""
        ...


@runtime_checkable
class Phone(Protocol):
    """The owner's phone, reached by message through the brain (Milo by message, ADR 17)."""

    def send(self, path: str, caption: str = "") -> dict:
        """Send one file. The brain checks it and asks the user first. Raises ToolError."""
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
    phone: Phone | None = None


# ---- memory: episodes, facts and the user's things (docs/design/memory.md)
#
# Files are the truth and the index is a cache: EpisodeLog and FactStore append JSON lines, MemoryIndex can be
# deleted and rebuilt from them. Everything here blocks; the brain calls it on its memory thread.


@runtime_checkable
class EpisodeLog(Protocol):
    def append(self, episode: Episode) -> None:
        """Add an episode, or a newer version of one with the same id (a summary replacing a stub)."""
        ...

    def between(self, start: datetime, end: datetime) -> list[Episode]:
        """Episodes with start <= at < end, oldest first, latest version of each, forgotten ones left out."""
        ...

    def forget(self, id: str, reason: str) -> None:
        """Leave the episode out from now on. The old lines stay, so it can be brought back."""
        ...


@runtime_checkable
class FactStore(Protocol):
    def current(self) -> list[Fact]:
        """Facts that are neither retired nor replaced."""
        ...

    def add(self, fact: Fact) -> None: ...

    def retire(self, id: str, reason: str) -> None: ...

    def restore(self, id: str, reason: str) -> None:
        """Undo a retire."""
        ...

    def get(self, id: str) -> Fact | None:
        """Any fact ever added, current or not, with `retired` as it is now."""
        ...

    def forgotten(self) -> list[Fact]:
        """Facts the user had Milo forget (themselves, or through the worker after a yes), still retired, newest
        first. The night must not learn them again from the day's episodes."""
        ...


@runtime_checkable
class Embedder(Protocol):
    """Turns text into vectors for search. Local, runs on its own single-thread executor like STT and TTS."""

    dimensions: int
    key: str
    """Names the vector space (engine and model). The index re-embeds everything when it changes."""
    relevant_margin: float
    """How far above unrelated text (Hit.margin) a match must be to count without a shared word. Each model
    spreads differently."""

    def warm(self) -> None: ...

    def embed(self, texts: Sequence[str], *, query: bool = False) -> np.ndarray:
        """One unit-length float32 row per text. `query`: the text is a search, not something to be found."""
        ...


@runtime_checkable
class MemoryIndex(Protocol):
    """Search over facts, episodes and knowledge. A cache: rebuild() recreates it from the logs."""

    def upsert(self, items: Sequence[IndexItem]) -> None: ...

    def remove(self, ids: Collection[str]) -> None: ...

    def search(self, query: str, *, kinds: Collection[str] = (), since: datetime | None = None,
               until: datetime | None = None, limit: int = 20) -> list[Hit]:
        """Best first. Text and vector matches fused, so something comes back even for a vague query."""
        ...

    def rebuild(self) -> None: ...

    def refresh(self, limit: int | None = None) -> int:
        """Catch up with the logs, at most `limit` items at a time. Returns how many changed; 0: up to date."""
        ...


@runtime_checkable
class Recaller(Protocol):
    """Picks what memory a turn needs, within a token budget. No LLM call."""

    def recall(self, turn: str, context: TurnContext, budget_tokens: int) -> Recall: ...


@runtime_checkable
class Consolidator(Protocol):
    """The nightly "sleep": turns the day's raw records into episodes and facts."""

    async def consolidate(self, day: date) -> ConsolidationReport: ...


@runtime_checkable
class KnowledgeSource(Protocol):
    """One place the user's things live: a folder, Notes, Mail, meeting notes."""

    name: str

    def changed_since(self, since: datetime) -> Iterable[Document]: ...


# ---- meeting notes (docs/design/meetings.md)


@runtime_checkable
class TimedTranscriber(Protocol):
    """Speech to words with times, for meeting transcripts. Runs on the STT thread, below dictation."""

    def words(self, audio: Audio, language: str | None = None) -> list[TimedWord]:
        """16 kHz mono audio to the words in it, seconds from its start. [] for silence or noise. Blocking.
        `language` ("de") skips detecting it."""
        ...

    def spoken_language(self, audio: Audio) -> str:
        """The language spoken in the audio, like "en". Blocking."""
        ...


@runtime_checkable
class Diarizer(Protocol):
    """Whose voice each stretch of the call's audio is. Blocking; runs on its own thread."""

    model: str
    """Names the voice embeddings: voices of different models don't compare."""
    match: float
    """How alike (cosine) two voices of this model must be to count as one person."""

    def warm(self) -> None:
        """Download and load the models. Blocking."""
        ...

    def speakers(self, audio: Audio, spans: Sequence[tuple[float, float]]) -> list[Turn]:
        """A voice for each span of speech (seconds into `audio`, from the transcriber's segments and pauses).
        Spans too short to tell a voice are left out."""
        ...


@runtime_checkable
class VoiceBook(Protocol):
    """Known voices, so "Speaker 2" becomes "Anna" after the user names her once. Kept on the Mac only."""

    def match(self, voice: np.ndarray) -> str | None:
        """The name of the known voice this one sounds like, None if none is close enough."""
        ...

    def learn(self, name: str, voice: np.ndarray) -> None: ...


@runtime_checkable
class MeetingStore(Protocol):
    """Meetings on disk, one folder each: audio chunks, transcript.jsonl, transcript.md and notes.md.

    Transcript lines are appended together with a progress mark for their track, so a crash between two
    passes loses nothing and repeats nothing: lines without their mark are dropped on reading.
    """

    def open(self, meeting: MeetingInfo) -> str:
        """Make the folder for a new meeting and return its id."""
        ...

    def info(self, meeting_id: str) -> MeetingInfo: ...

    def audio_dir(self, meeting_id: str) -> Path:
        """Where the app writes the chunks: `me-0001.wav`, `them-0001.wav`, ..."""
        ...

    def chunks(self, meeting_id: str) -> list[Chunk]:
        """Every chunk on disk, by track and index, including one the app is still writing."""
        ...

    def audio(self, meeting_id: str, track: Track, start: float, end: float) -> Audio:
        """The track's audio from `start` to `end` seconds, as far as it's on disk. Silence where a chunk is missing."""
        ...

    def append(self, meeting_id: str, lines: Sequence[TranscriptLine], *, track: Track, upto: float) -> None:
        """Add the lines of one pass over `track`, which is now transcribed up to `upto` seconds."""
        ...

    def progress(self, meeting_id: str) -> dict[Track, float]:
        """How far each track is transcribed, in seconds since the meeting started."""
        ...

    def lines(self, meeting_id: str) -> list[TranscriptLine]:
        """Every committed line, in the order they were added."""
        ...

    def state(self, meeting_id: str) -> dict:
        """The meeting's own small JSON state (speakers, names, private times, whether recording stopped)."""
        ...

    def save_state(self, meeting_id: str, state: dict) -> None: ...

    def render(self, meeting_id: str, text: str) -> None:
        """Replace transcript.md."""
        ...

    def close(self, meeting_id: str, notes: MeetingNotes, markdown: str, *, keep_audio: bool = False) -> Path:
        """Write notes.md, mark the meeting done and delete its audio unless kept. Returns the notes path."""
        ...

    def unfinished(self) -> list[str]:
        """Meetings with chunks on disk that aren't transcribed yet, for recovery after a crash."""
        ...
