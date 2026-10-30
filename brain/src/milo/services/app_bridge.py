"""Requests to the app that need an answer: a look at the screen, a computer-use action, Calendar and Reminders work.

Each goes out as an event with a fresh id; the app's reply command (look_result, hands_result,
app_response) resolves it through Brain. A request nobody answers in time fails, so a missing or
older app never leaves the brain waiting forever. Yes-or-no questions are not here: they belong to
Approvals (services/approvals.py).
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections.abc import Callable
from typing import Any

from milo.core.events import AppRequest, AppResponse, Event, HandsRequest, LookRequest
from milo.core.ports import AppLink
from milo.core.types import BorrowNeeded, HandsError, ScreenCapture

log = logging.getLogger("milo.app_bridge")

LOOK_TIMEOUT_S = 10.0
HANDS_TIMEOUT_S = 40.0  # an AppleScript may run up to 30 s in the app
APP_TIMEOUT_S = 90.0  # the first call may wait for the user to answer a macOS permission prompt

NO_APP = "Milo's window isn't connected, so I can't reach the screen."
LOOK_TIMED_OUT = "Looking at the screen took too long."
NOT_RUNNING = "Milo's app isn't running, so I can't reach your calendar or reminders."
APP_LEFT = "Milo's app closed before it answered."
APP_LEFT_WORDS = "Milo's app closed before it was done. Try again in a moment."


class AppGone(Exception):
    """No app is connected, or it didn't answer in time."""


class AppError(Exception):
    """The app couldn't do it. The message is plain language for the user."""


class AppBridge:
    """Requests waiting for the app, each under an id like `look-1`, `hands-2` or `app-3`.

    Each request goes to one app through `link` (AppLink), and waits on that app alone: if it hangs up,
    `app_gone` fails what it still owed at once instead of after the timeout. `ask` is the general form;
    `call` runs one Calendar or Reminders op (`app_request`) and turns failures into AppError with plain
    words. `timeout_s` is how long `call` waits for its `app_response`.
    """

    def __init__(self, link: AppLink, *, timeout_s: float = APP_TIMEOUT_S):
        self._link = link
        self._timeout_s = timeout_s
        self._ids = itertools.count(1)
        self._pending: dict[str, tuple[asyncio.Future, int]] = {}

    async def ask(self, kind: str, make: Callable[[str], Event], timeout_s: float) -> object:
        """Send make(id) to the app and wait for answer(id, ...). Raises AppGone (no app, it left, or no answer
        in time); CancelledError if cancel() hit it."""
        id = f"{kind}-{next(self._ids)}"
        connection = self._link.request(make(id))
        if connection is None:
            raise AppGone(NO_APP)
        future = asyncio.get_running_loop().create_future()
        self._pending[id] = (future, connection)
        try:
            return await asyncio.wait_for(future, timeout_s)
        except TimeoutError:
            raise AppGone(f"no answer from the app within {timeout_s:.0f}s") from None
        finally:
            self._pending.pop(id, None)

    def answer(self, id: str, value: object) -> None:
        future = self._pending.get(id, (None, 0))[0]
        if future is None or future.done():
            log.info("dropping an answer nobody waits for: %s", id)
            return
        future.set_result(value)

    def cancel(self, kind: str) -> None:
        """Every request of `kind` still waiting ends with CancelledError."""
        for id, (future, _) in list(self._pending.items()):
            if id.startswith(f"{kind}-") and not future.done():
                future.cancel()

    def app_gone(self, connection: int) -> None:
        """The app on `connection` hung up: what it still owed fails now with AppGone."""
        for id, (future, owner) in list(self._pending.items()):
            if owner == connection and not future.done():
                log.info("the app left before answering %s", id)
                future.set_exception(AppGone(APP_LEFT))

    async def call(self, op: str, args: dict) -> Any:
        """The app's result for app_request `op` (Calendar and Reminders through EventKit). Raises AppError."""
        try:
            response = await self.ask("app", lambda id: AppRequest(id, op, args), self._timeout_s)
        except AppGone as e:
            if str(e) == NO_APP:
                raise AppError(NOT_RUNNING) from None
            log.warning("the app didn't answer %s: %s", op, e)
            raise AppError("Milo's app didn't answer in time." if str(e) != APP_LEFT else APP_LEFT_WORDS) from None
        if not isinstance(response, AppResponse) or not response.ok:
            raise AppError(getattr(response, "error", "") or "Milo's app couldn't do that.")
        return response.result

    def resolve(self, response: AppResponse) -> None:
        self.answer(response.id, response)


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
            return ScreenCapture(error=NO_APP if str(e) in (NO_APP, APP_LEFT) else LOOK_TIMED_OUT)
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
            if isinstance(result, dict) and isinstance(result.get("borrow"), str):
                raise BorrowNeeded(result["borrow"], error)
            raise HandsError(error or f"{tool} failed")
        return result

    def cancel(self) -> None:
        self._bridge.cancel("hands")
