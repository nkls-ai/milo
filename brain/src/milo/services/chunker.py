from __future__ import annotations

import re

FIRST_MIN_WORDS = 5
FIRST_MAX_WORDS = 12
MIN_BUDGET = 45  # shorter pieces synthesize slower than they play, so they never help
MAX_CHARS = 220
OVERSHOOT = 1.4
"""A boundary this far past the budget beats a cut mid-clause: a short pause sounds better than broken prosody."""

# Punctuation counts as a boundary only once the following whitespace has arrived, so "2.5" never splits.
# A sentence also needs the next word to start with something other than a lowercase letter ("e.g. this").
_SENTENCE = re.compile(r"[.!?…]+[\"'”’)\]]*\s+(?=[^\s])")
_CLAUSE = re.compile(r"[,;:–—]\s+")
_WORD = re.compile(r"\S+(?=\s)")


class SpeechChunker:
    """Cuts streamed text into pieces for TTS, sized so the next piece is ready before the audio runs out.

    The first piece goes early so Milo starts talking: at the first clause or sentence end once there are
    FIRST_MIN_WORDS words, or after FIRST_MAX_WORDS words if no punctuation comes. Every later piece gets a
    budget, the characters the voice can synthesize while the queued audio plays, and ends at the furthest
    sentence or clause boundary that fits it.
    """

    def __init__(self):
        self._buf = ""
        self._first = True

    @property
    def empty(self) -> bool:
        return not self._buf.strip()

    def add(self, text: str) -> None:
        self._buf += text

    def next(self, budget: int | None = None, *, final: bool = False) -> str | None:
        """The next piece to synthesize, or None to wait for more text.

        `budget` is ignored for the first piece. `final` means no more text is coming, so the rest goes out.
        """
        if self.empty:
            self._buf = ""
            return None
        if self._first:
            cut = self._first_cut(self._buf)
        else:
            cut = self._budget_cut(self._buf, min(MAX_CHARS, max(MIN_BUDGET, MAX_CHARS if budget is None else budget)))
        if cut is None and final:
            cut = len(self._buf) if self._first or len(self._buf) <= MAX_CHARS else _hard_cut(self._buf, MAX_CHARS)
        if cut is None:
            return None
        chunk, self._buf = _tidy(self._buf[:cut]), self._buf[cut:].lstrip()
        self._first = False
        return chunk or self.next(budget, final=final)

    def flush(self) -> str:
        """Everything not yet returned, ready to speak. "" if nothing is left."""
        rest, self._buf = _tidy(self._buf), ""
        return rest

    @staticmethod
    def _first_cut(text: str) -> int | None:
        for end in _boundaries(text):
            if len(text[:end].split()) >= FIRST_MIN_WORDS:
                return end
        for i, m in enumerate(_WORD.finditer(text), 1):
            if i == FIRST_MAX_WORDS:
                return m.end()
        return _hard_cut(text, MAX_CHARS) if len(text) >= MAX_CHARS else None

    @staticmethod
    def _budget_cut(text: str, budget: int) -> int | None:
        ends = _boundaries(text)
        fitting = [e for e in ends if e <= budget]
        if fitting:
            return fitting[-1]
        near = [e for e in ends if e <= budget * OVERSHOOT]
        if near:
            return near[0]
        if len(text) > budget:
            return _hard_cut(text, budget)
        return None


def _boundaries(text: str) -> list[int]:
    """Sentence and clause ends, in order."""
    sentences = (m.end() for m in _SENTENCE.finditer(text) if not text[m.end()].islower())
    return sorted({*sentences, *(m.end() for m in _CLAUSE.finditer(text))})


def _hard_cut(text: str, limit: int) -> int:
    """Where to cut text with no usable boundary: the last space before `limit`, else `limit`."""
    space = text.rfind(" ", 0, limit + 1)
    return space + 1 if space > limit // 3 else limit


def _tidy(text: str) -> str:
    return " ".join(text.split())
