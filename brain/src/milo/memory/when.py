"""Time phrases in a turn ("yesterday", "letzte Woche", "on Monday") as a window of time. English and German."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3, "freitag": 4, "samstag": 5, "sonnabend": 5,
    "sonntag": 6,
}
TIME_WORDS = frozenset("""
today yesterday tonight week weeks month months ago morning evening night last past earlier recently days day
heute gestern vorgestern woche wochen monat monaten letzte letzten letzter vergangene vergangenen morgen abend
früh frueh tag tagen neulich kürzlich
""".split()) | frozenset(WEEKDAYS)
"""Words that say when, not what. Text search skips them; the window does their job."""

_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ein": 1, "einem": 1,
            "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7}


def window(text: str, now: datetime) -> tuple[datetime, datetime] | None:
    """[start, end) the turn asks about, or None if it names no time."""
    t = " " + re.sub(r"[^\w ]+", " ", text.lower()) + " "
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day = timedelta(days=1)
    monday = today - timedelta(days=today.weekday())

    def has(*phrases: str) -> bool:
        return any(f" {p} " in t for p in phrases)

    if has("last night", "gestern abend", "gestern nacht"):
        return today - day + timedelta(hours=17), today + timedelta(hours=5)
    if has("this morning", "heute morgen", "heute früh", "heute vormittag"):
        return today, today + timedelta(hours=12)
    if has("day before yesterday", "vorgestern"):
        return today - 2 * day, today - day
    if has("yesterday", "gestern"):
        return today - day, today
    if has("today", "heute", "tonight"):
        return today, now + timedelta(minutes=1)
    m = re.search(r" (\w+) (days|weeks) ago | vor (\w+) (tagen|wochen) ", t)
    if m:
        count = _number(m.group(1) or m.group(3))
        if count:
            unit = 7 if (m.group(2) or m.group(4)).startswith(("week", "woche")) else 1
            start = today - timedelta(days=count * unit)
            return start - day * (unit // 7 * 3), start + day * (1 + unit // 7 * 3)
    if has("last week", "letzte woche", "letzten woche", "vergangene woche", "vergangenen woche", "vorige woche"):
        return monday - 7 * day, monday
    if has("this week", "diese woche", "dieser woche"):
        return monday, now + timedelta(minutes=1)
    if has("last month", "letzten monat", "letzte monat", "vergangenen monat", "im letzten monat"):
        first = today.replace(day=1)
        return (first - day).replace(day=1), first
    if has("this month", "diesen monat", "diesem monat"):
        return today.replace(day=1), now + timedelta(minutes=1)
    for name, weekday in WEEKDAYS.items():
        if f" {name} " in t:  # not "on Sundays": that is a habit, not a day
            back = (today.weekday() - weekday) % 7 or (7 if has("last " + name, "letzten " + name) else 0)
            start = today - timedelta(days=back)
            return start, start + day
    if has("recently", "lately", "neulich", "kürzlich", "the other day", "letztens"):
        return today - 14 * day, now + timedelta(minutes=1)
    return None


def _number(word: str) -> int | None:
    if word.isdigit():
        return int(word)
    return _NUMBERS.get(word)
