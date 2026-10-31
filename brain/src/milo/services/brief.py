"""The morning brief sent to the owner's phone: today's calendar, due reminders and open helpers.

Built from local data with plain templates, so it costs zero tokens (ADR 0003). The heartbeat checks every
tick whether it is due; it goes once a day, at `[messages] brief_at` or within three hours after it (a Mac
that slept through 7:30 sends it when it wakes at 8:15).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, time, timedelta
from typing import Any

from milo.core.ports import ReminderSource
from milo.core.times import parse_local
from milo.core.words.dates import month, weekday

from .helpers import Helper, HelperStatus

log = logging.getLogger("milo.brief")

LATE_BY = timedelta(hours=3)
MAX_ITEMS = 12

AppCall = Callable[[str, dict], Awaitable[Any]]
"""The app's Calendar and Reminders (AppBridge.call). Raises when the app can't answer."""


def due(at: time | None, now: datetime, sent_on: str) -> bool:
    """Whether the brief should go now: it's past `at` today, not too long past, and none went today."""
    if at is None or sent_on == now.date().isoformat():
        return False
    start = datetime.combine(now.date(), at)
    return start <= now < start + LATE_BY


async def build(now: datetime, *, app: AppCall | None, calendar: bool, apple_reminders: bool,
                reminders: ReminderSource, helpers: Sequence[Helper]) -> str:
    """The brief's text. A part whose data can't be read (the app isn't running) is left out with a note."""
    lines = [f"Good morning! Here's {weekday(now)}, {now.day} {month(now)}."]
    if calendar and app is not None:
        lines += ["", *await _calendar(app, now)]
    lines += ["", *await _reminders(app if apple_reminders else None, reminders, now)]
    working = [h for h in helpers if h.active]
    if working:
        lines += ["", "Helpers still at work:"]
        lines += [f"• {h.title}: {'waiting for you' if h.status is HelperStatus.NEEDS_YOU else h.status.value}"
                  for h in working[:MAX_ITEMS]]
    return "\n".join(lines).strip()


async def _calendar(app: AppCall, now: datetime) -> list[str]:
    start = datetime.combine(now.date(), time())
    try:
        events = await app("calendar.events", {"start": _local(start), "end": _local(start + timedelta(days=1))})
    except Exception as e:  # noqa: BLE001 - the brief goes out without this part
        log.info("brief without the calendar: %s", type(e).__name__)
        return ["(I couldn't read your calendar: is Milo running on the Mac?)"]
    events = [e for e in events if isinstance(e, dict)] if isinstance(events, list) else []
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


async def _reminders(app: AppCall | None, reminders: ReminderSource, now: datetime) -> list[str]:
    today = now.date()
    items: list[tuple[datetime, str]] = [(r.due, r.text) for r in reminders.all()
                                         if not r.done and r.due.date() <= today]
    if app is not None:
        try:
            listed = await app("reminders.list", {})
        except Exception as e:  # noqa: BLE001
            log.info("brief without Apple Reminders: %s", type(e).__name__)
            listed = []
        for r in listed if isinstance(listed, list) else []:
            when = _parse(r.get("due")) if isinstance(r, dict) else None
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


def _local(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M")


def _one_line(value: object, limit: int = 100) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"

