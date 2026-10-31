"""What a reply's tags do once it is over: facts, reminders, tasks, steers, stops, routine runs and undos, and the
short questions asked first when the reply's TagPolicy says so (ADR 0010, 0014, 0026).

<open>, the act tags and <write> start while the reply still streams (LiveTalk); an <open> that waited for a yes
is asked about here, with the rest.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from milo.core.events import ActionDone
from milo.core.logtext import private
from milo.core.opening import OpenRequest
from milo.core.ports import ProfileMemory, ReminderBook
from milo.core.words import dates, say

from .approvals import Approvals
from .reply_stream import ReplyParser
from .tag_policy import TagPolicy
from .ui_state import UiState

if TYPE_CHECKING:
    from .orchestrator import Orchestrator
    from .quick_actions import QuickActions
    from .routines import Routines
    from .undo import Undo

log = logging.getLogger("milo.live")

QUESTION_CHARS = 80
_FIRST_SENTENCE = re.compile(r"(?<=[.!?;:])\s")
_PLAIN = ((re.compile(r"\s+for the user\b", re.I), ""),
          (re.compile(r"\bthe user's\b", re.I), "your"),
          (re.compile(r"\bthe user\b", re.I), "you"))


def task_question(description: str, *, title: str = "", language: str = "", computer: str = "computer") -> str:
    """A yes-or-no question a person can answer at a glance: the task's first sentence, short, in the second
    person. "Open Microsoft Excel on the user's Mac and make a table. Then ..." asks "Open Microsoft Excel and
    make a table?" (`computer`: what the platform calls the machine, Platform.computer). A first sentence too long
    to fit asks about the task's `title` instead, if it has one."""
    first = _FIRST_SENTENCE.split(" ".join(description.split()), maxsplit=1)[0].rstrip(".!?;: ")
    first = re.sub(rf"\s+(on|in) the user's ({re.escape(computer)}|computer)\b", "", first, flags=re.I)
    for pattern, plain in _PLAIN:
        first = pattern.sub(plain, first)
    if len(first) > QUESTION_CHARS - 1 and title.strip():
        return say("talk.start_titled", language, title=" ".join(title.split()))
    if len(first) > QUESTION_CHARS - 1:
        first = first[:QUESTION_CHARS - 2].rsplit(" ", 1)[0].rstrip(",;: ") + "…"
    return (first[:1].upper() + first[1:] or say("talk.go_ahead", language)) + "?"


def open_question(request: OpenRequest, language: str = "") -> str:
    """Asked before opening an address or a file the user didn't name, after Milo read outside text."""
    return say("talk.open", language, what=request.what)


def remember_question(fact: str, language: str = "") -> str:
    return say("talk.remember", language, fact=fact)


def remind_question(due: datetime, what: str, language: str = "") -> str:
    return say("talk.remind", language, when=dates.date_time(due, language), what=what)


class ReplyEffects:
    """Applies a finished reply's tags, asking first where its TagPolicy says so."""

    def __init__(self, ui: UiState, profile: ProfileMemory, reminders: ReminderBook, tasks: Orchestrator, *,
                 start_open: Callable[[OpenRequest], None], approvals: Approvals | None = None,
                 routines: Routines | None = None, undo: Undo | None = None, quick: QuickActions | None = None,
                 computer: str = "computer"):
        self._ui = ui
        self._profile = profile
        self._reminders = reminders
        self._tasks = tasks
        self._start_open = start_open
        self._approvals = approvals
        self._routines = routines
        self._undo = undo
        """Takes back what a helper did on <undo> (ADR 0026). None: the tag does nothing."""
        self._quick = quick
        self._computer = computer
        self._asking: set[asyncio.Task] = set()

    def apply(self, parser: ReplyParser, rule: TagPolicy, *, held: Sequence[OpenRequest] = (),
              remember: bool = True, language: str = "") -> None:
        """Save facts and reminders, start tasks, steers and routine runs, stop helpers, and ask about the <open>
        tags that waited (`held`).

        Some tags wait for the user's yes, because text from outside could have talked the model into them; `rule`
        says which (tag_policy). Without a way to ask, tags that need a yes are dropped. `remember=False`: the reply
        was to screen data, which never becomes a fact: facts come from the user, never from the screen.
        """
        if not remember and parser.remembers:
            log.info("not remembering %d fact(s) from a turn with screen data", len(parser.remembers))
        careful, user_asked, lang = rule.careful, rule.user_asked, language
        effects: list[tuple[str, str, Callable[[], None], bool]] = []
        for request in held:  # opening asks only here, for what outside text may have named (LiveTalk._open_now)
            effects.append((open_question(request, lang), request.url or request.path,
                            lambda request=request: self._start_open(request), True))
        for fact in parser.remembers if remember else ():
            effects.append((remember_question(fact, lang), "", lambda fact=fact: self._remember(fact),
                            rule.outside))
        for due, what in parser.reminders:  # open reminders go into later system prompts: screen text asks too
            effects.append((remind_question(due, what, lang), "",
                            lambda due=due, what=what: self._remind(due, what, parser.spoken),
                            rule.outside))
        for task in parser.tasks:
            question = task_question(task.description, title=task.title, language=lang, computer=self._computer)
            # The whole task shows under the short question in the window: the user approves all of it.
            detail = "" if question.rstrip("?") == task.description.rstrip(".?") else task.description
            effects.append((question, detail, lambda task=task: self._tasks.submit(
                task.description, title=task.title, screen=task.screen, careful=careful, user_asked=user_asked,
                language=lang), rule.ask_tasks))
        for ref, change in parser.steers:  # a change to a task is a task: same rule
            question = task_question(say("talk.steer", lang, change=change), computer=self._computer)
            detail = change if question.endswith("…?") else ""
            effects.append((question, detail, lambda ref=ref, change=change: self._tasks.steer(
                ref, change, careful=careful, user_asked=user_asked), rule.ask_tasks))
        if self._routines is not None:  # a routine run is a task: same rule, unless the routine says otherwise
            for question, detail, apply, ask in self._routines.effects(parser.routines, careful=careful):
                effects.append((question, detail, apply, rule.ask_routines if ask is None else ask))
        for ref in parser.stops:  # stopping is always safe
            self._tasks.stop(ref)
        for _, _, apply, ask in effects:
            if not ask:
                apply()
        asks = [(question, detail, apply) for question, detail, apply, ask in effects if ask]
        if asks and self._approvals is None:
            log.warning("dropped %d tag(s) from a reply to outside text: nobody to ask", len(asks))
        elif asks:
            asking = asyncio.create_task(self._ask_then_apply(asyncio.current_task(), asks))
            self._asking.add(asking)
            asking.add_done_callback(self._asking.discard)

    def take_back(self, parser: ReplyParser) -> None:
        """<undo> tags. Like stopping, undoing never asks first: it only puts back what a helper changed, and Undo
        itself asks when the user changed it since."""
        for ref in parser.undos if self._undo is not None else ():
            self._undo.undo(ref)

    async def _ask_then_apply(self, turn: asyncio.Task | None,
                              effects: list[tuple[str, str, Callable[[], None]]]) -> None:
        if turn is not None:
            await asyncio.wait({turn})  # ask once the reply is over, so the question is what the bubble shows
        for question, detail, apply in effects:
            if await self._approvals.confirm(question, detail=detail):
                apply()

    def _remember(self, fact: str) -> None:
        try:
            self._profile.remember(fact)
            log.info("remembered a fact, %s", private(fact))
        except Exception:
            log.exception("could not save to the profile")

    def _remind(self, due: datetime, what: str, said: str = "") -> None:
        try:
            reminder = self._reminders.add(due, what)
            log.info("reminder set, %s", private(what))
        except Exception:
            log.exception("could not save the reminder")
            return
        if self._quick is not None:
            self._quick.reminded(reminder, said)  # its card, with Undo
        else:
            self._ui.emit(ActionDone("reminder", what, when=due.isoformat(timespec="minutes")))
