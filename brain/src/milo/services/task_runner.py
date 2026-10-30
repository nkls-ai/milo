from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable

from milo.core.types import Emotion, HarnessError

from .context import UserContext
from .conversation import Conversation
from .quiet import POLL_S, wait_while
from .speaker import Speaker
from .transcript import Transcript, unrecorded

log = logging.getLogger("milo.tasks")

TASK_FAILED = "I couldn't finish that task. Check ~/Milo/logs/brain.log."
WAIT_FOR_QUIET_S = 30.0


class TaskRunner:
    """Real work the live model handed off (files, research, several steps), done by the agent harness.

    Tasks run in the background one at a time, on the harness session in `conversation`, so the agent
    keeps context across them and works in its sandbox. When one finishes Milo says the result. If the
    user is mid-turn (`quiet()`), the result waits for the turn to end, and is shown silently if that
    takes longer than `wait_s`. Each task and the steps the agent takes show in `transcript`.
    """

    def __init__(self, conversation: Conversation, speaker: Speaker, context: UserContext,
                 quiet: Callable[[], bool] = lambda: False, *, wait_s: float = WAIT_FOR_QUIET_S,
                 poll_s: float = POLL_S, transcript: Transcript | None = None):
        self._conversation = conversation
        self._transcript = transcript or unrecorded()
        self._speaker = speaker
        self._context = context
        self._quiet = quiet
        self._wait_s = wait_s
        self._poll_s = poll_s
        self._queue: deque[str] = deque()
        self._worker: asyncio.Task | None = None
        self.on_result: Callable[[str, str], None] | None = None
        """Called with (description, what Milo said) after each finished task, e.g. LiveTalk.note."""

    @property
    def busy(self) -> bool:
        return self._worker is not None and not self._worker.done()

    def submit(self, description: str) -> None:
        self._queue.append(description)
        if not self.busy:
            self._worker = asyncio.create_task(self._work())

    async def idle(self) -> None:
        """Wait until every submitted task is done and reported. For tests and shutdown."""
        while self.busy:
            await asyncio.wait({self._worker})

    async def _work(self) -> None:
        while self._queue:
            await self._run(self._queue.popleft())

    async def _run(self, description: str) -> None:
        log.info("task started: %s", description)
        task_id = self._transcript.task_started(description)
        try:
            reply = await self._conversation.chat(description, self._context.app, source="task",
                                                  on_step=lambda step: self._transcript.task_step(task_id, step))
        except HarnessError as e:
            log.error("task failed: %s", e)
            self._transcript.task_finished(task_id, False, TASK_FAILED)
            await self._report(TASK_FAILED, Emotion.CONFUSED, speak=False)
            return
        except Exception:
            log.exception("task crashed")
            self._transcript.task_finished(task_id, False, TASK_FAILED)
            await self._report(TASK_FAILED, Emotion.CONFUSED, speak=False)
            return
        log.info("task done: %s", reply.say)
        self._transcript.task_finished(task_id, True, reply.say)
        if self.on_result is not None:
            self.on_result(description, reply.say)
        if reply.say.strip():
            await self._report(reply.say, reply.emotion)

    async def _report(self, text: str, emotion: Emotion, *, speak: bool = True) -> None:
        free = await wait_while(self._quiet, self._wait_s, self._poll_s)
        await asyncio.wait({self._speaker.say(text, emotion, speak=speak and free)})
