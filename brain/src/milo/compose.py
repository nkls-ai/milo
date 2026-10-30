"""Composition root: the only module that names concrete classes. Everything else gets ports."""

from __future__ import annotations

import logging
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .brain import Brain
from .config import Config
from .core.clock import SystemClock
from .core.ports import Harness, LiveModel, Transcriber, Voice
from .core.registry import (AUDIO_INPUTS, AUDIO_OUTPUTS, HARNESSES, LIVE_MODELS, TEXT_CLEANERS, TRANSCRIBERS,
                            VOICES, AdapterContext, ConfigError, Registry)
from .core.types import LiveMode, ToolServer
from .services.app_bridge import AppBridge, AppEyes, AppHands
from .services.approvals import ActionPolicy, Approvals
from .services.context import UserContext
from .services.conversation import Conversation
from .services.dictation import DictationService
from .services.fallback_voice import FallbackVoice
from .services.hands import HandsService
from .services.heartbeat_runner import HeartbeatRunner
from .services.listening import Listening
from .services.live_talk import LiveTalk, untrusted
from .services.orchestrator import HelperQuestions, Orchestrator
from .services.speaker import Speaker
from .services.task_runner import TaskRunner
from .services.tool_requests import ToolRequests
from .services.transcript import Transcript
from .services.ui_state import UiState
from .services.updates import LiveSettings, Milestones, Updates
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
    helpers: Orchestrator | None = None


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
    # Helpers that don't work on the screen get the same worker without the Mac tools, so only one helper
    # at a time can reach the screen. Its own state folder keeps its MCP config apart.
    background = None
    if mac_tools:
        background_ctx = AdapterContext(home, workspace.state_dir / "background", clock, (), ctx.tool_servers)
        name, options = config.pluggable("harness")
        background = HARNESSES.create(name, options, background_ctx)
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
    transcript = Transcript(ui, JsonlTranscript(workspace.transcript_path), clock)
    approvals = Approvals(ui, speaker, ActionPolicy(config.approval_levels), timeout_s=config.approvals.timeout_s,
                          speak=config.approvals.speak, quiet=lambda: live_talk.busy or mic.active,
                          transcript=transcript)
    bridge = AppBridge(ui, connected=server.connected)
    settings = LiveSettings(workspace.config_path, _live_settings, config.chat.updates, config.harness.max_helpers)
    updates = Updates(ui, settings.updates, clock,
                      busy=lambda: live_talk.busy or mic.active or speaker.active or approvals.pending)
    hands = hands_server = None
    helpers: Orchestrator  # built below; the questions only reach it once a helper runs
    if config.hands.enabled:
        hands = HandsService(AppHands(bridge), HelperQuestions(approvals, lambda: helpers, screen=True), ui,
                             transcript=transcript, applescript=config.hands.applescript, locale=_mac_locale())
        hands_server = HandsSocketServer(hands_socket, hands.call)
    switches = config.connections
    enabled = [name for name in ("calendar", "reminders") if switches.enabled and getattr(switches, name)]
    tool_server = ToolSocketServer(workspace.tools_socket_path,
                                   ToolRequests(HelperQuestions(approvals, lambda: helpers, screen=False), bridge,
                                                enabled).handle)
    runner = TaskRunner(harness, ledger, clock, context, background=background, hands=hands)
    helpers = Orchestrator(runner, speaker, ui, clock, transcript=transcript, max_helpers=settings.max_helpers,
                           quiet=lambda: live_talk.busy or mic.active, updates=updates, milestones=Milestones(),
                           inert=untrusted)
    live_talk = LiveTalk(live_model, speaker, ui, context, clock, profile, reminders, ledger,
                         _persona(workspace.persona_path), idle_reset_s, helpers, transcript, eyes=AppEyes(bridge),
                         approvals=approvals)
    helpers.on_result = live_talk.note
    updates.speak = live_talk.speak_update
    listening = Listening(mic, transcriber, stt_executor, ui, DictationService(cleaner, history, ui),
                          live_talk, context, LiveMode(config.dictation.stream))

    heartbeat = None
    if config.heartbeat.enabled:
        from .proactive import build_engine

        engine = build_engine(config.section("heartbeat"), ctx, reminders)
        heartbeat = HeartbeatRunner(engine, context, conversation, speaker, ui, mic, clock,
                                    busy=lambda: live_talk.busy)

    brain = Brain(ui, listening, live_talk, context, heartbeat, config.ui, transcript, approvals=approvals,
                  bridge=bridge, hands=hands, screens=workspace.screens_dir, helpers=helpers)
    return Runtime(brain, server, heartbeat, transcriber, voice, stt_executor, tts_executor, harness,
                   live_model, live_talk, tool_server, hands_server, helpers)


def _tool_servers(config: Config, home: Path) -> tuple[ToolServer, ...]:
    """Milo's app connections as an MCP server for the worker: this Python, so no `uv run` on every task."""
    if not config.connections.enabled:
        return ()
    return (ToolServer("milo", (sys.executable, "-m", "milo.connect"), (("MILO_HOME", str(home)),)),)


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


def _fallback_voice(config: Config, ctx: AdapterContext):
    name = config.tts.fallback
    if not name:
        return None
    # Check the name now: otherwise a typo only shows once the primary engine fails, and Milo goes mute.
    if name not in VOICES.names():
        raise ConfigError(f"[tts] fallback: unknown tts engine {name!r}; available: {', '.join(VOICES.names())}")
    options = config.section("tts").get(name, {})
    return lambda: VOICES.create(name, options, ctx)
