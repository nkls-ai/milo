"""Routes each command from the app to the service that owns it."""

from __future__ import annotations

import logging
from pathlib import Path

from .config import UiSettings
from .core.events import (AppResponse, CallEnded, CallStarted, Command, ConfirmAnswer, ContextUpdate, DictationFixed,
                          EditFact,
                          EmotionChanged, Event, Facts, ForgetFact, GetConversations, GetFacts, GetHistory,
                          GetSettings, GetUsage, HandsResult, HandsStop, ListenCancel, ListenConfirm, ListenStart,
                          ListenStop,
                          LookResult, MeetingChunk, MeetingMail, MeetingPause, MeetingRecording, MeetingTodo,
                          MeetingToggle, Mute, OpenMeeting, NewConversation,
                          OpenConversation, RemoteForget, RemotePause, RenameConversation, RoutineAction,
                          RoutineDraftAnswer, SearchConversations, SetSetting, StateChanged, StopAll, StopHelper,
                          TextInput, UiConfig, WhatsThis)
from .core.types import ListenMode
from .services.app_bridge import AppBridge
from .services.approvals import Approvals
from .services.context import UserContext
from .services.corrections import Corrections
from .services.conversations import ConversationBrowser
from .services.hands import HandsService
from .services.heartbeat_runner import HeartbeatRunner
from .services.listening import Listening
from .services.live_talk import LiveTalk
from .services.meetings import MeetingService
from .services.memory import Memory
from .services.messages import MessageService
from .services.orchestrator import Orchestrator
from .services.routines import Routines
from .services.screen import checked, inside
from .services.transcript import Transcript
from .services.ui_state import UiState
from .services.usage import UsageService
from .settings import Settings

log = logging.getLogger("milo.brain")

WHATS_THIS = "What's this?"


class Brain:
    """`bridge` resolves the app's answers to looks, Mac actions and app work; `approvals` takes the answers
    to Milo's questions. `screens` is state/screens: an image path from the app counts only if it points in there.
    `settings` reads and changes config.toml for the Settings window and the menu. `usage` answers the Usage page."""

    def __init__(self, ui: UiState, listening: Listening, live_talk: LiveTalk, context: UserContext,
                 heartbeat: HeartbeatRunner | None, ui_settings: UiSettings, transcript: Transcript | None = None,
                 *, approvals: Approvals | None = None, bridge: AppBridge | None = None,
                 hands: HandsService | None = None, screens: Path | None = None,
                 helpers: Orchestrator | None = None, memory: Memory | None = None,
                 routines: Routines | None = None, settings: Settings | None = None,
                 messages: MessageService | None = None, meetings: MeetingService | None = None,
                 conversations: ConversationBrowser | None = None, usage: UsageService | None = None,
                 corrections: Corrections | None = None):
        self._conversations = conversations
        self._usage = usage
        self._corrections = corrections
        self._meetings = meetings
        self._memory = memory
        self._routines = routines
        self._settings = settings
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
        return [StateChanged(self._ui.state), EmotionChanged(self._ui.emotion), self._ui_config(),
                *([self._settings.report()] if self._settings is not None else []),
                *self._history(), *([self._helpers.snapshot()] if self._helpers is not None else []),
                *([self._meetings.status_event()] if self._meetings is not None else []),
                *([self._messages.status()] if self._messages is not None else [])]

    def app_gone(self) -> None:
        """No app is connected any more (it quit or crashed). A recording it started can't be stopped by its key
        any more: drop it, so the mic doesn't stay on and the next key press isn't ignored."""
        self._listening.cancel()

    def use_ui(self, ui_settings: UiSettings) -> None:
        """Keys or look changed in the Settings window: tell the app now and on every later connect."""
        self._ui_settings = ui_settings
        self._ui.emit(self._ui_config())

    def _ui_config(self) -> UiConfig:
        ui = self._ui_settings
        return UiConfig(ui.dictate_key, ui.talk_key, ui.hands_free_max_s, ui.whats_this_key, ui.character, ui.meeting_key)

    def _history(self) -> list[Event]:
        history = [self._transcript.history()] if self._transcript is not None else []
        if self._conversations is not None:
            history += [self._conversations.list_event(), self._conversations.reminders_event()]
        return history + ([self._routines.resend()] if self._routines is not None else [])

    async def handle(self, command: Command) -> None:
        match command:
            case ListenStart(mode, tentative):
                if mode is ListenMode.TALK:
                    self._live_talk.prepare()  # a fresh conversation starts while the user speaks
                self._listening.start(mode, tentative)
            case ListenConfirm():
                self._listening.confirm()
            case ListenStop():
                self._listening.release()  # transcribes in the background: the next command is read at once
            case ListenCancel():
                self._listening.cancel()
            case TextInput(text, speak, conversation):
                if conversation and self._transcript is not None:
                    recap = self._transcript.resume(conversation)
                    if recap is not None:
                        self._live_talk.pick_up(*recap)
                self._live_talk.start(text, via="typed", speak=speak)
            case GetConversations(before):
                if self._conversations is not None:
                    self._ui.emit(self._conversations.list_event(before))
                    if not before:
                        self._ui.emit(self._conversations.reminders_event())
            case OpenConversation(id):
                opened = self._conversations.open(id) if self._conversations is not None else None
                if opened is not None:
                    self._ui.emit(opened)
            case SearchConversations(query):
                if self._conversations is not None:
                    self._ui.emit(await self._conversations.search(query))
            case RenameConversation(id, title):
                if self._conversations is not None:
                    self._conversations.rename(id, title)
            case NewConversation():
                if self._transcript is not None:
                    self._transcript.new_conversation()
                self._live_talk.fresh()
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
            case ConfirmAnswer(id, yes, always, choice):
                if self._approvals is not None and not self._approvals.answer(id, yes, always=always,
                                                                              choice=choice):
                    log.info("an answer came for a question that is over")
            case StopAll():
                log.info("the user pressed Stop")
                if self._approvals is not None:
                    self._approvals.cancel()
                if self._helpers is not None:
                    self._helpers.stop("all")
                if self._hands is not None:
                    self._hands.stop("stop")
                self._live_talk.interrupt()
            case StopHelper(id):
                if self._helpers is not None and not self._helpers.stop(id):
                    log.info("Stop came for a helper that isn't working")
            case RoutineAction(id, action):
                if self._routines is not None:
                    self._routines.command(id, action)
            case RoutineDraftAnswer(id, save):
                if self._routines is not None:
                    if save:
                        self._routines.save(draft_id=id)
                    else:
                        self._routines.drop(id)
            case RemotePause(on):
                if self._messages is not None:
                    self._messages.pause(on)
            case RemoteForget():
                if self._messages is not None:
                    self._messages.forget()
            case AppResponse():
                if self._bridge is not None:
                    self._bridge.resolve(command)
            case (CallStarted() | CallEnded() | MeetingChunk() | MeetingRecording() | MeetingToggle() | MeetingPause()
                  | OpenMeeting() | MeetingTodo() | MeetingMail()):
                if self._meetings is not None:
                    self._meetings.handle(command)
            case DictationFixed(fixes):
                if self._corrections is not None:
                    self._corrections.fixed(fixes)
            case GetFacts() | ForgetFact() | EditFact():
                self._facts(command)
            case GetSettings():
                if self._settings is not None:
                    self._settings.send()
            case GetUsage(span):
                if self._usage is not None:
                    self._usage.request(span)
            case SetSetting(section, key, value):
                if self._settings is not None:
                    self._settings.change(section, key, value)
            case _:
                log.warning("no handler for %s", command.type)

    def _facts(self, command: Command) -> None:
        """The "What Milo knows" screen: list, forget, edit. The user's own clicks, so nobody asks again."""
        if self._memory is None:
            self._ui.emit(Facts([]))
            return
        match command:
            case ForgetFact(id):
                if self._memory.forget(id, "the user forgot it in What Milo knows") is None:
                    self._ui.emit(self._memory.facts_event())
            case EditFact(id, text):
                if self._memory.edit_fact(id, text) is None:
                    self._ui.emit(self._memory.facts_event())
            case _:
                self._ui.emit(self._memory.facts_event())

    def _answer(self, id: str, value: object) -> None:
        if self._bridge is not None:
            self._bridge.answer(id, value)
