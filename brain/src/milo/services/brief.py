"""The morning brief sent to the owner's phone: today's calendar, due reminders and open helpers.

Built from local data with plain templates, so it costs zero tokens (ADR 0003). The calendar and Apple Reminders come
from the talker's day (`Today.current`), which reads them again only when they are older than five minutes. The heartbeat checks every
tick whether it is due; it goes once a day, at `[messages] brief_at` or within three hours after it (a Mac
that slept through 7:30 sends it when it wakes at 8:15).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, time, timedelta

from milo.core.ports import ReminderSource
from milo.core.times import parse_local
from milo.core.words.dates import month, weekday

from .helpers import Helper, HelperStatus
from .today import Snapshot, Today

log = logging.getLogger("milo.brief")

LATE_BY = timedelta(hours=3)
MAX_ITEMS = 12

def due(at: time | None, now: datetime, sent_on: str) -> bool:
    """Whether the brief should go now: it's past `at` today, not too long past, and none went today."""
    if at is None or sent_on == now.date().isoformat():
        return False
    start = datetime.combine(now.date(), at)
    return start <= now < start + LATE_BY


async def build(now: datetime, *, today: Today | None, reminders: ReminderSource, helpers: Sequence[Helper]) -> str:
    """The brief's text. A part whose data can't be read (the app isn't running) is left out with a note. `today`:
    the day with the calendar and Apple Reminders, if they are switched on."""
    lines = [f"Good morning! Here's {weekday(now)}, {now.day} {month(now)}."]
    connections = today.connections if today is not None else None
    day = await today.current() if connections is not None else None
    if connections is not None and connections.calendar is not None:
        lines += ["", *_calendar(day, now)]
    apple = day if connections is not None and connections.reminders is not None else None
    lines += ["", *_reminders(apple, reminders, now)]
    working = [h for h in helpers if h.active]
    if working:
        lines += ["", "Helpers still at work:"]
        lines += [f"• {h.title}: {'waiting for you' if h.status is HelperStatus.NEEDS_YOU else h.status.value}"
                  for h in working[:MAX_ITEMS]]
    return "\n".join(lines).strip()


def _calendar(day: Snapshot | None, now: datetime) -> list[str]:
    if day is None:
        log.info("brief without the calendar")
        return ["(I couldn't read your calendar: is Milo running on the Mac?)"]
    events = [e for e in day.events if Today.on(e, now.date())]
    if not events:
        return ["Nothing in your calendar today."]
    out = ["Today:"]
    for event in events[:MAX_ITEMS]:
        title = _one_line(event.get("title")) or "(no title)"
        where = _one_line(event.get("location"))
        when = "all day" if event.get("all_day") else _span(event.get("start"), event.get("end"))
        out.append(f"• {when} {title}" + (f" ({where})" if where else ""))
    if len(events) > MAX_ITEMS:
        out.append(f"• and {len(events) - MAX_ITEMS} more")
    return out


def _reminders(day: Snapshot | None, reminders: ReminderSource, now: datetime) -> list[str]:
    """Milo's own reminders due today or before, and Apple Reminders' from `day` (the day's to-dos)."""
    today = now.date()
    items: list[tuple[datetime, str]] = [(r.due, r.text) for r in reminders.all()
                                         if not r.done and r.due.date() <= today]
    for r in day.todos if day is not None else ():
        when = _parse(r.get("due"))
        if when is not None and when.date() <= today and not r.get("done"):
            items.append((when, _one_line(r.get("title")) or "(no title)"))
    if not items:
        return ["No reminders due today."]
    items.sort(key=lambda item: item[0])
    out = ["To do:"]
    for when, text in items[:MAX_ITEMS]:
        out.append(f"• {'overdue' if when.date() < today else f'{when:%H:%M}'} {text}")
    if len(items) > MAX_ITEMS:
        out.append(f"• and {len(items) - MAX_ITEMS} more")
    return out


def _span(start: object, end: object) -> str:
    begin, finish = _parse(start), _parse(end)
    if begin is None:
        return ""
    return f"{begin:%H:%M}" + (f"–{finish:%H:%M}" if finish is not None and finish.date() == begin.date() else "")


def _parse(value: object) -> datetime | None:
    return parse_local(value) if isinstance(value, str) else None


def _one_line(value: object, limit: int = 100) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"

