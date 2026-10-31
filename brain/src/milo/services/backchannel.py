"""A short "Hm." when Milo's first word is late, so a slow reply doesn't feel like nobody heard.

The clips are rendered once, at warm-up, in Milo's own voice, so playing one costs nothing. Each reply arms
a timer (`arm`). Only if none of the model's text has come in `LATE_S` after the reply started does a clip queue
up, and only if still none comes in the next `QUEUE_S` does it play, on the stream the reply then goes on:
"Hm. Sure, it's nine." Text that is in already means the answer is close, so a clip would only land just before it
(it did, 0.1 to 0.3 s ahead, in 7 of the first 11).

Never on a conversation's first turn or a greeting, never more than one per turn, never within `COOLDOWN_S` of the
last, never the same clip twice in a row, and never while Milo is held or someone else is speaking.
`[chat] backchannels = false` turns them off.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path

import numpy as np

from milo.core.types import Audio, Emotion

from .speaker import Speaker, Utterance
from .speech_audio import shape

log = logging.getLogger("milo.backchannel")

CLIPS = ("Hm.", "Mm.", "Hmm.", "One sec.")
LATE_S = 1.8  # from the start of the reply to a clip queueing up, if no text came
QUEUE_S = 0.25  # the clip waits this long more; text in the meantime cancels it
COOLDOWN_S = 30.0
GREETING_WORDS = 5
_GREETING = re.compile(r"^\W*(hey|hi|hello|hallo|hallöchen|moin|servus|grüß dich|na|yo|good (morning|afternoon|evening)|"
                       r"guten (morgen|tag|abend))\b", re.IGNORECASE)


def is_greeting(text: str) -> bool:
    """"Hey, Milo", "Hi Milo, how are you?", "Guten Morgen": a short turn that opens with a greeting."""
    return bool(_GREETING.match(text)) and len(text.split()) <= GREETING_WORDS


class Backchannel:
    """Arms one filler per turn and plays it if the reply is late (see the module docstring)."""

    def __init__(self, speaker: Speaker, *, enabled: bool = True, cache: Path | None = None):
        self._speaker = speaker
        self.enabled = enabled
        self._cache = cache
        """Where rendered clips are kept between runs. A paid voice charged for every clip on every start: 57
        restarts in a day used up more than a tenth of the month's ElevenLabs credits."""
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
                self._clips[text] = shape(self._render(voice, text), voice.sample_rate)
            except Exception:
                log.exception("could not render the backchannel %r", text)

    def _render(self, voice, text: str) -> Audio:
        """The clip from the cache when this very voice made it before, else rendered (and kept, if the voice that
        rendered it has a key: not a fallback that stood in)."""
        key = getattr(voice, "clip_key", None)
        path = None
        if self._cache is not None and key:
            path = self._cache / (hashlib.sha256(f"{key}\n{text}".encode()).hexdigest()[:24] + ".npy")
            try:
                return np.load(path)
            except (OSError, ValueError):
                pass
        audio = voice.synthesize(text)
        if path is not None and getattr(voice, "clip_key", None) == key:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                np.save(path, np.asarray(audio, dtype=np.float32))
            except OSError as e:
                log.info("could not keep the backchannel %r: %s", text, e)
        return audio

    def arm(self, text: str = "", *, first: bool = False) -> None:
        """A reply to `text` started: listen for it being late. `first`: the conversation's first turn, which
        never gets a clip (nor does a greeting)."""
        self.disarm()
        self._open, self._filler, self._reply = True, None, None
        if self.enabled and self._clips and not first and not is_greeting(text):
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
        """The reply's text is all in. A filler the reply never took (it was silent or failed) finishes on its
        own."""
        self._open = False
        self.disarm()
        u = self._filler
        if u is not None and u is not self._reply and not u.done:
            finishing = asyncio.create_task(u.finish())
            self._finishing.add(finishing)
            finishing.add_done_callback(self._finishing.discard)

    async def _wait(self) -> None:
        await asyncio.sleep(LATE_S)
        if not self._late():
            return
        await asyncio.sleep(QUEUE_S)  # queued: text arriving now cancels it
        if not self._late():
            return
        target = self._filler = self._speaker.utterance(Emotion.THINKING)
        text = next(t for t in self._order() if t in self._clips)
        if target.interject(text, self._clips[text]):
            self._last, self._last_at = text, asyncio.get_running_loop().time()
            self.played += 1
            log.info("backchannel %r: no text from the model yet", text)

    def _late(self) -> bool:
        """Still nothing from the model, and a clip may play now."""
        speaker = self._speaker
        now = asyncio.get_running_loop().time()
        return (self._open and self._reply is None and not speaker.active and not speaker.held and not speaker.silent
                and (self._last_at is None or now - self._last_at >= COOLDOWN_S))

    def _order(self) -> list[str]:
        """The clips, starting after the last one played."""
        i = CLIPS.index(self._last) + 1 if self._last in CLIPS else 0
        return [*CLIPS[i:], *CLIPS[:i]]
