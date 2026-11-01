"""Time for the presentation models: a scheduler they ask for later work, so tests can step it by hand."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Protocol


class Scheduled(Protocol):
    def cancel(self) -> None: ...


class Scheduler(Protocol):
    def after(self, seconds: float, work: Callable[[], None]) -> Scheduled: ...


Clock = Callable[[], float]
monotonic: Clock = time.monotonic


@dataclass
class _Task:
    due: float
    work: Callable[[], None]
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


@dataclass
class ManualScheduler:
    """Runs work only when the test advances it (MiloKit's ManualScheduler). Its clock is `now`."""
    now: float = 0.0
    _tasks: list[_Task] = field(default_factory=list)

    def clock(self) -> float:
        return self.now

    def after(self, seconds: float, work: Callable[[], None]) -> _Task:
        task = _Task(self.now + max(0.0, seconds), work)
        self._tasks.append(task)
        return task

    def advance(self, seconds: float) -> None:
        end = self.now + seconds
        while True:
            due = sorted((t for t in self._tasks if not t.cancelled and t.due <= end), key=lambda t: t.due)
            if not due:
                break
            task = due[0]
            self._tasks.remove(task)
            self.now = max(self.now, task.due)
            task.work()
        self._tasks = [t for t in self._tasks if not t.cancelled]
        self.now = end
