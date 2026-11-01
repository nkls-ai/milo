"""Paces the bubble's words to Milo's voice (MiloKit/SpeechReveal.swift).

The brain sends the bubble one spoken piece at a time, as its audio starts. The new piece is laid out at once,
hidden, so nothing reflows; its words then show one by one at the speed he speaks. When the next piece arrives the
last one has been heard: what is still hidden shows, and the time it took teaches the speed. Unspoken text shows whole.
"""
from __future__ import annotations

from dataclasses import dataclass

START_RATE = 15.0  # characters a second before he said anything: about 150 words a minute
RATES = (9.0, 30.0)  # outside this is a pause or a hiccup, not his talking speed
FADE = 0.16  # seconds a new word takes to fade in


@dataclass
class Cut:
    shown: int
    fresh: int
    alpha: float


@dataclass
class SpeechReveal:
    text: str = ""
    settled: int = 0
    since: float = 0.0
    rate: float = START_RATE
    paced: bool = False

    def show(self, new: str, *, speaking: bool, at: float) -> None:
        try:
            if not speaking or not new:
                self.settled = len(new)
                self.paced = False
                return
            if new == self.text:
                return
            if len(new) > len(self.text) and new.startswith(self.text):
                # The next piece: the last one has been heard.
                if self.paced:
                    self._learn(len(self.text) - self.settled, at - self.since)
                self.settled = len(self.text)
            else:
                self.settled = 0  # a new answer
            self.since = at
            self.paced = True
        finally:
            self.text = new

    def clear(self) -> None:
        """The bubble went away. The speed he talks at stays."""
        self.text, self.settled, self.paced = "", 0, False

    def finish(self) -> None:
        """Milo stopped talking: everything shows."""
        self.settled, self.paced = len(self.text), False

    def _learn(self, characters: float, seconds: float) -> None:
        if seconds <= 0.3 or characters <= 8:
            return
        measured = min(RATES[1], max(RATES[0], characters / seconds))
        self.rate = (self.rate + measured) / 2

    def cut(self, now: float) -> Cut:
        """The characters shown in full, then one word fading in at `alpha`. Cuts fall on word ends."""
        if not self.paced or self.settled >= len(self.text):
            return Cut(len(self.text), 0, 1.0)
        reach = self.settled + max(0, int((now - self.since) * self.rate))
        end = _word_end(self.text, min(reach, len(self.text)))
        if end <= self.settled:
            return Cut(self.settled, 0, 1.0)
        start = _word_start(self.text, end, self.settled)
        revealed_at = self.since + (start - self.settled) / self.rate
        alpha = min(1.0, max(0.2, (now - revealed_at) / FADE))
        return Cut(end, 0, 1.0) if alpha >= 1 else Cut(start, end - start, alpha)

    def done(self, now: float) -> bool:
        cut = self.cut(now)
        return cut.shown + cut.fresh >= len(self.text) and cut.alpha >= 1


def _word_end(text: str, index: int) -> int:
    while index < len(text) and not text[index].isspace():
        index += 1
    return index


def _word_start(text: str, end: int, floor: int) -> int:
    i = end
    while i > floor and not text[i - 1].isspace():
        i -= 1
    while i > floor and text[i - 1].isspace():
        i -= 1
    return i
