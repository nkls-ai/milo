from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from milo.core.events import Bubble, Heard
from milo.core.ports import Clock, LiveModel, ProfileMemory, ReminderBook, UsageLedger
from milo.core.types import Emotion, HarnessError, MiloState

from .context import UserContext
from .conversation import stamp
from .reply_stream import ReplyParser
from .speaker import Speaker, Utterance
from .task_runner import TaskRunner
from .transcript import Transcript, unrecorded
from .ui_state import UiState

log = logging.getLogger("milo.live")

HICCUP = "My brain hiccuped. Check ~/Milo/logs/brain.log."

DEFAULT_PERSONA = "You are Milo, a small, cheerful voice assistant who lives in the corner of the user's Mac."

REPLY_RULES = """\
## How you reply

You talk out loud. Your reply is spoken while you are still writing it.

- Start every reply with exactly one emotion tag: [neutral], [happy], [excited], [thinking], [concerned], \
[sad], [sleepy] or [confused].
- Then speak: one to three short sentences in plain spoken language. No markdown, lists, code, emoji or URLs.
- Reply in the language the user speaks.
- Each user message starts with [weekday date time, frontmost app]. That is context, not something the \
user said.

Tags are never read aloud. Put them after what you say:

- <remember>one-line fact</remember> when the user tells you something about themselves worth keeping long \
term. Never passwords or other secrets.
- <reminder>YYYY-MM-DD HH:MM what to remind them of</reminder> to set a reminder, in the user's local time. \
Say when you will remind them.
- <task>a complete, self-contained description</task> for work that needs files, the web or several steps. \
A background agent does it and you will tell the user the result when it is done. Say a short \
acknowledgement, nothing more.
"""


class LiveTalk:
    """A user turn, typed or spoken, answered by the streaming live model and spoken as it arrives.

    One turn runs at a time; a new turn or the talk key interrupts the running one at once (barge-in).
    The conversation stays open in the model between turns and starts fresh after `idle_reset_s` of
    silence, with the persona, profile and open reminders reloaded into its system prompt.
    """

    def __init__(self, model: LiveModel, speaker: Speaker, ui: UiState, context: UserContext, clock: Clock,
                 profile: ProfileMemory, reminders: ReminderBook, ledger: UsageLedger,
                 persona: Callable[[], str], idle_reset_s: float, tasks: TaskRunner,
                 transcript: Transcript | None = None):
        self._model = model
        self._transcript = transcript or unrecorded()
        self._speaker = speaker
        self._ui = ui
        self._context = context
        self._clock = clock
        self._profile = profile
        self._reminders = reminders
        self._ledger = ledger
        self._persona = persona
        self._idle_reset_s = idle_reset_s
        self._tasks = tasks
        self._turn: asyncio.Task | None = None
        self._streaming = False
        self._stopping: asyncio.Task | None = None
        self._system: str | None = None
        """The system prompt the running conversation started with. None: start one before the next turn."""
        self._last_turn_at: float | None = None
        self._starting = asyncio.Lock()  # warm() at boot and the first turn may race
        self._notes: list[str] = []

    @property
    def busy(self) -> bool:
        """A turn is running: Milo is thinking or still speaking his answer."""
        return self._turn is not None and not self._turn.done()

    def start(self, text: str, *, via: str = "voice", speak: bool = True) -> asyncio.Task:
        """Run a turn in the background so listening and dictation keep working while Milo answers."""
        self.interrupt(rest=False)
        self._turn = asyncio.create_task(self.turn(text, via=via, speak=speak))
        return self._turn

    def interrupt(self, *, rest: bool = True) -> bool:
        """Stop thinking and speaking now, including speech that isn't a turn (a nudge, a task result).

        Returns whether anything was stopped. rest=False when the caller shows the next state itself.
        """
        stopped = self.busy or self._speaker.active
        if self._streaming:
            self._streaming = False
            self._stopping = asyncio.create_task(self._model.interrupt())
        if self.busy:
            self._turn.cancel()
        self._speaker.interrupt()
        self._ui.thinking = False
        if rest and stopped:
            self._ui.rest()
        return stopped

    def note(self, description: str, result: str) -> None:
        """A background task finished. The next user message carries the result, so Milo knows about it."""
        self._notes.append(f"[Background task done: {description} -> {result}]")

    async def warm(self) -> None:
        """Start the conversation ahead of the first turn. Raises HarnessError."""
        await self._ensure_conversation()

    async def turn(self, text: str, *, via: str = "voice", speak: bool = True) -> None:
        """`via` is "voice" or "typed", for the transcript. speak=False answers in the bubble without audio."""
        self._ui.emit(Heard(text))
        self._transcript.user(text, via)
        await self._settle_interrupt()
        self._ui.thinking = True
        self._ui.set_state(MiloState.THINKING)
        self._ui.set_emotion(Emotion.THINKING)
        parser = ReplyParser()
        utterance: Utterance | None = None
        shown: str | None = None  # transcript id of the reply, once it has text
        started = self._clock.monotonic()
        first_at: float | None = None
        try:
            await self._ensure_conversation()
            self._streaming = True
            async for delta in self._model.turn(self._prompt(text)):
                if first_at is None:
                    first_at = self._clock.monotonic()
                speech = parser.feed(delta)
                if speak and utterance is None and parser.emotion is not None:
                    utterance = self._speaker.utterance(parser.emotion)
                if speech:
                    shown = self._show(shown, parser, speech)
                    if speak:
                        utterance.add(speech)
            self._streaming = False
        except asyncio.CancelledError:
            self._end_reply(shown, parser)
            raise
        except HarnessError as e:
            log.error("live turn failed: %s", e)
            self._end_reply(shown, parser)
            self._hiccup()
            return
        except Exception:
            log.exception("live turn crashed")
            self._end_reply(shown, parser)
            self._hiccup()
            return
        finally:
            self._streaming = False
            self._ui.thinking = False

        self._last_turn_at = self._clock.monotonic()
        rest = parser.finish()
        if rest:
            shown = self._show(shown, parser, rest)
        self._end_reply(shown, parser)
        self._log(started, first_at, parser.spoken)
        self._ledger.record("chat", self._model.name, self._model.last_usage)
        self._apply(parser)
        if not speak:
            if parser.spoken.strip():
                await self._speaker.say(parser.spoken, parser.emotion, speak=False)
            else:
                self._ui.set_emotion(parser.emotion)
            self._ui.rest()
            return
        if utterance is None:
            if rest:
                utterance = self._speaker.utterance(parser.emotion)
            else:
                self._ui.set_emotion(parser.emotion)
                self._ui.rest()
                return
        utterance.add(rest)
        await utterance.finish()
        if self._ui.state is MiloState.THINKING:  # only tags, nothing was spoken
            self._ui.rest()

    def _show(self, shown: str | None, parser: ReplyParser, text: str) -> str:
        """Stream reply text into the transcript, starting the entry with its first words."""
        if shown is None:
            shown = self._transcript.reply_started(parser.emotion or Emotion.NEUTRAL)
        self._transcript.reply_delta(shown, text)
        return shown

    def _end_reply(self, shown: str | None, parser: ReplyParser) -> None:
        if shown is not None:
            self._transcript.reply_finished(shown, parser.spoken, parser.emotion or Emotion.NEUTRAL)

    async def _settle_interrupt(self) -> None:
        """Let the previous turn's interrupt reach the model before sending the next message."""
        stopping, self._stopping = self._stopping, None
        if stopping is None:
            return
        try:
            await stopping
        except Exception:
            log.exception("interrupting the live model failed; starting a fresh conversation")
            self._system = None

    async def _ensure_conversation(self) -> None:
        async with self._starting:
            system = self._system_prompt()
            now = self._clock.monotonic()
            idle = self._last_turn_at is not None and now - self._last_turn_at > self._idle_reset_s
            # A conversation nobody has talked to yet (warmed at boot) is kept unless its prompt went stale.
            unused_but_stale = self._last_turn_at is None and system != self._system
            if self._system is None or idle or unused_but_stale:
                await self._model.start(system)
                self._system, self._last_turn_at = system, None

    def _system_prompt(self) -> str:
        parts = [self._persona().strip() or DEFAULT_PERSONA, REPLY_RULES.strip()]
        profile = self._profile.read().strip()
        if profile:
            parts.append(f"## What you know about the user\n\n{profile}")
        open_reminders = [r for r in self._reminders.all() if not r.done]
        if open_reminders:
            lines = "\n".join(f"- {r.due:%Y-%m-%d %H:%M} {r.text}" for r in open_reminders)
            parts.append(f"## Open reminders\n\n{lines}")
        return "\n\n".join(p for p in parts if p) + "\n"

    def _prompt(self, text: str) -> str:
        notes, self._notes = self._notes, []
        return stamp("\n".join([*notes, text]), self._clock.now(), self._context.app)

    def _apply(self, parser: ReplyParser) -> None:
        for fact in parser.remembers:
            try:
                self._profile.remember(fact)
                log.info("remembered: %s", fact)
            except Exception:
                log.exception("could not save to the profile: %s", fact)
        for due, what in parser.reminders:
            try:
                self._reminders.add(due, what)
                log.info("reminder set for %s: %s", due, what)
            except Exception:
                log.exception("could not save the reminder: %s %s", due, what)
        for description in parser.tasks:
            self._tasks.submit(description)

    def _hiccup(self) -> None:
        self._system = None  # the conversation may be broken: start a fresh one next turn
        self._speaker.interrupt()
        self._ui.thinking = False
        self._ui.set_emotion(Emotion.CONFUSED)
        self._ui.emit(Bubble(HICCUP))
        self._transcript.say(HICCUP, Emotion.CONFUSED)
        self._ui.rest()

    def _log(self, started: float, first_at: float | None, spoken: str) -> None:
        u = self._model.last_usage
        first = f"{first_at - started:.2f}s" if first_at is not None else "never"
        log.info("chat %s turn %.1fs, first delta %s, %d in (%d cached), %d out: %r", self._model.name,
                 self._clock.monotonic() - started, first, u.input_tokens, u.cached_input_tokens,
                 u.output_tokens, spoken)
