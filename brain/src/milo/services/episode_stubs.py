"""Episode stubs written as the day goes: a line per conversation turn, task, routine run, look and (if switched
on) dictation, with the time, the app, the people named and a pointer to the raw record.

Each stub is a decorator around a port the brain already writes to, so the services that write there don't
change: the transcript store sees every finished turn and task, the dictation history every dictation, the
screen eyes every look. A routine run is a task too, but its stub comes from the routines service, which knows
the routine's name, inputs and apps. The nightly consolidation turns the stubs into proper summaries.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from milo.core.memory import Episode, new_id
from milo.core.ports import DictationHistory, ScreenEyes, TranscriptStore
from milo.core.types import ScreenCapture

log = logging.getLogger("milo.memory")

MAX_PART = 300
ANSWERS = frozenset({"yes", "no", "ja", "nein"})
"""A turn that only answers one of Milo's questions isn't worth an episode of its own."""
DICTATION_GAP = timedelta(seconds=90)
"""Dictations into the same app this close together are one episode (phrase by phrase in "type" mode)."""

Record = Callable[[Episode], None]
"""Memory.record."""


def _cut(text: str, limit: int = MAX_PART) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _at(entry: dict, fallback: Callable[[], datetime]) -> datetime:
    try:
        return datetime.fromisoformat(str(entry["ts"]))
    except (KeyError, ValueError):
        return fallback()


class EpisodeTranscript:
    """TranscriptStore that also writes episode stubs: one per user turn and Milo's answer, one per task.

    `outside()` says whether the live conversation carries outside text right now (task results, the screen,
    recalled outside episodes); its turns are then marked untrusted, since the replies may quote that text.
    `elsewhere(id)` says the task with that entry id gets its episode from somewhere else (a routine run, from
    RoutineEpisodes), so it isn't written twice.
    """

    def __init__(self, inner: TranscriptStore, record: Record, *, now: Callable[[], datetime],
                 app: Callable[[], str | None] = lambda: None, people: Callable[[str], tuple[str, ...]] = lambda t: (),
                 outside: Callable[[], bool] = lambda: False, elsewhere: Callable[[str], bool] = lambda id: False):
        self._inner = inner
        self._record = record
        self._now = now
        self._app = app
        self._people = people
        self._outside = outside
        self._elsewhere = elsewhere
        self._waiting: dict | None = None
        """The user's last turn, until Milo's answer to it arrives."""

    def append(self, entry: dict) -> None:
        self._inner.append(entry)
        try:
            self._stub(entry)
        except Exception:
            log.exception("could not write an episode stub")

    def tail(self, n: int) -> list[dict]:
        return self._inner.tail(n)

    def _stub(self, entry: dict) -> None:
        kind = entry.get("kind")
        if kind == "user":
            if self._waiting is not None:
                self._turn(self._waiting, None)
            self._waiting = entry
        elif kind == "milo":
            if self._waiting is not None:
                self._turn(self._waiting, entry)
                self._waiting = None
        elif kind == "task":
            if self._waiting is not None:
                self._turn(self._waiting, None)
                self._waiting = None
            self._task(entry)

    def _turn(self, user: dict, milo: dict | None) -> None:
        said = _cut(user.get("text", ""))
        if not said or said.lower().strip(" .!") in ANSWERS:
            return
        summary = f"The user said: “{said}”"
        if milo is not None and str(milo.get("text", "")).strip():
            summary += f" Milo answered: “{_cut(milo['text'])}”"
        at = _at(user, self._now)
        app = self._app()
        self._record(Episode(new_id(at), at, "conversation", summary, self._people(summary),
                             (app,) if app else (), f"transcript:{user.get('id', '')}", not self._outside()))

    def _task(self, entry: dict) -> None:
        if self._elsewhere(str(entry.get("id", ""))):
            return
        at = _at(entry, self._now)
        done = entry.get("status") == "done"
        summary = f"Task: {_cut(entry.get('text', ''))}"
        result = _cut(entry.get("result", ""))
        if result:
            summary += f" {'Result' if done else 'It failed'}: {result}"
        elif not done:
            summary += " It failed."
        app = self._app()
        # The result may quote mail, files or web pages: outside text.
        self._record(Episode(new_id(at), at, "task", summary, self._people(summary), (app,) if app else (),
                             f"transcript:{entry.get('id', '')}", trusted=False))


class RoutineEpisodes:
    """Routines.on_episode: each finished routine run as a "task" episode, named after the routine.

    Points at the run's transcript entry like any task. The result is helper output, so it is outside text.
    """

    def __init__(self, record: Record, *, people: Callable[[str], tuple[str, ...]] = lambda t: ()):
        self._record = record
        self._people = people

    def __call__(self, run: dict) -> None:
        at = datetime.fromisoformat(str(run["at"]))
        inputs = ", ".join(f"{k} {v}" for k, v in (run.get("inputs") or {}).items())
        summary = f"Routine “{_cut(run.get('name', ''), 80)}”"
        summary += " on its schedule" if run.get("scheduled") else ""
        summary += f" for {_cut(inputs, 120)}" if inputs else ""
        outcome = str(run.get("outcome", ""))
        result = _cut(run.get("result", ""))
        if outcome == "done":
            summary += f". Result: {result}" if result else ", done."
        else:
            summary += f", {outcome or 'not finished'}" + (f": {result}" if result else ".")
        task = str(run.get("task") or "")
        source = f"transcript:{task}" if task else f"routine:{run.get('slug', '')}"
        apps = tuple(str(a) for a in run.get("apps") or ())
        self._record(Episode(new_id(at), at, "task", summary, self._people(summary), apps, source, trusted=False))


class EpisodeDictations:
    """DictationHistory that also writes the dictation as an episode. Only wired in when the user wants it."""

    def __init__(self, inner: DictationHistory | None, record: Record, *, now: Callable[[], datetime]):
        self._inner = inner
        self._record = record
        self._now = now
        self._last: Episode | None = None

    def append(self, text: str, app: str | None) -> None:
        if self._inner is not None:
            self._inner.append(text, app)
        now = self._now()
        apps = (app,) if app else ()
        last = self._last
        if last is not None and last.apps == apps and now - last.at <= DICTATION_GAP:
            # The same dictation going on: a newer version of the same episode.
            summary = _cut(f"{last.summary} {text}", 2000)
            episode = Episode(last.id, last.at, "dictation", summary, (), apps, last.source)
        else:
            episode = Episode(new_id(now), now, "dictation", _cut(text, 2000), (), apps, "dictation-history")
        self._last = episode
        self._record(episode)


class EpisodeEyes:
    """ScreenEyes that notes each look as an episode: which app and window. What was on screen stays out."""

    def __init__(self, inner: ScreenEyes, record: Record, *, now: Callable[[], datetime]):
        self._inner = inner
        self._record = record
        self._now = now

    async def look(self, mode: str = "window") -> ScreenCapture:
        capture = await self._inner.look(mode)
        if not capture.error and capture.app:
            noted(capture, self._record, self._now())
        return capture


def noted(capture: ScreenCapture, record: Record, at: datetime) -> None:
    """Record a look at `capture` (also used for "What's this?", which arrives without a look request)."""
    window = f", window “{_cut(capture.window, 120)}”" if capture.window else ""
    record(Episode(new_id(at), at, "look", f"Milo looked at the screen: {capture.app}{window}.", (), (capture.app,),
                   "screen", trusted=False))
