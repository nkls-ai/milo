"""Whether the user is busy, asked one way everywhere (finding A2 of docs/review/2026-10-30.md).

Before, compose.py spelled it eight ways (`live_talk.busy or mic.active`, `... or speaker.active`, ...), and
each caller picked its own mix. Now the plain facts live here once and the callers ask a question by name, so
a new kind of activity is added in one place.

The parts are attached once they exist (compose builds LiveTalk after the services that ask). Until then a
part counts as idle.
"""

from __future__ import annotations

from collections.abc import Callable

from milo.core.types import MiloState

_IDLE: Callable[[], bool] = lambda: False

USER_SPEAKS = (MiloState.LISTENING, MiloState.DICTATING, MiloState.TRANSCRIBING)


class Attention:
    def __init__(self, state: Callable[[], MiloState] | None = None):
        self._state = state
        self.turn: Callable[[], bool] = _IDLE
        """A live turn runs: Milo is thinking or answering (LiveTalk.busy)."""
        self.mic: Callable[[], bool] = _IDLE
        """The talk or dictate key's recording runs."""
        self.voice: Callable[[], bool] = _IDLE
        """Milo is speaking."""
        self.question: Callable[[], bool] = _IDLE
        """A yes-or-no question waits for the user."""
        self.helpers: Callable[[], bool] = _IDLE
        """A helper is at work."""

    def attach(self, *, turn: Callable[[], bool] | None = None, mic: Callable[[], bool] | None = None,
               voice: Callable[[], bool] | None = None, question: Callable[[], bool] | None = None,
               helpers: Callable[[], bool] | None = None) -> None:
        for name, part in (("turn", turn), ("mic", mic), ("voice", voice), ("question", question),
                           ("helpers", helpers)):
            if part is not None:
                setattr(self, name, part)

    # ---- the questions

    def in_conversation(self) -> bool:
        """The user is recording or Milo is answering: don't speak up, a question can wait for the bubble."""
        return self.turn() or self.mic()

    def using_voice(self) -> bool:
        """In a conversation or Milo is still speaking: a notice would talk over someone."""
        return self.in_conversation() or self.voice()

    def occupied(self) -> bool:
        """Using the voice, or a question waits: a helper's progress note would get in the way."""
        return self.using_voice() or self.question()

    def at_work(self) -> bool:
        """Milo is answering or a helper works: not the time for the nightly consolidation."""
        return self.turn() or self.helpers()

    def private(self) -> bool:
        """The user talks to Milo or Milo speaks: these moments stay out of a meeting's notes."""
        return self.mic() or self.voice()

    def user_speaking(self) -> bool:
        """A key is down or its words are still being transcribed: meeting passes give way."""
        return self.mic() or (self._state is not None and self._state() in USER_SPEAKS)

    def recording(self) -> bool:
        """The talk or dictate key's recording runs: barge-in leaves the mic to it."""
        return self.mic()

    def answering(self) -> bool:
        """A live turn runs: a nudge waits for it to end."""
        return self.turn()
