import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from milo.core import times


@pytest.fixture
def berlin():
    if not hasattr(time, "tzset"):
        pytest.skip("this test changes POSIX TZ; Windows timezone is managed by the OS")
    old = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Berlin"
    time.tzset()
    yield
    if old is None:
        del os.environ["TZ"]
    else:
        os.environ["TZ"] = old
    time.tzset()


def test_a_time_without_an_offset_is_local_already():
    assert times.local("2026-11-05T15:00") == datetime(2026, 11, 5, 15)
    assert times.local(" 2026-11-05 15:00:30 ") == datetime(2026, 11, 5, 15, 0, 30)
    assert times.local(datetime(2026, 11, 5, 15)) == datetime(2026, 11, 5, 15)


def test_a_time_with_an_offset_becomes_the_same_moment_in_local_time(berlin):
    assert times.local("2026-11-05T14:00Z") == datetime(2026, 11, 5, 15), "UTC 14:00 is 15:00 in Berlin in November"
    assert times.local("2026-07-05T14:00+00:00") == datetime(2026, 7, 5, 16), "and 16:00 in summer"
    aware = datetime(2026, 11, 5, 15, tzinfo=timezone(timedelta(hours=1)))
    assert times.local(aware) == datetime(2026, 11, 5, 15) and times.local(aware).tzinfo is None


def test_unreadable_times():
    with pytest.raises(ValueError):
        times.local("Thursday")
    assert times.parse_local("Thursday") is None
    assert times.parse_local("") is None and times.parse_local(None) is None and times.parse_local("  ") is None


def test_written_times():
    at = datetime(2026, 11, 5, 9, 5, 30)
    assert times.iso_minutes(at) == "2026-11-05T09:05"
    assert times.minute(at) == "2026-11-05 09:05"
    assert times.parse_minute("2026-11-05 09:05") == datetime(2026, 11, 5, 9, 5)
    assert times.parse_minute("tomorrow 9") is None
