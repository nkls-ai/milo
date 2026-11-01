"""Pure speech guards and vocabulary shared by both local Whisper engines."""
from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np

from milo.core.types import Audio, STT_SAMPLE_RATE

MIN_SECONDS = 0.3
MIN_RMS = 0.004
LEARNED_CHARS = 400
_HALLUCINATIONS = {
    "thank you", "thanks for watching", "thank you for watching", "you", "bye", ".",
    "untertitel im auftrag des zdf", "untertitelung des zdf", "vielen dank", "tschüss",
    "untertitel der amara.org-community", "closed captioning by www.microsoft.com",
    "subtitles by the amara.org community",
}


def is_silent(audio: Audio) -> bool:
    if len(audio) < STT_SAMPLE_RATE * MIN_SECONDS:
        return True
    return float(np.sqrt(np.mean(np.square(audio)))) < MIN_RMS


def is_hallucination(text: str) -> bool:
    key = re.sub(r"[!?.,]+$", "", text.strip().lower()).strip()
    return key in _HALLUCINATIONS or key.startswith("untertitel")


def vocabulary_prompt(configured: str, words: Sequence[str]) -> str:
    """Configured terms followed by deduplicated learned terms, capped at LEARNED_CHARS."""
    known = {w.strip().lower() for w in configured.split(",") if w.strip()}
    extra: list[str] = []
    size = 0
    for word in words:
        word = " ".join(word.split())
        if not word or word.lower() in known:
            continue
        if size + len(word) + 2 > LEARNED_CHARS:
            break
        known.add(word.lower())
        extra.append(word)
        size += len(word) + 2
    return ", ".join(p for p in (configured.strip().rstrip(","), *extra) if p)
