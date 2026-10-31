"""The connections for the brain's own use: the talker's quick actions, the <today> block, the morning brief and
meeting notes (ADR 0029, 0034).

They are the same Connections ports the worker's tools use. Where the app holds a connection (EventKit for Calendar
and Reminders, the system's player) the brain reaches it through AppBridge, about 100 ms and no tokens. Where the
brain has a connection of its own (the fake ones over world.json, for tests, the eval and trying Milo out) that one
runs, on a thread, so a quick action never writes to the real calendar while the worker plays with made-up data.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Awaitable, Callable
from typing import Any

from milo.core.app_connections import AppCalendar, AppContacts, AppPlayer, AppReminders
from milo.core.ports import Connections
from milo.core.types import ToolError

BridgeCall = Callable[[str, dict], Awaitable[Any]]
"""AppBridge.call."""


async def reach(method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call a connection's method from the event loop: awaited when it reaches the app (`awaits`), else on a thread,
    since it blocks. Raises ToolError with plain words."""
    if getattr(getattr(method, "__self__", None), "awaits", False):
        return await method(*args, **kwargs)
    return await asyncio.to_thread(method, *args, **kwargs)


def in_brain(connections: Connections, call: BridgeCall, *, music: bool) -> Connections:
    """`connections` as the brain uses them. A Calendar or Reminders that goes through the brain to the app
    (`approves_itself`) is reached on the AppBridge directly. Without a player of its own the system's player goes
    through the app, when `music` is switched on. The address book held by the app is reached the same way."""

    async def app(op: str, args: dict) -> Any:
        try:
            return await call(op, args)
        except Exception as e:  # AppError and the like: plain words already
            raise ToolError(str(e) or "Milo's app couldn't do that.") from None

    def via_app(connection: Any) -> bool:
        return getattr(connection, "approves_itself", False)

    return dataclasses.replace(
        connections,
        calendar=AppCalendar(app) if via_app(connections.calendar) else connections.calendar,
        reminders=AppReminders(app) if via_app(connections.reminders) else connections.reminders,
        music=connections.music or (AppPlayer(app) if music else None),
        contacts=AppContacts(app) if via_app(connections.contacts) else connections.contacts)
