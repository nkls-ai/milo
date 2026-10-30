"""The real composition root against a temp MILO home. Nothing is warmed, opened, started or called."""

import json
import re
from importlib import resources
from pathlib import Path

import pytest

from milo import compose
from milo.adapters.harness.claude import ClaudeHarness
from milo.adapters.harness.claude_live import ClaudeLiveModel
from milo.adapters.harness.codex import CodexHarness
from milo.adapters.stt.mlx_whisper import MlxWhisper
from milo.adapters.tts.say import MacSay
from milo.brain import Brain
from milo.core.registry import ConfigError
from milo.proactive import HeartbeatEngine
from milo.services.fallback_voice import FallbackVoice
from milo.services.heartbeat_runner import HeartbeatRunner
from milo.services.live_talk import LiveTalk
from milo.transport.unix_socket import UnixSocketServer

TEMPLATE = (resources.files("milo") / "workspace_template" / "config.toml").read_text()


def set_key(text: str, table: str, key: str, value) -> str:
    """Set `key` in `[table]` of a TOML text, replacing its line. JSON scalars are valid TOML."""
    start = text.index(f"[{table}]\n")
    line = re.compile(rf"^{key} = .*$", re.M).search(text, start)
    assert line, f"{key} not in [{table}]"
    return f"{text[:line.start()]}{key} = {json.dumps(value)}{text[line.end():]}"


def cheap(**edits) -> str:
    """The template with engines that cost nothing to construct, plus `edits` keyed "table.key"."""
    text = set_key(TEMPLATE, "tts", "use", "say")
    text = set_key(text, "harness.codex", "binary", "/nonexistent/codex")
    text = set_key(text, "harness.claude", "binary", "/nonexistent/claude")
    text = set_key(text, "chat.claude_live", "binary", "/nonexistent/claude")
    text = set_key(text, "heartbeat", "enabled", True)
    for path, value in edits.items():
        table, key = path.rsplit(".", 1)
        text = set_key(text, table, key, value)
    return text


@pytest.fixture
def build(tmp_path):
    runtimes = []

    def _build(config_text: str):
        home = tmp_path / "Milo"
        home.mkdir(exist_ok=True)
        (home / "config.toml").write_text(config_text)
        runtime = compose.build(home)
        runtimes.append(runtime)
        return runtime, home

    yield _build
    for runtime in runtimes:
        runtime.stt_executor.shutdown(wait=False)
        runtime.tts_executor.shutdown(wait=False)


def test_build_picks_the_engines_named_in_config(build):
    runtime, home = build(cheap(**{"heartbeat.tick_s": 7, "harness.codex.model": "gpt-x",
                                   "chat.claude_live.model": "claude-haiku-5-5"}))
    assert isinstance(runtime.brain, Brain)
    assert isinstance(runtime.live_model, ClaudeLiveModel) and runtime.live_model.model == "claude-haiku-5-5"
    assert runtime.live_model.binary == "/nonexistent/claude"
    assert isinstance(runtime.live_talk, LiveTalk) and runtime.live_talk._idle_reset_s == 600
    assert isinstance(runtime.harness, CodexHarness)
    assert runtime.harness.binary == "/nonexistent/codex" and runtime.harness.model == "gpt-x"
    assert runtime.harness.workdir == home
    assert isinstance(runtime.transcriber, MlxWhisper)
    assert isinstance(runtime.voice, FallbackVoice) and isinstance(runtime.voice.current, MacSay)
    assert isinstance(runtime.server, UnixSocketServer)
    assert isinstance(runtime.heartbeat, HeartbeatRunner)
    engine = runtime.heartbeat._engine
    assert isinstance(engine, HeartbeatEngine) and engine.tick_s == 7


def test_build_has_no_side_effects_beyond_the_workspace(build):
    runtime, home = build(cheap())
    assert runtime.server.path == home / "run" / "brain.sock"
    assert not runtime.server.path.exists(), "the socket is bound by main(), not by build()"
    assert (home / "reminders.md").exists(), "the workspace template was copied in"
    assert "/nonexistent/codex" in (home / "config.toml").read_text(), "an existing config is kept"
    assert not (home / "state" / "usage.jsonl").exists(), "no harness call was made"
    assert (home / "persona.md").exists() and (home / "memory" / "profile.md").exists()


def test_another_harness_is_one_config_line_away(build):
    runtime, _ = build(cheap(**{"harness.use": "claude"}))
    assert isinstance(runtime.harness, ClaudeHarness) and runtime.harness.name == "claude"


def test_the_chat_idle_reset_comes_from_the_chat_section(build):
    runtime, _ = build(cheap(**{"chat.conversation_idle_reset_s": 90}))
    assert runtime.live_talk._idle_reset_s == 90


def test_an_old_config_without_chat_still_builds(build):
    old = cheap()
    start, end = old.index("[chat]\n"), old.index("[harness]\n")
    old = old[:start] + old[end:].replace("[harness]\n", "[harness]\nconversation_idle_reset_s = 600\n", 1)
    runtime, _ = build(old)
    assert isinstance(runtime.live_model, ClaudeLiveModel)


def test_persona_is_read_from_the_workspace_on_each_conversation_start(build):
    runtime, home = build(cheap())
    (home / "persona.md").write_text("You are Milo, but a pirate.")
    assert runtime.live_talk._system_prompt().startswith("You are Milo, but a pirate.")
    (home / "persona.md").unlink()
    assert runtime.live_talk._system_prompt().startswith("You are Milo, a small"), "a missing file falls back"


def test_the_worker_gets_the_mac_tools_through_the_hands_socket(build):
    runtime, home = build(cheap(**{"harness.use": "claude"}))
    assert runtime.hands_server is not None and runtime.hands_server.path == home / "run" / "hands.sock"
    assert runtime.harness.mac_tools[1:] == ("-m", "milo.mcp_server", "--socket", str(home / "run" / "hands.sock"))
    assert not runtime.hands_server.path.exists(), "bound by main(), not by build()"
    assert runtime.live_talk._eyes is not None


def test_hands_disabled_gives_the_worker_no_mac_tools(build):
    runtime, _ = build(cheap(**{"hands.enabled": False}))
    assert runtime.hands_server is None and runtime.harness.mac_tools == ()


def test_screen_and_background_workers_both_run_with_milos_tools_only(build):
    runtime, home = build(cheap(**{"harness.use": "codex"}))
    screen, background = runtime.harness, runtime.helpers._runner._background
    assert isinstance(background, CodexHarness) and background is not screen
    assert screen.home == background.home == home / ".codex", "both in Milo's own Codex home"
    assert screen.mac_tools and background.mac_tools == ()
    runtime, home = build(cheap(**{"harness.use": "claude"}))
    for worker in (runtime.harness, runtime.helpers._runner._background):
        cmd = worker.command("hi", None)
        assert cmd[cmd.index("--setting-sources") + 1] == "project,local" and "--strict-mcp-config" in cmd


def test_heartbeat_disabled_builds_no_runner(build):
    runtime, _ = build(cheap(**{"heartbeat.enabled": False}))
    assert runtime.heartbeat is None


@pytest.mark.parametrize("section, available", [
    ("chat", "claude_live"),
    ("harness", "claude, codex"),
    ("stt", "mlx_whisper, none"),
    ("tts", "none, omnivoice, say"),
    ("audio", "none, sounddevice"),
    ("dictation", "fillers, plain"),
])
def test_a_bogus_use_name_lists_the_available_ones(build, section, available):
    with pytest.raises(ConfigError, match=rf"'bogus'; available: {available}$"):
        build(cheap(**{f"{section}.use": "bogus"}))


def test_a_bogus_fallback_voice_fails_at_build_not_when_the_primary_breaks(build):
    with pytest.raises(ConfigError, match=r"fallback.*'sya'; available: none, omnivoice, say"):
        build(cheap(**{"tts.fallback": "sya"}))


def test_no_fallback_voice_is_allowed(build):
    runtime, _ = build(cheap(**{"tts.fallback": ""}))
    assert isinstance(runtime.voice.current, MacSay)


def test_an_unknown_heartbeat_key_fails_at_build(build):
    with pytest.raises(ConfigError, match="tikc_s"):
        build(cheap().replace("tick_s = 30", "tikc_s = 30"))


def test_an_unknown_adapter_option_names_its_table(build):
    with pytest.raises(ConfigError, match=r"\[tts.say\].*pitch"):
        build(cheap().replace('[tts.say]\nvoice = ""', '[tts.say]\nvoice = ""\npitch = 3'))


def test_messages_are_off_until_switched_on(build):
    runtime, _ = build(cheap())
    assert runtime.messages is None and runtime.brain._messages is None


def test_messages_switched_on_wire_the_channel_relay_and_watchers(build):
    from milo.adapters.channel.telegram import TelegramChannel
    from milo.services.messages import MessageService

    runtime, home = build(cheap(**{"messages.enabled": True, "messages.brief_at": "07:30",
                                   "messages.away_after_min": 2}))
    messages = runtime.messages
    assert isinstance(messages, MessageService) and isinstance(messages._channel, TelegramChannel)
    assert messages._channel._token_path == home / "secrets" / "telegram-token"
    assert (home / "secrets").stat().st_mode & 0o777 == 0o700
    assert messages.settings.away_after_s == 120 and str(messages.settings.brief_at) == "07:30:00"
    assert messages in runtime.brain._approvals.relays
    assert messages.helper_changed in runtime.helpers.watchers
    assert messages.tick in runtime.heartbeat.on_tick
    assert runtime.brain.greeting()[-1].type == "remote"


def test_a_bad_messages_setting_names_the_key(build):
    with pytest.raises(ConfigError, match="brief_at"):
        build(cheap(**{"messages.enabled": True, "messages.brief_at": "7.30am"}))
    with pytest.raises(ConfigError, match=r"messages\.telegram.*tokn_file"):
        build(cheap(**{"messages.enabled": True}).replace("token_file =", "tokn_file ="))
