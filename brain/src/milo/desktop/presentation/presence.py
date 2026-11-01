"""Whether Milo is on screen (MiloKit/Presence.swift, the deciding half; the overlay animates the way off and back).

With nothing going on for `hide_after` seconds he leaves; anything that needs him brings him straight back: a key,
a word from him, a question, work, a meeting, the tray. The pointer resting on him keeps him a little longer.
"""
from __future__ import annotations

from typing import Callable

from .clock import Scheduled, Scheduler

DEFAULT_HIDE_AFTER = 15.0  # `[ui] hide_after_s` until the brain says otherwise
POINTER_WAIT = 3.0


def hide_after(value) -> float | None:
    """Seconds from `[ui] hide_after_s`: None (0) keeps him on screen; no number leaves the default."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return DEFAULT_HIDE_AFTER
    return seconds if seconds > 0 else None


class Presence:
    def __init__(self, scheduler: Scheduler, needed: Callable[[], bool],
                 on_change: Callable[[bool], None] = lambda shown: None):
        self.scheduler, self._needed, self.on_change = scheduler, needed, on_change
        self.shown = True
        self.held = False  # the user drags him: he stays put
        self.pointing: Callable[[], bool] = lambda: False
        self._hide_after: float | None = DEFAULT_HIDE_AFTER
        self._countdown: Scheduled | None = None
        self._was_needed = False
        self.check()

    @property
    def hide_after(self) -> float | None:
        return self._hide_after

    @hide_after.setter
    def hide_after(self, value: float | None) -> None:
        if value == self._hide_after:
            return
        self._hide_after = value
        if value is None:
            self._stop()
            self._set(True)
        elif self.shown and not self.needed:
            self._count_down()

    @property
    def needed(self) -> bool:
        return self.held or self._needed()

    def summon(self) -> None:
        """The user asked for him: back now, and the wait starts over."""
        self._set(True)
        if not self.needed:
            self._count_down()

    def dismiss(self) -> None:
        """"Hide Milo": off now, unless something needs him."""
        if not self.needed:
            self._stop()
            self._set(False)

    def check(self) -> None:
        """Look again after the model changed."""
        need = self.needed
        was, self._was_needed = self._was_needed, need
        if need:
            self._stop()
            self._set(True)
        elif self.shown and (was or self._countdown is None):
            # The wait starts when the last thing that needed him is over, or once he is back.
            self._count_down()

    def _count_down(self, wait: float | None = None) -> None:
        self._stop()
        if self._hide_after is None:
            return

        def done():
            self._countdown = None
            if self.needed:
                return
            if self.pointing():
                return self._count_down(POINTER_WAIT)
            self._set(False)
        self._countdown = self.scheduler.after(self._hide_after if wait is None else wait, done)

    def _stop(self) -> None:
        if self._countdown is not None:
            self._countdown.cancel()
            self._countdown = None

    def _set(self, shown: bool) -> None:
        if shown != self.shown:
            self.shown = shown
            self.on_change(shown)
