"""Real HTTP CalDAV round trips against an isolated loopback Radicale server.

No user's service or credentials are used. The server and its disposable account
exist only under pytest's temporary directory and are stopped after each test.
"""
from __future__ import annotations

import importlib.util
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest

from milo.adapters.connect.caldav import CalDAVCalendar, CalDAVGateway, CalDAVOptions, CalDAVReminders

pytestmark = pytest.mark.skipif(importlib.util.find_spec("radicale") is None or
                                importlib.util.find_spec("caldav") is None,
                                reason="real CalDAV integration needs the dev and desktop dependencies")


@pytest.fixture
def dav_server(tmp_path):
    import caldav

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    users = tmp_path / "users"
    users.write_text("milo:local-test-password\n", encoding="utf-8")
    config = tmp_path / "radicale.conf"
    config.write_text(f"""[server]
hosts = 127.0.0.1:{port}
[auth]
type = htpasswd
htpasswd_filename = {users.as_posix()}
htpasswd_encryption = plain
[storage]
filesystem_folder = {(tmp_path / 'storage').as_posix()}
[logging]
level = error
""", encoding="utf-8")
    url = f"http://127.0.0.1:{port}"
    with (tmp_path / "server.log").open("wb") as log:
        process = subprocess.Popen([sys.executable, "-m", "radicale", "--config", str(config)],
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    pytest.fail("Radicale exited: " + (tmp_path / "server.log").read_text(encoding="utf-8"))
                try:
                    urlopen(url, timeout=1).close()
                    break
                except HTTPError:
                    break  # an authentication challenge means the HTTP server is ready
                except URLError:
                    if time.monotonic() >= deadline:
                        pytest.fail("Radicale did not start in time")
                    time.sleep(0.05)
            with caldav.DAVClient(url=url, username="milo", password="local-test-password", timeout=5) as client:
                calendar = client.principal().make_calendar(name="Milo E2E", cal_id="milo-e2e")
                assert str(calendar.name) == "Milo E2E"
            home = tmp_path / "Milo"
            (home / "secrets").mkdir(parents=True)
            (home / "secrets" / "caldav.key").write_text("local-test-password", encoding="utf-8")
            options = CalDAVOptions(url=url, username="milo", calendar="Milo E2E", tasks="Milo E2E", timeout_s=5)
            call = CalDAVGateway(options, home)
            yield SimpleNamespace(calendar=CalDAVCalendar(call, options.calendar),
                                  tasks=CalDAVReminders(call, options.tasks), url=url)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_real_calendar_and_tasks_add_read_update_undo_delete(dav_server):
    calendar, tasks = dav_server.calendar, dav_server.tasks
    start, end = datetime(2026, 11, 5, 9), datetime(2026, 11, 5, 10)
    event = calendar.add_event("Milo E2E", start, end, "Desk", "Disposable test event")
    assert calendar.event(event["id"])["title"] == "Milo E2E"
    assert calendar.events(start - timedelta(days=1), end + timedelta(days=1), "Milo E2E")[0]["id"] == event["id"]
    moved = calendar.move_event(event["id"], None, start + timedelta(hours=1), end + timedelta(hours=1))
    assert moved["start"] == "2026-11-05T10:00"
    restored = calendar.move_event(event["id"], None, start, end)
    assert restored["start"] == event["start"]
    calendar.delete_event(event["id"])
    assert calendar.events(start - timedelta(days=1), end + timedelta(days=1)) == []
    task = tasks.add("Milo E2E task", start, "Disposable test task")
    assert task["due"] == "2026-11-05T09:00"
    assert tasks.list("Milo E2E task")[0]["id"] == task["id"]
    assert tasks.complete(task["id"])["done"]
    assert tasks.list("Milo E2E task") == []
    assert not tasks.complete(task["id"], False)["done"]
    tasks.delete(task["id"])
    assert tasks.list("Milo E2E task", include_done=True) == []


def test_real_recurring_edits_only_change_one_occurrence(dav_server):
    import caldav

    start = datetime(2026, 11, 5, 9)
    with caldav.DAVClient(url=dav_server.url, username="milo", password="local-test-password", timeout=5) as client:
        calendar = client.principal().calendars()[0]
        calendar.add_event(uid="milo-recurring-e2e", summary="Milo recurring E2E", dtstart=start.astimezone(),
                           dtend=(start + timedelta(hours=1)).astimezone(), rrule={"FREQ": "DAILY", "COUNT": 3})
    connection = dav_server.calendar
    occurrences = connection.events(start - timedelta(days=1), start + timedelta(days=4), "recurring")
    assert len(occurrences) == 3
    identity = occurrences[1]["id"]
    at = start + timedelta(days=1)
    connection.move_event(identity, at, at + timedelta(hours=1), at + timedelta(hours=2))
    after = connection.events(start - timedelta(days=1), start + timedelta(days=4), "recurring")
    assert [event["start"] for event in after] == ["2026-11-05T09:00", "2026-11-06T10:00", "2026-11-07T09:00"]
    connection.delete_event(identity, start + timedelta(days=2))
    remaining = connection.events(start - timedelta(days=1), start + timedelta(days=4), "recurring")
    assert len(remaining) == 2 and remaining[0]["start"] == "2026-11-05T09:00"
