from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from milo.core.events import Bubble, Heard, Looking
from milo.core.language import SpokenLanguage
from milo.core.language import name as language_name
from milo.core.logtext import private
from milo.core.opening import OpenRequest, named_by
from milo.core.ports import Clock, LiveModel, ProfileMemory, ReminderBook, ScreenEyes, UsageLedger
from milo.core.types import Emotion, HarnessError, MiloState, ScreenCapture

from .approvals import Approvals
from .backchannel import Backchannel
from .context import UserContext
from .conversation import stamp
from .memory import Recalled, TurnMemory
from .reply_effects import ReplyEffects
from .reply_stream import ActRequest, ReplyParser
from .screen import look_prompt
from .speaker import Speaker, Utterance
from .tag_policy import TagPolicy, policy
from .today import Today
from .talk_prompt import NAME_IT, PromptParts, system_prompt, untrusted, update_prompt
from .transcript import Transcript, unrecorded
from .ui_state import UiState

if TYPE_CHECKING:
    from .meetings import MeetingService
    from .opener import Opener
    from .orchestrator import Orchestrator
    from .quick_actions import QuickActions
    from .routines import Routines
    from .undo import Undo
    from .writing import Writer

log = logging.getLogger("milo.live")

HICCUP = "My brain hiccuped. Check ~/Milo/logs/brain.log."
HOLD_MAX_S = 330.0  # a held reply is dropped after this: longer than the longest hands-free recording

class LiveTalk:
    """A user turn, typed or spoken, answered by the streaming live model and spoken as it arrives.

    One turn runs at a time; a new turn or the talk key interrupts the running one at once (barge-in).
    The conversation stays open in the model between turns and starts fresh after `idle_reset_s` of
    silence, with the persona and profile reloaded into its system prompt.
    """

    def __init__(self, model: LiveModel, speaker: Speaker, ui: UiState, context: UserContext, clock: Clock,
                 profile: ProfileMemory, reminders: ReminderBook, ledger: UsageLedger,
                 persona: Callable[[], str], idle_reset_s: float, tasks: Orchestrator, *,
                 transcript: Transcript | None = None, eyes: ScreenEyes | None = None,
                 approvals: Approvals | None = None, memory: TurnMemory | None = None,
                 backchannel: Backchannel | None = None, routines: Routines | None = None,
                 meetings: MeetingService | None = None, undo: Undo | None = None, opener: Opener | None = None,
                 language: SpokenLanguage | None = None, quick: QuickActions | None = None,
                 writer: Writer | None = None, computer: str = "computer"):
        self._model = model
        self._computer = computer
        """What the platform calls the machine Milo lives on, for the prompt (Platform.computer)."""
        self._writer = writer
        """Pastes what a <write> tag wrote where the user is (ADR 0033). None: the tag does nothing."""
        self._quick = quick
        self._today = quick.today if quick is not None else Today(None, clock, reminders=reminders)
        """The <today> block (services/today.py): the day, Milo's own open reminders, his timers. Without quick
        actions only the reminders."""
        """Does the everyday act tags itself and keeps the <today> block (ADR 0029). None: those tags do nothing."""
        self._opener = opener
        """Opens what an <open> tag names at once (ADR 0028). None: the tag does nothing."""
        self._language = language or SpokenLanguage()
        """The language of the message being answered; the reply, helpers and questions follow it."""
        self._opening: set[asyncio.Task] = set()
        self._heard_at: float | None = None
        self._meetings = meetings
        self._backchannel = backchannel
        self._routines = routines
        self._memory = memory
        """Recalls what each turn needs (services/memory.py). None: Milo remembers only the profile."""
        self._eyes = eyes
        self._approvals = approvals
        self._saw_screen = False
        """The running conversation has read screen data. Until it restarts, its tasks run careful."""
        self._look_started: asyncio.Task[ScreenCapture] | None = None
        self._ui_looking = False
        self._transcript = transcript or unrecorded()
        self._speaker = speaker
        self._ui = ui
        self._context = context
        self._clock = clock
        self._profile = profile
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
        self._started_at: float | None = None
        """When the running conversation started. One nobody talked to goes stale after `idle_reset_s` too."""
        self._starting = asyncio.Lock()  # warm() at boot and the first turn may race
        self._notes: list[str] = []
        self._earlier: list[str] = []
        """Recaps of an earlier conversation the user picked up again, trusted ones: they don't taint."""
        self._tainted = False
        """Task results entered the running conversation, so outside text can steer every later reply in it."""
        self._request = ""
        """The user's own words in the turn being answered (auto mode reads them, ADR 0022)."""
        self._recent: list[str] = []
        """The user's own words in this conversation's last few turns: "open YouTube", then "search for cats" names
        YouTube for the search."""
        self._via = ""
        """Where the turn came from: "voice" or "typed" at the Mac, "message" from the phone."""
        self._effects = ReplyEffects(ui, profile, reminders, tasks, start_open=self._start_open, approvals=approvals,
                                     routines=routines, undo=undo, quick=quick, computer=computer)
        """Does what a finished reply's tags say, asking first where its TagPolicy says so."""
        self._preparing: asyncio.Task | None = None
        self._hold_timer: asyncio.TimerHandle | None = None

    @property
    def carries_outside(self) -> bool:
        """The chat model's conversation has seen the screen or outside text (a task result, meeting notes,
        an untrusted memory): its replies may quote it, so the conversation they land in counts as outside."""
        return self._tainted or self._saw_screen or bool(self._notes)

    @property
    def busy(self) -> bool:
        """A turn is running: Milo is thinking or still speaking his answer."""
        return self._turn is not None and not self._turn.done()

    def start(self, text: str, *, via: str = "voice", speak: bool = True,
              capture: ScreenCapture | None = None, language: str = "") -> asyncio.Task:
        """Run a turn in the background so listening and dictation keep working while Milo answers.

        While Milo waits for a yes or no, a short "yes" or "no" answers his question instead.
        """
        self.interrupt(rest=False)
        if capture is None and self._approvals is not None and self._approvals.answer_text(text, via=via):
            self._ui.emit(Heard(text))
            self._ui.rest()
            self._turn = asyncio.create_task(asyncio.sleep(0))
            return self._turn
        self._turn = asyncio.create_task(self.turn(text, via=via, speak=speak, capture=capture, language=language))
        return self._turn

    def interrupt(self, *, rest: bool = True) -> bool:
        """Stop thinking and speaking now, including speech that isn't a turn (a nudge, a task result).

        Returns whether anything was stopped. rest=False when the caller shows the next state itself.
        """
        stopped = self.busy or self._speaker.active
        if self._hold_timer is not None:
            self._hold_timer.cancel()
            self._hold_timer = None
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

    def hold(self) -> bool:
        """The user started talking: go quiet at once, but keep the reply going and the place in it.

        The user may say nothing after all (a cough, a key pressed by mistake): then resume() goes on
        from the phrase that was cut off. A new turn drops the held reply, like interrupt(). Returns whether
        anything was held.
        """
        if not (self.busy or self._speaker.active):
            return False
        self._speaker.hold()
        if self._hold_timer is not None:
            self._hold_timer.cancel()
        self._hold_timer = asyncio.get_running_loop().call_later(HOLD_MAX_S, self._hold_expired)
        return True

    def resume(self) -> bool:
        """Go on after hold(), when the user said nothing. False if nothing was held: the caller shows the next
        state then."""
        if self._hold_timer is not None:
            self._hold_timer.cancel()
            self._hold_timer = None
        if not self._speaker.held:
            return False
        if self._speaker.resume():
            log.info("going on after an interruption with nothing said")
            self._ui.set_state(MiloState.THINKING)  # until the first piece is ready again
            return True
        if self.busy:  # still thinking, nothing spoken yet
            self._ui.thinking = True
            self._ui.set_state(MiloState.THINKING)
            return True
        return False

    def _hold_expired(self) -> None:
        self._hold_timer = None
        if self._speaker.held:
            log.info("a held reply waited too long; dropping it")
            self.interrupt(rest=False)

    def note(self, description: str, result: str) -> None:
        """A background task finished. The next user message carries the result, so Milo knows about it.

        The result may quote mail, web pages or files, so it goes in as delimited, escaped data, and the
        tags in every later reply of this conversation wait for the user's yes (see _apply).
        """
        self._notes.append(f"<task_result>\nTask: {untrusted(description)}\nResult: {untrusted(result)}\n</task_result>")

    # ---- conversations (see transcript.py)

    def pick_up(self, recap: str, trusted: bool) -> None:
        """The user picked an earlier conversation up again: the next message carries its recap. An untrusted
        one (it carried task results or the screen) counts like a task result: later tags ask first."""
        (self._earlier if trusted else self._notes).append(recap)

    def fresh(self) -> None:
        """The user asked for a new conversation: the next turn starts a fresh one in the model too."""
        self._system = None
        self._earlier.clear()

    # ---- helpers (see orchestrator.py)

    def speak_update(self, update: str) -> bool:
        """Say a helper's milestone in Milo's own words (`[chat] updates = "chatty"`), if he is free.

        Returns False when he is busy answering or speaking; the caller shows the update instead.
        """
        if self.busy or self._speaker.active:
            return False
        self._turn = asyncio.create_task(self._update_turn(update))
        return True

    async def _update_turn(self, update: str) -> None:
        await self._settle_interrupt()
        await self._reply(update_prompt(untrusted(update, 300)), (), True, screen=False, tags=False)

    # ---- text turns from a chat channel (the owner's phone, see messages.py)

    def message(self, text: str, prompt: str, *, data: Sequence[str] = ()) -> asyncio.Task[str | None]:
        """A message from the owner's phone, answered in text: the same conversation, persona and memory as
        a spoken turn, without speech and without looking at the screen.

        `text` is what the user wrote, for the transcript; `prompt` is what the model gets (messages.py adds
        how to answer by message). `data` are blocks of outside text (forwarded, quoted, pasted), already
        made inert: like task results they make every later tag in this conversation wait for a yes. The
        task's result is what Milo answered, or None if the model failed. It is a turn like any other, so
        a turn at the Mac interrupts it.
        """
        self.interrupt(rest=False)
        self._turn = asyncio.create_task(self._message_turn(text, prompt, list(data)))
        return self._turn

    async def _message_turn(self, text: str, prompt: str, data: list[str]) -> str | None:
        self._ui.emit(Heard(text))
        self._transcript.user(text, "message")
        self._heard_at = self._clock.monotonic()
        await self._settle_interrupt()
        self._request = text
        self._recent = [*self._recent[-2:], text]
        self._via = "message"
        self._language.hear(text)
        self._notes.extend(data)
        try:
            parser = await self._reply(prompt, (), False, screen=False)
            if parser is not None and self._quick is not None:  # what the acts did goes along with the answer
                done = await self._quick.lines(asyncio.current_task())
                said = " ".join(t for t in (parser.spoken.strip(), done) if t)
                return "\n\n".join(t for t in (said, *parser.writes) if t)  # a <write> goes as text from afar
        finally:
            if self._look_started is not None:  # no looking at the screen from afar
                self._look_started.cancel()
                self._look_started = None
                self._looking(False)
                self._ui.thinking = False
        return None if parser is None else "\n\n".join(t for t in (parser.spoken, *parser.writes) if t)

    async def warm(self) -> None:
        """Start the conversation ahead of the first turn. Raises HarnessError."""
        await self._ensure_conversation()

    def prepare(self) -> None:
        """The user started talking to Milo: get the conversation ready while they speak.

        After `idle_reset_s` of silence the next turn starts a fresh conversation, a new model process that
        takes 1 to 3 s before its first word. Starting it now hides that behind the user's own words. A streaming
        voice opens its connection now too.
        """
        self._speaker.prepare()
        if self._today is not None:
            self._today.soon()
        if (self._preparing is None or self._preparing.done()) and self._needs_fresh_conversation():
            self._preparing = asyncio.create_task(self._prepare())

    async def _prepare(self) -> None:
        try:
            await self._ensure_conversation()
        except HarnessError as e:
            log.warning("could not start the conversation ahead of the turn: %s", e)

    async def turn(self, text: str, *, via: str = "voice", speak: bool = True,
                   capture: ScreenCapture | None = None, language: str = "") -> None:
        """`via` is "voice" or "typed", for the transcript. speak=False answers in the bubble without audio.
        `language` is the code the transcriber heard ("de"); without one Milo guesses from the words.

        `capture` goes along with the message (the "What's this?" shortcut). Without one, the model may ask
        to look (`<look/>`): Milo captures the front window while he says his first words, then answers
        again with what he saw.
        """
        self._ui.emit(Heard(text))
        self._transcript.user(text, via)
        self._heard_at = self._clock.monotonic()
        await self._settle_interrupt()
        self._request = text
        self._recent = [*self._recent[-2:], text]
        self._via = via
        self._language.hear(text, language)
        looking = None
        try:
            if capture is not None:
                self._looking(True)
                await self._reply(*self._screen_message(capture, text), speak, screen=True)
                return
            parser = await self._reply(text, (), speak, screen=False)
            if parser is None or parser.look is None or self._eyes is None:
                return
            looking = self._look_started
            capture = await looking
            await self._reply(*self._screen_message(capture, text), speak, screen=True)
        finally:
            if looking is not None and not looking.done():
                looking.cancel()
            self._look_started = None
            if self._ui_looking:
                self._looking(False)

    async def _reply(self, text: str, images: Sequence[Path], speak: bool, *, screen: bool,
                     tags: bool = True) -> ReplyParser | None:
        """Stream one reply to `text` into speech and the transcript and apply its tags. None if the model failed.

        `screen`: the message carries screen data, so the reply may not remember facts or look again.
        `tags=False` ignores every tag (a spoken helper update must not start anything).
        """
        self._ui.thinking = True
        self._ui.set_state(MiloState.THINKING)
        self._ui.set_emotion(Emotion.THINKING)
        parser = ReplyParser()
        held: list[OpenRequest] = []  # <open> tags that wait for a yes (see _open_now)
        utterance: Utterance | None = None
        shown: str | None = None  # transcript id of the reply, once it has text
        started = self._clock.monotonic()
        first_at: float | None = None
        opened = 0
        acted = 0
        wrote = 0
        notes, self._notes = self._notes, []
        earlier, self._earlier = self._earlier, []
        if speak and self._backchannel is not None:
            self._backchannel.arm(text, first=self._last_turn_at is None or
                                  self._clock.monotonic() - self._last_turn_at > self._idle_reset_s)
        try:
            await self._ensure_conversation()
            meeting, (today, outside), recalled = await asyncio.gather(
                self._meeting(text) if tags and not screen else asyncio.sleep(0, ""),
                self._today.note() if self._today is not None and tags else asyncio.sleep(0, ("", False)),
                self._recall(text, screen, outside=self._tainted or bool(notes) or self._saw_screen))
            if meeting and self._memory is not None:
                self._memory.outside = True  # what was said in the call: the episode is stored as outside text
            # Another person's line in <today> stays in the conversation, so later turns count as outside too.
            self._tainted = self._tainted or bool(notes) or bool(meeting) or outside or not recalled.trusted
            self._saw_screen = self._saw_screen or screen
            rule = self._policy(now=screen or outside)
            self._streaming = True
            blocks = [*earlier, *notes, recalled.block, *([meeting] if meeting else []), today]
            async for delta in self._model.turn(self._prompt(text, blocks, name=tags and not screen), images):
                if first_at is None:
                    first_at = self._clock.monotonic()
                    if self._ui_looking:
                        self._looking(False)  # he has seen it and starts to answer
                speech = parser.feed(delta)
                if tags and len(parser.opens) > opened:
                    held += self._open_now(parser.opens[opened:], rule)
                    opened = len(parser.opens)
                if tags and len(parser.acts) > acted:
                    self._act_now(parser.acts[acted:], rule)
                    acted = len(parser.acts)
                if tags and len(parser.writes) > wrote:
                    self._write_now(parser.writes[wrote:], rule)
                    wrote = len(parser.writes)
                if speak and utterance is None and parser.emotion is not None:
                    utterance = (self._backchannel.utterance(parser.emotion) if self._backchannel is not None
                                 else self._speaker.utterance(parser.emotion))
                if speech:
                    shown = self._show(shown, parser, speech)
                    if speak:
                        utterance.add(speech)
            self._streaming = False
        except asyncio.CancelledError:
            self._notes[:0] = notes  # the model may not have seen them: send them again next turn
            self._earlier[:0] = earlier
            if self._today is not None:
                self._today.unsent()
            self._end_reply(shown, parser)
            raise
        except HarnessError as e:
            log.error("live turn failed: %s", e)
            self._notes[:0] = notes
            self._earlier[:0] = earlier
            self._end_reply(shown, parser)
            self._hiccup()
            return None
        except Exception:
            log.exception("live turn crashed")
            self._notes[:0] = notes  # like a failed turn: the next one still tells the user what helpers found
            self._end_reply(shown, parser)
            self._hiccup()
            return None
        finally:
            self._streaming = False
            self._ui.thinking = False
            if self._backchannel is not None:
                self._backchannel.release()

        self._last_turn_at = self._clock.monotonic()
        rest = parser.finish()
        if tags and len(parser.opens) > opened:  # an unclosed tag at the very end
            held += self._open_now(parser.opens[opened:], rule)
        if tags and len(parser.acts) > acted:
            self._act_now(parser.acts[acted:], rule)
        if tags and len(parser.writes) > wrote:
            self._write_now(parser.writes[wrote:], rule)
        if rest:
            shown = self._show(shown, parser, rest)
        self._end_reply(shown, parser)
        self._log(started, first_at, parser.spoken)
        self._ledger.record("chat", self._model.name, self._model.last_usage)
        if tags:
            if parser.title:
                self._transcript.titled(parser.title)
            self._apply(parser, rule, held=held, remember=not screen)
        if not speak:
            if parser.spoken.strip():
                await self._speaker.say(parser.spoken, parser.emotion, speak=False)
            else:
                self._ui.set_emotion(parser.emotion)
            self._ui.rest()
            return parser
        if utterance is None:
            if rest:
                utterance = (self._backchannel.utterance(parser.emotion) if self._backchannel is not None
                             else self._speaker.utterance(parser.emotion))
            else:
                self._ui.set_emotion(parser.emotion)
                self._ui.rest()
                return parser
        utterance.add(rest)
        await utterance.finish()
        if self._ui.state is MiloState.THINKING and not self._ui.thinking:  # only tags, nothing was spoken
            self._ui.rest()
        return parser

    async def _meeting(self, text: str) -> str:
        """During a call Milo takes notes in: what was said, as data (see services/meetings.py)."""
        if self._meetings is None:
            return ""
        try:
            return await self._meetings.before_turn(text)
        except Exception:
            log.exception("the meeting context failed")
            return ""

    def _screen_message(self, capture: ScreenCapture, question: str) -> tuple[str, list[Path]]:
        images = [Path(capture.image)] if capture.image else []
        return look_prompt(capture, question, image=bool(images)), images

    def _looking(self, on: bool) -> None:
        self._ui_looking = on
        self._ui.emit(Looking(on))

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

    def _needs_fresh_conversation(self, system: str | None = None) -> bool:
        system = self._system_prompt() if system is None else system
        last = self._last_turn_at if self._last_turn_at is not None else self._started_at
        idle = last is not None and self._clock.monotonic() - last > self._idle_reset_s
        # A conversation nobody has talked to yet (warmed at boot) is kept unless its prompt changed or it sat
        # unused past idle_reset_s: by then the model's prompt cache has expired too.
        unused_but_stale = self._last_turn_at is None and system != self._system
        return self._system is None or idle or unused_but_stale

    async def _ensure_conversation(self) -> None:
        async with self._starting:
            system = self._system_prompt()
            if self._needs_fresh_conversation(system):
                await self._model.start(system)
                self._system, self._last_turn_at, self._started_at = system, None, self._clock.monotonic()
                self._saw_screen = False
                self._tainted = False
                self._recent = self._recent[-1:]  # the turn that started it
                if self._memory is not None:
                    self._memory.new_conversation()
                if self._today is not None:
                    self._today.new_conversation()

    def _system_prompt(self) -> str:
        return system_prompt(PromptParts(
            persona=self._persona(), computer=self._computer, look=self._eyes is not None,
            quick=self._quick.rules() if self._quick is not None else "",
            writing=self._writer.rules() if self._writer is not None else "",
            memory=self._memory.rules if self._memory is not None else "",
            routines=self._routines.rules() if self._routines is not None else "",
            profile=self._profile.read()))

    def _prompt(self, text: str, notes: list[str], *, name: bool = False) -> str:
        helpers = self._tasks.board()
        routines = self._routines.note(self._system or "") if self._routines is not None else ""
        if name and self._transcript.wants_title():
            text += f"\n\n{NAME_IT}"
        lines = [*(n for n in notes if n), *([helpers] if helpers else []), *([routines] if routines else []), text]
        language = language_name(self._language.code) if self._language.code else ""
        return stamp("\n".join(lines), self._clock.now(), self._context.app, language)

    async def _recall(self, text: str, screen: bool, *, outside: bool) -> Recalled:
        """The <memory> block for this turn. A reply to screen data already had one with the question."""
        if self._memory is None or screen:
            if self._memory is not None:
                self._memory.outside = True  # the reply may quote the screen
            return Recalled("", True)
        return await self._memory.before_turn(text, self._context.app, outside=outside,
                                              at_mac=self._via in ("voice", "typed"))

    def _policy(self, *, now: bool) -> TagPolicy:
        """The rules for this reply's tags (tag_policy). `now`: the message being answered carries outside text."""
        auto = self._approvals is not None and self._approvals.permits.ask == "auto"
        return policy(tainted=self._tainted, saw_screen=self._saw_screen, now=now, auto=auto, via=self._via,
                      request=self._request)

    def _open_now(self, requests: Sequence[OpenRequest], rule: TagPolicy) -> list[OpenRequest]:
        """Open what the reply's <open> tags name, while the reply still streams, so the page is up by the time
        Milo has said "Opening YouTube in Chrome". An app always opens: that changes nothing. An address or a file
        opens at once when the user's own words named it ("go on YouTube") or the conversation read no outside
        text, or in auto mode at the Mac for an address (`TagPolicy.ask_undoable`); otherwise outside text may have
        put it there (a link on a page, in a mail), so it waits for a yes after the reply. Returns those."""
        if self._opener is None:
            if requests:
                log.info("ignoring %d <open> tag(s): nothing to open them with", len(requests))
            return []
        held = []
        for request in requests:
            ask = rule.outside if request.path else rule.ask_undoable  # a file from a mail could be a program
            if (request.url or request.path) and ask and not named_by(request, " ".join(self._recent)):
                held.append(request)
                continue
            self._start_open(request)
        return held

    def _act_now(self, acts: Sequence[ActRequest], rule: TagPolicy) -> None:
        """Start the reply's act tags while it still streams, like <open> (ADR 0029). An act follows the <reminder>
        rule: after outside text it asks, and its question waits for the reply to end."""
        if self._quick is None:
            log.info("ignoring %d act tag(s): quick actions are off", len(acts))
            return
        self._quick.start(acts, outside=rule.ask_undoable, via=self._via)

    def _write_now(self, texts: Sequence[str], rule: TagPolicy) -> None:
        """Paste what <write> wrote the moment its tag closes (ADR 0033). After outside text it goes in only when the
        user's own words asked for the writing; Writer decides that from them."""
        if self._writer is None:
            log.info("ignoring %d <write> tag(s): nothing to paste them with", len(texts))
            return
        self._writer.start(texts, outside=rule.outside, request=self._request,
                           via=self._via)

    def _start_open(self, request: OpenRequest) -> None:
        task = asyncio.create_task(self._opener.open(request, since=self._heard_at, language=self._language.code))
        self._opening.add(task)
        task.add_done_callback(self._opening.discard)

    def _apply(self, parser: ReplyParser, rule: TagPolicy, *, held: Sequence[OpenRequest] = (),
               remember: bool = True) -> None:
        """Start a look the reply asked for, then do what its other tags say (ReplyEffects). `remember=False`: the
        reply was to screen data, so it doesn't look again or remember facts."""
        if remember and parser.look is not None and self._eyes is not None:
            # Look while the first words are spoken; thinking keeps Milo from resting in between.
            self._looking(True)
            self._ui.thinking = True
            self._look_started = asyncio.create_task(self._eyes.look("window"))
        self._effects.apply(parser, rule, held=held, remember=remember, language=self._language.code)
        self._effects.take_back(parser)

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
        log.info("chat %s turn %.1fs, first delta %s, %d in (%d cached), %d out, said %s", self._model.name,
                 self._clock.monotonic() - started, first, u.input_tokens, u.cached_input_tokens,
                 u.output_tokens, private(spoken))
