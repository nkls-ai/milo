from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import Executor

from milo.core.events import Status
from milo.core.logtext import private
from milo.core.ports import AudioInput, Transcriber
from milo.core.types import STT_SAMPLE_RATE, ListenMode, LiveMode, MiloState

from .context import UserContext
from .dictation import DictationService, TypedDictation
from .levels import throttled_levels
from .live_talk import LiveTalk
from .live_transcript import LiveTranscript, PauseSegmenter
from .ui_state import UiState

log = logging.getLogger("milo.listening")


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
    """

    def __init__(self, mic: AudioInput, transcriber: Transcriber, executor: Executor, ui: UiState,
                 dictation: DictationService, live_talk: LiveTalk, context: UserContext,
                 live: LiveMode = LiveMode.OFF):
        self._mic = mic
        self._transcriber = transcriber
        self._executor = executor
        self._ui = ui
        self._dictation = dictation
        self._live_talk = live_talk
        self._context = context
        self._live_mode = live
        self._mode: ListenMode | None = None
        self._shown = False
        self._live: LiveTranscript | None = None
        self._typed: TypedDictation | None = None

    @property
    def live_mode(self) -> LiveMode:
        return self._live_mode

    @live_mode.setter
    def live_mode(self, mode: LiveMode) -> None:
        """Takes effect from the next recording."""
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
        if not tentative:
            self._show()

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
        if self._live_mode is LiveMode.OFF:
            return
        self._typed = self._dictation.typed() if dictate and self._live_mode is LiveMode.TYPE else None
        self._live = LiveTranscript(self._mic, self._transcriber, self._executor, self._ui, PauseSegmenter(),
                                    on_phrase=self._typed.add if self._typed is not None else None)
        self._live.start()

    async def stop(self) -> None:
        if not self._mic.active:
            return
        mode, self._mode = self._mode, None
        live, self._live = self._live, None
        typed, self._typed = self._typed, None
        if not self._shown and mode is ListenMode.TALK:
            self._live_talk.hold()  # released before the confirm arrived: still a real hold
        self._shown = False
        audio = self._mic.stop()
        self._ui.set_state(MiloState.TRANSCRIBING)
        started = time.monotonic()
        try:
            if live is not None:
                text = await live.finish(audio)
            else:
                text = await asyncio.get_running_loop().run_in_executor(
                    self._executor, self._transcriber.transcribe, audio)
        except Exception:
            log.exception("transcription failed")
            self._ui.emit(Status("I couldn't transcribe that."))
            if typed is not None:
                typed.finish(self._context.app)
            if mode is ListenMode.TALK:
                self._live_talk.interrupt(rest=False)
            self._ui.rest()
            return
        log.info("stt %.2fs audio, ready %.2fs after release: %s", len(audio) / STT_SAMPLE_RATE,
                 time.monotonic() - started, private(text))
        text = text.strip()
        if typed is not None:
            typed.finish(self._context.app)
            self._ui.rest()
        elif mode is ListenMode.DICTATE:
            self._dictation.handle(text, self._context.app)
            self._ui.rest()
        elif text:
            self._live_talk.start(text)
        elif not self._live_talk.resume():  # nothing said: go on with what was cut off
            self._ui.rest()

    def cancel(self) -> None:
        """Drop the recording. A tentative one vanishes without a trace; typed phrases stay typed."""
        live, self._live = self._live, None
        typed, self._typed = self._typed, None
        if live is not None:
            live.abort()
        if typed is not None:
            typed.finish(self._context.app)
        if self._mic.active:
            self._mic.stop()
        mode, self._mode = self._mode, None
        shown, self._shown = self._shown, False
        resumed = mode is ListenMode.TALK and self._live_talk.resume()  # e.g. right ⌥ was for typing an @
        if shown and not resumed:
            self._ui.rest()
