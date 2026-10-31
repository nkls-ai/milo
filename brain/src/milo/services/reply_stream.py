from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime

from milo.core.logtext import private
from milo.core.opening import OpenRequest, resolve_url
from milo.core.types import Emotion

log = logging.getLogger("milo.reply")

TAGS = ("remember", "reminder", "task", "look", "steer", "stop", "undo", "routine", "title", "open")
_SELF_CLOSING = ("<look/>", "<look />")
_MARKERS = tuple(f"<{name}>" for name in TAGS) + tuple(f"</{name}>" for name in TAGS) + _SELF_CLOSING
# Tags that may carry attributes: <task title="..." screen="yes">, <steer helper="2">, <stop helper="all"/>, <undo/>,
# <routine do="run" name="...">, <open app="..." url="..."/>.
_OPENER = re.compile(r"<(task|steer|stop|undo|routine|open)((?:\s+[a-z_]+\s*=\s*(?:\"[^\"<>]*\"|'[^'<>]*'|[^\s<>/\"']+))*)\s*(/?)>",
                     re.IGNORECASE)
_OPENING = re.compile(r"<(task|steer|stop|undo|routine|open)\s[^<>]*$", re.IGNORECASE)
_ATTR = re.compile(r"([a-z_]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>/]+))", re.IGNORECASE)
_MAX_OPENER = 1000  # an <open> may carry a long address
_LONGEST_MARKER = max(map(len, _MARKERS))
# "[happy]" is short; a longer bracket is real text, not an emotion tag.
_MAX_BRACKET = 16
_EMOTIONS = frozenset(e.value for e in Emotion)
_NOISE = re.compile(r"[*#`]")
_REMINDER = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{1,2}:\d{2})\s+(.+)$", re.S)


@dataclass(frozen=True)
class TaskRequest:
    """A <task> tag: the work, a short title for the small bird, and whether it needs the screen (None: unsaid)."""

    description: str
    title: str = ""
    screen: bool | None = None


@dataclass(frozen=True)
class RoutineRequest:
    """A <routine> tag: `do` (create, save, change, run, schedule, rename, pause, resume, delete), the
    routine's `name`, its other attributes, and the text inside (inputs for a run, the change for a change)."""

    do: str
    name: str
    text: str = ""
    helper: str = ""
    schedule: str | None = None
    """None when the tag has no schedule attribute; "" when it says to drop the schedule."""
    to: str = ""


class ReplyParser:
    """Turns the live model's streamed deltas into speakable text plus the side effects it asked for.

    The model opens each reply with an emotion tag like `[happy]` and may embed `<remember>fact</remember>`,
    `<reminder>YYYY-MM-DD HH:MM text</reminder>`, `<task title="..." screen="yes">description</task>`,
    `<steer helper="2">change</steer>`, `<stop helper="2"/>` (or "all") and `<look/>` (or
    `<look>what for</look>`) to see the screen. feed() returns only text
    that is safe to speak: a tag is never spoken, even when it arrives split across deltas, because text
    that could still become one is held back until it can't.
    """

    def __init__(self):
        self.emotion: Emotion | None = None
        """None until the opening tag (or the lack of one) is known."""
        self.remembers: list[str] = []
        self.reminders: list[tuple[datetime, str]] = []
        self.tasks: list[TaskRequest] = []
        self.steers: list[tuple[str, str]] = []
        """(which helper, what changed) for each <steer> tag."""
        self.stops: list[str] = []
        """Which helper each <stop> tag means: a number, "all", or "" for the only one."""
        self.undos: list[str] = []
        """Which helper's work each <undo> tag takes back: a number, or "" for the newest that can be (ADR 0026)."""
        self.routines: list[RoutineRequest] = []
        """Each <routine> tag: save, run, schedule or manage a routine (services/routines.py)."""
        self.opens: list[OpenRequest] = []
        """Each <open> tag: an app, a web page (its address resolved, see core/opening.py) or a file to open now.
        LiveTalk opens them while the reply still streams, so it reads this list after every feed()."""
        self.title = ""
        """A <title> tag: Milo's name for the conversation, when he was asked for one."""
        self.look: str | None = None
        """Set when the model asked to see the screen: what it wants to look at, often ""."""
        self.spoken = ""
        """Everything feed() and finish() returned so far."""
        self._buf = ""
        self._tag: str | None = None
        self._tag_text = ""
        self._attrs: dict[str, str] = {}

    def feed(self, delta: str) -> str:
        self._buf += delta
        return self._emit(self._drain(final=False))

    def finish(self) -> str:
        """Flush what was held back. An unclosed tag still counts: the model just forgot to close it."""
        out = self._drain(final=True)
        if self._tag is not None:
            self._collect(self._tag, self._tag_text)
            self._tag, self._tag_text = None, ""
        if self.emotion is None:
            self.emotion = Emotion.NEUTRAL
        return self._emit(out)

    def _emit(self, text: str) -> str:
        text = _NOISE.sub("", text)
        if not self.spoken:
            text = text.lstrip()
        self.spoken += text
        return text

    def _drain(self, *, final: bool) -> str:
        out: list[str] = []
        while self._buf:
            if self._tag is not None:
                if not self._inside_tag(final):
                    break
            elif self.emotion is None:
                if not self._opening(final):
                    break
            else:
                text, more = self._speech(final)
                out.append(text)
                if not more:
                    break
        return "".join(out)

    def _inside_tag(self, final: bool) -> bool:
        close = f"</{self._tag}>"
        end = self._buf.lower().find(close)
        if end < 0:
            keep = 0 if final else _partial_suffix(self._buf.lower(), close)
            self._tag_text += self._buf[:len(self._buf) - keep]
            self._buf = self._buf[len(self._buf) - keep:]
            return False
        self._collect(self._tag, self._tag_text + self._buf[:end])
        self._buf = self._buf[end + len(close):]
        self._tag, self._tag_text = None, ""
        return True

    def _opening(self, final: bool) -> bool:
        """Read the leading `[emotion]`. Anything else at the start means neutral."""
        text = self._buf.lstrip()
        if not text:
            return False
        if text[0] != "[":
            self.emotion = Emotion.NEUTRAL
            return True
        end = text.find("]")
        if end < 0:
            if len(text) <= _MAX_BRACKET and not final:
                return False
            self.emotion = Emotion.NEUTRAL
            return True
        word = text[1:end].strip().lower()
        if len(text[:end + 1]) > _MAX_BRACKET or not word.isalpha():
            self.emotion = Emotion.NEUTRAL
            return True
        self.emotion = Emotion.parse(word)
        self._buf = text[end + 1:]
        return True

    def _speech(self, final: bool) -> tuple[str, bool]:
        """Return the text before the next `<` or `[`, and whether to keep draining."""
        cut = min((i for i in (self._buf.find("<"), self._buf.find("[")) if i >= 0), default=-1)
        if cut < 0:
            text, self._buf = self._buf, ""
            return text, False
        text, rest = self._buf[:cut], self._buf[cut:]
        if rest[0] == "<":
            opener = _OPENER.match(rest, 0, _MAX_OPENER)
            if opener is not None:
                name, attrs = opener.group(1).lower(), _attributes(opener.group(2))
                self._buf = rest[opener.end():]
                if opener.group(3):
                    self._attrs = attrs
                    self._collect(name, "")
                else:
                    self._tag, self._attrs = name, attrs
                return text, True
            if not final and len(rest) < _MAX_OPENER and _OPENING.match(rest):
                self._buf = rest  # an opening tag with attributes, not closed yet
                return text, False
            lower = rest[:_LONGEST_MARKER].lower()
            marker = next((m for m in _MARKERS if lower.startswith(m)), None)
            if marker in _SELF_CLOSING:
                self.look = self.look or ""
                self._buf = rest[len(marker):]
                return text, True
            if marker is not None:
                if not marker.startswith("</"):
                    self._tag, self._attrs = marker[1:-1], {}
                self._buf = rest[len(marker):]  # a stray closing tag is dropped
                return text, True
            if not final and any(m.startswith(lower) for m in _MARKERS):
                self._buf = rest
                return text, False
            self._buf = rest[1:]
            return text + "<", True
        end = rest.find("]")
        if end < 0:
            if len(rest) <= _MAX_BRACKET and not final:
                self._buf = rest
                return text, False
            self._buf = rest[1:]
            return text + "[", True
        word = rest[1:end].strip().lower()
        if word in _EMOTIONS:
            self._buf = rest[end + 1:]  # a mid-reply emotion tag: the face is already set, just drop it
            return text, True
        self._buf = rest[1:]
        return text + "[", True

    def _collect(self, tag: str, content: str) -> None:
        content = " ".join(content.split())
        attrs, self._attrs = self._attrs, {}
        if tag == "look":
            self.look = self.look or content
            return
        if tag == "stop":
            self.stops.append(attrs.get("helper") or content)
            return
        if tag == "undo":
            self.undos.append(attrs.get("helper") or content)
            return
        if tag == "open":
            self._open(attrs, content)
            return
        if tag == "routine":
            do = attrs.get("do", "").strip().lower()
            if do:
                self.routines.append(RoutineRequest(do, " ".join(attrs.get("name", "").split()), content,
                                                    attrs.get("helper", "").strip(), attrs.get("schedule"),
                                                    " ".join(attrs.get("to", "").split())))
            return
        if not content:
            return
        if tag == "title":
            self.title = self.title or content[:80]
        elif tag == "remember":
            self.remembers.append(content)
        elif tag == "task":
            self.tasks.append(TaskRequest(content, " ".join(attrs.get("title", "").split()),
                                          _yes_no(attrs.get("screen"))))
        elif tag == "steer":
            self.steers.append((attrs.get("helper", ""), content))
        else:
            reminder = parse_reminder(content)
            if reminder is None:
                log.warning("ignoring malformed reminder tag: %s", private(content))
            else:
                self.reminders.append(reminder)


    def _open(self, attrs: dict[str, str], content: str) -> None:
        app = " ".join(attrs.get("app", "").split())
        path = attrs.get("path", "").strip()
        raw = attrs.get("url", "").strip() or ("" if path else content)
        url = resolve_url(raw) if raw else ""
        if url is None:
            log.warning("ignoring an <open> that isn't a web page: %s", private(raw))
            return
        if app or url or path:
            self.opens.append(OpenRequest(app, url, "" if url else path))


def _attributes(text: str) -> dict[str, str]:
    return {m.group(1).lower(): next(g for g in m.groups()[1:] if g is not None) for m in _ATTR.finditer(text or "")}


def _yes_no(value: str | None) -> bool | None:
    value = (value or "").strip().lower()
    if value in ("yes", "true", "1"):
        return True
    if value in ("no", "false", "0"):
        return False
    return None


def parse_reminder(content: str) -> tuple[datetime, str] | None:
    """`YYYY-MM-DD HH:MM text` to (due, text). None if it doesn't parse or the date is impossible."""
    m = _REMINDER.match(content.strip())
    if not m:
        return None
    day, clock, text = m.groups()
    try:
        return datetime.strptime(f"{day} {clock}", "%Y-%m-%d %H:%M"), text.strip()
    except ValueError:
        return None


def _partial_suffix(text: str, marker: str) -> int:
    """Length of the longest end of `text` that is a proper start of `marker`."""
    for n in range(min(len(text), len(marker) - 1), 0, -1):
        if marker.startswith(text[-n:]):
            return n
    return 0
