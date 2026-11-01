"""Calendar and to-dos through CalDAV on every desktop.

Opt-in credentials stay in a private secret file. IDs contain calendar names
and UIDs, never arbitrary remote URLs. Per-call clients avoid sharing network
sessions across executor threads. Recurrence changes save a single override;
they never replace or delete the recurring series.
"""
from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from milo.core.ports import Connections, ConnectionIdentity
from milo.core.registry import CONNECTIONS, AdapterContext, ConfigError, options_from
from milo.core.secrets import SecretError, read_secret
from milo.core.times import local
from milo.core.types import ToolError


def _value(component, name: str, default=None):
    value = component.get(name, default)
    return value.dt if hasattr(value, "dt") else value


def _datetime(value) -> datetime:
    return local(value) if isinstance(value, datetime) else datetime.combine(value, time.min)


def _iso(value) -> str:
    return _datetime(value).isoformat(timespec="minutes") if value is not None else ""


def _aware(value: datetime) -> datetime:
    return value.astimezone()


def _id(calendar, component, kind: str) -> str:
    raw = json.dumps([kind, str(calendar.name), str(component["UID"])]).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _identity(identity: str, kind: str) -> tuple[str, str]:
    try:
        stored_kind, calendar, uid = json.loads(base64.b64decode(identity, altchars=b"-_", validate=True))
        if stored_kind != kind or not isinstance(calendar, str) or not isinstance(uid, str) or not uid:
            raise ValueError
        return calendar, uid
    except (ValueError, TypeError, UnicodeError):
        raise ToolError("That CalDAV item ID is invalid or belongs to a different kind of item.") from None


def _set(component, **properties) -> None:
    for name, value in properties.items():
        name = name.replace("_", "-").upper()
        component.pop(name, None)
        if value is not None:
            component.add(name, value)


def _matches(query: str, *values) -> bool:
    text = " ".join(str(value or "") for value in values).casefold()
    return all(word in text for word in query.casefold().split())


def _calendars(principal, kind: str, name: str = "") -> list:
    calendars = [cal for cal in principal.calendars()
                 if kind in cal.get_supported_components() and (not name or str(cal.name).casefold() == name.casefold())]
    if name and len(calendars) != 1:
        raise ToolError(f"Choose a unique CalDAV calendar named “{name}”; it is missing or ambiguous.")
    return calendars


def _calendar(principal, kind: str, name: str = ""):
    calendars = _calendars(principal, kind, name)
    if len(calendars) != 1:
        raise ToolError("Choose the CalDAV calendar or task list by name in settings; there isn't exactly one.")
    return calendars[0]


@dataclass(frozen=True)
class CalDAVOptions:
    url: str = ""
    username: str = ""
    key_ref: str = "caldav.key"
    calendar: str = ""
    tasks: str = ""
    timeout_s: float = 20.0

    def __post_init__(self):
        parts = urlsplit(self.url)
        local_http = parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")
        if not parts.hostname or (parts.scheme != "https" and not local_http) or parts.username or parts.password:
            raise ConfigError("[connections.caldav] url must be HTTPS without credentials (HTTP is allowed on loopback)")
        if not self.key_ref or Path(self.key_ref).name != self.key_ref or "/" in self.key_ref or "\\" in self.key_ref:
            raise ConfigError("[connections.caldav] key_ref must be one filename under secrets")
        if not isinstance(self.timeout_s, int | float) or not 0 < self.timeout_s <= 120:
            raise ConfigError("[connections.caldav] timeout_s must be between 0 and 120")


class CalDAVGateway:
    def __init__(self, options: CalDAVOptions, home: Path):
        self._options, self._home = options, home

    def __call__(self, action: Callable[[Any], Any]) -> Any:
        try:
            import caldav
            from caldav.lib.error import DAVError
            from caldav.lib.http_sync import requests as http
        except ImportError:
            raise ToolError("CalDAV needs the desktop extra: uv sync --extra desktop") from None
        options = self._options
        try:
            password = read_secret(self._home / "secrets" / options.key_ref, "The CalDAV password") \
                if options.username else None
            with caldav.DAVClient(url=options.url, username=options.username or None, password=password,
                                  timeout=options.timeout_s) as client:
                return action(client.principal())
        except SecretError as e:
            raise ToolError(str(e)) from None
        except (DAVError, http.exceptions.RequestException):
            raise ToolError("I couldn't reach that CalDAV item, or it changed while I was editing it. "
                            "Check your calendar connection and try reading it again.") from None


class CalDAVCalendar:
    def __init__(self, call: Callable, calendar: str = ""):
        self._call, self._name = call, calendar
        self.identity = ConnectionIdentity(calendar or "Calendar")

    @staticmethod
    def _record(calendar, obj):
        comp = obj.get_icalendar_component()
        start, end = _value(comp, "DTSTART"), _value(comp, "DTEND")
        if end is None:
            end = start + (_value(comp, "DURATION") or timedelta(days=1 if isinstance(start, date) and
                                                                           not isinstance(start, datetime) else 0))
        return {"id": _id(calendar, comp, "event"), "title": str(comp.get("SUMMARY", "")),
                "start": _iso(start), "end": _iso(end), "location": str(comp.get("LOCATION", "")),
                "notes": str(comp.get("DESCRIPTION", "")), "calendar": str(calendar.name),
                "all_day": isinstance(start, date) and not isinstance(start, datetime),
                # CalDAV discovery does not establish who authored a shared resource.
                "shared": True}

    def events(self, start: datetime, end: datetime, query: str = "") -> list[dict]:
        if end <= start:
            raise ToolError("The calendar's end must be after its start.")

        def run(principal):
            result = []
            for cal in _calendars(principal, "VEVENT", self._name):
                for obj in cal.search(event=True, start=_aware(start), end=_aware(end), expand=True):
                    if str(obj.get_icalendar_component().get("STATUS", "")) == "CANCELLED":
                        continue
                    record = self._record(cal, obj)
                    if _matches(query, record["title"], record["notes"], record["location"]):
                        result.append(record)
            return sorted(result, key=lambda event: event["start"])
        return self._call(run)

    def add_event(self, title: str, start: datetime, end: datetime, location: str = "", notes: str = "",
                  calendar: str = "", all_day: bool = False) -> dict:
        if end <= start:
            raise ToolError("The event's end must be after its start.")

        def run(principal):
            cal = _calendar(principal, "VEVENT", calendar or self._name)
            obj = cal.add_event(uid=uuid.uuid4().hex, summary=title, description=notes, location=location,
                                dtstart=start.date() if all_day else _aware(start),
                                dtend=end.date() if all_day else _aware(end))
            return self._record(cal, obj)
        return self._call(run)

    @staticmethod
    def _find(principal, identity: str, at: datetime | None, *, changing: bool = False):
        name, uid = _identity(identity, "event")
        cal = _calendar(principal, "VEVENT", name)
        obj = cal.get_event_by_uid(uid)
        comp = obj.get_icalendar_component()
        if "RRULE" in comp or "RDATE" in comp:
            if at is None:
                if changing:
                    raise ToolError("Name the start time of that occurrence; I won't change a whole repeating series.")
            else:
                for occurrence in cal.search(event=True, uid=uid, start=_aware(at - timedelta(days=1)),
                                             end=_aware(at + timedelta(days=1)), expand=True):
                    part = occurrence.get_icalendar_component()
                    original = _value(part, "RECURRENCE-ID", _value(part, "DTSTART"))
                    if _datetime(original) == at or _datetime(_value(part, "DTSTART")) == at:
                        if "RECURRENCE-ID" not in part:
                            raise ToolError("The calendar didn't identify that occurrence safely. Change it in your calendar app.")
                        return cal, occurrence
                raise ToolError("I couldn't find that occurrence. Read the event again before changing it.")
        return cal, obj

    def event(self, id: str, at: datetime | None = None) -> dict:
        return self._call(lambda principal: self._record(*self._find(principal, id, at)))

    def move_event(self, id: str, at: datetime | None, start: datetime, end: datetime) -> dict:
        if end <= start:
            raise ToolError("The event's end must be after its start.")

        def run(principal):
            cal, obj = self._find(principal, id, at, changing=True)
            all_day = self._record(cal, obj)["all_day"]
            with obj.edit_icalendar_component() as comp:
                _set(comp, dtstart=start.date() if all_day else _aware(start),
                     dtend=end.date() if all_day else _aware(end), duration=None)
            obj.save(only_this_recurrence=True)
            return self._record(cal, obj)
        return self._call(run)

    def delete_event(self, id: str, at: datetime | None = None) -> dict:
        def run(principal):
            cal, obj = self._find(principal, id, at, changing=True)
            record = self._record(cal, obj)
            if "RECURRENCE-ID" in obj.get_icalendar_component():
                with obj.edit_icalendar_component() as comp:
                    _set(comp, status="CANCELLED")
                obj.save(only_this_recurrence=True)
            else:
                obj.delete(if_match=True)
            return record
        return self._call(run)


class CalDAVReminders:
    def __init__(self, call: Callable, tasks: str = ""):
        self._call, self._name = call, tasks
        self.identity = ConnectionIdentity(tasks or "To-dos")

    @staticmethod
    def _record(calendar, obj):
        comp = obj.get_icalendar_component()
        return {"id": _id(calendar, comp, "task"), "title": str(comp.get("SUMMARY", "")),
                "notes": str(comp.get("DESCRIPTION", "")), "due": _iso(_value(comp, "DUE")),
                "done": str(comp.get("STATUS", "")) == "COMPLETED", "list": str(calendar.name),
                "shared": True}

    def list(self, query: str = "", include_done: bool = False) -> list[dict]:
        def run(principal):
            result = []
            for cal in _calendars(principal, "VTODO", self._name):
                for obj in cal.search(todo=True, include_completed=include_done):
                    record = self._record(cal, obj)
                    if (include_done or not record["done"]) and _matches(query, record["title"], record["notes"]):
                        result.append(record)
            return result
        return self._call(run)

    def add(self, title: str, due: datetime | None = None, notes: str = "", list_name: str = "") -> dict:
        def run(principal):
            cal = _calendar(principal, "VTODO", list_name or self._name)
            obj = cal.add_todo(uid=uuid.uuid4().hex, summary=title, description=notes,
                               **({"due": _aware(due)} if due is not None else {}))
            return self._record(cal, obj)
        return self._call(run)

    @staticmethod
    def _find(principal, identity: str):
        name, uid = _identity(identity, "task")
        cal = _calendar(principal, "VTODO", name)
        obj = cal.get_todo_by_uid(uid)
        if "RRULE" in obj.get_icalendar_component() or "RDATE" in obj.get_icalendar_component():
            raise ToolError("Change that recurring task in your calendar app; I won't alter its whole series.")
        return cal, obj

    def complete(self, id: str, done: bool = True) -> dict:
        def run(principal):
            cal, obj = self._find(principal, id)
            with obj.edit_icalendar_component() as comp:
                _set(comp, status="COMPLETED" if done else "NEEDS-ACTION", percent_complete=100 if done else 0,
                     completed=datetime.now().astimezone() if done else None)
            obj.save()
            return self._record(cal, obj)
        return self._call(run)

    def delete(self, id: str) -> dict:
        def run(principal):
            cal, obj = self._find(principal, id)
            record = self._record(cal, obj)
            obj.delete(if_match=True)
            return record
        return self._call(run)


@CONNECTIONS.register("caldav")
def _caldav(options: Mapping[str, Any], ctx: AdapterContext) -> Connections:
    o = options_from(CalDAVOptions, options, "connections.caldav")
    call = CalDAVGateway(o, ctx.home)
    return Connections(calendar=CalDAVCalendar(call, o.calendar), reminders=CalDAVReminders(call, o.tasks))
