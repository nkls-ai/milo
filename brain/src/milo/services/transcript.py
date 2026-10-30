from __future__ import annotations

import logging
import uuid
from collections import deque

from milo.core.clock import SystemClock
from milo.core.events import Activity, EntryChanged, History, ReplyDelta
from milo.core.logtext import private
from milo.core.ports import Clock, EventSink, TranscriptStore
from milo.core.types import Emotion, EntryKind, Step, StepStatus, TranscriptEntry

log = logging.getLogger("milo.transcript")

RECENT = 50
MAX_STEPS = 80


class Transcript:
    """What was said and done, for the Milo window: user turns, Milo's replies as they stream, and tasks
    with their steps.

    The last RECENT entries live in memory, so sending history costs no file read. They are loaded once
    from the end of the store when first needed. An entry goes to the store when it is finished; one
    still running when the brain stops is lost.
    """

    def __init__(self, sink: EventSink, store: TranscriptStore, clock: Clock, *, recent: int = RECENT):
        self._sink = sink
        self._store = store
        self._clock = clock
        self._limit = recent
        self._recent: deque[TranscriptEntry] | None = None

    def history(self) -> History:
        return History([e.to_dict() for e in self._entries()])

    def user(self, text: str, via: str) -> str:
        """A user turn, `via` "voice" or "typed". Finished at once."""
        return self._add(EntryKind.USER, text, finished=True, via=via).id

    def reply_started(self, emotion: Emotion) -> str:
        return self._add(EntryKind.MILO, "", emotion=emotion, done=False).id

    def reply_delta(self, id: str, text: str) -> None:
        entry = self._find(id)
        if entry is None or not text:
            return
        entry.text += text
        self._sink.emit(ReplyDelta(id, text))

    def reply_finished(self, id: str, text: str, emotion: Emotion) -> None:
        entry = self._find(id)
        if entry is None:
            return
        entry.text, entry.emotion, entry.done = text.strip(), emotion, True
        self._finish(entry)

    def say(self, text: str, emotion: Emotion) -> None:
        """A whole Milo line at once, e.g. an error he shows."""
        self._add(EntryKind.MILO, text, finished=True, emotion=emotion)

    def task_started(self, description: str) -> str:
        return self._add(EntryKind.TASK, description, status=StepStatus.RUNNING).id

    def task_step(self, id: str, step: Step) -> None:
        entry = self._find(id)
        if entry is None:
            return
        for i, old in enumerate(entry.steps):
            if old.id == step.id:
                entry.steps[i] = step
                break
        else:
            if len(entry.steps) >= MAX_STEPS:
                return
            entry.steps.append(step)
        self._sink.emit(Activity(id, step.to_dict()))

    def task_finished(self, id: str, ok: bool, result: str) -> None:
        entry = self._find(id)
        if entry is None:
            return
        entry.status = StepStatus.DONE if ok else StepStatus.FAILED
        entry.result = result
        # A step the agent never reported back on didn't finish either.
        entry.steps = [s if s.status is not StepStatus.RUNNING else
                       Step(s.id, s.kind, s.title, s.detail, StepStatus.DONE if ok else StepStatus.FAILED)
                       for s in entry.steps]
        self._finish(entry)

    def _add(self, kind: EntryKind, text: str, *, finished: bool = False, **fields) -> TranscriptEntry:
        entry = TranscriptEntry(uuid.uuid4().hex[:12], self._clock.now().isoformat(timespec="seconds"), kind, text,
                                **fields)
        self._entries().append(entry)
        if finished:
            self._finish(entry)
        else:
            self._sink.emit(EntryChanged(entry.to_dict()))
        return entry

    def _finish(self, entry: TranscriptEntry) -> None:
        data = entry.to_dict()
        self._sink.emit(EntryChanged(data))
        try:
            self._store.append(data)
        except Exception:
            log.exception("could not save the transcript entry")

    def _find(self, id: str) -> TranscriptEntry | None:
        return next((e for e in reversed(self._entries()) if e.id == id), None)

    def _entries(self) -> deque[TranscriptEntry]:
        if self._recent is None:
            self._recent = deque(maxlen=self._limit)
            try:
                loaded = self._store.tail(self._limit)
            except Exception:
                log.exception("could not read the transcript")
                loaded = []
            # The store is in the order entries finished; a long task finishes after later turns.
            for data in sorted(loaded, key=lambda d: str(d.get("ts", ""))):
                try:
                    self._recent.append(TranscriptEntry.from_dict(data))
                except (KeyError, TypeError, ValueError):
                    log.warning("skipping a malformed transcript entry: %s", private(data))
        return self._recent


class _Nowhere:
    def emit(self, event) -> None:
        pass

    def append(self, entry: dict) -> None:
        pass

    def tail(self, n: int) -> list[dict]:
        return []


def unrecorded() -> Transcript:
    """A transcript that shows and keeps nothing, for services built without the Milo window."""
    return Transcript(_Nowhere(), _Nowhere(), SystemClock())
