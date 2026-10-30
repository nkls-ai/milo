from __future__ import annotations

from milo.core.events import Bubble, EmotionChanged, Event, StateChanged
from milo.core.ports import EventSink
from milo.core.types import Emotion, MiloState


class UiState:
    """An EventSink that remembers what the avatar shows, so services can agree on the state to return to.

    Speaker sets `speaking` and LiveTalk sets `thinking`; `resting()` turns those into the state to show
    once a step (recording, transcribing, a turn) finishes.
    """

    def __init__(self, sink: EventSink):
        self._sink = sink
        self.state = MiloState.IDLE
        self.emotion = Emotion.NEUTRAL
        self.speaking = False
        self.thinking = False
        self.bubble = ""
        """The text in the speech bubble: the last thing Milo said or showed."""

    def emit(self, event: Event) -> None:
        if isinstance(event, StateChanged):
            self.state = event.state
        elif isinstance(event, EmotionChanged):
            self.emotion = event.emotion
        elif isinstance(event, Bubble):
            self.bubble = event.text
        self._sink.emit(event)

    def set_state(self, state: MiloState) -> None:
        self.emit(StateChanged(state))

    def set_emotion(self, emotion: Emotion) -> None:
        self.emit(EmotionChanged(emotion))

    def resting(self) -> MiloState:
        if self.speaking:
            return MiloState.SPEAKING
        return MiloState.THINKING if self.thinking else MiloState.IDLE

    def rest(self) -> None:
        self.set_state(self.resting())
