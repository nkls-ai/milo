"""Dictation that learns from the user's fixes (ADR 21).

The app watches the words it pasted for a while and reports the small fixes the user made by hand ("Cloud Code"
to "Claude Code"). Corrections keeps them in the dictionary and hands the words to the transcribers;
DictationFixes puts the meant words in before the next paste. No model call anywhere.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from milo.core.dictionary import Entries, Replacements
from milo.core.events import Status
from milo.core.logtext import private
from milo.core.ports import Dictionary, EventSink, TextCleaner, Vocabulary

log = logging.getLogger("milo.corrections")

MAX_PER_PASTE = 8
"""The app sends at most this many; more from one paste would be a rewrite, not fixes."""


class Corrections:
    """`enabled` is `[dictation] learn`, which the Settings window switches while Milo runs. `busy`: Milo talks,
    listens or asks, so the "Learned" note would get in the way (the file has it either way)."""

    def __init__(self, dictionary: Dictionary, ui: EventSink, vocabularies: Sequence[Vocabulary] = (), *,
                 busy: Callable[[], bool] = lambda: False, enabled: bool = True):
        self._dictionary = dictionary
        self._ui = ui
        self._vocabularies = tuple(vocabularies)
        self._busy = busy
        self.enabled = enabled

    def fixed(self, fixes: Sequence[tuple[str, str]]) -> None:
        """The user changed `heard` to `meant` in text Milo pasted, once for each pair."""
        if not self.enabled or not fixes:
            return
        learned = []
        for heard, meant in list(fixes)[:MAX_PER_PASTE]:
            try:
                outcome = self._dictionary.learn(heard, meant)
            except OSError as e:
                log.warning("could not save a dictation fix: %s", e)
                return
            log.info("dictation fix %s -> %s: %s", private(heard), private(meant), outcome)
            if outcome in ("new", "replaced"):
                learned.append(meant)
        self.refresh()
        if learned and not self._busy():
            self._ui.emit(Status(f"Learned: {', '.join(dict.fromkeys(learned))}"))

    def refresh(self) -> None:
        """Give the transcribers the dictionary's words if the file changed (Milo learned, or the user edited it).
        Called when a key goes down: one stat() when nothing changed."""
        if self._vocabularies and self._dictionary.changed():
            self.push()

    def push(self) -> None:
        try:
            words = self._dictionary.entries().vocabulary()
        except OSError as e:
            log.warning("could not read the dictionary: %s", e)
            return
        for vocabulary in self._vocabularies:
            vocabulary.use_vocabulary(words)


class DictationFixes:
    """A TextCleaner around the configured one: after it, the dictionary's fixes that apply replace what Whisper
    heard with what the user meant. The fixes are compiled again only when the file changed."""

    def __init__(self, cleaner: TextCleaner, dictionary: Dictionary):
        self._cleaner = cleaner
        self._dictionary = dictionary
        self._compiled: tuple[Entries, Replacements] | None = None

    def clean(self, text: str) -> str:
        text = self._cleaner.clean(text)
        if not text:
            return text
        replacements = self._replacements()
        return replacements.apply(text) if replacements else text

    def _replacements(self) -> Replacements:
        try:
            entries = self._dictionary.entries()
        except OSError as e:
            log.warning("could not read the dictionary: %s", e)
            entries = Entries()
        if self._compiled is None or self._compiled[0] is not entries:
            self._compiled = (entries, Replacements(entries.fixes))
        return self._compiled[1]
