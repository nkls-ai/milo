"""The services wired together with fakes, the way compose.py wires the real thing."""

from __future__ import annotations

import asyncio
from concurrent.futures import Executor, Future
from dataclasses import dataclass, field
from pathlib import Path

from milo.adapters.embed.hashing import HashEmbedder
from milo.brain import Brain
from milo.config import UiSettings
from milo.core.events import Bubble, StateChanged
from milo.core.types import MiloState
from milo.memory.recall import HybridRecaller, render
from milo.services.app_bridge import AppBridge
from milo.services.approvals import Approvals
from milo.services.context import UserContext
from milo.services.conversation import Conversation
from milo.services.dictation import DictationService
from milo.services.hands import HandsService
from milo.services.heartbeat_runner import HeartbeatRunner
from milo.services.listening import Listening
from milo.services.live_talk import LiveTalk
from milo.services.memory import Memory, MemoryParts, TurnMemory
from milo.services.speaker import Speaker
from milo.services.task_runner import TaskRunner
from milo.services.ui_state import UiState
from tests.fakes import (FakeAudioInput, FakeAudioOutput, FakeClock, FakeEyes, FakeHands, FakeHarness,
                         FakeLiveModel, FakeTranscriber, FakeVoice, ListReminders, MemoryHistory, MemoryLedger,
                         MemoryProfile, RecordingSink, ScriptedEngine, UpperCleaner, FakeMemoryIndex, MemoryEpisodeLog,
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
    screens: Path | None = None
    confirm_timeout_s: float = 1.0
    with_memory: bool = False  # recall per turn, episode stubs and the facts screen, all on fakes

    def __post_init__(self):
        executor = InlineExecutor()
        self.ui = UiState(self.sink)
        self.context = UserContext(self.clock)
        self.conversation = Conversation(self.harness, self.ledger, self.clock, self.idle_reset_s)
        self.speaker = Speaker(self.voice, self.output, self.ui, executor)
        self.approvals = Approvals(self.ui, self.speaker, timeout_s=self.confirm_timeout_s,
                                   quiet=lambda: self.live_talk.busy)
        self.bridge = AppBridge(self.ui, timeout_s=self.confirm_timeout_s)
        self.hands = HandsService(self.hands_port, self.approvals, self.ui)
        self.tasks = TaskRunner(self.conversation, self.speaker, self.context,
                                quiet=lambda: self.live_talk.busy or self.mic.active, wait_s=self.wait_s,
                                poll_s=0.005, hands=self.hands)
        self.memory = self.turn_memory = None
        if self.with_memory:
            self.facts, self.episodes = MemoryFactStore(), MemoryEpisodeLog()
            self.index = FakeMemoryIndex(self.facts, self.episodes)
            parts = MemoryParts(self.facts, self.episodes, self.index, HybridRecaller(self.index, self.facts),
                                HashEmbedder(), render)
            self.memory = Memory(parts, executor, self.sink, self.clock)
            self.memory.ready.set()
            self.turn_memory = TurnMemory(self.memory)
        self.live_talk = LiveTalk(self.model, self.speaker, self.ui, self.context, self.clock, self.profile,
                                  self.reminders, self.ledger, lambda: self.persona, self.idle_reset_s, self.tasks,
                                  eyes=self.eyes, approvals=self.approvals, memory=self.turn_memory)
        self.tasks.on_result = self.live_talk.note
        self.dictation = DictationService(UpperCleaner(), self.history, self.ui)
        self.listening = Listening(self.mic, self.transcriber, executor, self.ui, self.dictation, self.live_talk,
                                   self.context)
        self.heartbeat = HeartbeatRunner(self.engine, self.context, self.conversation, self.speaker, self.ui,
                                         self.mic, self.clock, busy=lambda: self.live_talk.busy,
                                         wait_s=self.wait_s, poll_s=0.005)
        self.brain = Brain(self.ui, self.listening, self.live_talk, self.context, self.heartbeat, UiSettings(),
                           approvals=self.approvals, bridge=self.bridge, hands=self.hands, screens=self.screens,
                           memory=self.memory)

    def states(self) -> list[MiloState]:
        return [e.state for e in self.sink.of(StateChanged)]

    def bubbles(self) -> list[str]:
        return [e.text for e in self.sink.of(Bubble)]


async def settle(rounds: int = 50) -> None:
    """Let background tasks (turns, speech, threadsafe callbacks) run to their next real wait."""
    for _ in range(rounds):
        await asyncio.sleep(0)
