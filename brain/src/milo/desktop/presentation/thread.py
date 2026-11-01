"""How a conversation's lines sit in the thread (MiloKit TranscriptList, DayHeading, PendingRow)."""
from __future__ import annotations

from datetime import date

from . import dates

MOODS = ("neutral", "happy", "excited", "thinking", "concerned", "sad", "sleepy", "confused")
VIA = {"voice": ("mic", "You said this"), "typed": ("keyboard", "You typed this"),
       "message": ("phone", "You sent this from your phone")}


def shows_time(entry: dict, previous: dict | None) -> bool:
    """A new time only when the minute changes."""
    if previous is None:
        return True
    a, b = dates.parse(entry.get("ts")), dates.parse(previous.get("ts"))
    if a is None or b is None:
        return previous is None
    return a.replace(second=0, microsecond=0) != b.replace(second=0, microsecond=0)


def gap(entry: dict, previous: dict | None) -> int:
    """More air before the user speaks than between Milo's answer and his work on it."""
    if previous is None:
        return 0
    return 18 if entry.get("kind") == "user" else 8


def day_heading(entry: dict, previous: dict | None, today: date) -> str:
    moment = dates.parse(entry.get("ts"))
    if moment is None:
        return ""
    return dates.day_heading(moment, dates.parse(previous.get("ts")) if previous else None, today)


def time_label(entry: dict) -> str:
    moment = dates.parse(entry.get("ts"))
    return dates.clock(moment) if moment else ""


def pending(state: str, last: dict | None) -> str:
    """"Listening…" or "Thinking…" at the end while nothing has arrived yet."""
    if state == "listening":
        return "Listening…"
    if state == "transcribing":
        return "Writing down what you said…"
    streaming = last is not None and last.get("kind") == "milo" and not last.get("done", True)
    return "Thinking…" if state == "thinking" and not streaming else ""


def mood(entry: dict) -> str:
    value = str(entry.get("emotion", "neutral"))
    return value if value in MOODS else "neutral"
