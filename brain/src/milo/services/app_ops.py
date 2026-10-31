"""Calendar, Reminders and the music player by op name, the way the app answers `app_request` (ADR 0029).

The live model's quick actions and the Today block reach them through one call, `await ops(name, args)`. Where the app
holds the connection (EventKit for Calendar and Reminders, the system's player for media) the op goes to the app
through AppBridge, about 100 ms and no tokens. Where the brain has a connection of its own (the fake ones over
world.json, for tests, the eval and trying Milo out) the same op runs on that connection, on a thread, so a quick
action never writes to the real calendar while the worker plays with made-up data.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Collection
from datetime import datetime
from typing import Any

from milo.core.ports import Connections
from milo.core.types import ToolError

AppCall = Callable[[str, dict], Awaitable[Any]]

OPS = {
    "calendar": ("calendar.events", "calendar.add_event", "calendar.event", "calendar.update_event",
                 "calendar.delete_event"),
    "reminders": ("reminders.list", "reminders.add", "reminders.delete"),
    "media": ("media.state", "media.play", "media.pause", "media.next", "media.previous"),
}
"""The ops, by the connection that answers them."""


class OpsError(Exception):
    """The op can't be done: switched off, no app, or the app or connection said no. Plain words for the user."""


def _time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        raise OpsError(f"{text!r} isn't a time like 2026-11-05T15:00") from None


class AppOps:
    """`via_app`: the connections ("calendar", "reminders", "media") the app answers for. The rest run on
    `connections` (calendar, reminders, music), if it has them. `enabled`: the ones switched on in config.toml."""

    def __init__(self, connections: Connections | None = None, call: AppCall | None = None, *,
                 via_app: Collection[str] = (), enabled: Collection[str] = ("calendar", "reminders", "media")):
        self._connections = connections or Connections()
        self._call = call
        self._via_app = frozenset(via_app)
        self._enabled = frozenset(enabled)

    def has(self, connection: str) -> bool:
        if connection not in self._enabled:
            return False
        if connection in self._via_app:
            return self._call is not None
        return getattr(self._connections, "music" if connection == "media" else connection) is not None

    async def __call__(self, op: str, args: dict) -> Any:
        connection = next((c for c, ops in OPS.items() if op in ops), None)
        if connection is None:
            raise OpsError(f"unknown op {op!r}")
        if not self.has(connection):
            raise OpsError(f"The {connection} connection is switched off in Milo's settings.")
        if connection in self._via_app:
            try:
                return await self._call(op, args)
            except Exception as e:  # AppError and the like: plain words already
                raise OpsError(str(e) or "Milo's app couldn't do that.") from None
        try:
            return await asyncio.to_thread(self._local, op, args)
        except ToolError as e:
            raise OpsError(str(e)) from None

    def _local(self, op: str, a: dict) -> Any:
        c = self._connections
        match op:
            case "calendar.events":
                return c.calendar.events(_time(a.get("start")), _time(a.get("end")), str(a.get("query") or ""))
            case "calendar.add_event":
                return c.calendar.add_event(str(a["title"]), _time(a["start"]), _time(a["end"]),
                                            str(a.get("location") or ""), str(a.get("notes") or ""),
                                            str(a.get("calendar") or ""), all_day=bool(a.get("all_day")))
            case "calendar.event":
                return c.calendar.event(str(a["id"]), _time(a.get("at")))
            case "calendar.update_event":
                return c.calendar.move_event(str(a["id"]), _time(a.get("at")), _time(a["start"]), _time(a["end"]))
            case "calendar.delete_event":
                return c.calendar.delete_event(str(a["id"]), _time(a.get("at")))
            case "reminders.list":
                return c.reminders.list(str(a.get("query") or ""), bool(a.get("include_done")))
            case "reminders.add":
                return c.reminders.add(str(a["title"]), _time(a.get("due")), str(a.get("notes") or ""),
                                       str(a.get("list") or ""))
            case "reminders.delete":
                return c.reminders.delete(str(a["id"]))
            case "media.state":
                return {"state": c.music.state()}
            case _:
                return {"state": c.music.control(op.split(".", 1)[1])}
