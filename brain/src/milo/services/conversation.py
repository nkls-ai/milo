from __future__ import annotations

import logging
from datetime import datetime

from milo.core.ports import Clock, Harness, StepCallback, UsageLedger
from milo.core.types import HarnessError, Reply

log = logging.getLogger("milo.conversation")


def stamp(text: str, now: datetime, app: str | None) -> str:
    """Prefix a turn with the time and frontmost app so the model needs no tool call for either."""
    where = f", frontmost app: {app}" if app else ""
    return f"[{now:%A %Y-%m-%d %H:%M}{where}]\n{text}"


class Conversation:
    """The harness session behind delegated tasks: one session id, reset after a long pause, every call metered."""

    def __init__(self, harness: Harness, ledger: UsageLedger, clock: Clock, idle_reset_s: float):
        self._harness = harness
        self._ledger = ledger
        self._clock = clock
        self._idle_reset_s = idle_reset_s
        self.session_id: str | None = None
        self._last_turn_at: float | None = None

    def prompt(self, text: str, app: str | None) -> str:
        return stamp(text, self._clock.now(), app)

    async def chat(self, text: str, app: str | None, *, source: str = "chat",
                   on_step: StepCallback | None = None) -> Reply:
        """Answer a turn, continuing the session. Raises HarnessError if even a fresh session fails.

        `source` labels the call in the usage ledger. `on_step` hears what the agent does while it works.
        """
        now = self._clock.monotonic()
        if self._last_turn_at is None or now - self._last_turn_at > self._idle_reset_s:
            self.session_id = None
        prompt = self.prompt(text, app)
        try:
            reply = await self._ask(prompt, self.session_id, source, on_step)
        except HarnessError:
            if not self.session_id:
                raise
            log.warning("resuming session %s failed, starting a fresh one", self.session_id)
            self.session_id = None
            reply = await self._ask(prompt, None, source, on_step)
        self.session_id = reply.session_id
        self._last_turn_at = self._clock.monotonic()
        return reply

    async def proactive(self, text: str, app: str | None) -> Reply:
        """A one-off call for heartbeat wording. Never touches the chat session."""
        return await self._ask(self.prompt(text, app), None, "proactive")

    async def _ask(self, prompt: str, session_id: str | None, source: str,
                   on_step: StepCallback | None = None) -> Reply:
        started = self._clock.monotonic()
        if on_step is None:
            reply = await self._harness.reply(prompt, session_id)
        else:
            reply = await self._harness.reply(prompt, session_id, on_step=on_step)
        u = reply.usage
        log.info("%s %s turn %.1fs, %d in (%d cached), %d out", source, self._harness.name,
                 self._clock.monotonic() - started, u.input_tokens, u.cached_input_tokens, u.output_tokens)
        self._ledger.record(source, self._harness.name, u)
        return reply
