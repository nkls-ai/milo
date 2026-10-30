"""Routines: recipes for work the user wants done again, as plain Markdown files. Pure: no I/O.

A routine is `~/Milo/routines/<slug>.md`: front matter, then the recipe in words.

    ---
    name: Monday report
    description: Sums last week's sales files into a one-page report.
    inputs:
      - name: month
        ask: Which month?
        default: last month
    schedule: every Monday at 09:00
    apps: [Numbers]
    paused: no
    last_run: 2026-10-27 09:00, done
    version: 1
    ---

    ## Goal
    ...
    ## Steps
    1. Open ... Check: ...
    ## Ask first
    - ...

The front matter is a small subset of YAML that people can edit by hand: `key: value` lines, `[a, b]` lists
and the list of input blocks. Values are text; `"..."` quotes one that needs it. Keys Milo doesn't know are
kept as they are. See docs/research/routines.md for why it isn't full YAML.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

MAX_SLUG = 48
MAX_NAME = 60
_KEY = re.compile(r"^([a-z_][a-z0-9_]*)\s*:\s?(.*)$")
_ITEM = re.compile(r"^\s*-\s+([a-z_][a-z0-9_]*)\s*:\s?(.*)$")
_FIELD = re.compile(r"^\s+([a-z_][a-z0-9_]*)\s*:\s?(.*)$")
_INPUT_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_YES = ("yes", "true", "on")
_NO = ("no", "false", "off", "")


class RecipeError(ValueError):
    """A routine file that can't be read. The message says what to fix, in plain words."""


@dataclass(frozen=True)
class RoutineInput:
    """A value that changes between runs: `month`, asked as "Which month?", "last month" when not given."""

    name: str
    ask: str = ""
    default: str = ""


@dataclass(frozen=True)
class Routine:
    slug: str
    """The file name without .md, and the id the app uses."""
    name: str
    description: str = ""
    inputs: tuple[RoutineInput, ...] = ()
    schedule: str = ""
    """In plain words, "every Monday at 09:00". "" for none. See Schedule."""
    apps: tuple[str, ...] = ()
    paused: bool = False
    last_run: str = ""
    """"2026-10-27 09:00, done", written by Milo after each run."""
    version: int = 1
    body: str = ""
    """The recipe: goal, steps with their checks, what to ask the user about."""
    extra: tuple[tuple[str, str], ...] = field(default=(), compare=False)
    """Front matter keys Milo doesn't know, kept so a hand edit survives a save."""

    def fingerprint(self) -> str:
        """What a run follows: the recipe and its inputs. A change means the user should look again before
        it runs; a new name, schedule or last run doesn't."""
        data = json.dumps([self.body.strip(), [(i.name, i.ask, i.default) for i in self.inputs]])
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def input(self, name: str) -> RoutineInput | None:
        key = name.strip().lower()
        return next((i for i in self.inputs if i.name == key), None)


# ---- the file format


def parse(text: str, slug: str) -> Routine:
    """A routine file's text to a Routine. Raises RecipeError."""
    text = text.lstrip("﻿")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise RecipeError("it must start with a line of three dashes (---)")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise RecipeError("the part at the top never ends: add a line of three dashes (---) after it")
    head = _front_matter(lines[1:end])
    body = "\n".join(lines[end + 1:]).strip("\n")
    name = " ".join(head.pop("name", "").split())
    if not name:
        raise RecipeError("it needs a name: line")
    inputs = head.pop("inputs", [])
    try:
        version = int(head.pop("version", "1") or 1)
    except ValueError:
        raise RecipeError("version: must be a whole number") from None
    paused = head.pop("paused", "no").strip().lower()
    if paused not in _YES + _NO:
        raise RecipeError("paused: must be yes or no")
    apps = head.pop("apps", [])
    return Routine(
        slug=slug, name=name[:MAX_NAME], description=" ".join(head.pop("description", "").split()),
        inputs=tuple(inputs), schedule=" ".join(head.pop("schedule", "").split()),
        apps=tuple(apps) if isinstance(apps, list) else tuple(a for a in [apps.strip()] if a),
        paused=paused in _YES, last_run=head.pop("last_run", "").strip(), version=max(1, version), body=body,
        extra=tuple(head.items()))


def render(routine: Routine) -> str:
    """The file text for a routine. parse(render(r)) == r."""
    out = ["---", f"name: {_value(routine.name)}"]
    if routine.description:
        out.append(f"description: {_value(routine.description)}")
    if routine.inputs:
        out.append("inputs:")
        for i in routine.inputs:
            out.append(f"  - name: {i.name}")
            if i.ask:
                out.append(f"    ask: {_value(i.ask)}")
            if i.default:
                out.append(f"    default: {_value(i.default)}")
    out.append(f"schedule: {_value(routine.schedule)}" if routine.schedule else "schedule:")
    if routine.apps:
        out.append("apps: [" + ", ".join(_list_item(a) for a in routine.apps) + "]")
    out.append(f"paused: {'yes' if routine.paused else 'no'}")
    if routine.last_run:
        out.append(f"last_run: {_value(routine.last_run)}")
    out.append(f"version: {routine.version}")
    out += [f"{k}: {_value(v)}" for k, v in routine.extra]
    out += ["---", "", routine.body.strip("\n"), ""]
    return "\n".join(out)


def _front_matter(lines: list[str]) -> dict:
    head: dict = {}
    inputs: list[dict] | None = None
    for n, line in enumerate(lines, start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if inputs is not None and line[:1].isspace():
            item, field_ = _ITEM.match(line), _FIELD.match(line)
            if item:
                inputs.append({item.group(1): _scalar(item.group(2), n)})
            elif field_ and inputs:
                inputs[-1][field_.group(1)] = _scalar(field_.group(2), n)
            else:
                raise RecipeError(f"line {n} under inputs: should look like '  - name: month' or '    ask: Which month?'")
            continue
        inputs = None
        match = _KEY.match(line)
        if not match:
            raise RecipeError(f"line {n} should look like 'key: value'")
        key, value = match.groups()
        if key in head:
            raise RecipeError(f"{key}: is there twice")
        if key == "inputs":
            if value.strip():
                raise RecipeError("inputs: takes a list on the lines below it")
            inputs = []
            head[key] = inputs
        elif key == "apps" and value.strip().startswith("["):
            head[key] = _flow_list(value, n)
        else:
            head[key] = _scalar(value, n)
    if "inputs" in head:
        head["inputs"] = _inputs(head["inputs"])
    return head


def _inputs(items: list[dict]) -> list[RoutineInput]:
    out: list[RoutineInput] = []
    for item in items:
        unknown = set(item) - {"name", "ask", "default"}
        if unknown:
            raise RecipeError(f"an input can have name, ask and default, not {', '.join(sorted(unknown))}")
        name = input_name(item.get("name", ""))
        if not name:
            raise RecipeError("every input needs a short name: lowercase letters, digits and _")
        if any(i.name == name for i in out):
            raise RecipeError(f"the input {name} is there twice")
        out.append(RoutineInput(name, " ".join(item.get("ask", "").split()), " ".join(item.get("default", "").split())))
    return out


def input_name(text: str) -> str:
    """"Month" or "the month" to `month`; "" when nothing usable is left."""
    name = re.sub(r"[^a-z0-9_]+", "_", text.strip().lower()).strip("_")
    return name if _INPUT_NAME.match(name) else ""


def _scalar(value: str, line: int) -> str:
    value = value.strip()
    if value[:1] == '"':
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            raise RecipeError(f"line {line} opens a quote it doesn't close") from None
        if not isinstance(parsed, str):
            raise RecipeError(f"line {line} should be text")
        return parsed
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _flow_list(value: str, line: int) -> list[str]:
    value = value.strip()
    if not value.endswith("]"):
        raise RecipeError(f"line {line} opens a [ list it doesn't close")
    inner = value[1:-1]
    items = [m.group(1) or m.group(2) for m in re.finditer(r'\s*(?:"((?:[^"\\]|\\.)*)"|([^,]+?))\s*(?:,|$)', inner)]
    return [i.strip() for i in items if i and i.strip()]


def field_line(key: str, value: str) -> str:
    """One front matter line, as render() writes it."""
    return f"{key}: {_value(value)}" if value.strip() else f"{key}:"


def split(text: str) -> tuple[list[str], str] | None:
    """The front matter lines and the rest of a routine file, or None if it has no front matter."""
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None
    return lines[1:end], "\n".join(lines[end + 1:])


def _value(text: str) -> str:
    """A front matter value, quoted only when it has to be."""
    text = " ".join(text.split())
    if not text or text[0] in "\"'[{#-|>&*!%@`" or text != text.strip():
        return json.dumps(text, ensure_ascii=False)
    return text


def _list_item(text: str) -> str:
    text = " ".join(text.split())
    return json.dumps(text, ensure_ascii=False) if not text or any(c in text for c in ',[]"') else text


# ---- names


def slugify(name: str) -> str:
    """"Monday report" to `monday-report`, for the file name. Never empty."""
    ascii_ = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:MAX_SLUG].rstrip("-")
    return slug or "routine"


_FILLER = re.compile(r"\b(the|my|a|an|routine|please|do|run|start)\b")


def _words(text: str) -> str:
    return " ".join(_FILLER.sub(" ", re.sub(r"[^\w]+", " ", text.lower())).split())


def find(routines: list[Routine], ref: str) -> Routine | None:
    """The routine the user means: by slug, by name, then by its words ("the monday report", "Monday
    Report routine"), then the only one whose name contains the words. None if it's not clear."""
    ref = ref.strip()
    if not ref:
        return None
    for r in routines:
        if r.slug == ref or r.name.lower() == ref.lower():
            return r
    words = _words(ref)
    if not words:
        return None
    exact = [r for r in routines if _words(r.name) == words or r.slug == slugify(words)]
    if len(exact) == 1:
        return exact[0]
    partial = [r for r in routines if words in _words(r.name) or _words(r.name) in words]
    return partial[0] if len(partial) == 1 else None


# ---- schedules

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_TIME = re.compile(r"\b(?:at\s+)?(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.|h|uhr)?\s*$")
_MONTHDAY = re.compile(r"\b(?:on\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\b(?:\s+of)?")


@dataclass(frozen=True)
class Schedule:
    """When a routine runs: on some weekdays, or on a day of the month, at one time. Local time."""

    at: time
    weekdays: frozenset[int] = frozenset(range(7))
    """0 is Monday. Ignored when `monthday` is set."""
    monthday: int | None = None

    def __str__(self) -> str:
        at = f"at {self.at:%H:%M}"
        if self.monthday is not None:
            return f"on the {_ordinal(self.monthday)} of every month {at}"
        days = sorted(self.weekdays)
        if len(days) == 7:
            return f"every day {at}"
        if days == [0, 1, 2, 3, 4]:
            return f"every weekday {at}"
        if days == [5, 6]:
            return f"every weekend day {at}"
        names = [WEEKDAYS[d].capitalize() for d in days]
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        return f"every {joined} {at}"

    def _on(self, day: datetime) -> bool:
        if self.monthday is not None:
            return day.day == self.monthday
        return day.weekday() in self.weekdays

    def last_due(self, now: datetime) -> datetime | None:
        """The latest time it was due at or before `now`, looking back up to 62 days."""
        day = now.replace(hour=self.at.hour, minute=self.at.minute, second=0, microsecond=0)
        if day > now:
            day -= timedelta(days=1)
        for _ in range(63):
            if self._on(day):
                return day
            day -= timedelta(days=1)
        return None

    def next_due(self, now: datetime) -> datetime | None:
        """The first time it is due after `now`, looking ahead up to 62 days."""
        day = now.replace(hour=self.at.hour, minute=self.at.minute, second=0, microsecond=0)
        if day <= now:
            day += timedelta(days=1)
        for _ in range(63):
            if self._on(day):
                return day
            day += timedelta(days=1)
        return None


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def parse_schedule(text: str) -> Schedule:
    """Plain words to a Schedule. Raises RecipeError.

    "every Monday at 9", "mondays and thursdays at 8:30am", "every weekday at 8", "daily at 18:00",
    "every day at 6pm", "on the 1st of every month at 9", "monthly on the 15th at 09:30".
    """
    words = " ".join(text.lower().replace(",", " ").split())
    if not words:
        raise RecipeError("the schedule is empty")
    if words in ("noon", "at noon") or words.endswith(" noon"):
        words = words.removesuffix("noon").strip() + " at 12:00"
    match = _TIME.search(words)
    if not match:
        raise RecipeError(f"I can't tell the time in “{text}”. Say it like “every Monday at 9:00”.")
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    meridiem = (match.group(3) or "").replace(".", "")
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise RecipeError(f"“{text}” has a time that doesn't exist")
    rest = words[:match.start()].strip()
    at = time(hour, minute)
    if "month" in rest:
        day = _MONTHDAY.search(rest.replace("every month", " ").replace("monthly", " "))
        if not day or not 1 <= int(day.group(1)) <= 31:
            raise RecipeError(f"“{text}” needs a day of the month, like “on the 1st of every month at 9”")
        return Schedule(at, monthday=int(day.group(1)))
    if re.search(r"\b(every day|daily|each day|every morning|every evening)\b", rest) or rest in ("every", ""):
        if rest == "":
            raise RecipeError(f"“{text}” needs the days too, like “every day at 9”")
        return Schedule(at)
    if re.search(r"\b(weekdays?|workdays?|working days?)\b", rest) and "weekend" not in rest:
        return Schedule(at, frozenset(range(5)))
    if re.search(r"\bweekends?\b", rest):
        return Schedule(at, frozenset({5, 6}))
    days = {i for i, name in enumerate(WEEKDAYS) if re.search(rf"\b{name[:3]}(?:{name[3:]})?s?\b", rest)}
    if not days:
        raise RecipeError(f"I can't tell the days in “{text}”. Say it like “every Monday at 9:00”.")
    return Schedule(at, frozenset(days))


def schedule_or_none(text: str) -> Schedule | None:
    try:
        return parse_schedule(text) if text.strip() else None
    except RecipeError:
        return None

