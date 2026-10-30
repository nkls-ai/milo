"""Requests to the app that need an answer: a look at the screen, a computer-use action, a yes-or-no question.

Each goes out as an event with a fresh id; the app's reply command (look_result, hands_result,
confirm_result) resolves it through Brain. A request nobody answers in time fails, so a missing or
older app never leaves the brain waiting forever.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections.abc import Callable

from milo.core.events import ConfirmEnd, ConfirmRequest, Event, HandsRequest, LookRequest
from milo.core.ports import EventSink
from milo.core.types import HandsError, ScreenCapture

log = logging.getLogger("milo.app_bridge")

LOOK_TIMEOUT_S = 10.0
HANDS_TIMEOUT_S = 40.0  # an AppleScript may run up to 30 s in the app
CONFIRM_TIMEOUT_S = 60.0

NO_APP = "Milo's window isn't connected, so I can't reach the screen."
LOOK_TIMED_OUT = "Looking at the screen took too long."


class AppGone(Exception):
    """No app is connected, or it didn't answer in time."""


class AppBridge:
    def __init__(self, sink: EventSink, connected: Callable[[], bool] = lambda: True):
        self._sink = sink
        self._connected = connected
        self._ids = itertools.count(1)
        self._pending: dict[str, asyncio.Future] = {}

    async def ask(self, kind: str, make: Callable[[str], Event], timeout_s: float) -> object:
        """Emit make(id) and wait for answer(id, ...). Raises AppGone; CancelledError if cancel() hit it."""
        if not self._connected():
            raise AppGone(NO_APP)
        id = f"{kind}-{next(self._ids)}"
        future = asyncio.get_running_loop().create_future()
        self._pending[id] = future
        try:
            self._sink.emit(make(id))
            return await asyncio.wait_for(future, timeout_s)
        except TimeoutError:
            raise AppGone(f"no answer from the app within {timeout_s:.0f}s") from None
        finally:
            self._pending.pop(id, None)

    def answer(self, id: str, value: object) -> None:
        future = self._pending.get(id)
        if future is None or future.done():
            log.info("dropping an answer nobody waits for: %s", id)
            return
        future.set_result(value)

    def cancel(self, kind: str) -> None:
        """Every request of `kind` still waiting ends with CancelledError."""
        for id, future in list(self._pending.items()):
            if id.startswith(f"{kind}-") and not future.done():
                future.cancel()


class AppEyes:
    """ScreenEyes through the app."""

    def __init__(self, bridge: AppBridge, *, timeout_s: float = LOOK_TIMEOUT_S):
        self._bridge = bridge
        self._timeout_s = timeout_s

    async def look(self, mode: str = "window") -> ScreenCapture:
        try:
            capture = await self._bridge.ask("look", lambda id: LookRequest(id, mode), self._timeout_s)
        except AppGone as e:
            log.warning("look failed: %s", e)
            return ScreenCapture(error=NO_APP if str(e) == NO_APP else LOOK_TIMED_OUT)
        return capture if isinstance(capture, ScreenCapture) else ScreenCapture(error=LOOK_TIMED_OUT)


class AppHands:
    """The AppHands port through the app. A result is (ok, result, error) from hands_result."""

    def __init__(self, bridge: AppBridge, *, timeout_s: float = HANDS_TIMEOUT_S):
        self._bridge = bridge
        self._timeout_s = timeout_s

    async def act(self, tool: str, args: dict) -> dict:
        try:
            ok, result, error = await self._bridge.ask("hands", lambda id: HandsRequest(id, tool, args),
                                                       self._timeout_s)
        except AppGone as e:
            raise HandsError(str(e)) from None
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            raise HandsError("stopped") from None
        if not ok:
            raise HandsError(error or f"{tool} failed")
        return result

    def cancel(self) -> None:
        self._bridge.cancel("hands")


class BubbleConfirm:
    """ConfirmGate: a Yes/No question in Milo's bubble. No answer within `timeout_s` counts as no.

    Stands in for the shared approval flow until it exists; anything that asks goes through ConfirmGate.
    """

    def __init__(self, bridge: AppBridge, sink: EventSink, *, timeout_s: float = CONFIRM_TIMEOUT_S):
        self._bridge = bridge
        self._sink = sink
        self._timeout_s = timeout_s

    async def confirm(self, summary: str) -> bool:
        asked: list[str] = []

        def request(id: str) -> Event:
            asked.append(id)
            return ConfirmRequest(id, summary)

        try:
            yes = await self._bridge.ask("confirm", request, self._timeout_s)
        except AppGone as e:
            log.info("no answer to %r: %s", summary, e)
            yes = False
        finally:
            for id in asked:
                self._sink.emit(ConfirmEnd(id))
        log.info("asked %r: %s", summary, "yes" if yes else "no")
        return yes is True
