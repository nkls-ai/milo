from __future__ import annotations

import logging
import re
from datetime import datetime

from milo.core.logtext import private
from milo.core.types import Emotion

log = logging.getLogger("milo.reply")

TAGS = ("remember", "reminder", "task")
_MARKERS = tuple(f"<{name}>" for name in TAGS) + tuple(f"</{name}>" for name in TAGS)
_LONGEST_MARKER = max(map(len, _MARKERS))
# "[happy]" is short; a longer bracket is real text, not an emotion tag.
_MAX_BRACKET = 16
_EMOTIONS = frozenset(e.value for e in Emotion)
_NOISE = re.compile(r"[*#`]")
_REMINDER = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{1,2}:\d{2})\s+(.+)$", re.S)


class ReplyParser:
    """Turns the live model's streamed deltas into speakable text plus the side effects it asked for.

    The model opens each reply with an emotion tag like `[happy]` and may embed `<remember>fact</remember>`,
    `<reminder>YYYY-MM-DD HH:MM text</reminder>` and `<task>description</task>`. feed() returns only text
    that is safe to speak: a tag is never spoken, even when it arrives split across deltas, because text
    that could still become one is held back until it can't.
    """

    def __init__(self):
        self.emotion: Emotion | None = None
        """None until the opening tag (or the lack of one) is known."""
        self.remembers: list[str] = []
        self.reminders: list[tuple[datetime, str]] = []
        self.tasks: list[str] = []
        self.spoken = ""
        """Everything feed() and finish() returned so far."""
        self._buf = ""
        self._tag: str | None = None
        self._tag_text = ""

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
            lower = rest[:_LONGEST_MARKER].lower()
            marker = next((m for m in _MARKERS if lower.startswith(m)), None)
            if marker is not None:
                if not marker.startswith("</"):
                    self._tag = marker[1:-1]
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
        if not content:
            return
        if tag == "remember":
            self.remembers.append(content)
        elif tag == "task":
            self.tasks.append(content)
        else:
            reminder = parse_reminder(content)
            if reminder is None:
                log.warning("ignoring malformed reminder tag: %s", private(content))
            else:
                self.reminders.append(reminder)


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
