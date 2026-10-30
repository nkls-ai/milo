"""What the Usage page shows: tokens and dictations per day, where the tokens went, which apps got the words, and
the accounts Milo works with. Read from the usage ledger and the dictation history; no model call."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .types import Usage

MAX_SPAN = 366
TOP_APPS = 6


@dataclass(frozen=True)
class Call:
    """One harness or chat-model call from state/usage.jsonl."""

    at: datetime
    source: str
    harness: str
    usage: Usage


@dataclass(frozen=True)
class Dictated:
    """One dictation from dictation-history.jsonl. Only the count of words, never the text."""

    at: datetime
    app: str
    words: int


@dataclass(frozen=True)
class Account:
    """A service Milo uses and who it is signed in as. `uses` names what for, in plain words ("Talking").

    state: "ok" (signed in), "signed_out", "unknown" (`detail` says why) or "local" (runs on this Mac, no account).
    `plan` and `who` are empty when the service doesn't say."""

    service: str
    uses: tuple[str, ...]
    state: str = "ok"
    plan: str = ""
    who: str = ""
    detail: str = ""

    def wire(self) -> dict:
        return {"service": self.service, "uses": list(self.uses), "state": self.state, "plan": self.plan,
                "who": self.who, "detail": self.detail}


def merge(accounts: Iterable[Account]) -> list[Account]:
    """One row per service, its uses joined in order: Scribe and the voice are both the ElevenLabs account."""
    merged: dict[str, Account] = {}
    for a in accounts:
        old = merged.get(a.service)
        if old is None:
            merged[a.service] = a
            continue
        better = old if old.state == "ok" or a.state != "ok" else a
        merged[a.service] = Account(a.service, old.uses + tuple(u for u in a.uses if u not in old.uses), better.state,
                                    old.plan or a.plan, old.who or a.who, better.detail)
    return list(merged.values())


@dataclass(frozen=True)
class Summary:
    """The days from `today - span + 1` to `today`, every one of them, oldest first."""

    span: int
    today: date
    since: date | None
    daily: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    apps: list[dict] = field(default_factory=list)


def start_of(today: date, span: int) -> date:
    return today - timedelta(days=span - 1)


def summarize(calls: Iterable[Call], dictations: Iterable[Dictated], today: date, span: int,
              since: date | None) -> Summary:
    """Totals per day, per source and per app. Records outside the span are ignored, so callers may pass more."""
    span = max(1, min(MAX_SPAN, span))
    first = start_of(today, span)
    days = {first + timedelta(days=i): _empty_day(first + timedelta(days=i)) for i in range(span)}
    sources: dict[str, dict] = {}
    for c in calls:
        day = days.get(c.at.date())
        if day is None:
            continue
        u = c.usage
        day["calls"] += 1
        day["input_tokens"] += u.input_tokens
        day["cached_input_tokens"] += u.cached_input_tokens
        day["output_tokens"] += u.output_tokens
        s = sources.setdefault(c.source, {"source": c.source, "calls": 0, "tokens": 0})
        s["calls"] += 1
        s["tokens"] += u.input_tokens + u.output_tokens
    apps: Counter[str] = Counter()
    app_words: Counter[str] = Counter()
    for d in dictations:
        day = days.get(d.at.date())
        if day is None:
            continue
        day["dictations"] += 1
        day["words"] += d.words
        apps[d.app] += 1
        app_words[d.app] += d.words
    top = sorted(apps, key=lambda a: (-app_words[a], -apps[a], a))[:TOP_APPS]
    return Summary(span, today, since, list(days.values()),
                   sorted(sources.values(), key=lambda s: (-s["tokens"], s["source"])),
                   [{"app": a, "dictations": apps[a], "words": app_words[a]} for a in top])


def _empty_day(day: date) -> dict:
    return {"day": day.isoformat(), "calls": 0, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
            "dictations": 0, "words": 0}
