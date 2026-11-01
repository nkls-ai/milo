"""Calendar, Reminders, the music player, the brightness keys and the address book held by Milo's app, as
Connections ports (ADR 0029, 0034, 0036, 0039).

The app answers `app_request` ops (`calendar.events`, `reminders.add`, `media.state`, ...; protocol/messages.json).
These classes turn the ports' calls into those ops over any `call(op, args)`. The worker's tools give them one that
blocks (adapters/connect, through the brain's tool socket); the brain gives them one that awaits AppBridge. With an
awaiting call every method returns an awaitable and `awaits` is True: `services.connections.reach` calls either kind.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .ports import ConnectionIdentity

AppCall = Callable[[str, dict], Any]
"""Runs one app op and returns its result, or an awaitable of it. Raises ToolError with plain words."""


def _iso(dt: datetime | None) -> str:
    return dt.isoformat(timespec="minutes") if dt is not None else ""


def _then(result: Any, f: Callable[[Any], Any]) -> Any:
    """`f` of the call's result, awaiting it first when it is awaitable."""
    if inspect.isawaitable(result):
        async def done() -> Any:
            return f(await result)
        return done()
    return f(result)


class _App:
    approves_itself = True
    """The app's side applies no action level: the brain does, before it sends the op."""

    def __init__(self, call: AppCall, identity: ConnectionIdentity | None = None):
        self._call = call
        self.identity = identity
        self.awaits = inspect.iscoroutinefunction(call)


class AppCalendar(_App):
    def events(self, start: datetime, end: datetime, query: str = "") -> list[dict]:
        return self._call("calendar.events", {"start": _iso(start), "end": _iso(end), "query": query})

    def add_event(self, title: str, start: datetime, end: datetime, location: str = "", notes: str = "",
                  calendar: str = "", all_day: bool = False) -> dict:
        return self._call("calendar.add_event", {"title": title, "start": _iso(start), "end": _iso(end),
                                                 "location": location, "notes": notes, "calendar": calendar,
                                                 **({"all_day": True} if all_day else {})})

    def event(self, id: str, at: datetime | None = None) -> dict:
        return self._call("calendar.event", {"id": id, "at": _iso(at)})

    def move_event(self, id: str, at: datetime | None, start: datetime, end: datetime) -> dict:
        return self._call("calendar.update_event", {"id": id, "at": _iso(at), "start": _iso(start), "end": _iso(end)})

    def delete_event(self, id: str, at: datetime | None = None) -> dict:
        return self._call("calendar.delete_event", {"id": id, "at": _iso(at)})


class AppReminders(_App):
    def list(self, query: str = "", include_done: bool = False) -> list[dict]:
        return self._call("reminders.list", {"query": query, "include_done": include_done})

    def add(self, title: str, due: datetime | None = None, notes: str = "", list_name: str = "") -> dict:
        return self._call("reminders.add", {"title": title, "due": _iso(due), "notes": notes, "list": list_name})

    def complete(self, id: str, done: bool = True) -> dict:
        return self._call("reminders.complete", {"id": id, **({} if done else {"done": False})})

    def delete(self, id: str) -> dict:
        return self._call("reminders.delete", {"id": id})


class AppContacts(_App):
    """The address book, as the app reads it (`contacts.find`, ADR 0039). Read only."""

    def find(self, name: str, relation: str = "") -> list[dict]:
        return self._call("contacts.find", {"name": name, **({"relation": relation} if relation else {})})


class AppPlayer(_App):
    """The system's player, as the app sees it. Its state is "" when the system doesn't say in time."""

    def state(self) -> str:
        return _then(self._call("media.state", {}), _state)

    def control(self, do: str) -> str:
        return _then(self._call(f"media.{do}", {}), _state)


def _state(result: Any) -> str:
    return str((result or {}).get("state", ""))


class AppBrightness(_App):
    """The screen's brightness, through the app's brightness keys (ADR 0036)."""

    def change(self, do: str, steps: int = 1) -> dict:
        return self._call(f"media.brightness_{do}", {"steps": steps})
