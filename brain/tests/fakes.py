"""Fakes for every port in milo.core.ports. Deterministic: fixed clock, scripted replies, no devices."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import date, datetime, timedelta

import numpy as np

from milo.core.events import Event
from milo.core.ports import LevelCallback
from milo.core.types import Audio, Emotion, HarnessError, Nudge, Reminder, Reply, Signals, Step, Usage


class FakeClock:
    def __init__(self, start: datetime = datetime(2026, 10, 29, 9, 0)):
        self._now = start
        self._mono = 1000.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._mono

    def advance(self, **delta) -> None:
        d = timedelta(**delta)
        self._now += d
        self._mono += d.total_seconds()


class FakeHarness:
    """Replies from a script. Each entry is a Reply, a HarnessError to raise, or a str to say happily."""

    name = "fake"

    def __init__(self, *script: Reply | HarnessError | str, delay_s: float = 0, steps: list[Step] = ()):
        self.script = deque(script)
        self.calls: list[tuple[str, str | None]] = []
        self.delay_s = delay_s
        self.steps = list(steps)
        """Reported to on_step on every call, before the reply."""

    async def reply(self, prompt: str, session_id: str | None, *, on_step=None) -> Reply:
        self.calls.append((prompt, session_id))
        for step in self.steps if on_step is not None else ():
            on_step(step)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        item = self.script.popleft() if self.script else "ok"
        if isinstance(item, HarnessError):
            raise item
        if isinstance(item, str):
            return Reply(Emotion.HAPPY, item, Usage(100, 50, 10), session_id or f"s{len(self.calls)}")
        return item


class FakeTranscriber:
    def __init__(self, *texts: str):
        self.texts = deque(texts)
        self.calls: list[Audio] = []
        self.warmed = False

    def warm(self) -> None:
        self.warmed = True

    def transcribe(self, audio: Audio) -> str:
        self.calls.append(audio)
        return self.texts.popleft() if self.texts else ""


class FakeVoice:
    sample_rate = 1000

    def __init__(self, fail: bool = False):
        self.spoken: list[str] = []
        self.fail = fail
        self.warmed = False
        self.cancels = 0

    def warm(self) -> None:
        self.warmed = True

    def synthesize(self, text: str) -> Audio:
        if self.fail:
            raise RuntimeError("tts broke")
        self.spoken.append(text)
        return np.full(10 * len(text), 0.1, dtype=np.float32)

    def cancel(self) -> None:
        self.cancels += 1


class FakeAudioInput:
    def __init__(self, seconds: float = 1.0, fail: bool = False):
        self.seconds = seconds
        self.fail = fail
        self._active = False
        self.starts = 0

    @property
    def active(self) -> bool:
        return self._active

    def start(self, on_level: LevelCallback) -> None:
        if self.fail:
            raise OSError("no input device")
        self._active = True
        self.starts += 1
        on_level(0.5)

    def stop(self) -> Audio:
        self._active = False
        return np.full(int(16000 * self.seconds), 0.1, dtype=np.float32)

    def peek(self, start: int = 0) -> Audio:
        if not self._active:
            return np.zeros(0, dtype=np.float32)
        return np.full(max(0, int(16000 * self.seconds) - start), 0.1, dtype=np.float32)


class FakeAudioOutput:
    """Streaming output. drain() finishes at once, unless `block` is set: then it waits for interrupt()."""

    def __init__(self, block: bool = False):
        self.block = block
        self.streams: list[dict] = []  # one entry per begin(): sample_rate and the fed chunk lengths
        self.interrupts = 0
        self._stop = asyncio.Event()
        self._interrupted = False

    @property
    def fed(self) -> list[int]:
        return self.streams[-1]["chunks"] if self.streams else []

    def begin(self, sample_rate: int, on_level: LevelCallback) -> None:
        self.streams.append({"sample_rate": sample_rate, "chunks": []})
        self._on_level = on_level
        self._interrupted = False
        self._stop.clear()

    def feed(self, audio: Audio) -> None:
        self.streams[-1]["chunks"].append(len(audio))
        self._on_level(0.3)

    async def drain(self) -> bool:
        if self.block and not self._interrupted:
            await self._stop.wait()
        await asyncio.sleep(0)
        self._on_level(0.0)
        return not self._interrupted

    def interrupt(self) -> None:
        self.interrupts += 1
        self._interrupted = True
        self._stop.set()


class FakeLiveModel:
    """Streams scripted replies. Each script entry is a list of deltas, or a HarnessError to raise.

    `gate` (an asyncio.Event) pauses after the first delta until set, so tests can interrupt mid-reply.
    """

    name = "fake-live"

    def __init__(self, *script: list[str] | HarnessError, gate: asyncio.Event | None = None):
        self.script = deque(script)
        self.gate = gate
        self.system_prompts: list[str] = []
        self.turns: list[str] = []
        self.interrupts = 0
        self.closed = False
        self.last_usage = Usage()
        self._interrupted = asyncio.Event()

    async def start(self, system_prompt: str) -> None:
        self.system_prompts.append(system_prompt)

    async def turn(self, text: str):
        if not self.system_prompts:
            self.system_prompts.append("")
        self.turns.append(text)
        self._interrupted.clear()
        item = self.script.popleft() if self.script else ["[neutral] ok."]
        if isinstance(item, HarnessError):
            raise item
        for i, delta in enumerate(item):
            if self._interrupted.is_set():
                return
            yield delta
            await asyncio.sleep(0)
            if i == 0 and self.gate is not None:
                await asyncio.wait([asyncio.ensure_future(self.gate.wait()),
                                    asyncio.ensure_future(self._interrupted.wait())],
                                   return_when=asyncio.FIRST_COMPLETED)
        self.last_usage = Usage(600, 0, len(item))

    async def interrupt(self) -> None:
        self.interrupts += 1
        self._interrupted.set()

    async def close(self) -> None:
        self.closed = True


class MemoryProfile:
    def __init__(self, text: str = "# About the user\n"):
        self.text = text
        self.facts: list[str] = []

    def read(self) -> str:
        return self.text + "".join(f"- {f}\n" for f in self.facts)

    def remember(self, fact: str) -> None:
        if fact not in self.facts:
            self.facts.append(fact)


class UpperCleaner:
    def clean(self, text: str) -> str:
        return text.strip().upper()


class RecordingSink:
    def __init__(self):
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)

    def of(self, cls: type) -> list:
        return [e for e in self.events if isinstance(e, cls)]

    def wire(self) -> list[dict]:
        return [e.to_wire() for e in self.events]


class ListReminders:
    def __init__(self, *items: Reminder):
        self.items = list(items)

    def all(self) -> list[Reminder]:
        return self.items

    def add(self, due: datetime, text: str) -> Reminder:
        reminder = Reminder(id=f"r{len(self.items)}", due=due, text=text, done=False)
        self.items.append(reminder)
        return reminder


class MemoryLedger:
    def __init__(self):
        self.entries: list[tuple[str, str, Usage]] = []

    def record(self, source: str, harness: str, usage: Usage) -> None:
        self.entries.append((source, harness, usage))


class MemoryHistory:
    def __init__(self):
        self.entries: list[tuple[str, str | None]] = []

    def append(self, text: str, app: str | None) -> None:
        self.entries.append((text, app))


class CountingBudget:
    def __init__(self, calls_per_day: int = 0):
        self.calls_per_day = calls_per_day
        self.spent: dict[date, int] = {}

    def allow(self, today: date) -> bool:
        return self.spent.get(today, 0) < self.calls_per_day

    def spend(self, today: date) -> None:
        self.spent[today] = self.spent.get(today, 0) + 1


class ScriptedEngine:
    """A ProactiveEngine that returns queued nudges on the next tick."""

    def __init__(self, budget: CountingBudget | None = None, tick_s: float = 0.01):
        self.tick_s = tick_s
        self.budget = budget or CountingBudget()
        self.queue: deque[list[Nudge]] = deque()
        self.seen: list[Signals] = []

    def tick(self, signals: Signals) -> list[Nudge]:
        self.seen.append(signals)
        return self.queue.popleft() if self.queue else []


class MemoryTranscript:
    """TranscriptStore in a list."""

    def __init__(self, *entries: dict):
        self.entries = list(entries)

    def append(self, entry: dict) -> None:
        self.entries.append(entry)

    def tail(self, n: int) -> list[dict]:
        return self.entries[-n:] if n > 0 else []
