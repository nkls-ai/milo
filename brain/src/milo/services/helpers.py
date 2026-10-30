"""Helpers: the small Milos that do the work while the one you talk to keeps talking.

A helper is one piece of work the talker handed off ("Budget table in Excel"), run by its own worker
process. This module holds what a helper is and how it reads, for the app (`to_wire`) and for the talker
(`board`). Running them is the orchestrator's job.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from milo.core.types import Step, StepStatus

MAX_TITLE = 32
RECENT_STEPS = 3
"""Steps the talker sees of a working helper: the current one and the two before it."""
BOARD_FINISHED_S = 600.0
"""How long a finished helper stays on the talker's board, so "how did the Excel thing go?" still works."""
BOARD_MAX = 6
KIND_WORDS = {"read": "reading", "edit": "making changes", "search": "searching", "web": "looking things up online",
              "command": "running a command", "tool": "using a tool", "app": "working in an app"}
"""What a step of each kind is doing, in words that carry no outside text."""
APP_FOLDERS = (Path("/Applications"), Path("/System/Applications"), Path("/System/Applications/Utilities"),
               Path.home() / "Applications")

_APP_IN_TITLE = re.compile(r"^Opening (.+)$|^(?:Working in|Controlling) (.+)$| in ([^“”]+)$")
_APP_NAME = re.compile(r"^[\w .&+-]{1,40}$", re.UNICODE)
_WORDS = re.compile(r"[\w’'-]+", re.UNICODE)
_LEAD = re.compile(r"^(please|can you|could you|go and|then)\s+", re.IGNORECASE)


class HelperStatus(StrEnum):
    QUEUED = "queued"
    WORKING = "working"
    NEEDS_YOU = "needs_you"
    DONE = "done"
    FAILED = "failed"
    STOPPED = "stopped"


ACTIVE = (HelperStatus.QUEUED, HelperStatus.WORKING, HelperStatus.NEEDS_YOU)


@dataclass
class Helper:
    id: str
    """The transcript entry of its task, so the app can open it in the Milo window."""
    number: int
    """What the talker calls it: helper 1, 2, 3 in the order they were asked for."""
    title: str
    description: str
    screen: bool
    """Works in apps on the screen. Those helpers take turns, since there is one screen."""
    created_at: float
    status: HelperStatus = HelperStatus.QUEUED
    steps: list[Step] = field(default_factory=list)
    """The last few steps, newest last."""
    step_count: int = 0
    progress: float | None = None
    """0..1 through the worker's own to-do list, None while it has none."""
    session_id: str | None = None
    amendments: list[str] = field(default_factory=list)
    """What the user changed while it ran ("make it 2000 instead"), oldest first."""
    follow_up: str = ""
    """A change that came after the helper finished: the next run continues its session with it."""
    result: str = ""
    started_at: float | None = None
    finished_at: float | None = None
    questions: int = 0
    """Questions to the user it is waiting on."""
    careful: bool = False
    """Asked for in a conversation that read outside text (the screen): its tools ask before changes too.
    See ADR 0014."""
    user_asked: bool = False
    """The user asked for it themselves, in a conversation without outside text (a look at the screen they asked
    for doesn't count as outside). In auto mode its work in apps needs no question (ADR 0022). Routines, meeting
    follow-ups and anything a mail or web page could have suggested are False."""
    instructions: str = ""
    """What the worker gets instead of the description, when that is long: a routine's recipe. The
    description stays short, for the Milo window."""
    on_finish: Callable[[Helper], None] | None = field(default=None, compare=False, repr=False)
    """Called once when it ends, however it ends (a routine's run log)."""

    @property
    def active(self) -> bool:
        return self.status in ACTIVE

    @property
    def step(self) -> str:
        """What it is doing now, in a few plain words."""
        if self.status is HelperStatus.QUEUED:
            return "Waiting for the screen" if self.screen else "Waiting for a free helper"
        if self.status is HelperStatus.NEEDS_YOU:
            return "Waiting for your answer"
        if self.status is HelperStatus.STOPPED:
            return "Stopped"
        if not self.active:
            return ""
        running = [s for s in self.steps if s.status is StepStatus.RUNNING]
        if running:
            return running[-1].title
        return self.steps[-1].title if self.steps else "Getting started"

    def record(self, step: Step) -> bool:
        """Keep a step the worker reported. True if it is a new one, False for an update of a known one."""
        for i, old in enumerate(self.steps):
            if old.id == step.id:
                self.steps[i] = step
                return False
        self.steps.append(step)
        del self.steps[:-8]
        self.step_count += 1
        return True

    def to_wire(self) -> dict:
        data = {"id": self.id, "title": self.title, "status": self.status.value, "step": self.step}
        if self.progress is not None:
            data["progress"] = round(self.progress, 2)
        return data


def short_title(description: str, title: str = "") -> str:
    """The talker's title if it gave one, else the first few words of the task. Plain and short."""
    text = " ".join((title or "").split())
    if not text:
        first = re.split(r"[.!?;:\n]", description.strip(), maxsplit=1)[0]
        words = _WORDS.findall(_LEAD.sub("", first.strip()))
        text = " ".join(words[:5])
    text = text.strip(" .,") or "A task"
    text = text[:1].upper() + text[1:]
    return text if len(text) <= MAX_TITLE else text[:MAX_TITLE - 1].rstrip() + "…"


def reads_outside(step: Step) -> bool:
    """A worker step that brings in text someone else wrote: a web page, a search, a download, mail."""
    return step.kind == "web" or (step.kind == "tool" and step.title.lower().startswith(("mail", "message")))


def plain_step(step: Step, installed=None) -> str:
    """A step in words with no outside text in them, for the talker: "working in Microsoft Excel", "reading".

    Step titles name files, web pages, buttons and typed text, any of which a web page or an email could
    have chosen, so the talker never sees them. Only the kind of step goes through, and the app's name when
    it is an app installed on this Mac.
    """
    if step.kind == "app":
        match = _APP_IN_TITLE.search(step.title)
        app = next((g for g in match.groups() if g), "") if match else ""
        if app and (installed or is_installed_app)(app.strip()):
            return f"working in {app.strip()}"
    return KIND_WORDS.get(step.kind, "working")


@lru_cache(maxsize=64)
def is_installed_app(name: str) -> bool:
    """A real app on this Mac by that name, so the name is no outside text."""
    if not _APP_NAME.match(name) or name.startswith("."):
        return False
    return any((folder / f"{name}.app").is_dir() for folder in APP_FOLDERS)


def board(helpers: list[Helper], now: float, inert, installed=None) -> str:
    """The helpers as the talker sees them before each message: who does what, how far, what came of it.

    Nothing here is outside text, so it doesn't make the conversation untrusted (ADR 0010): titles,
    descriptions and changes are the talker's own words (still passed through `inert`, live_talk.untrusted),
    steps are reduced to their kind (plain_step), progress is a number. Results are not repeated here: they
    arrive once, as <task_result> data.
    """
    shown = [h for h in helpers if h.active or (h.finished_at is not None and now - h.finished_at < BOARD_FINISHED_S)]
    if not shown:
        return ""
    shown = shown[-BOARD_MAX:]
    lines = []
    for h in shown:
        head = f"- helper {h.number} “{inert(h.title, MAX_TITLE)}”: {_state(h, now)}"
        if h.active and h.status is not HelperStatus.QUEUED and h.steps:
            recent = list(dict.fromkeys(plain_step(s, installed) for s in reversed(h.steps[-RECENT_STEPS:])))
            steps = f"{h.step_count} step{'s' if h.step_count != 1 else ''}"
            head += f". {steps} so far, now {', before that '.join(recent)}"
        if h.amendments:
            head += f". Changed by the user: {inert('; '.join(h.amendments), 200)}"
        lines.append(head)
    return "<helpers>\n" + "\n".join(lines) + "\n</helpers>"


def _state(h: Helper, now: float) -> str:
    if h.status is HelperStatus.QUEUED:
        return "waiting for the screen" if h.screen else "waiting for a free helper"
    if h.status in (HelperStatus.WORKING, HelperStatus.NEEDS_YOU):
        took = _ago(now - (h.started_at or now))
        what = "waiting for the user's answer to a question" if h.status is HelperStatus.NEEDS_YOU else "working"
        where = ", on the screen" if h.screen else ""
        plan = f", about {round(h.progress * 100)}% through its plan" if h.progress is not None else ""
        return f"{what} for {took}{where}{plan}"
    ended = _ago(now - (h.finished_at or now))
    return {HelperStatus.DONE: f"finished {ended} ago", HelperStatus.FAILED: f"failed {ended} ago",
            HelperStatus.STOPPED: f"stopped {ended} ago"}[h.status]


def _ago(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"
