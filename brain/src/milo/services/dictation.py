from __future__ import annotations

import logging

from milo.core.events import Dictation
from milo.core.ports import DictationHistory, EventSink, TextCleaner

log = logging.getLogger("milo.dictation")


class DictationService:
    """Turns a raw transcript into text the app pastes. History is optional ([dictation] keep_history)."""

    def __init__(self, cleaner: TextCleaner, history: DictationHistory | None, sink: EventSink):
        self._cleaner = cleaner
        self._history = history
        self._sink = sink

    def handle(self, transcript: str, app: str | None) -> str:
        text = self._cleaner.clean(transcript)
        if not text:
            return ""
        self._sink.emit(Dictation(text))
        _remember(self._history, text, app)
        return text

    def typed(self) -> TypedDictation:
        """For [dictation] stream = "type": pastes one recording phrase by phrase."""
        return TypedDictation(self._cleaner, self._history, self._sink)


class TypedDictation:
    """One recording pasted phrase by phrase. Each phrase is cleaned on its own; all but the first get a
    leading space, since they continue what was just pasted. A phrase that goes on mid-sentence (the last
    one didn't end a sentence and Whisper wrote this one in lower case) stays in lower case."""

    def __init__(self, cleaner: TextCleaner, history: DictationHistory | None, sink: EventSink):
        self._cleaner = cleaner
        self._history = history
        self._sink = sink
        self.texts: list[str] = []

    def add(self, transcript: str) -> str:
        """Clean and paste one phrase. Returns the cleaned text, "" if nothing was left to paste."""
        text = self._cleaner.clean(transcript)
        if not text:
            return ""
        raw = transcript.lstrip()
        if self.texts and raw[:1].islower() and not self.texts[-1].endswith((".", "!", "?", ":")):
            text = text[0].lower() + text[1:]
        self._sink.emit(Dictation(f" {text}" if self.texts else text))
        self.texts.append(text)
        return text

    def finish(self, app: str | None) -> None:
        """Log what was pasted as one history entry."""
        if self.texts:
            _remember(self._history, " ".join(self.texts), app)


def _remember(history: DictationHistory | None, text: str, app: str | None) -> None:
    if history is None:
        return
    try:
        history.append(text, app)
    except Exception:
        log.exception("could not save dictation history")
