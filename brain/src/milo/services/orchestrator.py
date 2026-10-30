"""The orchestrator: Milo-you-talk-to hands work to helpers, keeps an eye on them, and steers or stops them.

The talker never waits for a helper. submit() returns at once; each helper runs in its own worker process,
up to `max_helpers` at a time. Helpers that work on the screen take turns, since there is one screen and
one mouse; the others run alongside. While they work, their steps go to the transcript (the Milo window),
the `helpers` event (the small birds) and the board the talker reads before every message, so it can say
how far they are. When one finishes Milo says the result, and the talker gets it as untrusted data.

Steering stops the worker's turn and continues its session with the change ("make it 2000 instead"); if
the session can't be continued, the task starts over with the change written in. See ADR 0011.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable

from milo.core.events import Helpers
from milo.core.logtext import private
from milo.core.ports import Clock, EventSink
from milo.core.types import Decision, Emotion, HarnessError, Reply, Step

from . import helpers as board_text
from .helpers import Helper, HelperStatus, plain_step, short_title
from .quiet import POLL_S
from .speaker import Speaker
from .task_runner import NEEDS_SCREEN, TASK_FAILED, TaskRunner, follow_up_prompt, steer_prompt
from .transcript import Transcript, unrecorded
from .updates import Milestones, Updates

log = logging.getLogger("milo.helpers")

WAIT_FOR_QUIET_S = 30.0
SHOWN_AFTER_S = 8.0
"""A finished helper stays in the `helpers` event this long, so its bird can show how it ended."""
COALESCE_S = 0.25
"""Step changes are sent to the app at most this often; status changes go at once."""
KEEP = 30
STOPPED_RESULT = "Stopped."

# Words that mean working in an app on the screen, for tasks the talker didn't mark either way.
_SCREEN_WORDS = re.compile(
    r"\b(click|klick\w*|type (it )?in(to)?|fill (in|out)|on (the|my) screen|bildschirm|in (the )?window|"
    r"excel|numbers|pages|keynote|word|powerpoint|safari|chrome|firefox|finder|system settings|"
    r"spreadsheet|tabelle)\b", re.IGNORECASE)


def needs_screen(description: str) -> bool:
    """A guess for tasks the talker didn't mark: does this sound like work in an app on the screen?"""
    return bool(_SCREEN_WORDS.search(description))


class Orchestrator:
    """Runs helpers in parallel and keeps everyone informed. See the module docstring.

    `max_helpers` is read again before every start, so a changed setting applies at once. `quiet()` is true
    while the user talks or Milo answers: results wait for it to pass (up to `wait_s`, then they are only
    shown). `inert` makes outside text harmless for the talker's prompt.
    """

    def __init__(self, runner: TaskRunner, speaker: Speaker, sink: EventSink, clock: Clock, *,
                 transcript: Transcript | None = None, max_helpers: Callable[[], int] = lambda: 3,
                 quiet: Callable[[], bool] = lambda: False, updates: Updates | None = None,
                 milestones: Milestones | None = None, inert: Callable[[str, int], str] = lambda s, n: s[:n],
                 wait_s: float = WAIT_FOR_QUIET_S, poll_s: float = POLL_S, shown_after_s: float = SHOWN_AFTER_S,
                 coalesce_s: float = COALESCE_S):
        self._runner = runner
        self._speaker = speaker
        self._sink = sink
        self._clock = clock
        self._transcript = transcript or unrecorded()
        self._max_helpers = max_helpers
        self._quiet = quiet
        self.updates = updates
        self._milestones = milestones or Milestones()
        self._inert = inert
        self._wait_s = wait_s
        self._poll_s = poll_s
        self._shown_after_s = shown_after_s
        self._coalesce_s = coalesce_s
        self._helpers: list[Helper] = []
        self._numbers = 0
        self._supervisors: dict[str, asyncio.Task] = {}
        self._attempts: dict[str, asyncio.Task] = {}
        self._pending: dict[str, list[str]] = {}
        """Changes the user made to a running helper that its worker hasn't been told yet."""
        self._reports: set[asyncio.Task] = set()
        self._speaking = asyncio.Lock()
        self._emit_handle: asyncio.TimerHandle | None = None
        self._expire_handle: asyncio.TimerHandle | None = None
        self._sent: Helpers | None = None
        self.on_result: Callable[[str, str], None] | None = None
        """Called with (description, what Milo said) after each finished helper, e.g. LiveTalk.note."""
        self.on_done: list[Callable[[Helper], None]] = []
        """Hear every helper that ended, after its own `on_finish` (routines look for tasks that repeat)."""

    # ---- what the talker and the app see

    @property
    def helpers(self) -> list[Helper]:
        return list(self._helpers)

    @property
    def reporting(self) -> bool:
        """A helper's result is waiting to be said or being said."""
        return bool(self._reports)

    @property
    def busy(self) -> bool:
        return any(h.active for h in self._helpers)

    def board(self) -> str:
        """The helpers for the talker's next message, "" when there are none worth mentioning."""
        return board_text.board(self._helpers, self._clock.monotonic(), self._inert)

    def snapshot(self) -> Helpers:
        """The `helpers` event as of now: active helpers and those that finished moments ago."""
        now = self._clock.monotonic()
        shown = [h for h in self._helpers
                 if h.active or (h.finished_at is not None and now - h.finished_at < self._shown_after_s)]
        return Helpers([h.to_wire() for h in shown])

    def find(self, ref: str) -> Helper | None:
        """A helper by the talker's number ("2", "#2", "helper 2") or by id. "" means the only active one."""
        ref = ref.strip().lower().removeprefix("helper").strip().lstrip("#").strip()
        if not ref:
            active = [h for h in self._helpers if h.active]
            return active[0] if len(active) == 1 else None
        for h in reversed(self._helpers):
            if (ref.isdigit() and h.number == int(ref)) or h.id == ref:
                return h
        return None

    # ---- what the talker (and the Stop button) can do

    def submit(self, description: str, *, title: str = "", screen: bool | None = None,
               careful: bool = False, instructions: str = "",
               on_finish: Callable[[Helper], None] | None = None) -> Helper:
        """Hand off a task. Returns at once with the new helper, queued or already working. `careful`: the
        conversation that asked for it read the screen, so its tools ask before changes too. `instructions`
        replace the description for the worker (a routine's recipe); `on_finish` hears how it ended."""
        screen = (needs_screen(description) if screen is None else screen) and self._runner.has_screen
        self._numbers += 1
        helper = Helper(self._transcript.task_started(description), self._numbers, short_title(description, title),
                        description, screen, self._clock.monotonic(), careful=careful, instructions=instructions,
                        on_finish=on_finish)
        log.info("helper %d %s%s, %s", helper.number, "on the screen" if screen else "in the background",
                 " (careful)" if careful else "", private(description))
        self._add(helper)
        return helper

    def steer(self, ref: str, change: str, *, careful: bool = False) -> Helper | None:
        """Tell a helper the user changed the task. A finished one continues its session as a new helper.
        A `careful` change makes the helper careful from its next turn on.

        Returns the helper that will act on it, or None if `ref` names no helper.
        """
        helper = self.find(ref)
        change = " ".join(change.split())
        if helper is None or not change:
            log.info("no helper %r to steer", ref)
            return None
        log.info("steering helper %d, %s", helper.number, private(change))
        careful = careful or helper.careful
        helper.careful = careful
        if helper.status is HelperStatus.QUEUED:
            helper.amendments.append(change)
            self._changed(now=True)
            return helper
        if helper.active:
            helper.amendments.append(change)
            self._pending.setdefault(helper.id, []).append(change)
            attempt = self._attempts.get(helper.id)
            if attempt is not None and not attempt.done():
                attempt.cancel()  # the supervisor continues the session with the change
            self._changed(now=True)
            return helper
        follow = Helper(self._transcript.task_started(f"{helper.description}\n\nChange: {change}"),
                        self._next_number(), helper.title, helper.description, helper.screen, self._clock.monotonic(),
                        session_id=helper.session_id, amendments=[*helper.amendments, change], follow_up=change,
                        careful=careful, instructions=helper.instructions)
        self._add(follow)
        return follow

    def stop(self, ref: str) -> list[Helper]:
        """Stop one helper, or every active one for "all". Returns the helpers that were stopped."""
        if ref.strip().lower() in ("all", "*", "everything"):
            targets = [h for h in self._helpers if h.active]
        else:
            helper = self.find(ref)
            targets = [helper] if helper is not None and helper.active else []
        for helper in targets:
            log.info("stopping helper %d", helper.number)
            self._finish(helper, HelperStatus.STOPPED, STOPPED_RESULT)
            supervisor = self._supervisors.get(helper.id)
            if supervisor is not None:
                supervisor.cancel()
        if targets:
            self._changed(now=True)
            self._schedule()
        return targets

    async def idle(self) -> None:
        """Wait until every helper is done and reported. For tests and shutdown."""
        while self._supervisors or self._reports:
            await asyncio.wait({*self._supervisors.values(), *self._reports})

    async def close(self) -> None:
        """Stop every helper and its worker. On shutdown."""
        self.stop("all")
        for task in (*self._supervisors.values(), *self._reports):
            task.cancel()
        await asyncio.gather(*self._supervisors.values(), *self._reports, return_exceptions=True)

    # ---- questions

    def asking(self, *, screen: bool) -> Helper | None:
        """A question to the user started. Marks the helper it is for as needing the user, if that is clear:
        the screen helper for Mac actions, else the only helper at work."""
        working = [h for h in self._helpers if h.status in (HelperStatus.WORKING, HelperStatus.NEEDS_YOU)]
        candidates = [h for h in working if h.screen] if screen else working
        if len(candidates) != 1:
            return None
        helper = candidates[0]
        helper.questions += 1
        helper.status = HelperStatus.NEEDS_YOU
        self._changed(now=True)
        return helper

    def careful(self, *, screen: bool) -> bool:
        """Whether a question from the helpers' tools is for a careful helper: the screen helper for Mac
        actions, else the helper at work. When it can't tell which of several helpers asks, any careful one
        counts, so a careful helper never acts unasked."""
        working = [h for h in self._helpers if h.status in (HelperStatus.WORKING, HelperStatus.NEEDS_YOU)]
        return any(h.careful for h in working if h.screen or not screen)

    def answered(self, helper: Helper | None) -> None:
        if helper is None:
            return
        helper.questions = max(0, helper.questions - 1)
        if helper.questions == 0 and helper.status is HelperStatus.NEEDS_YOU:
            helper.status = HelperStatus.WORKING
            self._changed(now=True)

    # ---- running

    def _next_number(self) -> int:
        self._numbers += 1
        return self._numbers

    def _add(self, helper: Helper) -> None:
        self._helpers.append(helper)
        finished = [h for h in self._helpers if not h.active]
        for old in finished[:max(0, len(self._helpers) - KEEP)]:
            self._helpers.remove(old)
        self._schedule(tell=False)
        self._changed(now=True)

    def _schedule(self, *, tell: bool = True) -> None:
        """Start queued helpers while there is room: at most max_helpers at work, one on the screen."""
        working = [h for h in self._helpers if h.status in (HelperStatus.WORKING, HelperStatus.NEEDS_YOU)]
        room = self._max_helpers() - len(working)
        screen_taken = any(h.screen for h in working)
        started = False
        for helper in [h for h in self._helpers if h.status is HelperStatus.QUEUED]:
            if room <= 0:
                break
            if helper.screen and screen_taken:
                continue
            helper.status = HelperStatus.WORKING
            helper.started_at = self._clock.monotonic()
            self._supervisors[helper.id] = asyncio.create_task(self._supervise(helper))
            room -= 1
            screen_taken = screen_taken or helper.screen
            started = True
        if started and tell:
            self._changed(now=True)

    async def _supervise(self, helper: Helper) -> None:
        """Run a helper's turns until it is done: the first one, and one more for each change the user made."""
        if helper.follow_up and helper.session_id:
            prompt, session = follow_up_prompt(helper.follow_up), helper.session_id
        else:
            prompt, session = self._runner.first_prompt(helper), None
        try:
            while True:
                attempt = asyncio.create_task(self._runner.run(
                    helper, prompt, session, on_step=lambda step: self._step(helper, step),
                    on_session=lambda sid: setattr(helper, "session_id", sid),
                    on_plan=lambda done, total: self._plan(helper, done, total)))
                self._attempts[helper.id] = attempt
                try:
                    reply = await attempt
                except asyncio.CancelledError:
                    if asyncio.current_task().cancelling() or not self._pending.get(helper.id):
                        raise  # stopped
                    prompt, session = self._continue(helper)
                    continue
                except HarnessError as e:
                    if session is None:
                        raise
                    log.warning("helper %d: continuing its session failed (%s), starting over", helper.number, e)
                    prompt, session = self._runner.first_prompt(helper), None
                    continue
                if self._pending.get(helper.id):
                    prompt, session = self._continue(helper)  # changed just as the turn ended
                    continue
                if reply.say.strip() == NEEDS_SCREEN and not helper.screen and self._runner.has_screen:
                    log.info("helper %d needs the screen after all, queueing it for the screen", helper.number)
                    helper.screen, helper.status, helper.session_id = True, HelperStatus.QUEUED, None
                    self._changed(now=True)
                    return
                self._done(helper, reply)
                return
        except asyncio.CancelledError:
            if helper.active:
                self._finish(helper, HelperStatus.STOPPED, STOPPED_RESULT)
            raise
        except HarnessError as e:
            log.error("helper %d failed: %s", helper.number, e)
            self._failed(helper)
        except Exception:
            log.exception("helper %d crashed", helper.number)
            self._failed(helper)
        finally:
            self._attempts.pop(helper.id, None)
            self._pending.pop(helper.id, None)
            self._supervisors.pop(helper.id, None)
            self._schedule()

    def _continue(self, helper: Helper) -> tuple[str, str | None]:
        """The next turn after the user changed a running helper's task: its session with the change, or
        the whole task again with every change written in when there is no session to continue."""
        changes = self._pending.pop(helper.id, [])
        if helper.session_id:
            return steer_prompt("; ".join(changes)), helper.session_id
        return self._runner.first_prompt(helper), None

    def _step(self, helper: Helper, step: Step) -> None:
        if not helper.active:
            return
        self._transcript.task_step(helper.id, step)
        if helper.record(step) and self.updates is not None:
            text = self._milestones.step(helper, step, self._clock.monotonic())
            if text is not None:
                self.updates.milestone(helper, text, plain_step(step))
        self._changed()

    def _plan(self, helper: Helper, done: int, total: int) -> None:
        if not helper.active:
            return
        helper.progress = done / total
        if self.updates is not None:
            text = self._milestones.plan(helper, done, total, self._clock.monotonic())
            if text is not None:
                self.updates.milestone(helper, text)
        self._changed()

    def _done(self, helper: Helper, reply: Reply) -> None:
        log.info("helper %d done, said %s", helper.number, private(reply.say))
        self._finish(helper, HelperStatus.DONE, reply.say)
        if self.on_result is not None:
            self.on_result(helper.description, reply.say)
        if reply.say.strip():
            self._report(reply.say, reply.emotion, speak=True)

    def _failed(self, helper: Helper) -> None:
        self._finish(helper, HelperStatus.FAILED, TASK_FAILED)
        self._report(TASK_FAILED, Emotion.CONFUSED, speak=False)

    def _finish(self, helper: Helper, status: HelperStatus, result: str) -> None:
        helper.status, helper.result, helper.finished_at = status, result, self._clock.monotonic()
        if status is HelperStatus.DONE:
            helper.progress = 1.0 if helper.progress is not None else None
        self._milestones.forget(helper.id)
        self._transcript.task_finished(helper.id, status is HelperStatus.DONE, result)
        self._changed(now=True)
        finished, helper.on_finish = helper.on_finish, None
        if finished is not None:
            try:
                finished(helper)
            except Exception:
                log.exception("helper %d: on_finish failed", helper.number)
        for listener in self.on_done:
            try:
                listener(helper)
            except Exception:
                log.exception("helper %d: on_done failed", helper.number)

    def _report(self, text: str, emotion: Emotion, *, speak: bool) -> None:
        task = asyncio.create_task(self._say(text, emotion, speak=speak))
        self._reports.add(task)
        task.add_done_callback(self._reports.discard)

    async def _say(self, text: str, emotion: Emotion, *, speak: bool) -> None:
        """One result at a time, after the user's turn and whatever Milo is saying, so none cuts off another."""
        async with self._speaking:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self._wait_s
            while self._quiet() or self._speaker.active:
                if loop.time() >= deadline:
                    speak = False
                    break
                await asyncio.sleep(self._poll_s)
            await asyncio.wait({self._speaker.say(text, emotion, speak=speak)})

    # ---- telling the app

    def _changed(self, *, now: bool = False) -> None:
        """Send the helpers event: now for a new status, within COALESCE_S for a step."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if now or self._coalesce_s <= 0:
            if self._emit_handle is not None:
                self._emit_handle.cancel()
                self._emit_handle = None
            self._emit()
        elif self._emit_handle is None:
            self._emit_handle = loop.call_later(self._coalesce_s, self._emit)

    def _emit(self) -> None:
        self._emit_handle = None
        event = self.snapshot()
        if event != self._sent:
            self._sent = event
            self._sink.emit(event)
        if self._expire_handle is not None:
            self._expire_handle.cancel()
            self._expire_handle = None
        now = self._clock.monotonic()
        ends = [h.finished_at + self._shown_after_s - now for h in self._helpers
                if h.finished_at is not None and now - h.finished_at < self._shown_after_s]
        if ends:
            self._expire_handle = asyncio.get_running_loop().call_later(max(0.05, min(ends)), self._emit)


class HelperQuestions:
    """Approvals as the helpers' tools see them: while a question waits, the helper it is for shows
    needs_you. `screen` says whether these are the Mac tools' questions (the screen helper's).
    `orchestrator` returns the orchestrator, which compose builds after the tools."""

    def __init__(self, approvals, orchestrator: Callable[[], Orchestrator], *, screen: bool):
        self._approvals = approvals
        self._orchestrator = orchestrator
        self._screen = screen

    async def confirm(self, summary: str, *, detail: str = "") -> bool:
        helper = self._orchestrator().asking(screen=self._screen)
        try:
            return await self._approvals.confirm(summary, detail=detail)
        finally:
            self._orchestrator().answered(helper)

    async def approve(self, kind: str, summary: str) -> Decision:
        """Approvals.approve, careful when the helper that asks is (see Orchestrator.careful)."""
        careful = self._orchestrator().careful(screen=self._screen)
        if not self._approvals.asks(kind, careful=careful):
            return await self._approvals.approve(kind, summary, careful=careful)
        helper = self._orchestrator().asking(screen=self._screen)
        try:
            return await self._approvals.approve(kind, summary, careful=careful)
        finally:
            self._orchestrator().answered(helper)

    def __getattr__(self, name: str):
        return getattr(self._approvals, name)
