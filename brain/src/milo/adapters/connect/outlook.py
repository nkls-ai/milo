"""Classic Outlook connections through its supported COM object model.

Opt in with [connections] use = "outlook". New Outlook has no COM object
model. Every call creates its COM apartment on the calling thread; no COM
object crosses the brain's executors. Mail is saved and displayed as a draft,
never sent. Recurring edits require an occurrence time and never edit a series.
"""
from __future__ import annotations

import base64
import json
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from milo.core.ports import Connections, ConnectionIdentity
from milo.core.registry import CONNECTIONS, AdapterContext, options_from
from milo.core.types import ToolError, AppRef

CALENDAR, TASKS, INBOX, SENT, NOTES = 9, 13, 6, 5, 12
_CLASSES = {"event": 26, "task": 48, "mail": 43, "note": 44}
MAX_ITEMS = 2000


def _iso(value) -> str:
    # Outlook's Start/End/DueDate properties are local wall-clock values.
    if value is None:
        return ""
    if value.year >= 4500:  # Outlook's sentinel for an unset task due date
        return ""
    return value.replace(tzinfo=None).isoformat(timespec="minutes")


def _date(value: datetime) -> str:
    """Use Windows' short date/time format, as Outlook's Jet Restrict requires."""
    import win32api
    # LOCALE_USER_DEFAULT, DATE_SHORTDATE and TIME_NOSECONDS (WinNls.h).
    return (win32api.GetDateFormat(0x0400, 0x1, value) + " " +
            win32api.GetTimeFormat(0x0400, 0x2, value))


def _id(item, kind: str) -> str:
    raw = json.dumps([kind, str(item.EntryID), str(item.Parent.StoreID)]).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _item(namespace, identity: str, kind: str):
    try:
        stored_kind, entry, store = json.loads(base64.b64decode(identity, altchars=b"-_", validate=True))
        if stored_kind != kind or not isinstance(entry, str) or not isinstance(store, str):
            raise ValueError
        item = namespace.GetItemFromID(entry, store)
        if item.Class != _CLASSES[kind]:
            raise ValueError
        return item
    except (ValueError, TypeError, UnicodeError):
        raise ToolError("That Outlook item ID is invalid or belongs to a different kind of item.") from None


def _folder(namespace, number: int, name: str = ""):
    folder = namespace.GetDefaultFolder(number)
    if not name or folder.Name.casefold() == name.casefold():
        return folder
    # Only the selected default folder's children: never guess another account.
    for child in folder.Folders:
        if child.Name.casefold() == name.casefold():
            return child
    raise ToolError(f"There's no Outlook folder named “{name}” under {folder.Name}.")


def _matches(query: str, *values: Any) -> bool:
    text = " ".join(str(value or "") for value in values).casefold()
    return all(word in text for word in query.casefold().split())


class OutlookGateway:
    """The one boundary for COM initialization, errors and serialized mutations."""

    def __init__(self):
        self._lock = threading.RLock()

    def __call__(self, action: Callable[[Any], Any]) -> Any:
        try:
            import pythoncom
            import pywintypes
            import win32com.client
        except ImportError:
            raise ToolError("Outlook connections need Windows and Classic Outlook, with a signed-in profile.") from None
        with self._lock:
            pythoncom.CoInitialize()
            app = None
            try:
                app = win32com.client.Dispatch("Outlook.Application")
                return action(app)
            except pywintypes.com_error:
                raise ToolError("I couldn't reach that Outlook item. Open Classic Outlook with your profile and "
                                "check that the item still exists; New Outlook does not support these connections.") from None
            finally:
                app = None
                pythoncom.CoUninitialize()


class OutlookCalendar:
    controls = "Microsoft Outlook"
    identity = ConnectionIdentity("Outlook", AppRef("Microsoft Outlook", "outlook.exe"))

    def __init__(self, call: Callable = None, folder: str = "", date_format: Callable = _date):
        self._call, self._name, self._date = call or OutlookGateway(), folder, date_format

    @staticmethod
    def _record(item) -> dict:
        return {"id": _id(item, "event"), "title": str(item.Subject or ""), "start": _iso(item.Start),
                "end": _iso(item.End), "location": str(item.Location or ""), "notes": str(item.Body or ""),
                "calendar": str(item.Parent.Name), "all_day": bool(item.AllDayEvent),
                "shared": True}

    def events(self, start: datetime, end: datetime, query: str = "") -> list[dict]:
        if end <= start:
            raise ToolError("The calendar's end must be after its start.")

        def run(app):
            items = _folder(app.GetNamespace("MAPI"), CALENDAR, self._name).Items
            items.Sort("[Start]")
            items.IncludeRecurrences = True
            found = items.Restrict(f"[Start] < '{self._date(end)}' AND [End] > '{self._date(start)}'")
            result = []
            for index, item in enumerate(found):
                if index >= MAX_ITEMS:
                    raise ToolError("That calendar range is too large. Ask for a shorter range.")
                record = self._record(item)
                if _matches(query, record["title"], record["location"], record["notes"]):
                    result.append(record)
            return sorted(result, key=lambda event: event["start"])
        return self._call(run)

    def add_event(self, title: str, start: datetime, end: datetime, location: str = "", notes: str = "",
                  calendar: str = "", all_day: bool = False) -> dict:
        if end <= start:
            raise ToolError("The event's end must be after its start.")

        def run(app):
            item = _folder(app.GetNamespace("MAPI"), CALENDAR, calendar or self._name).Items.Add("IPM.Appointment")
            item.Subject, item.Start, item.End = title, start, end
            item.Location, item.Body, item.AllDayEvent = location, notes, all_day
            item.Save()
            return self._record(item)
        return self._call(run)

    @staticmethod
    def _occurrence(app, identity: str, at: datetime | None, *, changing: bool = False):
        item = _item(app.GetNamespace("MAPI"), identity, "event")
        if item.IsRecurring:
            if at is None and changing:
                raise ToolError("Name the start time of that occurrence; I won't change the whole repeating series.")
            if at is not None:
                item = item.GetRecurrencePattern().GetOccurrence(at)
        return item

    def event(self, id: str, at: datetime | None = None) -> dict:
        return self._call(lambda app: self._record(self._occurrence(app, id, at)))

    def move_event(self, id: str, at: datetime | None, start: datetime, end: datetime) -> dict:
        if end <= start:
            raise ToolError("The event's end must be after its start.")

        def run(app):
            item = self._occurrence(app, id, at, changing=True)
            item.Start, item.End = start, end
            item.Save()
            return self._record(item)
        return self._call(run)

    def delete_event(self, id: str, at: datetime | None = None) -> dict:
        def run(app):
            item = self._occurrence(app, id, at, changing=True)
            record = self._record(item)
            item.Delete()  # Outlook moves ordinary items to Deleted Items
            return record
        return self._call(run)


class OutlookReminders:
    controls = "Microsoft Outlook"
    identity = OutlookCalendar.identity

    def __init__(self, call: Callable = None, folder: str = ""):
        self._call, self._name = call or OutlookGateway(), folder

    @staticmethod
    def _record(item):
        return {"id": _id(item, "task"), "title": str(item.Subject or ""), "due": _iso(item.DueDate),
                "notes": str(item.Body or ""), "list": str(item.Parent.Name), "done": bool(item.Complete),
                "shared": True}

    def list(self, query: str = "", include_done: bool = False) -> list[dict]:
        def run(app):
            result = []
            for index, item in enumerate(_folder(app.GetNamespace("MAPI"), TASKS, self._name).Items):
                if index >= MAX_ITEMS:
                    break
                if (include_done or not item.Complete) and _matches(query, item.Subject, item.Body):
                    result.append(self._record(item))
            return result
        return self._call(run)

    def add(self, title: str, due: datetime | None = None, notes: str = "", list_name: str = "") -> dict:
        def run(app):
            item = _folder(app.GetNamespace("MAPI"), TASKS, list_name or self._name).Items.Add("IPM.Task")
            item.Subject, item.Body = title, notes
            if due is not None:
                item.DueDate = due
                item.ReminderSet, item.ReminderTime = True, due
            item.Save()
            return self._record(item)
        return self._call(run)

    def complete(self, id: str, done: bool = True) -> dict:
        def run(app):
            item = _item(app.GetNamespace("MAPI"), id, "task")
            item.Complete = done
            item.Save()
            return self._record(item)
        return self._call(run)

    def delete(self, id: str) -> dict:
        def run(app):
            item = _item(app.GetNamespace("MAPI"), id, "task")
            record = self._record(item)
            item.Delete()
            return record
        return self._call(run)


class OutlookMail:
    controls = "Microsoft Outlook"
    identity = OutlookCalendar.identity

    def __init__(self, call: Callable = None):
        self._call = call or OutlookGateway()

    @staticmethod
    def _record(item, mailbox: str = "", *, body: bool = False):
        record = {"id": _id(item, "mail"), "from": str(item.SenderEmailAddress or ""),
                  "subject": str(item.Subject or ""), "date": _iso(item.ReceivedTime), "mailbox": mailbox}
        if body:
            record.update(to=str(item.To or ""), text=str(item.Body or ""))
        return record

    def search(self, query: str, limit: int = 20) -> list[dict]:
        limit = max(0, min(100, limit))

        def run(app):
            found = []
            ns = app.GetNamespace("MAPI")
            for number, label in ((INBOX, "inbox"), (SENT, "sent")):
                items = ns.GetDefaultFolder(number).Items
                items.Sort("[ReceivedTime]", True)
                for index, item in enumerate(items):
                    if index >= MAX_ITEMS:
                        break
                    if item.Class == _CLASSES["mail"] and _matches(query, item.Subject, item.SenderName,
                                                                  item.SenderEmailAddress):
                        found.append(self._record(item, label))
                        if len(found) >= limit * 2:
                            break
            return sorted(found, key=lambda item: item["date"], reverse=True)[:limit]
        return self._call(run)

    def read(self, id: str) -> dict:
        return self._call(lambda app: self._record(_item(app.GetNamespace("MAPI"), id, "mail"), body=True))

    @staticmethod
    def _save(item, to: list[str]) -> dict:
        if to:
            item.To = "; ".join(to)
        item.Save()
        item.Display(False)
        return {"draft": True, "sent": False, "id": _id(item, "mail"), "subject": str(item.Subject or ""),
                "to": to, "where": "Open in Outlook for you to check and send."}

    def draft(self, to: list[str], subject: str, body: str, reply_to: str = "") -> dict:
        def run(app):
            item = (_item(app.GetNamespace("MAPI"), reply_to, "mail").Reply()
                    if reply_to else app.CreateItem(0))
            if subject:
                item.Subject = subject
            item.Body = body
            return self._save(item, to)
        return self._call(run)

    def forward(self, id: str, to: list[str]) -> dict:
        return self._call(lambda app: self._save(_item(app.GetNamespace("MAPI"), id, "mail").Forward(), to))


class OutlookNotes:
    controls = "Microsoft Outlook"
    identity = OutlookCalendar.identity

    def __init__(self, call: Callable = None, folder: str = ""):
        self._call, self._name = call or OutlookGateway(), folder

    @staticmethod
    def _record(item, *, body: bool = False):
        record = {"id": _id(item, "note"), "title": str(item.Subject or ""), "folder": str(item.Parent.Name),
                  "modified": _iso(item.LastModificationTime)}
        if body:
            record["text"] = str(item.Body or "")
        return record

    def search(self, query: str, limit: int = 20) -> list[dict]:
        def run(app):
            result = []
            items = _folder(app.GetNamespace("MAPI"), NOTES, self._name).Items
            items.Sort("[LastModificationTime]", True)
            for index, item in enumerate(items):
                if index >= MAX_ITEMS or len(result) >= max(0, min(100, limit)):
                    break
                if _matches(query, item.Subject, item.Body):
                    result.append(self._record(item))
            return result
        return self._call(run)

    def read(self, id: str) -> dict:
        return self._call(lambda app: self._record(_item(app.GetNamespace("MAPI"), id, "note"), body=True))

    def create(self, title: str, body: str, folder: str = "") -> dict:
        def run(app):
            item = _folder(app.GetNamespace("MAPI"), NOTES, folder or self._name).Items.Add("IPM.StickyNote")
            item.Body = title + "\r\n" + body
            item.Save()
            return self._record(item, body=True)
        return self._call(run)

    def append(self, id: str, text: str) -> dict:
        def run(app):
            item = _item(app.GetNamespace("MAPI"), id, "note")
            item.Body = str(item.Body or "").rstrip() + "\r\n" + text
            item.Save()
            return self._record(item, body=True)
        return self._call(run)

    def delete(self, id: str) -> dict:
        def run(app):
            item = _item(app.GetNamespace("MAPI"), id, "note")
            record = self._record(item, body=True)
            item.Delete()
            return record
        return self._call(run)


@dataclass(frozen=True)
class OutlookOptions:
    calendar: str = ""
    tasks: str = ""
    notes: str = ""


@CONNECTIONS.register("outlook")
def _outlook(options: Mapping[str, Any], ctx: AdapterContext) -> Connections:
    o = options_from(OutlookOptions, options, "connections.outlook")
    call = OutlookGateway()
    return Connections(calendar=OutlookCalendar(call, o.calendar), reminders=OutlookReminders(call, o.tasks),
                       mail=OutlookMail(call), notes=OutlookNotes(call, o.notes))
