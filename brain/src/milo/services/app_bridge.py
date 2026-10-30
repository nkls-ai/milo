from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from typing import Any

from milo.core.events import AppRequest, AppResponse
from milo.core.ports import EventSink

log = logging.getLogger("milo.app_bridge")

DEFAULT_TIMEOUT_S = 90.0  # the first call may wait for the user to answer a macOS permission prompt
NOT_RUNNING = "Milo's app isn't running, so I can't reach your calendar or reminders."


class AppError(Exception):
    """The app couldn't do it. The message is plain language for the user."""


class AppBridge:
    """Asks Milo.app for work only it has permission for: Calendar and Reminders through EventKit.

    The request goes out as an `app_request` event over the app's connection, and `resolve()` gets the
    matching `app_response` command from Brain.
    """

    def __init__(self, sink: EventSink, connected: Callable[[], bool] = lambda: True, *,
                 timeout_s: float = DEFAULT_TIMEOUT_S):
        self._sink = sink
        self._connected = connected
        self._timeout_s = timeout_s
        self._waiting: dict[str, asyncio.Future[AppResponse]] = {}

    async def call(self, op: str, args: dict) -> Any:
        """The app's result for `op`. Raises AppError."""
        if not self._connected():
            raise AppError(NOT_RUNNING)
        id = uuid.uuid4().hex[:12]
        future: asyncio.Future[AppResponse] = asyncio.get_running_loop().create_future()
        self._waiting[id] = future
        try:
            self._sink.emit(AppRequest(id, op, args))
            response = await asyncio.wait_for(future, self._timeout_s)
        except TimeoutError:
            log.warning("the app didn't answer %s in %.0fs", op, self._timeout_s)
            raise AppError("Milo's app didn't answer in time.") from None
        finally:
            self._waiting.pop(id, None)
        if not response.ok:
            raise AppError(response.error or "Milo's app couldn't do that.")
        return response.result

    def resolve(self, response: AppResponse) -> None:
        future = self._waiting.get(response.id)
        if future is None or future.done():
            log.warning("dropping an app response nobody waits for")
            return
        future.set_result(response)
