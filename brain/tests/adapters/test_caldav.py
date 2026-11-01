"""Calendar/reminder contracts against fake DAV resources and real date rules."""
from contextlib import contextmanager
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from milo.adapters.connect.caldav import CalDAVCalendar, CalDAVOptions, CalDAVReminders
from milo.core.ports import Calendar, Reminders
from milo.core.registry import ConfigError
from milo.core.types import ToolError


class Component(dict):
    def add(self, key, value):
        self[key] = value


class Resource:
    def __init__(self, properties):
        self.component = Component({key.upper(): value for key, value in properties.items()})
        self.saved, self.deleted, self.if_match = [], False, None

    def get_icalendar_component(self):
        return self.component

    @contextmanager
    def edit_icalendar_component(self):
        yield self.component

    def save(self, **options):
        self.saved.append(options)

    def delete(self, **options):
        self.deleted = True
        self.if_match = options.get("if_match")


class DAVCalendar:
    name = "Personal"

    def __init__(self):
        self.objects = []
        self.searches = []
        self.expanded = []

    def get_supported_components(self):
        return ["VEVENT", "VTODO"]

    def add_event(self, **properties):
        obj = Resource(properties)
        self.objects.append(obj)
        return obj

    add_todo = add_event

    def search(self, **options):
        self.searches.append(options)
        if options.get("expand") and self.expanded:
            return self.expanded
        return [obj for obj in self.objects if ("DTSTART" in obj.component) == bool(options.get("event"))]

    def get_event_by_uid(self, uid):
        return next(obj for obj in self.objects if obj.component["UID"] == uid)

    get_todo_by_uid = get_event_by_uid


@pytest.fixture
def world():
    cal = DAVCalendar()
    principal = SimpleNamespace(calendars=lambda: [cal])
    return SimpleNamespace(cal=cal, principal=principal, call=lambda action: action(principal))


def test_calendar_create_read_move_delete_and_optimistic_precondition(world):
    connection = CalDAVCalendar(world.call)
    assert isinstance(connection, Calendar)
    start, end = datetime(2026, 11, 2, 9), datetime(2026, 11, 2, 10)
    event = connection.add_event("Dentist", start, end, "Town", "Bring insurance")
    assert event["start"] == "2026-11-02T09:00" and event["calendar"] == "Personal"
    assert connection.event(event["id"]) == event
    moved = connection.move_event(event["id"], None, start.replace(hour=10), end.replace(hour=11))
    assert moved["start"] == "2026-11-02T10:00"
    assert world.cal.objects[0].saved == [{"only_this_recurrence": True}]
    assert connection.delete_event(event["id"]) == moved
    assert world.cal.objects[0].deleted and world.cal.objects[0].if_match is True


def test_calendar_search_expands_recurrences_and_filters_user_words_as_data(world):
    connection = CalDAVCalendar(world.call)
    connection.add_event("Dentist", datetime(2026, 11, 2, 9), datetime(2026, 11, 2, 10))
    found = connection.events(datetime(2026, 11, 2), datetime(2026, 11, 3), "dentist")
    assert len(found) == 1
    assert world.cal.searches[-1]["event"] and world.cal.searches[-1]["expand"]
    assert world.cal.searches[-1]["start"].tzinfo is not None
    assert connection.events(datetime(2026, 11, 2), datetime(2026, 11, 3), "other") == []


def test_all_day_values_stay_dates_and_exclusive_end_is_preserved(world):
    connection = CalDAVCalendar(world.call)
    event = connection.add_event("Away", datetime(2026, 11, 2), datetime(2026, 11, 4), all_day=True)
    assert event["all_day"] and event["end"] == "2026-11-04T00:00"
    assert type(world.cal.objects[0].component["DTSTART"]) is date


def test_recurring_delete_saves_cancellation_override_never_deletes_series(world):
    connection = CalDAVCalendar(world.call)
    event = connection.add_event("Weekly", datetime(2026, 11, 2, 9), datetime(2026, 11, 2, 10))
    master = world.cal.objects[0]
    master.component["RRULE"] = "FREQ=WEEKLY"
    at = datetime(2026, 11, 9, 9)
    occurrence = Resource({"uid": master.component["UID"], "dtstart": at.astimezone(),
                           "dtend": at.replace(hour=10).astimezone(), "recurrence-id": at.astimezone()})
    world.cal.expanded = [occurrence]
    with pytest.raises(ToolError, match="whole repeating series"):
        connection.delete_event(event["id"])
    connection.delete_event(event["id"], at)
    assert occurrence.component["STATUS"] == "CANCELLED"
    assert occurrence.saved == [{"only_this_recurrence": True}]
    assert not occurrence.deleted and not master.deleted and not master.saved


def test_reminder_due_completion_undo_and_delete(world):
    connection = CalDAVReminders(world.call)
    assert isinstance(connection, Reminders)
    task = connection.add("Book dentist", datetime(2026, 11, 2, 9), "Call in the morning")
    assert task["due"] == "2026-11-02T09:00" and not task["done"]
    assert connection.list("dentist") == [task]
    assert connection.complete(task["id"])["done"]
    assert connection.list() == [] and connection.list(include_done=True)[0]["done"]
    assert not connection.complete(task["id"], False)["done"]
    assert "COMPLETED" not in world.cal.objects[0].component
    connection.delete(task["id"])
    assert world.cal.objects[0].deleted and world.cal.objects[0].if_match is True


def test_recurring_task_mutation_is_refused_instead_of_altering_series(world):
    connection = CalDAVReminders(world.call)
    task = connection.add("Weekly")
    world.cal.objects[0].component["RRULE"] = "FREQ=WEEKLY"
    with pytest.raises(ToolError, match="whole series"):
        connection.complete(task["id"])
    assert not world.cal.objects[0].saved


def test_missing_or_ambiguous_calendar_does_not_choose_a_writable_target(world):
    connection = CalDAVCalendar(world.call)
    world.principal.calendars = lambda: [world.cal, DAVCalendar()]
    with pytest.raises(ToolError, match="exactly one"):
        connection.add_event("Test", datetime(2026, 11, 2), datetime(2026, 11, 3))
    with pytest.raises(ToolError, match="ambiguous"):
        connection.add_event("Test", datetime(2026, 11, 2), datetime(2026, 11, 3), calendar="Missing")
    assert not world.cal.objects


@pytest.mark.parametrize("options", [{"url": "http://example.test"}, {"url": "https://user:secret@example.test"},
                                    {"url": "https://example.test", "key_ref": "../outside"},
                                    {"url": "https://example.test", "key_ref": "C:\\outside"},
                                    {"url": "https://example.test", "timeout_s": 0}])
def test_credentials_and_transport_validation_do_not_expose_secrets(options):
    with pytest.raises(ConfigError, match=r"\[connections.caldav\]") as error:
        CalDAVOptions(**options)
    assert "secret@example" not in str(error.value)


def test_loopback_is_allowed_for_self_hosted_test_servers():
    assert CalDAVOptions(url="http://127.0.0.1:5232").timeout_s == 20
