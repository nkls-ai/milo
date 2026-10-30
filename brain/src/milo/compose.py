"""Composition root: the only module that names concrete classes. Everything else gets ports."""

from __future__ import annotations

import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .brain import Brain
from .config import Config
from .core.clock import SystemClock
from .core.ports import Harness, LiveModel, PlaybackTap, Transcriber, Voice
from .core.registry import (AUDIO_INPUTS, AUDIO_OUTPUTS, HARNESSES, LIVE_MODELS, TEXT_CLEANERS, TRANSCRIBERS,
                            VOICES, AdapterContext, ConfigError, Registry)
from .core.types import LiveMode, ToolServer
from .services.app_bridge import AppBridge, AppEyes, AppHands
from .services.approvals import ActionPolicy, Approvals
from .services.backchannel import Backchannel
from .services.barge_in import BargeIn
from .services.context import UserContext
from .services.conversation import Conversation
from .services.dictation import DictationService
from .services.fallback_voice import FallbackVoice
from .services.hands import HandsService
from .services.heartbeat_runner import HeartbeatRunner
from .services.listening import Listening
from .services.live_talk import LiveTalk
from .services.speaker import Speaker
from .services.task_runner import TaskRunner
from .services.tool_requests import ToolRequests
from .services.transcript import Transcript
from .services.ui_state import UiState
from .transport.hands_socket import HandsSocketServer
from .transport.tool_socket import ToolSocketServer
from .transport.unix_socket import UnixSocketServer

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
    barge_in: BargeIn | None = None
    backchannel: Backchannel | None = None


def build(home: Path) -> Runtime:
    # Lazy, so importing compose neither registers adapters nor touches the workspace.
    from . import adapters
    from .memory.history import JsonlDictationHistory
    from .memory.ledger import JsonlUsageLedger
    from .memory.profile import MarkdownProfile
    from .memory.reminders import MarkdownReminders
    from .memory.transcript import JsonlTranscript
    from .memory.workspace import Workspace

    workspace = Workspace(home)
    workspace.ensure()
    config = Config.load(workspace.config_path)
    adapters.load_builtin()
    clock = SystemClock()
    hands_socket = workspace.hands_socket_path
    # The worker CLI starts the MCP server with the brain's own interpreter, so it needs no install step.
    mac_tools = (sys.executable, "-m", "milo.mcp_server", "--socket", str(hands_socket)) if config.hands.enabled else ()
    ctx = AdapterContext(home, workspace.state_dir, clock, mac_tools, _tool_servers(config, home))

    def create(registry: Registry, section: str):
        name, options = config.pluggable(section)
        return registry.create(name, options, ctx)

    live_model = create(LIVE_MODELS, "chat")
    harness = create(HARNESSES, "harness")
    transcriber = create(TRANSCRIBERS, "stt")
    voice = FallbackVoice(create(VOICES, "tts"), _fallback_voice(config, ctx))
    mic = create(AUDIO_INPUTS, "audio")
    output = create(AUDIO_OUTPUTS, "audio")
    cleaner = create(TEXT_CLEANERS, "dictation")
    ledger = JsonlUsageLedger(workspace.usage_path, clock)
    history = JsonlDictationHistory(workspace.dictation_history_path, clock) if config.dictation.keep_history else None
    profile = MarkdownProfile(workspace.profile_path)
    reminders = MarkdownReminders(workspace.reminders_path)

    stt_executor = ThreadPoolExecutor(1, thread_name_prefix="stt")
    tts_executor = ThreadPoolExecutor(1, thread_name_prefix="tts")
    server = UnixSocketServer(workspace.socket_path, on_command=lambda c: brain.handle(c),
                              on_connect=lambda: brain.greeting())
    ui = UiState(server)
    context = UserContext(clock)
    idle_reset_s = config.chat.conversation_idle_reset_s
    conversation = Conversation(harness, ledger, clock, idle_reset_s)
    speaker = Speaker(voice, output, ui, tts_executor)
    backchannel = Backchannel(speaker, enabled=config.chat.backchannels)
    transcript = Transcript(ui, JsonlTranscript(workspace.transcript_path), clock)
    approvals = Approvals(ui, speaker, ActionPolicy(config.approval_levels), timeout_s=config.approvals.timeout_s,
                          speak=config.approvals.speak, quiet=lambda: live_talk.busy or mic.active,
                          transcript=transcript)
    bridge = AppBridge(ui, connected=server.connected)
    hands = hands_server = None
    if config.hands.enabled:
        hands = HandsService(AppHands(bridge), approvals, ui, transcript=transcript,
                             applescript=config.hands.applescript)
        hands_server = HandsSocketServer(hands_socket, hands.call)
    switches = config.connections
    enabled = [name for name in ("calendar", "reminders") if switches.enabled and getattr(switches, name)]
    tool_server = ToolSocketServer(workspace.tools_socket_path, ToolRequests(approvals, bridge, enabled).handle)
    tasks = TaskRunner(conversation, speaker, context, quiet=lambda: live_talk.busy or mic.active,
                       transcript=transcript, hands=hands)
    live_talk = LiveTalk(live_model, speaker, ui, context, clock, profile, reminders, ledger,
                         _persona(workspace.persona_path), idle_reset_s, tasks, transcript, eyes=AppEyes(bridge),
                         approvals=approvals, backchannel=backchannel)
    tasks.on_result = live_talk.note
    listening = Listening(mic, transcriber, stt_executor, ui, DictationService(cleaner, history, ui),
                          live_talk, context, LiveMode(config.dictation.stream))

    barge_in = None
    if config.chat.voice_barge_in:
        if isinstance(output, PlaybackTap):
            # A mic of its own, so the talk key's recording never has to wait for it.
            barge_in = BargeIn(create(AUDIO_INPUTS, "audio"), output, transcriber, stt_executor, ui, live_talk,
                               speaker, mic_busy=lambda: mic.active)
        else:
            log.warning("[chat] voice_barge_in needs an audio output that reports what it played; it is off")

    heartbeat = None
    if config.heartbeat.enabled:
        from .proactive import build_engine

        engine = build_engine(config.section("heartbeat"), ctx, reminders)
        heartbeat = HeartbeatRunner(engine, context, conversation, speaker, ui, mic, clock,
                                    busy=lambda: live_talk.busy)

    brain = Brain(ui, listening, live_talk, context, heartbeat, config.ui, transcript, approvals=approvals,
                  bridge=bridge, hands=hands, screens=workspace.screens_dir)
    return Runtime(brain, server, heartbeat, transcriber, voice, stt_executor, tts_executor, harness,
                   live_model, live_talk, tool_server, hands_server, barge_in, backchannel)


def _tool_servers(config: Config, home: Path) -> tuple[ToolServer, ...]:
    """Milo's app connections as an MCP server for the worker: this Python, so no `uv run` on every task."""
    if not config.connections.enabled:
        return ()
    return (ToolServer("milo", (sys.executable, "-m", "milo.connect"), (("MILO_HOME", str(home)),)),)


def _persona(path: Path):
    """Read persona.md on every conversation start, so the user's edits apply without a restart."""

    def read() -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            log.warning("could not read %s, talking without a persona: %s", path, e)
            return ""

    return read


def _fallback_voice(config: Config, ctx: AdapterContext):
    name = config.tts.fallback
    if not name:
        return None
    # Check the name now: otherwise a typo only shows once the primary engine fails, and Milo goes mute.
    if name not in VOICES.names():
        raise ConfigError(f"[tts] fallback: unknown tts engine {name!r}; available: {', '.join(VOICES.names())}")
    options = config.section("tts").get(name, {})
    return lambda: VOICES.create(name, options, ctx)
