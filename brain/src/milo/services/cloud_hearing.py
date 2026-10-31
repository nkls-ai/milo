"""Listening along in the cloud: the recording streams to a StreamingTranscriber while the key is held, so the text
is there right after the key comes up, instead of after a full Whisper pass.

Only for recordings config.toml lets leave the Mac (`[stt] talk`, and dictation only with `[stt] cloud_dictation`).
If the service can't answer (offline, a bad key, too slow), the recording is transcribed locally as before, the
cloud gets another try after RETRY_S, and Milo says once that he is listening on his own for now.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable

from milo.core.ports import AudioInput, StreamingTranscriber, TranscriptionSession
from milo.core.types import Audio, VoiceUnavailable

log = logging.getLogger("milo.hearing")

POLL_S = 0.1  # how often new microphone audio goes out
RETRY_S = 120.0

NOTICE = "I can't reach the cloud to listen right now, so I'm transcribing on this Mac for a while."


class CloudRecording:
    """One recording on its way to the cloud: sends what the microphone has every POLL_S."""

    def __init__(self, session: TranscriptionSession, mic: AudioInput):
        self._session = session
        self._mic = mic
        self._sent = 0
        self._pump = asyncio.create_task(self._send_along())

    @property
    def language(self) -> str:
        """The language the service heard ("en", "deu"), once finish() returned; "" if it didn't say."""
        return str(getattr(self._session, "language", "") or "")

    async def finish(self, recording: Audio) -> str:
        """The whole recording (as AudioInput.stop() returned it): send the rest and wait for the text.
        Raises VoiceUnavailable."""
        self._pump.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._pump
        self._session.feed(recording[self._sent:])
        return await self._session.finish()

    def cancel(self) -> None:
        self._pump.cancel()
        self._session.cancel()

    async def _send_along(self) -> None:
        while True:
            audio = self._mic.peek(self._sent)
            if len(audio):
                self._session.feed(audio)
                self._sent += len(audio)
            await asyncio.sleep(POLL_S)


class CloudHearing:
    """Starts cloud recordings, and stops starting them for a while after one failed."""

    def __init__(self, engine: StreamingTranscriber, *, dictation: bool = False,
                 on_switch: Callable[[str], None] | None = None, clock: Callable[[], float] = time.monotonic):
        self._engine = engine
        self.dictation = dictation
        """Dictation may go to the cloud too, not only talking to Milo."""
        self.on_switch = on_switch
        self._clock = clock
        self._down_since: float | None = None

    def start(self, mic: AudioInput, on_partial: Callable[[str], None] | None = None) -> CloudRecording | None:
        """A recording that listens along, or None while the cloud is down. `on_partial` gets the live words."""
        if self._down_since is not None:
            if self._clock() - self._down_since < RETRY_S:
                return None
            self._down_since = None
        return CloudRecording(self._engine.session(on_partial), mic)

    def failed(self, reason: str) -> None:
        now = self._clock()
        if self._down_since is None:
            log.warning("cloud transcription failed, transcribing locally for %.0f s: %s", RETRY_S, reason)
            if self.on_switch is not None:
                self.on_switch(reason)
        self._down_since = now

    async def transcribe(self, recording: CloudRecording, audio: Audio) -> str | None:
        """The text of a finished recording, or None if the cloud couldn't say (transcribe it locally)."""
        try:
            return await recording.finish(audio)
        except VoiceUnavailable as e:
            self.failed(str(e))
            return None
        except Exception as e:
            # Anything else (a library bug, a malformed answer) must not leave Milo stuck transcribing.
            log.exception("cloud transcription crashed")
            self.failed(str(e) or type(e).__name__)
            return None
