"""The services wired together with fakes, the way compose.py wires the real thing."""

from __future__ import annotations

import asyncio
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from milo.adapters.connect.fake import _fake
from milo.adapters.embed.hashing import HashEmbedder
from milo.core.registry import AdapterContext
from milo.services.app_ops import AppOps
from milo.services.quick_actions import QuickActions
from milo.brain import Brain
from milo.config import UiSettings
from milo.core.events import Bubble, StateChanged
from milo.core.types import LiveMode, MiloState
from milo.memory.recall import HybridRecaller, render
from milo.core.language import SpokenLanguage
from milo.services.opener import Opener
from milo.services.access import AccessGate
from milo.services.app_bridge import AppBridge
from milo.services.approvals import Approvals
from milo.services.context import UserContext
from milo.services.conversation import Conversation
from milo.services.dictation import DictationService
from milo.services.hands import HandsService
from milo.services.heartbeat_runner import HeartbeatRunner
from milo.services.cloud_hearing import CloudHearing
from milo.services.listening import Listening
from milo.services.live_talk import LiveTalk, untrusted
from milo.services.memory import Memory, MemoryParts, TurnMemory
from milo.services.messages import MessageService, MessageSettings
from milo.services.speaker import Speaker
from milo.services.orchestrator import Orchestrator
from milo.services.permits import Permits
from milo.services.routines import Routines
from milo.services.task_runner import TaskRunner
from milo.services.tool_requests import ToolRequests
from milo.services.undo import Undo
from milo.memory.undo_shelf import FileUndoShelf
from milo.core.control import Protected
from milo.services.ui_state import UiState
from milo.settings import Settings
from tests.fakes import (FakeAudioInput, FakeAudioOutput, FakeChannel, FakeClock, FakeEyes, FakeHands, FakeHarness,
                         FakeLiveModel, FakeTranscriber, FakeVoice, ListReminders, MemoryConfigFile, MemoryHistory,
                         MemoryLedger, MemoryProfile, MemoryRemoteState, MemoryRoutineBook, MemoryState,
                         RecordingSink, ScriptedEngine, UpperCleaner, FakeMemoryIndex, MemoryEpisodeLog,
                         MemoryFactStore)

PERSONA = "You are Milo, a test persona."


class InlineExecutor(Executor):
    """Runs submitted work immediately on the calling thread, so tests stay deterministic."""

    def submit(self, fn, /, *args, **kwargs) -> Future:
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as e:
            future.set_exception(e)
        return future


@dataclass
class Stack:
    model: FakeLiveModel = field(default_factory=FakeLiveModel)
    harness: FakeHarness = field(default_factory=FakeHarness)
    background: object | None = None
    """The worker without the Mac tools. None: every helper runs on `harness`, none on the screen."""
    max_helpers: int = 3
    transcriber: FakeTranscriber = field(default_factory=FakeTranscriber)
    voice: FakeVoice = field(default_factory=FakeVoice)
    mic: FakeAudioInput = field(default_factory=FakeAudioInput)
    output: FakeAudioOutput = field(default_factory=FakeAudioOutput)
    engine: ScriptedEngine = field(default_factory=ScriptedEngine)
    clock: FakeClock = field(default_factory=FakeClock)
    sink: RecordingSink = field(default_factory=RecordingSink)
    ledger: MemoryLedger = field(default_factory=MemoryLedger)
    history: MemoryHistory = field(default_factory=MemoryHistory)
    profile: MemoryProfile = field(default_factory=MemoryProfile)
    reminders: ListReminders = field(default_factory=ListReminders)
    persona: str = PERSONA
    idle_reset_s: float = 600
    wait_s: float = 0.05  # how long task results and nudges wait for a live turn to end
    eyes: FakeEyes | None = None  # None: Milo can't look, and his prompt says nothing about looking
    hands_port: FakeHands = field(default_factory=FakeHands)
    access: object | None = None
    """An AppAccess (FakeAccess): what the system lets Milo do (ADR 0025). None: HandsService doesn't check."""
    screens: Path | None = None
    confirm_timeout_s: float = 1.0
    hearing: CloudHearing | None = None  # a cloud transcriber that listens along in talk mode
    with_memory: bool = False  # recall per turn, episode stubs and the facts screen, all on fakes
    routine_book: MemoryRoutineBook = field(default_factory=MemoryRoutineBook)
    routine_state: MemoryState = field(default_factory=MemoryState)
    max_routine_runs: int = 6
    config_file: MemoryConfigFile = field(default_factory=MemoryConfigFile)
    ask: str | None = None
    """[approvals] ask: how often Milo asks about work in an app (ADR 0022). None: the default (auto)."""
    allowed_apps: list | None = None
    """[approvals] allowed_apps: the apps the user said Allow always to."""
    channel: FakeChannel | None = None
    """A chat app for Milo by message. None: no MessageService."""
    remote: MemoryRemoteState = field(default_factory=MemoryRemoteState)
    message_settings: MessageSettings = field(default_factory=MessageSettings)
    home: Path | None = None
    """The user's home for Undo (ADR 0026): Milo keeps its records in home/Milo/state/undo, and Excel's own folder is
    under it. None: no Undo, so the Mac tools run no scripts of Milo's own around the worker's."""
    world: Path | None = None
    """A folder for made-up connections (adapters/connect/fake.py, world.json): the talker's quick actions and its
    <today> block work on them (ADR 0029). None: no quick actions."""
    paste: object | None = None
    """What the app answers to text.write and text.unwrite (a FakePaste, tests/services/test_writing.py): <write> tags
    paste through it (ADR 0033). None: no Writer."""
    meetings: object | None = None
    """What <meeting> tags start and stop: a MeetingService or a stand-in with recording, toggle and pause."""
    real_threads: bool = False
    """STT, TTS and memory each on a real single thread, like compose builds them, instead of inline. For tests
    that look for ordering bugs between the event loop and those threads (tests/test_races.py). close() ends them."""

    def __post_init__(self):
        self.executors = {name: ThreadPoolExecutor(1, thread_name_prefix=name) if self.real_threads
                          else InlineExecutor() for name in ("stt", "tts", "memory")}
        executor = self.executors["stt"]
        self.ui = UiState(self.sink)
        self.context = UserContext(self.clock)
        self.conversation = Conversation(self.harness, self.ledger, self.clock, self.idle_reset_s)
        self.speaker = Speaker(self.voice, self.output, self.ui, self.executors["tts"])
        approvals = {**({"ask": self.ask} if self.ask else {}),
                     **({"allowed_apps": self.allowed_apps} if self.allowed_apps else {})}
        self.config_file.raw = {**self.config_file.raw,
                                "approvals": {**self.config_file.raw.get("approvals", {}), **approvals}}
        settings = self.config_file.read().approvals
        self.permits = Permits(settings.ask, settings.allowed_apps)
        self.language = SpokenLanguage()
        self.approvals = Approvals(self.ui, self.speaker, timeout_s=self.confirm_timeout_s,
                                   quiet=lambda: self.live_talk.busy, permits=self.permits, language=self.language.get)
        self.bridge = AppBridge(self.sink, timeout_s=self.confirm_timeout_s)
        self.gate = AccessGate(self.access, self.sink, pause_s=0) if self.access is not None else None
        self.undo = None
        if self.home is not None:
            self.undo = Undo(FileUndoShelf(self.home / "Milo" / "state" / "undo", self.home,
                                           protected=Protected(self.home / "Milo")), self.hands_port, self.ui,
                             self.clock, confirm=self.approvals, speaker=self.speaker, helpers=lambda: self.tasks,
                             quiet=lambda: self.live_talk.busy, wait_s=self.wait_s, poll_s=0.005)
        self.hands = HandsService(self.hands_port, self.approvals, self.ui, access=self.gate,
                                  before_change=self.undo.before_change if self.undo is not None else None,
                                  language=self.language.get)
        self.opener = Opener(self.hands_port, self.ui, self.clock)
        self.runner = TaskRunner(self.harness, self.ledger, self.clock, self.context, background=self.background,
                                 hands=self.hands)
        self.tasks = Orchestrator(self.runner, self.speaker, self.ui, self.clock,
                                  max_helpers=lambda: self.max_helpers,
                                  quiet=lambda: self.live_talk.busy or self.mic.active, wait_s=self.wait_s,
                                  poll_s=0.005, coalesce_s=0)
        self.memory = self.turn_memory = None
        if self.with_memory:
            self.facts, self.episodes = MemoryFactStore(), MemoryEpisodeLog()
            self.index = FakeMemoryIndex(self.facts, self.episodes)
            parts = MemoryParts(self.facts, self.episodes, self.index, HybridRecaller(self.index, self.facts),
                                HashEmbedder(), render)
            self.memory = Memory(parts, self.executors["memory"], self.sink, self.clock)
            self.memory.ready.set()
            self.turn_memory = TurnMemory(self.memory)
        self.routines = Routines(self.routine_book, self.routine_state, self.tasks, self.speaker, self.ui,
                                 self.clock, approvals=self.approvals, quiet=lambda: self.live_talk.busy,
                                 max_runs_per_day=lambda: self.max_routine_runs, inert=untrusted, wait_s=self.wait_s,
                                 poll_s=0.005)
        self.tasks.on_done.append(self.routines.seen)
        if self.undo is not None:
            self.tasks.on_done.append(self.undo.finished)
        self.tasks.on_done.append(lambda helper: self.permits.end(helper.id))
        self.permits.user_asked = self.tasks.user_asked
        self.quick = self.connections = None
        if self.world is not None:
            self.connections = _fake({"dir": str(self.world)}, AdapterContext(self.world, self.world / "state",
                                                                              self.clock))
            self.quick = QuickActions(AppOps(self.connections), self.connections, self.ui, self.speaker, self.clock,
                                      approvals=self.approvals, undo=self.undo, reminders=self.reminders,
                                      meetings=self.meetings, quiet=lambda: self.mic.active, wait_s=self.wait_s,
                                      language=self.language.get, poll_s=0.005)
        self.writer = None
        if self.paste is not None:
            from milo.services.writing import Writer
            from milo.services.transcript import Transcript
            from tests.fakes import MemoryConversations
            self.writer = Writer(self.paste, self.ui, self.speaker, undo=self.undo, quiet=lambda: self.mic.active,
                                 transcript=Transcript(self.sink, MemoryConversations(), self.clock),
                                 language=self.language.get, wait_s=self.wait_s, poll_s=0.005)
        self.live_talk = LiveTalk(self.model, self.speaker, self.ui, self.context, self.clock, self.profile,
                                  self.reminders, self.ledger, lambda: self.persona, self.idle_reset_s, self.tasks,
                                  eyes=self.eyes, approvals=self.approvals, memory=self.turn_memory,
                                  routines=self.routines, undo=self.undo, opener=self.opener,
                                  language=self.language, quick=self.quick, writer=self.writer)
        self.tasks.on_result = self.live_talk.note
        self.dictation = DictationService(UpperCleaner(), self.history, self.ui)
        self.listening = Listening(self.mic, self.transcriber, executor, self.ui, self.dictation, self.live_talk,
                                   self.context, hearing=self.hearing)
        self.heartbeat = HeartbeatRunner(self.engine, self.context, self.conversation, self.speaker, self.ui,
                                         self.mic, self.clock, busy=lambda: self.live_talk.busy,
                                         wait_s=self.wait_s, poll_s=0.005)
        use_ui = lambda c: self.brain.use_ui(c.ui)  # noqa: E731
        live = {("ui", "dictate_key"): use_ui, ("ui", "talk_key"): use_ui,
                ("ui", "whats_this_key"): use_ui, ("ui", "meeting_key"): use_ui, ("ui", "voice"): lambda c: setattr(self.speaker, "silent", not c.ui.voice),
                ("dictation", "stream"): lambda c: setattr(self.listening, "live_mode", LiveMode(c.dictation.stream)),
                ("approvals", "ask"): lambda c: setattr(self.permits, "ask", c.approvals.ask),
                ("approvals", "allowed_apps"): lambda c: self.permits.use(c.approvals.allowed_apps)}
        self.settings = Settings(self.config_file, self.config_file.read(), self.ui, live)
        self.permits.save = lambda apps: self.settings.keep("approvals", "allowed_apps", apps)
        self.messages = None
        if self.channel is not None:
            self.messages = MessageService(self.channel, self.live_talk, self.approvals, self.remote, self.speaker,
                                           self.ui, self.context, self.clock, settings=self.message_settings,
                                           helpers=lambda: self.tasks.helpers, board=self.tasks.board,
                                           reminders=self.reminders, app=self.bridge.call,
                                           wait_for_mac_s=self.wait_s, typing_every_s=0.01, backoff_s=(0.01, 0.02))
            self.approvals.relays.append(self.messages)
            self.tasks.watchers.append(self.messages.helper_changed)
            self.heartbeat.after_tick.append(self.messages.tick)
        self.brain = Brain(self.ui, self.listening, self.live_talk, self.context, self.heartbeat, UiSettings(),
                           approvals=self.approvals, bridge=self.bridge, hands=self.hands, screens=self.screens,
                           helpers=self.tasks, memory=self.memory, routines=self.routines,
                           settings=self.settings, messages=self.messages, undo=self.undo)
        self.tool_requests = ToolRequests(self.approvals, self.bridge, undo=self.undo)

    def close(self) -> None:
        for executor in self.executors.values():
            executor.shutdown(wait=False, cancel_futures=True)

    def states(self) -> list[MiloState]:
        return [e.state for e in self.sink.of(StateChanged)]

    def bubbles(self) -> list[str]:
        return [e.text for e in self.sink.of(Bubble)]


async def settle(rounds: int = 50) -> None:
    """Let background tasks (turns, speech, threadsafe callbacks) run to their next real wait."""
    for _ in range(rounds):
        await asyncio.sleep(0)
