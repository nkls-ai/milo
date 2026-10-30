from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from milo.core.ports import AudioInput, Clock, ProactiveEngine
from milo.core.types import HarnessError, Nudge, Signals

from .context import UserContext
from .conversation import Conversation
from .quiet import POLL_S, wait_while
from .speaker import Speaker
from .ui_state import UiState

log = logging.getLogger("milo.heartbeat")

# Nudges the user asked for. They still show while muted.
REMINDER_RULES = frozenset({"reminder", "reminders"})
WAIT_FOR_TURN_S = 30.0


class HeartbeatRunner:
    """Ticks the proactive engine and delivers its nudges without getting in the user's way.

    `busy` says a live turn is running. A nudge waits for it to end (up to `wait_s`) instead of cutting
    Milo off, and is shown silently if the turn takes longer.
    """

    def __init__(self, engine: ProactiveEngine, context: UserContext, conversation: Conversation,
                 speaker: Speaker, ui: UiState, mic: AudioInput, clock: Clock,
                 busy: Callable[[], bool] = lambda: False, *, wait_s: float = WAIT_FOR_TURN_S,
                 poll_s: float = POLL_S):
        self._engine = engine
        self._context = context
        self._conversation = conversation
        self._speaker = speaker
        self._ui = ui
        self._mic = mic
        self._clock = clock
        self._busy = busy
        self._wait_s = wait_s
        self._poll_s = poll_s
        self.muted = False

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self._engine.tick_s)
            try:
                await self.tick()
            except Exception:
                log.exception("heartbeat tick failed")

    async def tick(self) -> None:
        for nudge in self._engine.tick(self.signals()):
            await self.deliver(nudge)

    def signals(self) -> Signals:
        return Signals(now=self._clock.now(), idle_s=self._context.idle_s(), app=self._context.app)

    async def deliver(self, nudge: Nudge) -> None:
        if self.muted and nudge.rule not in REMINDER_RULES:
            return
        log.info("nudge %s: %s", nudge.rule, nudge.text)
        await wait_while(self._busy, self._wait_s, self._poll_s)
        text = nudge.text
        today = self._clock.now().date()
        if nudge.llm_prompt and not self._in_turn() and self._engine.budget.allow(today):
            self._engine.budget.spend(today)
            try:
                text = (await self._conversation.proactive(nudge.llm_prompt, self._context.app)).say or text
            except HarnessError as e:
                log.warning("proactive wording failed, using the template: %s", e)
        # Muted: reminders still show, but silently (see milo.core.events.Mute).
        quiet = self.muted or self._mic.active or self._in_turn()
        self._speaker.say(text, nudge.emotion, speak=nudge.speak and not quiet)

    def _in_turn(self) -> bool:
        return self._ui.thinking or self._busy()
