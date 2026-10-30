"""One question per piece of work, and apps the user always allows (ADR 0022).

A question about working in an app (replacing filled cells, a script that only talks to that app, borrowing the
mouse there, a careful helper's first change) carries a `Scope`: the apps it acts in and the task that asks. The
user's Allow then covers that work for the rest of the task, and Allow always covers it in that app from now on.
Questions without a scope (sending, deleting, buying, scripts that can run other programs, terminals, system
settings) ask every time, and the never-rules come before any of this.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping

from milo.core.types import AppRef, Scope

log = logging.getLogger("milo.permits")


class Permits:
    """What the user already allowed: work in an app for one task (Allow), or always (Allow always).

    `ask` is "step" (an Allow covers only that step), "task" (the rest of that task in that app) or "auto" (work
    the user asked for needs no question at all: `user_asked(task)` says whether they did; anything else is
    asked once per task). Allow always works in every mode. `save` gets the always-allowed apps whenever they
    change, as dicts for config.toml.
    """

    def __init__(self, ask: str = "task", always: Iterable[AppRef | Mapping | str] = (),
                 save: Callable[[list[dict]], None] | None = None):
        self.ask = ask
        self._always: list[AppRef] = []
        self.use(always)
        self.save = save
        self.user_asked: Callable[[str], bool] = lambda task: False
        self._tasks: dict[str, list[AppRef]] = {}

    @property
    def always(self) -> tuple[AppRef, ...]:
        return tuple(self._always)

    def use(self, apps: Iterable[AppRef | Mapping | str]) -> None:
        """The always-allowed apps as config.toml has them now (the Settings window took one away)."""
        self._always = []
        for app in apps:
            ref = app if isinstance(app, AppRef) else AppRef.of(app)
            if ref.key and not any(ref.same(a) for a in self._always):
                self._always.append(ref)

    def covers(self, scope: Scope) -> str:
        """"always" or "task" if every app of `scope` is allowed that way, else ""."""
        if not scope.apps:
            return ""
        if all(any(app.same(a) for a in self._always) for app in scope.apps):
            return "always"
        if self.ask == "auto" and scope.task and self.user_asked(scope.task):
            return "auto"
        granted = self._tasks.get(scope.task, []) if scope.task and self.ask != "step" else []
        if all(any(app.same(a) for a in granted) for app in scope.apps) and granted:
            return "task"
        return ""

    def allowed(self, scope: Scope, *, always: bool) -> None:
        """The user said Allow (or Allow always) to a question about `scope`."""
        if always:
            new = [app for app in scope.apps if not any(app.same(a) for a in self._always)]
            if new:
                self._always.extend(new)
                log.info("always allowed now: %s", ", ".join(a.label for a in new))
                self._save()
        if scope.task and self.ask != "step":
            granted = self._tasks.setdefault(scope.task, [])
            granted.extend(app for app in scope.apps if not any(app.same(a) for a in granted))

    def end(self, task: str) -> None:
        """The task is over: its Allow ends with it."""
        self._tasks.pop(task, None)

    def _save(self) -> None:
        if self.save is None:
            return
        try:
            self.save([a.to_dict() for a in self._always])
        except Exception:
            log.exception("could not save the always-allowed apps")
