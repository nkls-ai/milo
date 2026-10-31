"""Composition root: the only module that names concrete classes. Everything else gets ports."""

from __future__ import annotations

import logging
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from .brain import Brain
from .config import Config, app_names, brief_time
from .core.clock import SystemClock
from .core.conversations import SplitRules
from .core.language import SpokenLanguage
from .core.ports import Harness, LiveModel, PlaybackTap, TimedTranscriber, Transcriber, Vocabulary, Voice
from .core.registry import (AUDIO_INPUTS, AUDIO_OUTPUTS, CHANNELS, DIARIZERS, EMBEDDERS, HARNESSES, LIVE_MODELS,
                            STREAMING_TRANSCRIBERS, TEXT_CLEANERS, TRANSCRIBERS, VOICES, AdapterContext, ConfigError,
                            Registry)
from .core.task_scope import CONNECT_SERVER
from .core.types import Emotion, LiveMode, ToolServer
from .services.app_bridge import AppAccessLink, AppBridge, AppEyes, AppHands
from .services.approvals import ActionPolicy, Approvals
from .services.attention import Attention
from .services.backchannel import Backchannel
from .services.background_stt import BackgroundStt
from .services.barge_in import BargeIn
from .services.cloud_hearing import NOTICE as HEARING_NOTICE
from .services.cloud_hearing import CloudHearing
from .services.context import UserContext
from .services.conversations import ConversationBrowser
from .services.conversation import Conversation
from .services.corrections import Corrections, DictationFixes
from .services.dictation import DictationService
from .services.fallback_voice import NOTICE as VOICE_NOTICE
from .services.fallback_voice import FallbackVoice, VoiceNotice
from .services.access import AccessGate
from .services.hands import HandsService
from .services.heartbeat_runner import HeartbeatRunner
from .services.episode_stubs import EpisodeDictations, EpisodeEyes, EpisodeTranscript, RoutineEpisodes
from .services.listening import Listening
from .services.live_talk import LiveTalk, untrusted
from .services.meetings import MeetingOptions, MeetingService
from .services.opener import Opener
from .services.messages import MessageService, MessageSettings
from .services.orchestrator import HelperQuestions, Orchestrator, ScreenSteps
from .services.permits import Permits
from .services.memory import Memory, MemoryParts, TurnMemory
from .services.memory_requests import MemoryRequests
from .services.sleep import SleepRunner
from .services.routines import Routines
from .services.settings_guard import SettingsGuard
from .services.speaker import Speaker
from .services.task_runner import TaskRunner
from .services.tool_requests import ToolRequests
from .services.transcript import NO_TRANSCRIPT, Transcript
from .services.ui_state import UiState
from .services.undo import Undo
from .services.updates import LiveSettings, Milestones, Updates
from .settings import Settings
from .transport.hands_socket import HandsSocketServer
from .transport.tool_socket import ToolSocketServer
from .transport.unix_socket import UnixSocketServer

if TYPE_CHECKING:
    from .memory.fact_profile import FactProfile

log = logging.getLogger("milo.compose")


@dataclass
class Runtime:
    """Everything main() starts: the socket, the heartbeat loop, the engines to warm up and close."""

    brain: Brain
    server: UnixSocketServer
    heartbeat: HeartbeatRunner | None
    transcriber: Transcriber
    voice: Voice
    stt_executor: ThreadPoolExecutor
    tts_executor: ThreadPoolExecutor
    harness: Harness
    live_model: LiveModel
    live_talk: LiveTalk
    tool_server: ToolSocketServer
    hands_server: HandsSocketServer | None = None
    helpers: Orchestrator | None = None
    memory: MemoryRuntime | None = None
    barge_in: BargeIn | None = None
    backchannel: Backchannel | None = None
    messages: MessageService | None = None
    notices: tuple[VoiceNotice, ...] = ()
    """Said when the voice or the hearing falls back to the Mac; they need the event loop once it runs."""
    meetings: MeetingService | None = None
    diarize_executor: ThreadPoolExecutor | None = None
    attention: Attention | None = None


@dataclass
class MemoryRuntime:
    """Memory's parts: the service, the live chat's hook, profile.md as a view, its thread and the nightly sleep."""

    memory: Memory
    turns: TurnMemory
    profile: FactProfile
    executor: ThreadPoolExecutor
    sleep: SleepRunner | None


class Parts:
    """What the build steps have made so far. A step reads what earlier steps made and adds its own.

    Reading a part no earlier step made raises BuildOrder at once, naming it, so a reordered step fails while
    Milo starts, not later inside a callback. The few cycles (the server calls the brain, a helper's questions
    reach the orchestrator) go through `later(name)`, which looks the part up when it is called."""

    def __getattr__(self, name: str):
        raise BuildOrder(f"compose: {name!r} is used before the step that builds it")

    def get(self, name: str):
        """The part, or None if no step made it (yet)."""
        return self.__dict__.get(name)

    def later(self, name: str):
        """A function returning the part when called: for the cycles, which run only after the build."""
        return lambda: getattr(self, name)


class BuildOrder(RuntimeError):
    """A build step used a part a later step makes."""


def build(home: Path) -> Runtime:
    """Build Milo's brain, one named step after another (BUILD_STEPS)."""
    p = Parts()
    p.home = home
    for step in BUILD_STEPS:
        step(p)
    return Runtime(p.brain, p.server, p.heartbeat, p.transcriber, p.voice, p.stt_executor, p.tts_executor, p.harness,
                   p.live_model, p.live_talk, p.tool_server, p.hands_server, p.helpers, p.mem, p.barge_in,
                   p.backchannel, p.messages, p.notices, meetings=p.meetings, diarize_executor=p.diarize_executor,
                   attention=p.attention)


def _workspace(p: Parts) -> None:
    """The workspace, its config, the clock and what every adapter gets."""
    from . import adapters
    from .adapters import platform
    from .memory.workspace import Workspace

    # Lazy, so importing compose neither registers adapters nor touches the workspace.
    p.workspace = Workspace(p.home)
    p.workspace.ensure()
    p.platform = platform.current()
    p.config = Config.load(p.workspace.config_path, p.platform)
    log.info("platform %s", p.platform.name)
    adapters.load_builtin()
    p.clock = SystemClock()
    # The worker CLI starts the MCP server with the brain's own interpreter, so it needs no install step.
    p.mac_tools = (sys.executable, "-m", "milo.mcp_server", "--socket", str(p.workspace.hands_socket_path)) \
        if p.config.hands.enabled else ()
    p.ctx = AdapterContext(p.home, p.workspace.state_dir, p.clock, p.mac_tools, _tool_servers(p.home))


def _create(p: Parts, registry: Registry, section: str):
    name, options = p.config.pluggable(section)
    return registry.create(name, options, p.ctx)


def _engines(p: Parts) -> None:
    """The engines config.toml names: chat model, worker, hearing, voice, audio, dictation cleanup."""
    config = p.config
    p.live_model = _create(p, LIVE_MODELS, "chat")
    p.harness = _create(p, HARNESSES, "harness")
    # Helpers that don't work on the screen get the same worker without the Mac tools, so only one helper
    # at a time can reach the screen. Its own state folder keeps its MCP config apart.
    p.background = None
    if p.mac_tools:
        background_ctx = AdapterContext(p.home, p.workspace.state_dir / "background", p.clock, (), p.ctx.tool_servers)
        name, options = config.pluggable("harness")
        p.background = HARNESSES.create(name, options, background_ctx)
    p.transcriber = _create(p, TRANSCRIBERS, "stt")
    p.voice = FallbackVoice(_create(p, VOICES, "tts"), _fallback_voice(config, p.ctx))
    p.mic = _create(p, AUDIO_INPUTS, "audio")
    p.output = _create(p, AUDIO_OUTPUTS, "audio")
    p.cleaner = _create(p, TEXT_CLEANERS, "dictation")
    p.stt_executor = ThreadPoolExecutor(1, thread_name_prefix="stt")
    p.tts_executor = ThreadPoolExecutor(1, thread_name_prefix="tts")


def _stores(p: Parts) -> None:
    """The files in the workspace the services keep: usage, dictations, the dictionary, profile, reminders."""
    from .memory.dictionary import MarkdownDictionary
    from .memory.history import JsonlDictationHistory
    from .memory.ledger import JsonlUsageLedger
    from .memory.profile import MarkdownProfile
    from .memory.reminders import MarkdownReminders

    workspace = p.workspace
    p.ledger = JsonlUsageLedger(workspace.usage_path, p.clock)
    p.history = JsonlDictationHistory(workspace.dictation_history_path, p.clock) \
        if p.config.dictation.keep_history else None
    p.dictionary = MarkdownDictionary(workspace.dictionary_path)
    p.profile = MarkdownProfile(workspace.profile_path)
    p.reminders = MarkdownReminders(workspace.reminders_path)


def _presence(p: Parts) -> None:
    """The socket to the app, what it shows, whether the user is busy, memory, the voice, the transcript and
    the questions before an action."""
    from .memory.conversations import JsonlConversationStore, migrate

    config, clock, workspace = p.config, p.clock, p.workspace
    p.server = UnixSocketServer(workspace.socket_path, on_command=lambda c: p.brain.handle(c),
                                on_connect=lambda: p.brain.greeting(), on_disconnect=lambda: p.brain.app_gone())
    p.ui = ui = UiState(p.server)
    p.attention = attention = Attention(lambda: ui.state)  # the parts are attached as they are built
    mic = p.mic
    attention.attach(mic=lambda: mic.active)
    p.context = UserContext(clock)
    p.mem = mem = _memory(config, workspace, p.ctx, clock, ui, p.harness, p.ledger, p.context,
                          busy=attention.at_work) if config.memory.enabled else None
    if mem is not None:
        p.profile = mem.profile
        if config.memory.dictations:
            p.history = EpisodeDictations(p.history, mem.memory.record, now=clock.now)
    p.conversation = Conversation(p.harness, p.ledger, clock, config.chat.conversation_idle_reset_s)
    p.speaker = speaker = Speaker(p.voice, p.output, ui, p.tts_executor)
    speaker.silent = not config.ui.voice
    attention.attach(voice=lambda: speaker.active)
    # Milo says it once when his usual voice or hearing can't be reached and the local one takes over.
    p.notices = tuple(VoiceNotice(lambda text: speaker.say(text, Emotion.CONCERNED), text=text,
                                  busy=attention.using_voice)
                      for text in (VOICE_NOTICE, HEARING_NOTICE))
    p.voice.on_switch = p.notices[0]
    p.hearing_engine = _cloud_engine(config, p.ctx)
    p.hearing = CloudHearing(p.hearing_engine, dictation=config.stt.cloud_dictation, on_switch=p.notices[1]) \
        if p.hearing_engine is not None else None
    p.backchannel = Backchannel(speaker, enabled=config.chat.backchannels)
    rules = SplitRules(idle_s=config.chat.conversation_idle_reset_s)
    store = JsonlConversationStore(workspace.conversations_dir)
    try:
        migrate(workspace.transcript_path, workspace.transcript_kept_path, store, rules)
    except Exception:
        log.exception("could not move the old transcript into conversations; it stays where it is")
    episode_stubs = None
    if mem is not None:
        context = p.context
        episode_stubs = EpisodeTranscript(NO_TRANSCRIPT, mem.memory.record, now=clock.now, app=lambda: context.app,
                                          people=mem.memory.people_in, outside=lambda: mem.turns.outside,
                                          elsewhere=lambda id: p.get("routines") is not None and p.routines.is_run(id))
    # The live talk and the questions are built later; these run only once a conversation does.
    p.transcript = transcript = Transcript(
        ui, store, clock, rules=rules, recap_tokens=config.chat.recap_tokens,
        outside=lambda: p.live_talk.carries_outside or (mem is not None and mem.turns.outside),
        asking=lambda: p.approvals.pending, exists=lambda path: Path(path).expanduser().is_file(),
        on_finished=episode_stubs.append if episode_stubs is not None else None)
    p.conversations = ConversationBrowser(transcript, store, ui, clock,
                                          memory=mem.memory.search if mem is not None else None,
                                          reminders=p.reminders)
    p.permits = Permits(config.approvals.ask, config.approvals.allowed_apps)  # saves once Settings exists
    p.language = language = SpokenLanguage()  # the latest message's language: replies, helpers, questions follow it
    p.approvals = approvals = Approvals(ui, speaker, ActionPolicy(config.approval_levels),
                                        timeout_s=config.approvals.timeout_s, reask_s=config.approvals.reask_s,
                                        speak=config.approvals.speak,
                                        quiet=attention.in_conversation, transcript=p.transcript,
                                        permits=p.permits, language=language.get)
    attention.attach(question=lambda: approvals.pending)
    p.bridge = AppBridge(p.server)  # each request to one app; one that hangs up fails what it owed at once
    p.server.on_client_gone.append(p.bridge.app_gone)
    p.live_settings = LiveSettings(workspace.config_path, _live_settings, config.chat.updates,
                                   config.harness.max_helpers)
    p.updates = Updates(ui, p.live_settings.updates, clock, busy=attention.occupied)
    switches = config.connections
    p.enabled = [name for name in ("calendar", "reminders") if switches.enabled and getattr(switches, name)]


def _helpers(p: Parts) -> None:
    """Computer use, the helpers that do the real work, and the routines they follow."""
    from .memory.routines import JsonStateFile, MarkdownRoutineBook
    from .memory.undo_shelf import FileUndoShelf

    config, mem, workspace = p.config, p.mem, p.workspace
    # Takes back what a task changed (ADR 0026); the orchestrator, built below, finds its helpers.
    shelf = FileUndoShelf(workspace.undo_dir, Path.home(), protected=workspace.protected)
    p.undo = undo = Undo(shelf, AppHands(p.bridge), p.ui, p.clock,
                         confirm=p.approvals, speaker=p.speaker, helpers=p.later("helpers"), transcript=p.transcript,
                         quiet=p.attention.in_conversation)
    p.hands = p.hands_server = None
    # The system's permissions, before Milo first needs one (ADR 0025). The line before the system's own question
    # is spoken unless the user is talking or answering something.
    speaker, attention = p.speaker, p.attention
    p.access = AccessGate(AppAccessLink(p.bridge), p.ui, transcript=p.transcript,
                          say=lambda text: speaker.say(text, Emotion.NEUTRAL, speak=not attention.occupied()))
    if config.hands.enabled:
        # The questions reach the orchestrator, built below, only once a helper runs.
        p.hands = HandsService(AppHands(p.bridge), HelperQuestions(p.approvals, p.later("helpers"), screen=True),
                               p.ui, transcript=ScreenSteps(p.transcript, p.later("helpers")),
                               applescript=config.hands.applescript,
                               locale=_mac_locale(), protected=workspace.protected, access=p.access,
                               before_change=undo.before_change, language=p.language.get)
        p.hands_server = HandsSocketServer(workspace.hands_socket_path, p.hands.call)
    p.memory_requests = MemoryRequests(mem.memory, p.approvals, mem.profile.remember) if mem is not None else None
    p.eyes = AppEyes(p.bridge)
    if mem is not None:
        p.eyes = EpisodeEyes(p.eyes, mem.memory.record, now=p.clock.now)
    runner = TaskRunner(p.harness, p.ledger, p.clock, p.context, background=p.background, hands=p.hands,
                        available=_available(p.config))
    p.helpers = helpers = Orchestrator(runner, p.speaker, p.ui, p.clock, transcript=p.transcript,
                                       max_helpers=p.live_settings.max_helpers, quiet=p.attention.in_conversation,
                                       updates=p.updates, milestones=Milestones(), inert=untrusted)
    p.attention.attach(helpers=lambda: helpers.busy)
    helpers.on_done.append(lambda helper: p.permits.end(helper.id))  # an Allow lasts as long as its helper
    helpers.on_done.append(undo.finished)
    undo.expire()
    p.permits.user_asked = helpers.user_asked
    p.routines = None
    if config.routines.enabled:
        book = MarkdownRoutineBook(workspace.routines_dir, workspace.routine_runs_path, workspace.routine_drafts_dir)
        p.routines = routines = Routines(
            book, JsonStateFile(workspace.routine_state_path), helpers, p.speaker, p.ui, p.clock,
            transcript=p.transcript, approvals=p.approvals, quiet=p.attention.in_conversation,
            max_runs_per_day=lambda: config.routines.max_runs_per_day, grace_s=config.routines.grace_hours * 3600,
            inert=untrusted)
        helpers.on_done.append(routines.seen)
        if mem is not None:  # a run's episode names the routine; the transcript's task stub skips it
            routines.on_episode = RoutineEpisodes(mem.memory.record, people=mem.memory.people_in)


def _meetings(p: Parts) -> None:
    """Meeting notes, when the transcriber gives timings."""
    from .memory.meetings import FileMeetingStore, JsonVoiceBook

    p.meetings = p.diarize_executor = p.background_stt = None
    if not isinstance(p.transcriber, TimedTranscriber):
        return
    config, bridge, enabled, attention = p.config, p.bridge, p.enabled, p.attention
    m = config.meetings
    diarizer = DIARIZERS.create(m.diarizer, config.section("meetings").get(m.diarizer, {}), p.ctx) \
        if m.diarizer else None
    p.diarize_executor = ThreadPoolExecutor(1, thread_name_prefix="diarize") if diarizer else None
    chat_name, chat_options = config.pluggable("chat")
    ctx, helpers, switches = p.ctx, p.helpers, config.connections

    async def calendar(start, end):
        return await bridge.call("calendar.events", {"start": start.isoformat(timespec="minutes"),
                                                     "end": end.isoformat(timespec="minutes"), "query": ""})

    async def add_reminder(title, notes):
        return await bridge.call("reminders.add", {"title": title, "notes": notes})

    # Meeting passes wait while the user dictates or talks, and give way when a key goes down (Listening),
    # so the user's words stay instant during a call.
    p.background_stt = BackgroundStt(p.stt_executor, busy=attention.user_speaking, interrupt=p.transcriber.interrupt)
    p.meetings = MeetingService(
        FileMeetingStore(p.workspace.meetings_dir), p.ui, p.clock, p.background_stt, p.transcriber,
        approvals=p.approvals, speaker=p.speaker, transcript=p.transcript, diarizer=diarizer,
        diarize_executor=p.diarize_executor,
        voices=JsonVoiceBook(p.workspace.meetings_dir / "voices.json", diarizer.model) if diarizer else None,
        summarizer=lambda: LIVE_MODELS.create(chat_name, chat_options, ctx),
        calendar=calendar if "calendar" in enabled else None,
        add_reminder=add_reminder if "reminders" in enabled else None,
        # careful: the draft comes from other people's words, so the helper's tools ask before changes too
        draft_mail=(lambda task: helpers.submit(task, title="Follow-up mail", screen=False, careful=True))
        if switches.enabled and switches.mail else None,
        options=MeetingOptions(m.auto, m.keep_audio, m.offer_reminders, m.offer_mail, m.end_after_s,
                               app_names(m.always), app_names(m.never)),
        connected=p.server.connected, private=attention.private, quiet=attention.in_conversation,
        on_episode=p.mem.memory.record if p.mem is not None else None,
        match=diarizer.match if diarizer else 0.6)


def _quick(p: Parts):
    """The talker's quick actions and its <today> block (ADR 0029), on the same connections the worker gets. Calendar,
    Reminders and the music go through the app where the app holds them; the fake connections stay fake. None when
    `[chat] quick_actions` or `[connections] enabled` is off."""
    import dataclasses

    from .core.registry import CONNECTIONS
    from .services.app_ops import AppOps
    from .services.quick_actions import QuickActions
    from .services.today import Today

    config, switches = p.config, p.config.connections
    if not config.chat.quick_actions or not switches.enabled:
        return None
    name, options = config.pluggable("connections")
    connections = CONNECTIONS.create(name, options, p.ctx)
    connections = dataclasses.replace(connections, **{f.name: None for f in dataclasses.fields(connections)
                                                      if not getattr(switches, f.name, True)})
    # A connection that goes through the brain to the app (approves_itself) is reached on the AppBridge directly.
    via_app = [c for c in ("calendar", "reminders") if getattr(getattr(connections, c), "approves_itself", False)]
    if connections.music is None:
        via_app.append("media")  # the app's player op, when this platform's connections have no player of their own
    enabled = [c for c in ("calendar", "reminders") if getattr(switches, c)] + (["media"] if switches.music else [])
    ops = AppOps(connections, p.bridge.call, via_app=via_app, enabled=enabled)
    attention = p.attention
    return QuickActions(ops, connections, p.ui, p.speaker, p.clock, approvals=p.approvals, today=Today(ops, p.clock),
                        undo=p.undo, transcript=p.transcript, access=p.access, meetings=p.meetings,
                        reminders=p.reminders, quiet=attention.user_speaking, language=p.language.get)


def _talk(p: Parts) -> None:
    """The live conversation, the two keys that feed it, and barge-in."""
    config, mem, helpers = p.config, p.mem, p.helpers
    p.quick = _quick(p)
    p.live_talk = live_talk = LiveTalk(
        p.live_model, p.speaker, p.ui, p.context, p.clock, p.profile, p.reminders, p.ledger,
        _persona(p.workspace.persona_path), config.chat.conversation_idle_reset_s, helpers, p.transcript,
        eyes=p.eyes, approvals=p.approvals, memory=mem.turns if mem is not None else None,
        backchannel=p.backchannel, routines=p.routines, meetings=p.meetings, undo=p.undo,
        opener=Opener(AppHands(p.bridge), p.ui, p.clock), language=p.language, quick=p.quick)
    p.attention.attach(turn=lambda: live_talk.busy)
    p.helpers.on_result = live_talk.note
    p.updates.speak = live_talk.speak_update
    background_stt = p.background_stt
    # The dictionary's words go to every engine that hears dictation; its fixes apply before each paste (ADR 21).
    p.corrections = corrections = Corrections(
        p.dictionary, p.ui, [e for e in (p.transcriber, p.hearing_engine) if isinstance(e, Vocabulary)],
        busy=p.attention.occupied, enabled=config.dictation.learn)
    corrections.push()
    dictation = DictationService(DictationFixes(p.cleaner, p.dictionary), p.history, p.ui)
    p.listening = Listening(p.mic, p.transcriber, p.stt_executor, p.ui, dictation,
                            live_talk, p.context, LiveMode(config.dictation.stream), hearing=p.hearing,
                            yield_stt=background_stt.yield_now if background_stt is not None else lambda: None,
                            before=corrections.refresh)
    p.barge_in = None
    if config.chat.voice_barge_in:
        if isinstance(p.output, PlaybackTap):
            # A mic of its own, so the talk key's recording never has to wait for it.
            p.barge_in = BargeIn(_create(p, AUDIO_INPUTS, "audio"), p.output, p.transcriber, p.stt_executor, p.ui,
                                 live_talk, p.speaker, mic_busy=p.attention.recording)
        else:
            log.warning("[chat] voice_barge_in needs an audio output that reports what it played; it is off")


def _messages(p: Parts) -> None:
    """Milo by message from the owner's phone."""
    from .memory.remote import JsonRemoteState

    p.messages = None
    if not p.config.messages.enabled:
        return
    workspace, transcript, speaker, enabled, helpers = p.workspace, p.transcript, p.speaker, p.enabled, p.helpers
    name, options = p.config.pluggable("messages")
    channel = CHANNELS.create(name, options, p.ctx)

    def show(text: str) -> None:
        transcript.say(text, Emotion.CONCERNED)
        speaker.say(text, Emotion.CONCERNED, speak=False)

    m = p.config.messages
    p.messages = messages = MessageService(
        channel, p.live_talk, p.approvals, JsonRemoteState(workspace.remote_state_path), speaker, p.ui, p.context,
        p.clock,
        settings=MessageSettings(m.max_per_minute, m.away_after_min * 60, m.question_timeout_s,
                                 brief_time(m.brief_at), m.max_file_mb, "calendar" in enabled, "reminders" in enabled),
        helpers=lambda: helpers.helpers, board=helpers.board, reminders=p.reminders, app=p.bridge.call,
        guard=SettingsGuard([workspace.config_path, workspace.remote_state_path], [workspace.secrets_dir], show),
        transcript=transcript, home=Path.home(), milo=p.home)
    p.approvals.relays.append(messages)
    helpers.watchers.append(messages.helper_changed)


def _tool_socket(p: Parts) -> None:
    """run/tools.sock, where the helpers' tools ask the brain."""
    questions = HelperQuestions(p.approvals, p.later("helpers"), screen=False)
    p.tool_server = ToolSocketServer(p.workspace.tools_socket_path,
                                     ToolRequests(questions, p.bridge, p.enabled, p.memory_requests,
                                                  phone=p.messages, reminders=p.reminders,
                                                  access=p.access, undo=p.undo).handle)


def _heartbeat(p: Parts) -> None:
    """The local heartbeat: reminders, nudges and the routines' schedule, without the LLM."""
    p.heartbeat = None
    if not p.config.heartbeat.enabled:
        return
    from .proactive import build_engine

    engine = build_engine(p.config.section("heartbeat"), p.ctx, p.reminders)
    p.heartbeat = HeartbeatRunner(engine, p.context, p.conversation, p.speaker, p.ui, p.mic, p.clock,
                                  busy=p.attention.answering)
    if p.routines is not None:
        p.heartbeat.on_tick.append(p.routines.tick)
    if p.messages is not None:
        p.heartbeat.after_tick.append(p.messages.tick)


def _brain(p: Parts) -> None:
    """Settings that apply while Milo runs, and the Brain that routes the app's commands to all of the above."""
    from .adapters.accounts import CliAccounts
    from .config_file import TomlConfigFile
    from .memory.usage_log import JsonlUsageHistory
    from .services.usage import UsageService

    listening, speaker, live_settings, corrections = p.listening, p.speaker, p.live_settings, p.corrections

    def use_ui(changed: Config) -> None:
        p.brain.use_ui(changed.ui)

    def use_voice(changed: Config) -> None:
        speaker.silent = not changed.ui.voice

    def use_stream(changed: Config) -> None:
        listening.live_mode = LiveMode(changed.dictation.stream)

    def use_learn(changed: Config) -> None:
        corrections.enabled = changed.dictation.learn

    def use_updates(changed: Config) -> None:
        live_settings.use(changed.chat.updates, changed.harness.max_helpers)

    def use_ask(changed: Config) -> None:
        p.permits.ask = changed.approvals.ask

    def use_allowed(changed: Config) -> None:
        p.permits.use(changed.approvals.allowed_apps)

    def use_meetings(changed: Config) -> None:
        if p.meetings is not None:
            m = changed.meetings
            p.meetings.options = replace(p.meetings.options, auto=m.auto, always=app_names(m.always),
                                         never=app_names(m.never))

    live = {("ui", "dictate_key"): use_ui, ("ui", "talk_key"): use_ui,
            ("ui", "whats_this_key"): use_ui, ("ui", "meeting_key"): use_ui, ("ui", "voice"): use_voice,
            ("dictation", "stream"): use_stream, ("dictation", "learn"): use_learn, ("chat", "updates"): use_updates,
            ("ui", "hide_after_s"): lambda changed: None,  # the app reads it from the next `settings`
            ("hands", "show_window"): lambda changed: None,  # the app reads it from the next `settings`
            ("approvals", "ask"): use_ask, ("approvals", "allowed_apps"): use_allowed,
            ("meetings", "auto"): use_meetings, ("meetings", "always"): use_meetings,
            ("meetings", "never"): use_meetings}
    settings = Settings(TomlConfigFile(p.workspace.config_path, p.config.platform), p.config, p.ui, live)
    p.permits.save = lambda apps: settings.keep("approvals", "allowed_apps", apps)
    if p.meetings is not None:
        meetings = p.meetings

        def remember(key: str, app: str) -> None:
            """"Always for Zoom" or "Never for Zoom": into config.toml like any setting, out of the other list."""
            other = "never" if key == "always" else "always"
            mine, theirs = getattr(meetings.options, key), getattr(meetings.options, other)
            if any(a.lower() == app.lower() for a in theirs):
                settings.change("meetings", other, ", ".join(a for a in theirs if a.lower() != app.lower()))
            settings.change("meetings", key, ", ".join(app_names(", ".join([*mine, app]))))

        meetings.remember = remember
    usage = UsageService(JsonlUsageHistory(p.workspace.usage_path, p.workspace.dictation_history_path),
                         CliAccounts(p.config, p.workspace.home), p.ui, p.clock)
    p.brain = Brain(p.ui, listening, p.live_talk, p.context, p.heartbeat, p.config.ui, p.transcript,
                    approvals=p.approvals, bridge=p.bridge, hands=p.hands, screens=p.workspace.screens_dir,
                    helpers=p.helpers, memory=p.mem.memory if p.mem is not None else None, routines=p.routines,
                    settings=settings, messages=p.messages, meetings=p.meetings,
                    conversations=p.conversations, usage=usage, corrections=corrections, undo=p.undo)


BUILD_STEPS = (_workspace, _engines, _stores, _presence, _helpers, _meetings, _talk, _messages, _tool_socket,
               _heartbeat, _brain)
"""The order Milo is built in. Each step only reads what the steps before it made (see Parts)."""


def _memory(config: Config, workspace, ctx: AdapterContext, clock, ui: UiState, harness: Harness, ledger,
            context: UserContext, *, busy) -> MemoryRuntime:
    from .adapters.power import on_ac_power
    from .memory.consolidate import NightlyConsolidator
    from .memory.episodes import JsonlEpisodeLog
    from .memory.fact_profile import FactProfile, migrate
    from .memory.facts import JsonlFactStore
    from .memory.index import SqliteMemoryIndex
    from .memory.recall import HybridRecaller, RecallTuning, render
    from .memory.state import JsonState

    settings = config.memory
    name, options = config.embedder()
    embedder = EMBEDDERS.create(name, options, ctx)
    facts = JsonlFactStore(workspace.facts_path, clock)
    episodes = JsonlEpisodeLog(workspace.episodes_dir, clock)
    migrate(workspace.profile_path, facts, clock)
    index = SqliteMemoryIndex(workspace.memory_index_path, embedder, facts, episodes)
    recaller = HybridRecaller(index, facts, RecallTuning(min_margin=embedder.relevant_margin))
    executor = ThreadPoolExecutor(1, thread_name_prefix="memory")
    profile = FactProfile(facts, workspace.profile_path, workspace.profile_snapshot_path, clock, pinned_only=True)
    memory = Memory(MemoryParts(facts, episodes, index, recaller, embedder, render), executor, ui, clock,
                    recall_tokens=settings.recall_tokens, on_facts_changed=profile.write)
    profile.on_change = memory.facts_changed
    profile.write()
    sleep = None
    if settings.consolidate and settings.consolidate_calls_per_day > 0:
        sleeper = NightlyConsolidator(harness, episodes, facts, workspace.journal_dir, workspace.state_dir / "sleep",
                                      clock, ledger)

        sleep = SleepRunner(sleeper, context, clock, JsonState(workspace.sleep_state_path),
                            calls_per_day=settings.consolidate_calls_per_day, on_power=on_ac_power, busy=busy,
                            after=memory.notice_changes)
    return MemoryRuntime(memory, TurnMemory(memory), profile, executor, sleep)


def _available(config: Config) -> frozenset[str]:
    """The connections the worker's tools reach, as config.toml switches them (milo.connect reads the same)."""
    switches = config.connections
    names = ("calendar", "reminders", "mail", "notes", "shortcuts", "files")
    on = switches.enabled and config.pluggable("connections")[0] != "none"
    return frozenset({*(n for n in names if on and getattr(switches, n)),
                      *(("memory",) if config.memory.enabled else ()), *(("phone",) if config.messages.enabled else ())})


def _tool_servers(home: Path) -> tuple[ToolServer, ...]:
    """Milo's app connections, memory tools and reminders as an MCP server for the worker: this Python, so no
    `uv run` on every task. Always on: the worker can't write reminders.md itself (ADR 0020)."""
    return (ToolServer(CONNECT_SERVER, (sys.executable, "-m", "milo.connect"), (("MILO_HOME", str(home)),)),)


def _live_settings(text: str) -> tuple[str, int]:
    """The settings LiveSettings re-reads from a changed config.toml. Raises ConfigError on bad values."""
    config = Config.parse(text)
    return config.chat.updates, config.harness.max_helpers


def _mac_locale() -> str:
    """The Mac's region setting, like "en_US@rg=dezzzz", for money formats. "" if it can't be read."""
    try:
        done = subprocess.run(["/usr/bin/defaults", "read", "-g", "AppleLocale"], capture_output=True, text=True,
                              timeout=5, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip()


def _persona(path: Path):
    """Read persona.md on every conversation start, so the user's edits apply without a restart."""

    def read() -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            log.warning("could not read %s, talking without a persona: %s", path, e)
            return ""

    return read


def _cloud_engine(config: Config, ctx: AdapterContext):
    """[stt] talk: the cloud transcriber that listens along while the user talks to Milo. None: all local."""
    name = config.stt.talk
    if not name:
        if config.stt.cloud_dictation:
            log.warning("[stt] cloud_dictation needs [stt] talk to name a service; dictation stays on this Mac")
        return None
    options = config.section("stt").get(name, {})
    if not isinstance(options, dict):
        raise ConfigError(f"[stt.{name}] must be a table")
    return STREAMING_TRANSCRIBERS.create(name, options, ctx)


def _fallback_voice(config: Config, ctx: AdapterContext):
    name = config.tts.fallback
    if not name:
        return None
    # Check the name now: otherwise a typo only shows once the primary engine fails, and Milo goes mute.
    if name not in VOICES.names():
        raise ConfigError(f"[tts] fallback: unknown tts engine {name!r}; available: {', '.join(VOICES.names())}")
    options = config.section("tts").get(name, {})
    return lambda: VOICES.create(name, options, ctx)
