"""Progress updates while helpers work: when one reached a milestone, and how Milo tells the user.

Milestones come from simple rules over the steps the worker reports (a new app opened, the first change
to a file, the first look at the web, halfway through its plan), so spotting them costs nothing. What
happens then depends on `[chat] updates`:

- quiet: nothing. The small birds and the Milo window show the progress.
- bubble: a short note in the bubble ("Budget table: Opening Excel"), never spoken.
- chatty: Milo also says it, phrased by the chat model, at most once every `spoken_gap_s`. Otherwise a note.

Results and questions that need a yes don't go through here: they always come through.

Whatever the mode (except quiet), a task the user asked for by voice that is still at work after about 8 s gets one
short spoken line in the user's language, from what it is doing ("Opening Microsoft Excel now…"), built here from
plain words, with no model call (`progress_line`, ADR 0032). Then Milo stays quiet until the result or a question.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from milo.core.events import Bubble
from milo.core.ports import Clock, EventSink
from milo.core.types import Step
from milo.core.words import say

from .helpers import _APP_IN_TITLE, Helper, is_installed_app

log = logging.getLogger("milo.updates")

MILESTONE_KINDS = ("app", "edit", "web")
"""Step kinds whose first appearance in a helper is news: it opened an app, started changing things, went online."""
FIRST_AFTER_S = 5.0
"""Nothing in the first seconds: the talker has just said it is on it."""
GAP_S = 20.0
"""At most one milestone per helper in this long."""


PROGRESS_AFTER_S = 8.0
"""A voice task still at work after this long gets its one spoken line."""

_TOPICS = (("calendar", "calendar"), ("mail", "mail"), ("email", "mail"), ("draft", "mail"), ("reminder", "reminders"),
           ("note", "notes"), ("file", "files"), ("folder", "files"))
"""Words in the titles of Milo's own tool steps (core/wording.py) and what they are about."""
_KINDS = {"web": "web", "edit": "edit", "search": "files"}
"""Step kinds with a line of their own (core/words/updates.py); the rest say "still"."""
_BOOKKEEPING = ("Noting how things were", "Keeping a copy of", "Checking which apps are open")


def progress_line(helper: Helper, installed: Callable[[str], bool] = is_installed_app) -> str:
    """One short spoken line about what `helper` is doing, in its user's language. Only the kind of work and the name
    of an app installed here go in, never a file name or other text the step may carry."""
    lang = helper.language
    steps = [s for s in helper.steps if not s.title.startswith(_BOOKKEEPING)]
    step = next((s for s in reversed(steps) if s.kind == "app"), steps[-1] if steps else None)
    if step is None:
        return say("updates.still", lang)
    match = _APP_IN_TITLE.search(step.title)
    app = next((g for g in match.groups() if g), "").strip() if match else ""
    if app and installed(app):
        return say("updates.open" if step.title.startswith("Opening ") else "updates.app", lang, app=app)
    words = step.title.lower()
    topic = next((t for word, t in _TOPICS if word in words), "")
    if topic:
        return say(f"updates.{topic}", lang)
    return say(f"updates.{_KINDS.get(step.kind, 'still')}", lang)


class UpdateMode(StrEnum):
    QUIET = "quiet"
    BUBBLE = "bubble"
    CHATTY = "chatty"


@dataclass
class _Seen:
    kinds: set[str] = field(default_factory=set)
    apps: set[str] = field(default_factory=set)
    last_at: float = float("-inf")
    halfway: bool = False


class Milestones:
    """Decides, from step kinds and titles alone, which steps are worth telling the user about."""

    def __init__(self, *, first_after_s: float = FIRST_AFTER_S, gap_s: float = GAP_S):
        self._first_after_s = first_after_s
        self._gap_s = gap_s
        self._seen: dict[str, _Seen] = {}

    def step(self, helper: Helper, step: Step, now: float) -> str | None:
        """A step the helper just started. Returns the milestone's words, or None."""
        seen = self._seen.setdefault(helper.id, _Seen())
        news = False
        if step.title.startswith("Opening ") and step.title not in seen.apps:
            seen.apps.add(step.title)
            news = True
        if step.kind in MILESTONE_KINDS and step.kind not in seen.kinds:
            seen.kinds.add(step.kind)
            news = True
        return step.title if news and self._due(helper, seen, now) else None

    def plan(self, helper: Helper, done: int, total: int, now: float) -> str | None:
        """The worker's to-do list moved. Halfway through a list of three or more is a milestone."""
        seen = self._seen.setdefault(helper.id, _Seen())
        if seen.halfway or total < 3 or done * 2 < total or done >= total:
            return None
        seen.halfway = True
        return f"Halfway there, {done} of {total} done" if self._due(helper, seen, now) else None

    def forget(self, helper_id: str) -> None:
        self._seen.pop(helper_id, None)

    def _due(self, helper: Helper, seen: _Seen, now: float) -> bool:
        started = helper.started_at if helper.started_at is not None else now
        if now - started < self._first_after_s or now - seen.last_at < self._gap_s:
            return False
        seen.last_at = now
        return True


class Updates:
    """Tells the user about milestones the way `mode()` says.

    `busy()` is true while a note would get in the way: Milo is answering or speaking, the user is recording,
    or a question waits for a yes (the bubble must keep showing it). `speak(text)` asks the talker to say an
    update in its own words; it returns False when the talker isn't free, and the update becomes a note.
    """

    def __init__(self, sink: EventSink, mode: Callable[[], UpdateMode], clock: Clock, *,
                 busy: Callable[[], bool] = lambda: False, speak: Callable[[str], bool] | None = None,
                 spoken_gap_s: float = 45.0, note_gap_s: float = 6.0):
        self._sink = sink
        self._mode = mode
        self._clock = clock
        self._busy = busy
        self.speak = speak
        self._spoken_gap_s = spoken_gap_s
        self._note_gap_s = note_gap_s
        self._spoken_at = float("-inf")
        self._noted_at = float("-inf")

    @property
    def mode(self) -> UpdateMode:
        return self._mode()

    def busy(self) -> bool:
        return self._busy()

    def spoke(self) -> None:
        """Milo just said something about a helper himself: chatty mode's gap starts again from now."""
        self._spoken_at = self._noted_at = self._clock.monotonic()

    def milestone(self, helper: Helper, text: str, plain: str | None = None) -> None:
        """`text` goes in the bubble. `plain` is the same news without outside text (helpers.plain_step), for
        the chat model to phrase; defaults to `text` when that has none (e.g. plan progress)."""
        mode = self._mode()
        if mode is UpdateMode.QUIET or self._busy():
            return
        now = self._clock.monotonic()
        line = f"{helper.title}: {text}"
        if mode is UpdateMode.CHATTY and self.speak is not None and now - self._spoken_at >= self._spoken_gap_s:
            if self.speak(f"{helper.title}: {plain if plain is not None else text}"):
                self._spoken_at = self._noted_at = now
                return
        if now - self._noted_at < self._note_gap_s:
            return
        self._noted_at = now
        self._sink.emit(Bubble(line))


class LiveSettings:
    """Settings that apply without a restart (`[chat] updates`, `[harness] max_helpers`).

    Reads config.toml again when it changed, at most every `check_s`: one stat, no tokens. A file that
    doesn't parse keeps the last good values, with a warning in the log. `parse` turns the file's text into
    (updates, max_helpers) and raises on bad values.
    """

    def __init__(self, path: Path, parse: Callable[[str], tuple[str, int]], updates: str, max_helpers: int, *,
                 check_s: float = 2.0, monotonic: Callable[[], float] = time.monotonic):
        self._path = path
        self._parse = parse
        self._updates = UpdateMode(updates)
        self._max_helpers = max_helpers
        self._check_s = check_s
        self._monotonic = monotonic
        self._checked_at = monotonic()
        self._mtime = self._stat()

    def updates(self) -> UpdateMode:
        self._refresh()
        return self._updates

    def max_helpers(self) -> int:
        self._refresh()
        return self._max_helpers

    def use(self, updates: str, max_helpers: int) -> None:
        """The Settings window just saved config.toml: use its values now, without waiting for the next check."""
        self._updates, self._max_helpers = UpdateMode(updates), max_helpers
        self._mtime = self._stat()

    def _stat(self) -> float | None:
        try:
            return self._path.stat().st_mtime
        except OSError:
            return None

    def _refresh(self) -> None:
        now = self._monotonic()
        if now - self._checked_at < self._check_s:
            return
        self._checked_at = now
        mtime = self._stat()
        if mtime is None or mtime == self._mtime:
            return
        self._mtime = mtime
        try:
            updates, max_helpers = self._parse(self._path.read_text())
        except Exception as e:
            log.warning("config.toml changed but can't be read, keeping the old updates setting: %s", e)
            return
        if (UpdateMode(updates), max_helpers) != (self._updates, self._max_helpers):
            log.info("settings changed: updates %s, max_helpers %d", updates, max_helpers)
        self._updates, self._max_helpers = UpdateMode(updates), max_helpers
