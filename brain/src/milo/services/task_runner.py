from __future__ import annotations

import logging

from milo.core.logtext import private
from milo.core.ports import Clock, Harness, PlanCallback, SessionCallback, StepCallback, UsageLedger
from milo.core.types import Reply

from .context import UserContext
from .conversation import stamp
from .hands import HandsService
from .helpers import Helper

log = logging.getLogger("milo.tasks")

TASK_FAILED = "I couldn't finish that task. Check ~/Milo/logs/brain.log."
NEEDS_SCREEN = "NEEDS_SCREEN"

# Said to a helper that works without the screen. If it needs the screen after all, it comes back with
# NEEDS_SCREEN and the orchestrator queues it again for the screen.
NO_SCREEN = (f"(You have no milo-mac tools for this task. If it can only be done by working in an app on the "
             f"screen, stop at once and reply with say exactly {NEEDS_SCREEN}.)")


def first_prompt(helper: Helper, *, no_screen: bool) -> str:
    """The task as the talker wrote it, plus whatever the user changed since. Self-contained."""
    parts = [helper.description]
    if helper.amendments:
        changes = "\n".join(f"- {a}" for a in helper.amendments)
        parts.append(f"The user changed the task since:\n{changes}\nAn earlier try may have done part of it "
                     f"already: check before you redo anything.")
    if no_screen:
        parts.append(NO_SCREEN)
    return "\n\n".join(parts)


def steer_prompt(change: str) -> str:
    """Continues a helper's session after Milo stopped its turn because the user changed the task."""
    return (f"The user changed the task while you were working on it: {change}\n"
            f"Continue from where you stopped and take the change into account. Check what you already did "
            f"before you redo anything.")


def follow_up_prompt(change: str) -> str:
    """Continues the session of a helper that had finished."""
    return f"The user has a change to the task you just did: {change}"


class TaskRunner:
    """One turn of a helper on the worker harness. The orchestrator decides which turns run, and when.

    Helpers on the screen run on `harness`, which has the milo-mac tools, and hold `hands` for the turn.
    All others run on `background`, the same CLI without the Mac tools, so they can't reach for the one
    screen. Without `background` (the Mac tools are switched off) every helper runs on `harness`. A careful
    helper (one asked for in a conversation that read the screen) makes `hands` ask before changes it would
    otherwise just make; its connection tools ask through HelperQuestions, which reads the same flag.
    """

    def __init__(self, harness: Harness, ledger: UsageLedger, clock: Clock, context: UserContext, *,
                 background: Harness | None = None, hands: HandsService | None = None):
        self._harness = harness
        self._background = background
        self._ledger = ledger
        self._clock = clock
        self._context = context
        self._hands = hands

    @property
    def has_screen(self) -> bool:
        """Some helpers can work on the screen, so the others are told they can't."""
        return self._background is not None

    def first_prompt(self, helper: Helper) -> str:
        return first_prompt(helper, no_screen=self.has_screen and not helper.screen)

    async def run(self, helper: Helper, prompt: str, session_id: str | None, *, on_step: StepCallback,
                  on_session: SessionCallback, on_plan: PlanCallback) -> Reply:
        """Raises HarnessError. Cancelling it ends the worker."""
        harness = self._harness if helper.screen or self._background is None else self._background
        holds_hands = helper.screen and self._hands is not None
        started = self._clock.monotonic()
        if holds_hands:
            self._hands.begin(helper.id, careful=helper.careful)
        try:
            reply = await harness.reply(stamp(prompt, self._clock.now(), self._context.app), session_id,
                                        on_step=on_step, on_session=on_session, on_plan=on_plan)
        finally:
            if holds_hands:
                self._hands.end(helper.id)
        u = reply.usage
        log.info("helper %d %s turn%s %.1fs, %d in (%d cached), %d out, said %s", helper.number, harness.name,
                 " (careful)" if helper.careful else "", self._clock.monotonic() - started, u.input_tokens,
                 u.cached_input_tokens, u.output_tokens, private(reply.say))
        self._ledger.record("task", harness.name, u)
        return reply
