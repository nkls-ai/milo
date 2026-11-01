"""Small Qt pieces every view model shares: a scheduler on the Qt event loop and read-only properties."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Property, QTimer


class _Timer:
    def __init__(self, seconds: float, work: Callable[[], None]):
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(work)
        self._timer.start(max(0, int(seconds * 1000)))

    def cancel(self) -> None:
        self._timer.stop()


class QtScheduler:
    """presentation.clock.Scheduler on Qt timers. Call from the GUI thread."""

    def after(self, seconds: float, work: Callable[[], None]) -> _Timer:
        return _Timer(seconds, work)


def readonly(kind, getter: Callable, notify) -> Property:
    """A property QML reads and is told about through `notify`."""
    return Property(kind, getter, notify=notify)


def field(kind, name: str, notify) -> Property:
    """A property read from `self._values[name]`."""
    return Property(kind, lambda self: self._values[name], notify=notify)
