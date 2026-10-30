"""Fakes for every port in milo.core.ports. Deterministic: fixed clock, scripted replies, no devices."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import date, datetime, timedelta

import numpy as np

from milo.core.events import Event
from milo.core.ports import LevelCallback
from milo.core.types import (Audio, Emotion, HandsError, HarnessError, Nudge, Reminder, Reply, ScreenCapture, Signals,
                             Step, Usage)


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

    async def reply(self, prompt: str, session_id: str | None, *, on_step=None, on_session=None,
                    on_plan=None) -> Reply:
        self.calls.append((prompt, session_id))
        if on_session is not None:
            on_session(session_id or f"s{len(self.calls)}")
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


class WorkerScript:
    """What one scripted worker turn does, in order: report steps, plan progress, wait, then answer.

    Entries: a Step (reported to on_step), ("plan", done, total), ("sleep", seconds), an asyncio.Event (wait
    for it), and last a Reply, a str (said happily) or a HarnessError (raised). `session` is the id it names.
    """

    def __init__(self, *actions, session: str = ""):
        self.actions = actions
        self.session = session
        self.started = asyncio.Event()
        self.cancelled = False
        self.prompt = ""
        self.session_id: str | None = None


class ScriptedHarness:
    """A worker harness that plays one WorkerScript per call, in parallel, like separate worker processes.

    A call without a script left answers "ok" at once. Cancelling a call marks its script cancelled, the way
    the real adapters end the CLI.
    """

    def __init__(self, *scripts: WorkerScript, name: str = "scripted"):
        self.name = name
        self.scripts = deque(scripts)
        self.played: list[WorkerScript] = []
        self.running = 0
        self.most_at_once = 0

    def add(self, *scripts: WorkerScript) -> None:
        self.scripts.extend(scripts)

    async def reply(self, prompt: str, session_id: str | None, *, on_step=None, on_session=None,
                    on_plan=None) -> Reply:
        script = self.scripts.popleft() if self.scripts else WorkerScript("ok")
        script.prompt, script.session_id = prompt, session_id
        self.played.append(script)
        self.running += 1
        self.most_at_once = max(self.most_at_once, self.running)
        script.started.set()
        session = session_id or script.session or f"{self.name}-{len(self.played)}"
        try:
            if on_session is not None:
                on_session(session)
            for action in script.actions:
                if isinstance(action, Step):
                    if on_step is not None:
                        on_step(action)
                elif isinstance(action, tuple) and action[0] == "plan":
                    if on_plan is not None:
                        on_plan(action[1], action[2])
                elif isinstance(action, tuple) and action[0] == "sleep":
                    await asyncio.sleep(action[1])
                elif isinstance(action, asyncio.Event):
                    await action.wait()
                elif isinstance(action, HarnessError):
                    raise action
                elif isinstance(action, str):
                    return Reply(Emotion.HAPPY, action, Usage(100, 50, 10), session)
                elif isinstance(action, Reply):
                    return action
            return Reply(Emotion.HAPPY, "ok", Usage(100, 50, 10), session)
        except asyncio.CancelledError:
            script.cancelled = True
            raise
        finally:
            self.running -= 1


class FakeTranscriber:
    def __init__(self, *texts: str):
        self.texts = deque(texts)
        self.calls: list[Audio] = []
        self.previews: list[Audio] = []
        self.warmed = False

    def warm(self) -> None:
        self.warmed = True

    def wake(self) -> None:
        pass

    def transcribe(self, audio: Audio, before: str = "", *, quick: bool = False) -> str:
        self.calls.append(audio)
        return self.texts.popleft() if self.texts else ""

    def preview(self, audio: Audio) -> str:
        self.previews.append(audio)
        return ""

    def interrupt(self) -> None:
        pass


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
        self.images: list[list] = []
        """The images sent with each turn."""
        self.interrupts = 0
        self.closed = False
        self.last_usage = Usage()
        self._interrupted = asyncio.Event()

    async def start(self, system_prompt: str) -> None:
        self.system_prompts.append(system_prompt)

    async def turn(self, text: str, images=()):
        if not self.system_prompts:
            self.system_prompts.append("")
        self.turns.append(text)
        self.images.append(list(images))
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


class FakeEyes:
    """ScreenEyes that returns queued captures, then an empty one with an error."""

    def __init__(self, *captures: ScreenCapture):
        self.captures = deque(captures)
        self.modes: list[str] = []

    async def look(self, mode: str = "window") -> ScreenCapture:
        self.modes.append(mode)
        await asyncio.sleep(0)
        return self.captures.popleft() if self.captures else ScreenCapture(error="nothing to see")


class FakeHands:
    """AppHands. `targets[tool]` answers describe; `results[tool]` is a dict or a HandsError to raise, or a list
    of those, one per call.

    `gate` (an asyncio.Event) holds every non-describe action until set or cancel()."""

    def __init__(self, targets: dict | None = None, results: dict | None = None, gate: asyncio.Event | None = None):
        self.targets = targets or {}
        self.results = results or {}
        self.gate = gate
        self.calls: list[tuple[str, dict]] = []
        self.cancels = 0
        self._cancelled = asyncio.Event()

    async def act(self, tool: str, args: dict) -> dict:
        self.calls.append((tool, args))
        if tool == "describe":
            return dict(self.targets.get(args["tool"], {}))
        if self.gate is not None:
            await asyncio.wait([asyncio.ensure_future(self.gate.wait()),
                                asyncio.ensure_future(self._cancelled.wait())], return_when=asyncio.FIRST_COMPLETED)
            if self._cancelled.is_set():
                raise HandsError("stopped")
        result = self.results.get(tool, {"text": f"{tool} done"})
        if isinstance(result, list):
            result = result.pop(0)
        if isinstance(result, HandsError):
            raise result
        return result

    def cancel(self) -> None:
        self.cancels += 1
        self._cancelled.set()

    @property
    def actions(self) -> list[str]:
        return [tool for tool, _ in self.calls if tool != "describe"]


class FakeConfirm:
    """Confirmer that answers from a script (default no) and keeps the questions."""

    def __init__(self, *answers: bool):
        self.answers = deque(answers)
        self.asked: list[str] = []

    async def confirm(self, summary: str) -> bool:
        self.asked.append(summary)
        return self.answers.popleft() if self.answers else False


class MemoryEpisodeLog:
    """EpisodeLog in a list. Same rules as the file: a newer line with the same id wins, forget hides."""

    def __init__(self):
        self.lines: list = []
        self.forgotten: set[str] = set()

    def append(self, episode) -> None:
        self.lines.append(episode)

    def between(self, start, end) -> list:
        latest = {e.id: e for e in self.lines}
        return sorted((e for e in latest.values() if start <= e.at < end and e.id not in self.forgotten),
                      key=lambda e: (e.at, e.id))

    def forget(self, id: str, reason: str) -> None:
        if not any(e.id == id for e in self.lines):
            raise KeyError(id)
        self.forgotten.add(id)


class MemoryFactStore:
    """FactStore in a dict."""

    def __init__(self, *facts):
        self.facts: dict = {}
        self.log: list[tuple[str, str, str]] = []
        for fact in facts:
            self.add(fact)

    def current(self) -> list:
        replaced = {f.replaces for f in self.facts.values() if f.replaces and not f.retired}
        return [f for f in self.facts.values() if not f.retired and f.id not in replaced]

    def add(self, fact, *, by: str = "") -> None:
        self.facts[fact.id] = fact
        self.log.append(("add", fact.id, by))

    def retire(self, id: str, reason: str, *, by: str = "") -> None:
        from dataclasses import replace
        self.facts[id] = replace(self.facts[id], retired=True)
        self.log.append(("retire", id, by))

    def restore(self, id: str, reason: str, *, by: str = "") -> None:
        from dataclasses import replace
        self.facts[id] = replace(self.facts[id], retired=False)
        self.log.append(("restore", id, by))

    def get(self, id: str):
        return self.facts.get(id)

    def forgotten(self) -> list:
        ids = [id for op, id, by in reversed(self.log) if op == "retire" and by in ("you", "worker")]
        return [self.facts[id] for id in dict.fromkeys(ids) if self.facts[id].retired]


class FakeMemoryIndex:
    """MemoryIndex over a dict: words shared with the query make a hit. refresh() follows the fake logs."""

    def __init__(self, facts=None, episodes=None):
        self.items: dict = {}
        self.facts = facts
        self.episodes = episodes
        self.searches: list[str] = []

    def upsert(self, items) -> None:
        for item in items:
            self.items[item.id] = item

    def remove(self, ids) -> None:
        for id in ids:
            self.items.pop(id, None)

    def search(self, query, *, kinds=(), since=None, until=None, limit=20) -> list:
        from milo.core.memory import Hit
        from milo.memory.index import terms

        self.searches.append(query)
        words = set(terms(query))
        found = []
        for item in self.items.values():
            if (kinds and item.kind not in kinds) or (since and item.at < since) or (until and item.at >= until):
                continue
            shared = len(words & set(terms(item.text)))
            if shared or since is not None:
                found.append((shared, item))
        found.sort(key=lambda x: -x[0])
        return [Hit(item, 1 / (60 + rank), rank if shared else None, None, 0.0)
                for rank, (shared, item) in enumerate(found[:limit])]

    def rebuild(self) -> None:
        self.items.clear()
        self.refresh()

    def refresh(self, limit=None) -> int:
        from datetime import datetime

        from milo.core.memory import IndexItem

        want = {}
        if self.facts is not None:
            want |= {f.id: IndexItem.of_fact(f) for f in self.facts.current()}
        if self.episodes is not None:
            want |= {e.id: IndexItem.of_episode(e) for e in self.episodes.between(datetime.min, datetime.max)}
        self.items = want
        return 0  # all at once, so it is up to date after one call


class MemoryRoutineBook:
    """RoutineBook in memory. `drafts` holds what a worker "wrote" to each draft path."""

    def __init__(self, *routines):
        from milo.core.routines import Routine  # noqa: F401  for the type of what is stored

        self.routines = {r.slug: r for r in routines}
        self.broken: dict[str, str] = {}
        self.drafts: dict[str, str] = {}
        self.log: list[dict] = []
        self.deleted: list[str] = []

    def all(self):
        return sorted(self.routines.values(), key=lambda r: r.name.lower())

    def problems(self) -> dict[str, str]:
        return dict(self.broken)

    def get(self, slug):
        return self.routines.get(slug)

    def save(self, routine):
        self.routines[routine.slug] = routine
        return routine

    def rename(self, slug, name):
        from dataclasses import replace

        from milo.core.routines import slugify

        new = slugify(name)
        if new != slug and new in self.routines:
            raise ValueError(f"there is a routine called {name} already")
        renamed = replace(self.routines.pop(slug), slug=new, name=name)
        self.routines[new] = renamed
        return renamed

    def update(self, slug, fields):
        from dataclasses import replace

        if slug not in self.routines:
            raise ValueError("there is no such routine")
        if fields.get("paused", "no") not in ("yes", "no"):
            raise ValueError("paused: must be yes or no")
        values = {k: (v == "yes" if k == "paused" else v) for k, v in fields.items()}
        self.routines[slug] = replace(self.routines[slug], **values)
        return self.routines[slug]

    def delete(self, slug):
        if self.routines.pop(slug, None) is None:
            return False
        self.deleted.append(slug)
        return True

    def record_run(self, slug, run):
        self.log.append({**run, "slug": slug})

    def runs(self, slug, n=5):
        return [r for r in self.log if r["slug"] == slug][-n:]

    def draft_path(self, draft):
        from pathlib import Path

        return Path("/drafts") / f"{draft}.md"

    def read_draft(self, draft):
        return self.drafts.get(draft)

    def write_draft(self, draft, text):
        self.drafts[draft] = text

    def drop_draft(self, draft):
        self.drafts.pop(draft, None)


class MemoryState:
    """StateFile in memory; `saves` counts the writes."""

    def __init__(self, data: dict | None = None):
        self.data = data or {}
        self.saves = 0

    def load(self) -> dict:
        import copy

        return copy.deepcopy(self.data)

    def save(self, data: dict) -> None:
        import copy

        self.data = copy.deepcopy(data)
        self.saves += 1


class MemoryConfigFile:
    """config.toml as a dict. A write that makes it invalid raises and keeps the old one, like the real file."""

    def __init__(self, raw: dict | None = None):
        self.raw = raw if raw is not None else {}
        self.writes: list[tuple[str, str, object]] = []

    def read(self):
        from milo.config import Config

        return Config(self.raw)

    def write(self, section, key, value):
        from milo.config import Config

        raw = {**self.raw, section: {**self.raw.get(section, {}), key: value}}
        config = Config(raw)
        self.raw = raw
        self.writes.append((section, key, value))
        return config
