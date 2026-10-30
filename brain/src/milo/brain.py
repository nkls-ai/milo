"""Routes each command from the app to the service that owns it."""

from __future__ import annotations

import logging

from .config import UiSettings
from .core.events import (Command, ContextUpdate, EmotionChanged, Event, GetHistory, ListenCancel, ListenConfirm,
                          ListenStart, ListenStop, Mute, StateChanged, TextInput, UiConfig)
from .services.context import UserContext
from .services.heartbeat_runner import HeartbeatRunner
from .services.listening import Listening
from .services.live_talk import LiveTalk
from .services.transcript import Transcript
from .services.ui_state import UiState

log = logging.getLogger("milo.brain")


class Brain:
    def __init__(self, ui: UiState, listening: Listening, live_talk: LiveTalk, context: UserContext,
                 heartbeat: HeartbeatRunner | None, ui_settings: UiSettings, transcript: Transcript | None = None):
        self._ui = ui
        self._transcript = transcript
        self._listening = listening
        self._live_talk = live_talk
        self._context = context
        self._heartbeat = heartbeat
        self._ui_settings = ui_settings

    def greeting(self) -> list[Event]:
        """What a newly connected app needs to draw Milo as he is right now."""
        return [StateChanged(self._ui.state), EmotionChanged(self._ui.emotion),
                UiConfig(self._ui_settings.dictate_key, self._ui_settings.talk_key,
                         self._ui_settings.hands_free_max_s),
                *self._history()]

    def _history(self) -> list[Event]:
        return [self._transcript.history()] if self._transcript is not None else []

    async def handle(self, command: Command) -> None:
        match command:
            case ListenStart(mode, tentative):
                self._listening.start(mode, tentative)
            case ListenConfirm():
                self._listening.confirm()
            case ListenStop():
                await self._listening.stop()
            case ListenCancel():
                self._listening.cancel()
            case TextInput(text, speak):
                self._live_talk.start(text, via="typed", speak=speak)
            case GetHistory():
                for event in self._history():
                    self._ui.emit(event)
            case ContextUpdate(app, idle_s):
                self._context.update(app, idle_s)
            case Mute(on):
                log.info("proactive nudges %s", "muted" if on else "on")
                if self._heartbeat is not None:
                    self._heartbeat.muted = on
            case _:
                log.warning("no handler for %s", command.type)
