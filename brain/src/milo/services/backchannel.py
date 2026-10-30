"""A short "Hm." when Milo's first word is late, so a slow reply doesn't feel like nobody heard.

The clips are rendered once, at warm-up, in Milo's own voice, so playing one costs nothing. Each reply arms
a timer (`arm`). If no sound has gone out `LATE_S` after the user's words came in, and the first piece isn't about
to be ready either, one clip plays on the reply's own stream, ahead of the answer: "Hm. Sure, it's nine."

Never more than one per turn, never within `COOLDOWN_S` of the last, never the same clip twice in a row,
and never while Milo is held or someone else is speaking. `[chat] backchannels = false` turns them off.
"""

from __future__ import annotations

import asyncio
import logging

from milo.core.types import Audio, Emotion

from .speaker import Speaker, Utterance
from .speech_audio import shape

log = logging.getLogger("milo.backchannel")

CLIPS = ("Hm.", "Mm.", "Hmm.", "One sec.")
LATE_S = 2.0  # from the end of what the user said to Milo's first sound
SOON_S = 0.7  # the first piece will be ready within this: let it come
COOLDOWN_S = 30.0


class Backchannel:
    """Arms one filler per turn and plays it if the reply is late (see the module docstring)."""

    def __init__(self, speaker: Speaker, *, enabled: bool = True):
        self._speaker = speaker
        self.enabled = enabled
        self._clips: dict[str, Audio] = {}
        self._last: str | None = None
        self._last_at: float | None = None
        self._timer: asyncio.Task | None = None
        self._open = False  # a turn is streaming: a filler may start an utterance of its own
        self._filler: Utterance | None = None  # the utterance a filler started, until the reply takes it over
        self._reply: Utterance | None = None
        self._finishing: set[asyncio.Task] = set()
        self.played = 0

    def warm(self) -> None:
        """Render the clips. Blocking: run it on the TTS thread after the voice warmed up."""
        if not self.enabled:
            return
        voice = self._speaker.voice
        for text in CLIPS:
            try:
                self._clips[text] = shape(voice.synthesize(text), voice.sample_rate)
            except Exception:
                log.exception("could not render the backchannel %r", text)

    def arm(self) -> None:
        """A reply started: listen for it being late."""
        self.disarm()
        self._open, self._filler, self._reply = True, None, None
        if self.enabled and self._clips:
            self._timer = asyncio.create_task(self._wait())

    def disarm(self) -> None:
        if self._timer is not None and not self._timer.done():
            self._timer.cancel()
        self._timer = None

    def utterance(self, emotion: Emotion) -> Utterance:
        """The reply's utterance: the one a filler already began, or a new one. Use it instead of
        Speaker.utterance() for the reply that armed the timer."""
        u = self._filler
        if u is not None and self._speaker.current is u and u.open:
            self._speaker.ui.set_emotion(emotion)
        else:
            u = self._speaker.utterance(emotion)
        self._reply = u
        return u

    def release(self) -> None:
        """The reply's text is all in. The timer goes on watching its audio; a filler the reply never took
        (it was silent or failed) finishes on its own."""
        self._open = False
        if self._reply is None:
            self.disarm()
        u = self._filler
        if u is not None and u is not self._reply and not u.done:
            finishing = asyncio.create_task(u.finish())
            self._finishing.add(finishing)
            finishing.add_done_callback(self._finishing.discard)

    async def _wait(self) -> None:
        await asyncio.sleep(LATE_S)
        speaker = self._speaker
        now = asyncio.get_running_loop().time()
        if speaker.held or speaker.silent or (self._last_at is not None and now - self._last_at < COOLDOWN_S):
            return
        target = self._reply
        if target is not None:
            if target.done or target.first_sound_at is not None or target.ready_in() < SOON_S:
                return
        elif self._open and not speaker.active:
            target = self._filler = speaker.utterance(Emotion.THINKING)
        else:
            return
        text = next(t for t in self._order() if t in self._clips)
        if target.interject(text, self._clips[text]):
            self._last, self._last_at = text, now
            self.played += 1
            log.info("backchannel %r: the reply is late", text)

    def _order(self) -> list[str]:
        """The clips, starting after the last one played."""
        i = CLIPS.index(self._last) + 1 if self._last in CLIPS else 0
        return [*CLIPS[i:], *CLIPS[:i]]
