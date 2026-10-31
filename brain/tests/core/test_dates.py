import locale
from datetime import date, datetime

from milo.core import dates


def test_dates_are_english_words_without_platform_flags():
    day = date(2026, 11, 5)
    assert dates.long_date(day) == "Thursday 5 November"
    assert dates.long_date(day, year=True) == "Thursday 5 November 2026"
    assert dates.long_date(datetime(2026, 1, 4, 9, 30), short=True) == "Sun 4 Jan"


def test_dates_ignore_the_process_locale():
    old = locale.setlocale(locale.LC_TIME)
    try:
        for name in ("de_DE.UTF-8", "de_DE", "fr_FR.UTF-8"):
            try:
                locale.setlocale(locale.LC_TIME, name)
                break
            except locale.Error:
                continue
        assert dates.weekday(date(2026, 11, 5)) == "Thursday" and dates.month(date(2026, 3, 1)) == "March"
    finally:
        locale.setlocale(locale.LC_TIME, old)
