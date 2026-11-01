from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from concurrent.futures import Executor

from milo.core.events import Partial, Status
from milo.core.logtext import private
from milo.core.ports import AudioInput, Transcriber
from milo.core.types import STT_SAMPLE_RATE, ListenMode, LiveMode, MiloState

from .cloud_hearing import CloudHearing, CloudRecording
from .context import UserContext
from .dictation import DictationService, TypedDictation
from .levels import throttled_levels
from .live_talk import LiveTalk
from .live_transcript import LiveTranscript, PauseSegmenter
from .ui_state import UiState

log = logging.getLogger("milo.listening")


class _InOrder:
    """Hands over one recording's results (typed phrases, the paste, the turn) only once the recording before
    it handed over all of its own, so a quick second dictation never pastes before a slow first one."""

    def __init__(self, previous: _InOrder | None):
        self._open = previous is None or previous.closed
        self._held: list[Callable[[], None]] = []
        self._closing = False
        self._next: _InOrder | None = None
        self.closed = False  # all of this recording's results are out
        if not self._open:
            previous._next = self

    def run(self, deliver: Callable[[], None]) -> None:
        if self._open:
            deliver()
        else:
            self._held.append(deliver)

    def close(self) -> None:
        """Nothing more comes from this recording."""
        self._closing = True
        if self._open:
            self._done()

    def _start(self) -> None:
        self._open = True
        held, self._held = self._held, []
        for deliver in held:
            deliver()
        if self._closing:
            self._done()

    def _done(self) -> None:
        self.closed = True
        if self._next is not None:
            self._next._start()


class Listening:
    """Push-to-talk: record while the key is held, then transcribe and hand the text to dictation or live talk.

    Both keys listen the same way. With `live` on, a LiveTranscript shows the words while the user speaks
    and commits each phrase at the pause after it, so the release only waits for the last words; then
    the text is pasted (dictation) or goes to the chat model (talk). `live` = TYPE also pastes each
    dictated phrase as it is committed. OFF transcribes the whole recording on release.

    The talk key is also barge-in: pressing it while Milo thinks or speaks stops him at once. He keeps his
    place (LiveTalk.hold): if the recording turns out empty or is cancelled, he goes on where he was.

    A tentative start records without showing anything (no state, no levels, no barge-in) until confirm()
    or stop(), because the key press may still turn out to be a tap.

    release() hands the recording to a task and returns at once, so the next key press opens the mic right
    away while the last words are still being transcribed. Results go out in the order the recordings were
    made, and only the newest release puts Milo back to rest.

    `before` runs when the mic opens, before anything is transcribed.

    `hearing` streams talk recordings (and dictation, if allowed) to a cloud transcriber while they are made.
    Its guesses are the live words and its text wins, so the local model stays idle (and paged out); if it
    fails, the whole recording is transcribed here on release.
    """

    def __init__(self, mic: AudioInput, transcriber: Transcriber, executor: Executor, ui: UiState,
                 dictation: DictationService, live_talk: LiveTalk, context: UserContext,
                 live: LiveMode = LiveMode.OFF, hearing: CloudHearing | None = None, *,
                 yield_stt: Callable[[], None] = lambda: None, before: Callable[[], None] = lambda: None):
        self._mic = mic
        self._transcriber = transcriber
        self._executor = executor
        self._ui = ui
        self._dictation = dictation
        self._live_talk = live_talk
        self._context = context
        self._live_mode = live
        self._yield_stt = yield_stt
        self._before = before
        self._mode: ListenMode | None = None
        self._shown = False
        self._live: LiveTranscript | None = None
        self._typed: TypedDictation | None = None
        self._order: _InOrder | None = None  # the recording in progress
        self._last: _InOrder | None = None  # the newest recording, which the next one goes after
        self._released: _InOrder | None = None  # the newest recording that was let go (not cancelled)
        self._releases: set[asyncio.Task] = set()
        self._hearing = hearing
        self._cloud: CloudRecording | None = None

    @property
    def live_mode(self) -> LiveMode:
        return self._live_mode

    @live_mode.setter
    def live_mode(self, mode: LiveMode) -> None:
        """[dictation] stream changed in the Settings window or the menu. Takes effect from the next recording."""
        self._live_mode = mode

    def start(self, mode: ListenMode, tentative: bool = False) -> None:
        if self._mic.active:
            return
        # Barge-in. LISTENING comes next, no flash of IDLE in between.
        stopped = not tentative and mode is ListenMode.TALK and self._live_talk.hold()
        levels = throttled_levels(self._ui, asyncio.get_running_loop())
        try:
            self._mic.start(lambda value: self._shown and levels(value))
        except Exception as e:
            log.exception("mic failed")
            self._ui.emit(Status(f"Mic unavailable: {e}"))
            if stopped and not self._live_talk.resume():
                self._ui.rest()
            return
        self._mode = mode
        self._shown = False
        self._order = self._last = _InOrder(self._last)
        self._yield_stt()  # a meeting pass on the STT thread gives way, so nothing queues ahead of the user
        try:
            self._before()  # e.g. words the user just added to dictionary.md reach the transcriber
        except Exception:
            log.exception("could not prepare the recording")
        if not self._goes_to_cloud(mode):
            self._wake()
        if mode is ListenMode.TALK:
            self._live_talk.wake()
        if not tentative:
            self._show()

    def _wake(self) -> None:
        """Page the model in while the user starts talking (see Transcriber.wake)."""
        def failed(woken: asyncio.Future) -> None:
            if not woken.cancelled() and woken.exception() is not None:
                log.warning("waking the speech model failed: %s", woken.exception())

        asyncio.get_running_loop().run_in_executor(self._executor, self._transcriber.wake).add_done_callback(failed)

    def _goes_to_cloud(self, mode: ListenMode | None) -> bool:
        """config.toml lets this recording leave the Mac (typed dictation never does: it pastes phrase by phrase)."""
        if self._hearing is None:
            return False
        return mode is ListenMode.TALK or (self._hearing.dictation and self._live_mode is not LiveMode.TYPE)

    def confirm(self) -> None:
        """Show a tentative recording: the key is held, or a double tap locked it on."""
        if not self._mic.active or self._shown:
            return
        if self._mode is ListenMode.TALK:
            self._live_talk.hold()
        self._show()

    def _show(self) -> None:
        self._shown = True
        dictate = self._mode is ListenMode.DICTATE
        self._ui.set_state(MiloState.DICTATING if dictate else MiloState.LISTENING)
        if self._goes_to_cloud(self._mode):
            self._cloud = self._hearing.start(
                self._mic, on_partial=(lambda text: self._ui.emit(Partial(text))) if self._live_mode is not LiveMode.OFF
                else None)
            if self._cloud is None:  # the cloud is resting after a failure: this one is transcribed here
                self._wake()
        if self._live_mode is LiveMode.OFF or self._cloud is not None:
            return
        self._typed = self._dictation.typed() if dictate and self._live_mode is LiveMode.TYPE else None
        typed, order = self._typed, self._order
        self._live = LiveTranscript(self._mic, self._transcriber, self._executor, self._ui, PauseSegmenter(),
                                    on_phrase=(lambda text: order.run(lambda: typed.add(text))) if typed else None)
        self._live.start()

    async def stop(self) -> None:
        """Release and wait until the text is handed over."""
        task = self.release()
        if task is not None:
            await task

    def release(self) -> asyncio.Task | None:
        """The key came up: stop recording now and transcribe in the background (see the class)."""
        if not self._mic.active:
            return None
        mode, self._mode = self._mode, None
        live, self._live = self._live, None
        typed, self._typed = self._typed, None
        cloud, self._cloud = self._cloud, None
        order, self._order = self._order, None
        self._released = order
        if not self._shown and mode is ListenMode.TALK:
            self._live_talk.hold()  # released before the confirm arrived: still a real hold
        self._shown = False
        audio = self._mic.stop()
        self._ui.set_state(MiloState.TRANSCRIBING)
        task = asyncio.create_task(self._transcribe(mode, audio, live, typed, cloud, order))
        self._releases.add(task)
        task.add_done_callback(self._releases.discard)
        return task

    async def _transcribe(self, mode: ListenMode, audio, live: LiveTranscript | None, typed: TypedDictation | None,
                          cloud: CloudRecording | None, order: _InOrder) -> None:
        started = time.monotonic()
        try:
            text = await self._hearing.transcribe(cloud, audio) if cloud is not None else None
            by_cloud = text is not None
            language = ""
            if by_cloud:
                language = cloud.language
                if live is not None:
                    live.abort()  # its words were only for the pill
            elif live is not None:
                text = await live.finish(audio)
            else:
                text = await asyncio.get_running_loop().run_in_executor(
                    self._executor, self._transcriber.transcribe, audio)
            if not by_cloud:
                language = str(getattr(self._transcriber, "heard_language", "") or "")
        except Exception:
            log.exception("transcription failed")
            order.run(lambda: self._failed(mode, typed, order))
            order.close()
            return
        log.info("stt %.2fs audio, ready %.2fs after release%s: %s", len(audio) / STT_SAMPLE_RATE,
                 time.monotonic() - started, " (cloud)" if by_cloud else "", private(text))
        order.run(lambda: self._deliver(mode, text.strip(), typed, order, language))
        order.close()

    def _deliver(self, mode: ListenMode, text: str, typed: TypedDictation | None, order: _InOrder,
                 language: str = "") -> None:
        if typed is not None:
            typed.finish(self._context.app)
            self._rest(order)
        elif mode is ListenMode.DICTATE:
            self._dictation.handle(text, self._context.app)
            self._rest(order)
        elif text:
            self._live_talk.start(text, language=language)
        elif not self._live_talk.resume():  # nothing said: go on with what was cut off
            self._rest(order)

    def _failed(self, mode: ListenMode, typed: TypedDictation | None, order: _InOrder) -> None:
        self._ui.emit(Status("I couldn't transcribe that."))
        if typed is not None:
            typed.finish(self._context.app)
        if mode is ListenMode.TALK:
            self._live_talk.interrupt(rest=False)
        self._rest(order)

    def _rest(self, order: _InOrder) -> None:
        """Back to rest, unless a newer recording is under way or still being transcribed: its state stays."""
        if not self._mic.active and self._released is order:
            self._ui.rest()

    def cancel(self) -> None:
        """Drop the recording. A tentative one vanishes without a trace; typed phrases stay typed."""
        live, self._live = self._live, None
        typed, self._typed = self._typed, None
        if live is not None:
            live.abort()
        if typed is not None:
            typed.finish(self._context.app)
        cloud, self._cloud = self._cloud, None
        if cloud is not None:
            cloud.cancel()
        if self._mic.active:
            self._mic.stop()
        order, self._order = self._order, None
        if order is not None:
            order.close()
        mode, self._mode = self._mode, None
        shown, self._shown = self._shown, False
        resumed = mode is ListenMode.TALK and self._live_talk.resume()  # e.g. right ⌥ was for typing an @
        if shown and not resumed:
            if self._released is not None and not self._released.closed:  # an earlier release isn't out yet
                self._ui.set_state(MiloState.TRANSCRIBING)
            else:
                self._ui.rest()
