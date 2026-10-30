"""Routes each command from the app to the service that owns it."""

from __future__ import annotations

import logging
from pathlib import Path

from .config import UiSettings
from .core.events import (AppResponse, Command, ConfirmAnswer, ContextUpdate, EmotionChanged, Event, GetHistory,
                          HandsResult, HandsStop, ListenCancel, ListenConfirm, ListenStart, ListenStop, LookResult,
                          Mute, RemoteForget, RemotePause, StateChanged, StopHelper, TextInput, UiConfig, WhatsThis)
from .services.app_bridge import AppBridge
from .services.approvals import Approvals
from .services.context import UserContext
from .services.hands import HandsService
from .services.heartbeat_runner import HeartbeatRunner
from .services.listening import Listening
from .services.live_talk import LiveTalk
from .services.messages import MessageService
from .services.orchestrator import Orchestrator
from .services.screen import checked, inside
from .services.transcript import Transcript
from .services.ui_state import UiState

log = logging.getLogger("milo.brain")

WHATS_THIS = "What's this?"


class Brain:
    """`bridge` resolves the app's answers to looks, Mac actions and app work; `approvals` takes the answers
    to Milo's questions. `screens` is state/screens: an image path from the app counts only if it points in there."""

    def __init__(self, ui: UiState, listening: Listening, live_talk: LiveTalk, context: UserContext,
                 heartbeat: HeartbeatRunner | None, ui_settings: UiSettings, transcript: Transcript | None = None,
                 *, approvals: Approvals | None = None, bridge: AppBridge | None = None,
                 hands: HandsService | None = None, screens: Path | None = None,
                 helpers: Orchestrator | None = None, messages: MessageService | None = None):
        self._hands = hands
        self._messages = messages
        self._helpers = helpers
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
        return [StateChanged(self._ui.state), EmotionChanged(self._ui.emotion),
                UiConfig(self._ui_settings.dictate_key, self._ui_settings.talk_key,
                         self._ui_settings.hands_free_max_s, self._ui_settings.whats_this_key,
                         self._ui_settings.character),
                *self._history(), *([self._helpers.snapshot()] if self._helpers is not None else []),
                *([self._messages.status()] if self._messages is not None else [])]

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
            case StopHelper(id):
                if self._helpers is not None and not self._helpers.stop(id):
                    log.info("Stop came for a helper that isn't working")
            case RemotePause(on):
                if self._messages is not None:
                    self._messages.pause(on)
            case RemoteForget():
                if self._messages is not None:
                    self._messages.forget()
            case AppResponse():
                if self._bridge is not None:
                    self._bridge.resolve(command)
            case _:
                log.warning("no handler for %s", command.type)

    def _answer(self, id: str, value: object) -> None:
        if self._bridge is not None:
            self._bridge.answer(id, value)
