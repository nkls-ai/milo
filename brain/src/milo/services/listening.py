from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import Executor

from milo.core.events import Status
from milo.core.logtext import private
from milo.core.ports import AudioInput, Transcriber
from milo.core.types import STT_SAMPLE_RATE, ListenMode, LiveMode, MiloState

from .cloud_hearing import CloudHearing, CloudRecording
from .context import UserContext
from .dictation import DictationService
from .levels import throttled_levels
from .live_talk import LiveTalk
from .live_transcript import LiveTranscript, PauseSegmenter
from .ui_state import UiState

log = logging.getLogger("milo.listening")


class Listening:
    """Push-to-talk: record while the key is held, then transcribe and hand the text to dictation or live talk.

    The talk key is also barge-in: pressing it while Milo thinks or speaks stops him at once. He keeps his
    place (LiveTalk.hold): if the recording turns out empty or is cancelled, he goes on where he was.

    A tentative start records without showing anything (no state, no levels, no barge-in) until confirm()
    or stop(), because the key press may still turn out to be a tap. `live` transcribes while recording.
    `hearing` streams talk recordings (and dictation, if allowed) to a cloud transcriber while they are made;
    without it, or when it fails, the transcriber does the final pass.
    """

    def __init__(self, mic: AudioInput, transcriber: Transcriber, executor: Executor, ui: UiState,
                 dictation: DictationService, live_talk: LiveTalk, context: UserContext,
                 live: LiveMode = LiveMode.OFF, hearing: CloudHearing | None = None):
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
        self._hearing = hearing
        self._cloud: CloudRecording | None = None

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
        if self._hearing is not None and (not dictate or (self._hearing.dictation and
                                                          self._live_mode is not LiveMode.TYPE)):
            self._cloud = self._hearing.start(self._mic)
        if self._live_mode is LiveMode.OFF:
            return
        typed = self._dictation.typed() if dictate and self._live_mode is LiveMode.TYPE else None
        self._live = LiveTranscript(self._mic, self._transcriber.transcribe, self._executor, self._ui,
                                    PauseSegmenter(), typed, preview=self._transcriber.preview)
        self._live.start()

    async def stop(self) -> None:
        if not self._mic.active:
            return
        mode, self._mode = self._mode, None
        live, self._live = self._live, None
        cloud, self._cloud = self._cloud, None
        if not self._shown and mode is ListenMode.TALK:
            self._live_talk.hold()  # released before the confirm arrived: still a real hold
        self._shown = False
        audio = self._mic.stop()
        # The commit goes out at once; the live preview winds down meanwhile.
        heard = asyncio.create_task(self._hearing.transcribe(cloud, audio)) if cloud is not None else None
        self._ui.set_state(MiloState.TRANSCRIBING)
        started = time.monotonic()
        typed = None
        if live is not None:
            await live.close()
            typed = live.typed
            if typed is not None:
                audio = audio[live.tail_start:]  # earlier phrases are typed already
        text = await heard if heard is not None else None
        by_cloud = text is not None
        try:
            if text is None:
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
        log.info("stt %.2fs audio in %.2fs%s: %s", len(audio) / STT_SAMPLE_RATE, time.monotonic() - started,
                 " (cloud)" if by_cloud else "", private(text))
        text = text.strip()
        if typed is not None:
            typed.add(text)
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
        if live is not None:
            live.abort()
            if live.typed is not None:
                live.typed.finish(self._context.app)
        cloud, self._cloud = self._cloud, None
        if cloud is not None:
            cloud.cancel()
        if self._mic.active:
            self._mic.stop()
        mode, self._mode = self._mode, None
        shown, self._shown = self._shown, False
        resumed = mode is ListenMode.TALK and self._live_talk.resume()  # e.g. right ⌥ was for typing an @
        if shown and not resumed:
            self._ui.rest()
