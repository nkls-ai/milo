from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import Executor

from milo.core.events import Status
from milo.core.logtext import private
from milo.core.ports import AudioInput, Transcriber
from milo.core.types import STT_SAMPLE_RATE, ListenMode, MiloState

from .context import UserContext
from .dictation import DictationService
from .levels import throttled_levels
from .live_talk import LiveTalk
from .ui_state import UiState

log = logging.getLogger("milo.listening")


class Listening:
    """Push-to-talk: record while the key is held, then transcribe and hand the text to dictation or live talk.

    The talk key is also barge-in: pressing it while Milo thinks or speaks stops him at once.
    """

    def __init__(self, mic: AudioInput, transcriber: Transcriber, executor: Executor, ui: UiState,
                 dictation: DictationService, live_talk: LiveTalk, context: UserContext):
        self._mic = mic
        self._transcriber = transcriber
        self._executor = executor
        self._ui = ui
        self._dictation = dictation
        self._live_talk = live_talk
        self._context = context
        self._mode: ListenMode | None = None

    def start(self, mode: ListenMode) -> None:
        if self._mic.active:
            return
        # Barge-in. rest=False: LISTENING comes next, no flash of IDLE in between.
        stopped = mode is ListenMode.TALK and self._live_talk.interrupt(rest=False)
        try:
            self._mic.start(throttled_levels(self._ui, asyncio.get_running_loop()))
        except Exception as e:
            log.exception("mic failed")
            self._ui.emit(Status(f"Mic unavailable: {e}"))
            if stopped:
                self._ui.rest()
            return
        self._mode = mode
        self._ui.set_state(MiloState.DICTATING if mode is ListenMode.DICTATE else MiloState.LISTENING)

    async def stop(self) -> None:
        if not self._mic.active:
            return
        mode, self._mode = self._mode, None
        audio = self._mic.stop()
        self._ui.set_state(MiloState.TRANSCRIBING)
        started = time.monotonic()
        try:
            text = await asyncio.get_running_loop().run_in_executor(
                self._executor, self._transcriber.transcribe, audio)
        except Exception:
            log.exception("transcription failed")
            self._ui.emit(Status("I couldn't transcribe that."))
            self._ui.rest()
            return
        log.info("stt %.2fs audio in %.2fs: %s", len(audio) / STT_SAMPLE_RATE, time.monotonic() - started,
                 private(text))
        text = text.strip()
        if mode is ListenMode.DICTATE:
            self._dictation.handle(text, self._context.app)
            self._ui.rest()
        elif text:
            self._live_talk.start(text)
        else:
            self._ui.rest()

    def cancel(self) -> None:
        if self._mic.active:
            self._mic.stop()
        self._mode = None
        self._ui.rest()
