"""Times as Milo reads and writes them: naive datetimes in the user's local wall-clock time.

The rule, in one place: Milo's clock (`Clock.now()`), his files and the app all speak local time without a zone, like
"2026-11-05T15:00". A time that arrives with an offset ("2026-11-05T14:00Z" from a model, "+01:00" from a service) is
converted to local time first and then loses its tzinfo, so it compares with `Clock.now()` and means the same moment.
A time without an offset is taken as local already. Nothing in the brain keeps an aware datetime.

`local` raises on text that isn't a time; `parse_local` returns None, so a caller picks its own fallback
(`parse_local(x) or datetime.min`). Written times are `iso_minutes` on the wire and `minute` in Markdown files and tags.
"""

from __future__ import annotations

from datetime import datetime

MINUTE = "%Y-%m-%d %H:%M"
"""How reminders.md and the talker's <reminder> tag write a time: "2026-11-05 15:00"."""


def local(value: object) -> datetime:
    """An ISO time (text or a datetime) as naive local time. Raises ValueError if it isn't one."""
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip())
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo is not None else dt


def parse_local(value: object) -> datetime | None:
    """`local`, or None for nothing or text that isn't a time."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return local(value)
    except ValueError:
        return None


def iso_minutes(dt: datetime) -> str:
    """"2026-11-05T15:00": a time on the wire and in tool arguments."""
    return dt.isoformat(timespec="minutes")


def parse_minute(text: str) -> datetime | None:
    """"2026-11-05 15:00" (MINUTE) as a local time, or None."""
    try:
        return datetime.strptime(text.strip(), MINUTE)
    except ValueError:
        return None


def minute(dt: datetime) -> str:
    """"2026-11-05 15:00"."""
    return dt.strftime(MINUTE)
