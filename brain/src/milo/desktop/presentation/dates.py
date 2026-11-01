"""The window's words for times: the brain writes local ISO times ("2026-10-30T09:12:03")."""
from __future__ import annotations

from datetime import date, datetime, timedelta


def parse(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def wire(moment: datetime) -> str:
    """A date as the brain writes local times, for `get_conversations before`."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def clock(moment: datetime) -> str:
    return f"{moment.hour}:{moment.minute:02d}"


def heading(moment: datetime, now: datetime) -> str:
    """The sidebar's day groups: Today, Yesterday, This week, then months."""
    day, today = moment.date(), now.date()
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    if today - timedelta(days=6) <= day and moment < now:
        return "This week"
    return moment.strftime("%B") if moment.year == now.year else moment.strftime("%B %Y")


def short(moment: datetime, now: datetime) -> str:
    """The time on a row: "9:12" today, "Tue" this week, "28 Oct" before."""
    group = heading(moment, now)
    if group == "Today":
        return clock(moment)
    if group in ("Yesterday",):
        return group
    if group == "This week":
        return moment.strftime("%a")
    return f"{moment.day} {moment.strftime('%b')}"


def day_heading(moment: datetime, previous: datetime | None, today: date) -> str:
    """"Today", "Yesterday" or a date over the thread, when `moment` falls on another day than `previous`."""
    if previous is not None and previous.date() == moment.date():
        return ""
    if moment.date() == today:
        return "Today"
    if moment.date() == today - timedelta(days=1):
        return "Yesterday"
    return f"{moment.strftime('%A')}, {moment.day} {moment.strftime('%B')}"
