"""Dates in English words, the same on every platform and in every locale.

`%-d` (a day without its leading zero) is a glibc and BSD extension: Windows' strftime raises on it. `%A` and `%B`
follow the process's locale, so a library that calls setlocale would turn "Thursday" into "Donnerstag" in the
middle of a prompt. These spell days and months themselves. Times (`%H:%M`) and ISO dates are fine as they are.
"""

from __future__ import annotations

from datetime import date

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def weekday(day: date, *, short: bool = False) -> str:
    """"Thursday", or "Thu"."""
    name = WEEKDAYS[day.weekday()]
    return name[:3] if short else name


def month(day: date, *, short: bool = False) -> str:
    """"November", or "Nov"."""
    name = MONTHS[day.month - 1]
    return name[:3] if short else name


def long_date(day: date, *, year: bool = False, short: bool = False) -> str:
    """"Thursday 5 November", with " 2026" if `year`; "Thu 5 Nov" if `short`."""
    text = f"{weekday(day, short=short)} {day.day} {month(day, short=short)}"
    return f"{text} {day.year}" if year else text
