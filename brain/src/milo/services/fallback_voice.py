from __future__ import annotations

import logging
from collections.abc import Callable

from milo.core.ports import Voice
from milo.core.types import Audio

log = logging.getLogger("milo.tts")


class FallbackVoice:
    """A Voice that swaps to a simpler engine if the configured one fails to load, so Milo still talks."""

    def __init__(self, primary: Voice, fallback_factory: Callable[[], Voice] | None):
        self._voice = primary
        self._fallback_factory = fallback_factory

    @property
    def current(self) -> Voice:
        return self._voice

    @property
    def sample_rate(self) -> int:
        return self._voice.sample_rate

    def warm(self) -> None:
        try:
            self._voice.warm()
        except Exception:
            if self._fallback_factory is None:
                raise
            log.exception("tts engine %s failed to load, switching to the fallback", type(self._voice).__name__)
            self._voice = self._fallback_factory()
            self._voice.warm()

    def synthesize(self, text: str) -> Audio:
        return self._voice.synthesize(text)

    def cancel(self) -> None:
        self._voice.cancel()
