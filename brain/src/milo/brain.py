"""Routes each command from the app to the service that owns it."""

from __future__ import annotations

import logging
from pathlib import Path

from .config import UiSettings
from .core.events import (AppResponse, Command, ConfirmAnswer, ContextUpdate, EmotionChanged, Event, GetHistory,
                          HandsResult, HandsStop, ListenCancel, ListenConfirm, ListenStart, ListenStop, LookResult,
                          GetSettings, Mute, SetSetting, StateChanged, TextInput, UiConfig, WhatsThis)
from .services.app_bridge import AppBridge
from .services.approvals import Approvals
from .services.context import UserContext
from .services.hands import HandsService
from .services.heartbeat_runner import HeartbeatRunner
from .services.listening import Listening
from .services.live_talk import LiveTalk
from .services.screen import checked, inside
from .services.transcript import Transcript
from .services.ui_state import UiState
from .settings import Settings

log = logging.getLogger("milo.brain")

WHATS_THIS = "What's this?"


class Brain:
    """`bridge` resolves the app's answers to looks, Mac actions and app work; `approvals` takes the answers
    to Milo's questions. `screens` is state/screens: an image path from the app counts only if it points in there."""

    def __init__(self, ui: UiState, listening: Listening, live_talk: LiveTalk, context: UserContext,
                 heartbeat: HeartbeatRunner | None, ui_settings: UiSettings, transcript: Transcript | None = None,
                 *, approvals: Approvals | None = None, bridge: AppBridge | None = None,
                 hands: HandsService | None = None, screens: Path | None = None, settings: Settings | None = None):
        self._settings = settings
        self._hands = hands
        self._screens = screens
        self._ui = ui
        self._approvals = approvals
        self._bridge = bridge
        self._transcript = transcript
        self._listening = listening
        self._live_talk = live_talk
        self._context = context
        self._heartbeat = heartbeat
        self._ui_settings = ui_settings

    def greeting(self) -> list[Event]:
        """What a newly connected app needs to draw Milo as he is right now."""
        return [StateChanged(self._ui.state), EmotionChanged(self._ui.emotion), self._ui_config(), *self._history()]

    def use_ui(self, ui_settings: UiSettings) -> None:
        """Keys or look changed in the Settings window: tell the app now and on every later connect."""
        self._ui_settings = ui_settings
        self._ui.emit(self._ui_config())

    def _ui_config(self) -> UiConfig:
        ui = self._ui_settings
        return UiConfig(ui.dictate_key, ui.talk_key, ui.hands_free_max_s, ui.whats_this_key, ui.character)

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
            case LookResult(id, capture):
                self._answer(id, checked(capture, self._screens))
            case WhatsThis(capture):
                self._live_talk.start(WHATS_THIS, via="typed", capture=checked(capture, self._screens))
            case HandsResult(id, ok, result, error):
                if "image" in result:
                    result = {**result, "image": inside(str(result["image"]), self._screens)}
                self._answer(id, (ok, result, error))
            case HandsStop(reason):
                if self._hands is not None:
                    self._hands.stop(reason)
            case Mute(on):
                log.info("proactive nudges %s", "muted" if on else "on")
                if self._heartbeat is not None:
                    self._heartbeat.muted = on
            case ConfirmAnswer(id, yes):
                if self._approvals is not None and not self._approvals.answer(id, yes):
                    log.info("an answer came for a question that is over")
            case AppResponse():
                if self._bridge is not None:
                    self._bridge.resolve(command)
            case GetSettings():
                if self._settings is not None:
                    self._settings.send()
            case SetSetting(section, key, value):
                if self._settings is not None:
                    self._settings.change(section, key, value)
            case _:
                log.warning("no handler for %s", command.type)

    def _answer(self, id: str, value: object) -> None:
        if self._bridge is not None:
            self._bridge.answer(id, value)
