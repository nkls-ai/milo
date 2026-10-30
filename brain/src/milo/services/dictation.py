from __future__ import annotations

import logging

from milo.core.events import Dictation
from milo.core.ports import DictationHistory, EventSink, TextCleaner

from .live_transcript import TypedDictation

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
        if self._history is not None:
            try:
                self._history.append(text, app)
            except Exception:
                log.exception("could not save dictation history")
        return text

    def typed(self) -> TypedDictation:
        """For [dictation] stream = "type": pastes one recording phrase by phrase."""
        return TypedDictation(self._cleaner, self._history, self._sink)
