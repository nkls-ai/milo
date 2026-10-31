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
from dataclasses import replace

from milo.core.events import Helpers
from milo.core.logtext import private
from milo.core.ports import Clock, EventSink
from milo.core.task_scope import scope_for
from milo.core.types import Decision, Emotion, HarnessError, Reply, Scope, Step

from . import helpers as board_text
from .approvals import MONEY_KINDS, Parked
from .helpers import Helper, HelperStatus, plain_step, reads_outside, short_title
from .quiet import POLL_S
from .speaker import Speaker
from .task_runner import (NEEDS_SCREEN, NEEDS_TOOLS, TASK_FAILED, TaskRunner, answered_prompt, follow_up_prompt,
                          steer_prompt)
from .transcript import Transcript, unrecorded
from .updates import PROGRESS_AFTER_S, Milestones, UpdateMode, Updates, progress_line

log = logging.getLogger("milo.helpers")

WAIT_FOR_QUIET_S = 30.0
SHOWN_AFTER_S = 8.0
"""A finished helper stays in the `helpers` event this long, so its bird can show how it ended."""
COALESCE_S = 0.25
"""Step changes are sent to the app at most this often; status changes go at once."""
KEEP = 30
STOPPED_RESULT = "Stopped."
SAID_NO = "You said no, so I left it."
PARK_MARGIN_S = 20.0
"""A question parks this long before the harness would end the helper's turn, so the worker can still say that it
waits (ADR 0031)."""
MAX_TOOL_WAIT_S = 200.0
"""No question keeps a tool call waiting longer: Codex ends a tool call after 240 s (adapters/harness/codex.py)."""
_YES = ("yes", "always", "allowed")
VOICE_WITHIN_S = 120.0
"""A task counts as asked for by voice when the user's last turn was spoken this recently."""
PROGRESS_WAIT_S = 6.0
"""When Milo is busy at the moment for the spoken progress line, it waits this much longer at most, then skips it."""

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
                 coalesce_s: float = COALESCE_S, progress_after_s: float = PROGRESS_AFTER_S):
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
        self._progress_after_s = progress_after_s
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
        self.on_copy: Callable[[str, bool], None] | None = None
        """Puts a finished helper's `copy` on the clipboard (Writer.copy), with whether it may have read outside text.
        Only for a task asked for in a conversation: a routine, run on its schedule, never takes over the clipboard."""
        self.on_done: list[Callable[[Helper], None]] = []
        """Hear every helper that ended, after its own `on_finish` (routines look for tasks that repeat)."""
        self.watchers: list[Callable[[Helper, str], None]] = []
        """Called with (helper, "") when a helper is added and when it ends, and with (helper, the news) at
        each milestone. The owner's phone follows helpers this way (messages.py)."""

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
               on_finish: Callable[[Helper], None] | None = None, own: str = "", user_asked: bool = False,
               language: str = "") -> Helper:
        """Hand off a task. Returns at once with the new helper, queued or already working. `careful`: the
        conversation that asked for it read the screen, so its tools ask before changes too. `instructions`
        replace the description for the worker (a routine's recipe); `on_finish` hears how it ended. `own`
        = "routine": the window shows it as a conversation of its own (a routine run on its schedule).
        `user_asked`: the user asked for it in a conversation without outside text (Helper.user_asked).
        `language`: the code of the language the user asked in ("de"); the helper answers in it."""
        screen = (needs_screen(description) if screen is None else screen) and self._runner.has_screen
        self._numbers += 1
        name = short_title(description, title)
        spoken = not own and self._transcript.last_via(VOICE_WITHIN_S) == "voice"  # before the task's own entry
        helper = Helper(self._transcript.task_started(description, title=name, own=own), self._numbers, name,
                        description, screen, self._clock.monotonic(), careful=careful, instructions=instructions,
                        on_finish=on_finish, user_asked=user_asked, language=language,
                        scope=None if instructions else scope_for(description, screen=screen),
                        spoken=spoken)
        log.info("helper %d %s%s, %s", helper.number, "on the screen" if screen else "in the background",
                 " (careful)" if careful else "", private(description))
        self._add(helper)
        return helper

    def steer(self, ref: str, change: str, *, careful: bool = False, user_asked: bool = True) -> Helper | None:
        """Tell a helper the user changed the task. A finished one continues its session as a new helper.
        A `careful` change makes the helper careful from its next turn on; one that isn't `user_asked` (the
        conversation read outside text) takes the helper's user_asked away.

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
        user_asked = user_asked and helper.user_asked
        helper.user_asked = user_asked
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
        follow = Helper(self._transcript.task_started(f"{helper.description}\n\nChange: {change}",
                                                      title=helper.title),
                        self._next_number(), helper.title, helper.description, helper.screen, self._clock.monotonic(),
                        session_id=helper.session_id, amendments=[*helper.amendments, change], follow_up=change,
                        careful=careful, instructions=helper.instructions, user_asked=user_asked,
                        language=helper.language,
                        scope=helper.scope and scope_for(f"{helper.description}\n{change}", screen=helper.screen))
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

    def user_asked(self, id: str) -> bool:
        """Whether the helper `id` is still at work on something the user asked for themselves."""
        return any(h.id == id and h.active and h.user_asked for h in self._helpers)

    def question_wait(self, helper: Helper | None) -> float | None:
        """How long a question from `helper`'s tools may keep its tool call waiting before it parks: until shortly
        before the harness ends the turn. None: as long as it takes (no helper, or no limit to its turn)."""
        left = self._runner.turn_left(helper) if helper is not None else None
        return None if left is None else max(0.0, min(left - PARK_MARGIN_S, MAX_TOOL_WAIT_S))

    def park(self, helper: Helper | None, question: str, answer: asyncio.Future[str], *, grant: bool) -> None:
        """`helper`'s question outlived its turn: it stays open, and the supervisor goes on after the answer.
        `grant`: a yes lets the same question from this helper through once in the next turn (Helper.granted)."""
        if helper is None or not helper.active:
            answer.cancel()
            return
        log.info("helper %d waits for the user's answer", helper.number)
        helper.waiting, helper.waiting_for, helper.granted = answer, question, ""
        helper.grantable = grant
        self._changed(now=True)

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

    def _watch(self, helper: Helper, news: str = "") -> None:
        for watcher in self.watchers:
            try:
                watcher(helper, news)
            except Exception:
                log.exception("a helper watcher failed")

    def _add(self, helper: Helper) -> None:
        self._helpers.append(helper)
        finished = [h for h in self._helpers if not h.active]
        for old in finished[:max(0, len(self._helpers) - KEEP)]:
            self._helpers.remove(old)
        self._schedule(tell=False)
        self._changed(now=True)
        self._watch(helper)

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
        progress = asyncio.create_task(self._progress(helper)) if helper.spoken and not helper.told else None
        try:
            while True:
                attempt = asyncio.create_task(self._runner.run(
                    helper, prompt, session, on_step=lambda step: self._step(helper, step),
                    on_session=lambda sid: setattr(helper, "session_id", sid),
                    on_plan=lambda done, total: self._plan(helper, done, total)))
                self._attempts[helper.id] = attempt
                try:
                    reply = await attempt
                    helper.granted = ""  # only the turn right after the yes
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
                if helper.waiting is not None:  # its turn ended on a question the user hasn't answered yet
                    question, answer = helper.waiting_for, await helper.waiting
                    helper.waiting, helper.waiting_for = None, ""
                    self.answered(helper)
                    if answer not in _YES:
                        self._finish(helper, HelperStatus.STOPPED, SAID_NO)
                        return
                    log.info("helper %d goes on after the user's yes", helper.number)
                    helper.granted = question if helper.grantable else ""
                    prompt, session = (answered_prompt(question), helper.session_id) if helper.session_id else \
                        (f"{self._runner.first_prompt(helper)}\n\n{answered_prompt(question)}", None)
                    continue
                if reply.say.strip() == NEEDS_SCREEN and not helper.screen and self._runner.has_screen:
                    log.info("helper %d needs the screen after all, queueing it for the screen", helper.number)
                    helper.screen, helper.status, helper.session_id = True, HelperStatus.QUEUED, None
                    self._changed(now=True)
                    return
                if reply.say.strip() == NEEDS_TOOLS and helper.scope is not None:
                    log.info("helper %d needs more tools than its task named, running it with all", helper.number)
                    helper.scope = None
                    prompt, session = self._runner.first_prompt(helper), None
                    continue
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
            if progress is not None:
                progress.cancel()
            if helper.waiting is not None and not helper.waiting.done():
                helper.waiting.cancel()  # takes the question away
            helper.waiting = None
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

    async def _progress(self, helper: Helper) -> None:
        """The one spoken line for a voice task that takes a while: at about 8 s, if it is still at work and nothing
        else is being said or asked. Never in quiet mode, never more than once (ADR 0032)."""
        await asyncio.sleep(self._progress_after_s)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + PROGRESS_WAIT_S
        while not helper.told:
            if (helper.status is not HelperStatus.WORKING or self.updates is None
                    or self.updates.mode is UpdateMode.QUIET):
                return
            if not (self._quiet() or self._speaker.active or self.updates.busy() or self._reports):
                break
            if loop.time() >= deadline:
                helper.told = True
                return
            await asyncio.sleep(self._poll_s)
        if helper.told:
            return
        helper.told = True
        line = progress_line(helper)
        log.info("helper %d: saying how it goes, %s", helper.number, line)
        self.updates.spoke()
        await asyncio.wait({self._speaker.say(line, Emotion.NEUTRAL, speak=True)})

    def screen_step(self, id: str, step: Step) -> None:
        """A step the Mac tools took for the screen helper `id` (HandsService already put it in the transcript): the
        app's `helpers` event shows it as that helper's `step`, and it counts for milestones and the spoken line."""
        helper = next((h for h in self._helpers if h.id == id and h.active), None)
        if helper is not None:
            self._seen(helper, step)

    def _step(self, helper: Helper, step: Step) -> None:
        if not helper.active:
            return
        self._transcript.task_step(helper.id, step)
        if helper.user_asked and reads_outside(step):
            # What it read could steer the rest of its work: from now on it asks as usual (ADR 0022).
            helper.user_asked = False
            log.info("helper %d read outside text, so auto mode no longer covers it", helper.number)
        self._seen(helper, step)

    def _seen(self, helper: Helper, step: Step) -> None:
        if helper.record(step) and self.updates is not None:
            text = self._milestones.step(helper, step, self._clock.monotonic())
            if text is not None:
                self.updates.milestone(helper, text, plain_step(step))
                self._watch(helper, text)
        self._changed()

    def _plan(self, helper: Helper, done: int, total: int) -> None:
        if not helper.active:
            return
        helper.progress = done / total
        if self.updates is not None:
            text = self._milestones.plan(helper, done, total, self._clock.monotonic())
            if text is not None:
                self.updates.milestone(helper, text)
                self._watch(helper, text)
        self._changed()

    def _done(self, helper: Helper, reply: Reply) -> None:
        log.info("helper %d done, said %s", helper.number, private(reply.say))
        self._finish(helper, HelperStatus.DONE, reply.say)
        if self.on_result is not None:
            self.on_result(helper.description, reply.say)
        if reply.copy and not helper.instructions and self.on_copy is not None:
            self.on_copy(reply.copy, helper.careful or not helper.user_asked)
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
        self._watch(helper)
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


class ScreenSteps:
    """The transcript as HandsService sees it: each step of the Mac tools also goes to the orchestrator, so the screen
    helper's `step` in the app (the caption under the outline) and its spoken line follow what it does on screen.
    `orchestrator` returns the orchestrator, which compose builds after the Mac tools."""

    def __init__(self, transcript: Transcript, orchestrator: Callable[[], Orchestrator]):
        self._transcript = transcript
        self._orchestrator = orchestrator

    def task_step(self, id: str, step: Step) -> None:
        self._transcript.task_step(id, step)
        self._orchestrator().screen_step(id, step)


class HelperQuestions:
    """Approvals as the helpers' tools see them: while a question waits, the helper it is for shows
    needs_you. `screen` says whether these are the Mac tools' questions (the screen helper's).
    `orchestrator` returns the orchestrator, which compose builds after the tools."""

    def __init__(self, approvals, orchestrator: Callable[[], Orchestrator], *, screen: bool):
        self._approvals = approvals
        self._orchestrator = orchestrator
        self._screen = screen

    async def confirm(self, summary: str, *, detail: str = "", scope: Scope | None = None, undo: bool = False,
                      money: bool = False) -> bool:
        """Raises Parked when the question outlives the helper's turn (ADR 0031)."""
        if undo and not money and not self._approvals.asks_undoable():
            return True  # can be undone and nobody asks about it in this mode: the helper doesn't need you
        helper = self._orchestrator().asking(screen=self._screen)
        if self._granted(helper, summary, money=money):
            return True
        parked = False
        try:
            return await self._approvals.confirm(summary, detail=detail, scope=scope, undo=undo, money=money,
                                                 **self._waiting(helper, summary, grant=scope is None and not money))
        except Parked:
            parked = True
            raise
        finally:
            if not parked:
                self._orchestrator().answered(helper)

    async def approve(self, kind: str, summary: str, *, scope: Scope | None = None) -> Decision:
        """Approvals.approve, careful when the helper that asks is (see Orchestrator.careful). `scope` names the
        app; the helper that asks becomes its task, so the user's Allow lasts as long as that helper (ADR 0022).
        When it can't tell which helper asks, only Allow always covers it."""
        careful = self._orchestrator().careful(screen=self._screen)
        if not self._approvals.asks(kind, careful=careful):
            return await self._approvals.approve(kind, summary, careful=careful)
        helper = self._orchestrator().asking(screen=self._screen)
        if scope is not None:
            scope = replace(scope, task=helper.id if helper is not None else "")
        money = kind in MONEY_KINDS
        if self._granted(helper, summary, money=money):
            return Decision(True, self._approvals.policy.level(kind), "yes")
        decision = None
        try:
            decision = await self._approvals.approve(kind, summary, careful=careful, scope=scope,
                                                     **self._waiting(helper, summary, grant=scope is None and not money))
            return decision
        finally:
            if decision is None or decision.answer != "parked":
                self._orchestrator().answered(helper)

    def _waiting(self, helper: Helper | None, question: str, *, grant: bool) -> dict:
        """The question may keep the helper's tool call waiting until shortly before its turn ends, then parks."""
        orchestrator = self._orchestrator()
        wait_s = orchestrator.question_wait(helper)
        if wait_s is None:
            return {}
        return {"wait_s": wait_s, "parked": lambda answer: orchestrator.park(helper, question, answer, grant=grant)}

    def _granted(self, helper: Helper | None, question: str, *, money: bool) -> bool:
        """The worker tries again what the user said yes to while it waited: that yes counts, once, for this helper
        in the turn after it. Never for money: only a new click answers that (ADR 0023)."""
        if helper is None or money or not helper.granted or helper.granted != question:
            return False
        helper.granted = ""
        self._orchestrator().answered(helper)
        log.info("helper %d: the user's yes while it waited covers this", helper.number)
        return True

    def __getattr__(self, name: str):
        return getattr(self._approvals, name)
