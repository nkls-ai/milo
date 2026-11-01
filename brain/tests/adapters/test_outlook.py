"""Contract checks against an in-memory COM object model, without a user mailbox."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from milo.adapters.connect import outlook
from milo.core.ports import Calendar, Mail, Notes, Reminders
from milo.core.types import ToolError


class Items(list):
    def __init__(self, folder):
        super().__init__()
        self.folder = folder
        self.IncludeRecurrences = False
        self.calls = []

    def Add(self, kind):
        item = Item(self.folder, {"IPM.Appointment": 26, "IPM.Task": 48, "IPM.StickyNote": 44}[kind])
        self.append(item)
        return item

    def Sort(self, key, descending=False):
        self.calls.append(("sort", key, descending))

    def Restrict(self, query):
        self.calls.append(("restrict", query, self.IncludeRecurrences))
        return self


class Item:
    counter = 0

    def __init__(self, folder, cls):
        Item.counter += 1
        self.EntryID = str(Item.counter)
        self.Parent, self.Class = folder, cls
        self.Subject, self.Body, self.Location = "Title", "Body", "Home"
        self.Start = datetime(2026, 11, 2, 9)
        self.End = datetime(2026, 11, 2, 10)
        self.DueDate = datetime(4501, 1, 1)
        self.LastModificationTime = self.ReceivedTime = datetime(2026, 11, 1, 10)
        self.SenderName, self.SenderEmailAddress, self.To = "Anna", "anna@example.test", "you@example.test"
        self.IsRecurring, self.AllDayEvent, self.Complete = False, False, False
        self.saved, self.deleted, self.displayed = 0, False, False
        self.occurrence = None
        self.at = None
        self.reply, self.forward = None, None

    def Save(self):
        self.saved += 1

    def Delete(self):
        self.deleted = True

    def Display(self, modal):
        assert modal is False
        self.displayed = True

    def Send(self):
        raise AssertionError("Milo must never send through the Outlook connection")

    def GetRecurrencePattern(self):
        return self

    def GetOccurrence(self, at):
        self.at = at
        return self.occurrence

    def Reply(self):
        self.reply = Item(self.Parent, 43)
        return self.reply

    def Forward(self):
        self.forward = Item(self.Parent, 43)
        self.forward.Body = self.Body
        return self.forward


@pytest.fixture
def world():
    folders = {}
    for number, name in ((outlook.CALENDAR, "Calendar"), (outlook.TASKS, "Tasks"), (outlook.NOTES, "Notes"),
                         (outlook.INBOX, "Inbox"), (outlook.SENT, "Sent")):
        folder = SimpleNamespace(Name=name, StoreID="STORE", Folders=[])
        folder.Items = Items(folder)
        folders[number] = folder

    def get_item(entry, store):
        assert store == "STORE"
        return next(item for folder in folders.values() for item in folder.Items if item.EntryID == entry)

    namespace = SimpleNamespace(GetDefaultFolder=lambda number: folders[number], GetItemFromID=get_item)
    app = SimpleNamespace(GetNamespace=lambda name: namespace,
                          CreateItem=lambda number: Item(folders[outlook.INBOX], 43))
    return SimpleNamespace(folders=folders, app=app, call=lambda action: action(app))


def test_calendar_add_read_move_delete_preserve_json_and_store_ids(world):
    connection = outlook.OutlookCalendar(world.call)
    assert isinstance(connection, Calendar)
    start, end = datetime(2026, 11, 2, 9), datetime(2026, 11, 2, 10)
    created = connection.add_event("Dentist", start, end, "Town", "Bring insurance")
    assert created["start"] == "2026-11-02T09:00" and created["title"] == "Dentist"
    assert connection.event(created["id"]) == created
    changed = connection.move_event(created["id"], None, start.replace(hour=10), end.replace(hour=11))
    assert changed["end"] == "2026-11-02T11:00"
    assert connection.delete_event(created["id"]) == changed
    assert world.folders[outlook.CALENDAR].Items[0].deleted


def test_calendar_sorts_expands_then_restricts_before_reading(world):
    connection = outlook.OutlookCalendar(world.call, date_format=lambda dt: dt.isoformat())
    connection.add_event("Dentist", datetime(2026, 11, 2, 9), datetime(2026, 11, 2, 10))
    found = connection.events(datetime(2026, 11, 2), datetime(2026, 11, 3), "dentist")
    assert len(found) == 1
    calls = world.folders[outlook.CALENDAR].Items.calls
    assert calls[0] == ("sort", "[Start]", False)
    assert calls[1] == ("restrict", "[Start] < '2026-11-03T00:00:00' AND [End] > '2026-11-02T00:00:00'", True)


def test_recurring_mutations_require_occurrence_and_leave_series_alone(world):
    folder = world.folders[outlook.CALENDAR]
    master = Item(folder, 26)
    master.IsRecurring = True
    master.occurrence = Item(folder, 26)
    folder.Items.append(master)
    connection = outlook.OutlookCalendar(world.call)
    identity = outlook._id(master, "event")
    with pytest.raises(ToolError, match="whole repeating series"):
        connection.delete_event(identity)
    at = datetime(2026, 11, 2, 9)
    connection.delete_event(identity, at)
    assert master.at == at and master.occurrence.deleted and not master.deleted


def test_wrong_id_kind_and_invalid_range_are_refused_before_com_changes(world):
    connection = outlook.OutlookCalendar(world.call)
    task = world.folders[outlook.TASKS].Items.Add("IPM.Task")
    with pytest.raises(ToolError, match="different kind"):
        connection.event(outlook._id(task, "task"))
    with pytest.raises(ToolError, match="end must be after"):
        connection.add_event("bad", datetime(2026, 1, 2), datetime(2026, 1, 1))
    assert not world.folders[outlook.CALENDAR].Items


def test_task_due_completion_and_undo_roundtrip(world):
    connection = outlook.OutlookReminders(world.call)
    assert isinstance(connection, Reminders)
    task = connection.add("Book dentist", None, "Call in the morning")
    assert task["due"] == "" and not task["done"]
    assert connection.list("dentist") == [task]
    assert connection.complete(task["id"])["done"]
    assert connection.list() == []
    assert not connection.complete(task["id"], False)["done"]
    connection.delete(task["id"])
    assert world.folders[outlook.TASKS].Items[0].deleted


def test_mail_search_read_reply_forward_and_draft_never_send(world):
    mail = Item(world.folders[outlook.INBOX], 43)
    world.folders[outlook.INBOX].Items.append(mail)
    connection = outlook.OutlookMail(world.call)
    assert isinstance(connection, Mail)
    found = connection.search("anna")
    assert len(found) == 1 and found[0]["mailbox"] == "inbox"
    assert connection.read(found[0]["id"])["text"] == "Body"
    reply = connection.draft([], "Re: Title", "Tomorrow works", reply_to=found[0]["id"])
    assert reply["draft"] and not reply["sent"] and mail.reply.displayed and mail.reply.saved
    forwarded = connection.forward(found[0]["id"], ["other@example.test"])
    assert not forwarded["sent"] and mail.forward.Body == "Body" and mail.forward.displayed
    draft = connection.draft(["anna@example.test"], "Hello", "Test")
    assert draft["draft"] and not draft["sent"] and draft["subject"] == "Hello"


def test_notes_create_append_read_and_recoverable_delete(world):
    connection = outlook.OutlookNotes(world.call)
    assert isinstance(connection, Notes)
    note = connection.create("Trip", "Train at nine")
    assert note["text"] == "Trip\r\nTrain at nine"
    assert connection.read(note["id"]) == note
    changed = connection.append(note["id"], "Bring tickets")
    assert changed["text"].endswith("\r\nBring tickets")
    assert connection.search("tickets")[0]["id"] == note["id"]
    connection.delete(note["id"])
    assert world.folders[outlook.NOTES].Items[0].deleted


def test_named_folder_is_never_silently_replaced_by_default(world):
    connection = outlook.OutlookReminders(world.call)
    with pytest.raises(ToolError, match="no Outlook folder"):
        connection.add("Test", list_name="Missing")
    assert not world.folders[outlook.TASKS].Items
