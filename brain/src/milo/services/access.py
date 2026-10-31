"""The system's permissions, before Milo needs them (ADR 0025).

The first time Milo controls an app the system asks the user whether he may. Before that question appears, he says
in one line what is coming; if the user says no, he says so with a Fix it button, and the worker hears a plain
"not allowed" instead of an error from deep inside a script. An app that is already allowed shows nothing.

Clicks, typing and window reading need one switch, screenshots another. Both are checked before the first action
that needs them, and a missing one shows the same Fix it note.

Everything here is in the words of core/access.py. What a need is called on this system, how it asks and where it
is fixed come from the app (`AppAccess`), so another system's app can answer the same requests.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections.abc import Callable

from milo.core.access import Access, AccessAnswer, Need
from milo.core.events import AccessNote
from milo.core.ports import AppAccess, EventSink
from milo.core.types import AppRef, HandsError, Step, StepStatus

log = logging.getLogger("milo.access")

PAUSE_S = 1.5
"""How long the line stays alone before the system's question covers it, so it can be read first."""

# What Milo says. `system` is the system's name from the app, or "Your computer".
ASKING = "{system} will ask once whether I may use {app}. {click}"
REFUSED_NOW = "Okay, I won't use {app}. If you change your mind, Fix it shows the switch."
REFUSED_BEFORE = "I'm not allowed to use {app} yet. Fix it shows the switch."
NEEDS = {Need.UI: "To work in other apps' windows I need {label}. Fix it shows where to switch it on.",
         Need.SCREEN: "To see the screen I need {label}. Fix it shows where to switch it on."}

# What the worker hears.
WORKER_CONTROL = ("The user didn't allow Milo to control {app}; they were shown how to change that. Don't use {app} "
                  "through scripts, sheet_write, sheet_read or write_document again in this task. If the job can be "
                  "done another way, do that; otherwise stop and tell the user in one sentence what is left.")
WORKER_NEEDS = {
    Need.UI: ("Milo may not read or work other apps' windows on this computer yet; the user was shown how to allow "
              "it. Use sheet_write, sheet_read, write_document or a script if they fit; otherwise stop and "
              "tell the user in one sentence what is left."),
    Need.SCREEN: ("Milo may not take screenshots on this computer yet; the user was shown how to allow it. Use "
                  "window_text, ax_tree or ax_find instead."),
}

# The milo-mac tools by what they need. The rest (list_apps, open_app) need nothing.
_UI_TOOLS = frozenset({"window_text", "ax_tree", "ax_find", "ax_press", "ax_set_value", "click", "type", "key",
                       "scroll"})
_APP_TOOLS = frozenset({"sheet_write", "sheet_read", "write_document"})


class AccessGate:
    """Checks the system's permission before an action needs it, and lets the user know when it is missing.

    A yes is kept until Milo is told otherwise (a refusal found while running, `refused`), so an allowed app costs
    one check per brain. A no is never kept: the next task checks again and sees a switch the user turned on.
    """

    def __init__(self, access: AppAccess, sink: EventSink, *, transcript=None,
                 say: Callable[[str], None] | None = None, pause_s: float = PAUSE_S):
        """`say` speaks the line before the system asks (the bubble shows it either way). `transcript`, with
        `task_step(task_id, step)`, shows the wait for the user's answer as a step of the task."""
        self._access = access
        self._sink = sink
        self._transcript = transcript
        self._say = say
        self._pause_s = pause_s
        self._yes: set[str] = set()
        """Needs and apps the system said yes to: "ui", "screen", "control:<app key>"."""
        self._told: set[str] = set()
        """What the user was shown a refusal for during `_task`, so a task shows each one once."""
        self._task = ""
        self._lock = asyncio.Lock()
        self._ids = itertools.count(1)

    async def before(self, tool: str, args: dict, task_id: str) -> None:
        """Before Milo looks at what `tool` would touch: the checks that start nothing and ask nobody (the screen,
        other apps' windows), and filling cells, whose look already reads the sheet through the app. Raises
        HandsError in words for the worker when the system won't let `tool` run."""
        if tool == "screenshot":
            return await self.need(Need.SCREEN, task_id)
        if tool in _UI_TOOLS:
            return await self.need(Need.UI, task_id)
        if tool == "sheet_write":
            return await self.control(AppRef(str(args["app"])), task_id)

    async def before_running(self, tool: str, args: dict, task_id: str, apps: list[AppRef] | None = None) -> None:
        """Once Milo's own checks passed and the user said yes where he asked, just before `tool` runs: the apps it
        controls. Never earlier, so an action Milo refuses or the user turns down never starts an app or brings up
        the system's question. `apps`: the apps a script names, which services/hands.py reads from it."""
        if tool in _APP_TOOLS:
            return await self.control(AppRef(str(args["app"])), task_id)
        for app in apps or ():
            await self.control(app, task_id)

    async def control(self, app: AppRef, task_id: str = "") -> None:
        """Milo may control `app`, or raises HandsError. The first time the system would ask, Milo says so first."""
        key = f"control:{app.key}"
        if not app.key or key in self._yes:
            return
        async with self._lock:
            if key in self._yes:
                return
            answer = await self._access.check(Need.CONTROL, app)
            app = answer.app or app
            asked = answer.access is Access.ASK
            if asked:
                answer = await self._ask(answer, app, task_id)
            if answer.access is Access.YES:
                self._yes.add(key)
            elif answer.access is Access.NO:
                self._refuse(app, task_id, REFUSED_NOW if asked else REFUSED_BEFORE)
                raise HandsError(WORKER_CONTROL.format(app=app.label))

    async def need(self, need: Need, task_id: str = "") -> None:
        """The system lets Milo see the screen (SCREEN) or work other apps' windows (UI), or raises HandsError."""
        if need.value in self._yes:
            return
        answer = await self._access.check(need)
        if answer.access is Access.YES:
            self._yes.add(need.value)
            return
        if answer.access is Access.UNKNOWN:
            return
        self._show(task_id, need.value, NEEDS[need].format(label=answer.label or "your permission"), need)
        raise HandsError(WORKER_NEEDS[need])

    def refused(self, app: AppRef, task_id: str = "") -> str:
        """The system refused `app` while a script ran (it was allowed before, or the check couldn't tell). Shows
        the Fix it note once per task and returns the words for the worker."""
        self._yes.discard(f"control:{app.key}")
        self._refuse(app, task_id, REFUSED_BEFORE)
        return WORKER_CONTROL.format(app=app.label)

    async def allows(self, app: AppRef) -> tuple[bool, str]:
        """For the connection tools (tool socket): whether Milo may control `app`, and the words if not."""
        try:
            await self.control(app)
        except HandsError as e:
            return False, str(e)
        return True, ""

    async def places(self, app: AppRef) -> tuple[str, ...] | None:
        """Where `app` can save without the system stopping it to ask the user (None: anywhere). Snapshots and
        working copies an app writes for Milo go there."""
        return await self._access.places(app)

    # ---- inside

    async def _ask(self, answer: AccessAnswer, app: AppRef, task_id: str) -> AccessAnswer:
        """Say what is coming, give it a moment, then have the system ask."""
        click = f"Click {answer.button}." if answer.button else "Please allow it."
        line = ASKING.format(system=answer.system or "Your computer", app=app.label, click=click)
        self._sink.emit(AccessNote(Need.CONTROL.value, Access.ASK.value, line, app.name, app.bundle))
        if self._say is not None:
            self._say(line)
        step = Step(f"access_{next(self._ids)}", "app", f"Asking to use {app.label}", "", StepStatus.RUNNING)
        self._step(task_id, step)
        if self._pause_s:
            await asyncio.sleep(self._pause_s)
        answer = await self._access.request(Need.CONTROL, app)
        log.info("the system asked about %s: %s", app.label, answer.access.value)
        self._step(task_id, Step(step.id, step.kind, step.title, step.detail,
                                 StepStatus.FAILED if answer.access is Access.NO else StepStatus.DONE))
        return answer

    def _refuse(self, app: AppRef, task_id: str, words: str) -> None:
        self._show(task_id, f"control:{app.key}", words.format(app=app.label), Need.CONTROL, app)

    def _show(self, task_id: str, what: str, text: str, need: Need, app: AppRef | None = None) -> None:
        if task_id != self._task:
            self._task, self._told = task_id, set()
        if what in self._told:
            return
        self._told.add(what)
        self._sink.emit(AccessNote(need.value, Access.NO.value, text, app.name if app else "",
                                   app.bundle if app else ""))

    def _step(self, task_id: str, step: Step) -> None:
        if self._transcript is not None and task_id:
            self._transcript.task_step(task_id, step)
