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
    assert runtime.harness.workdir == home / "work", "helpers write only their own folder (ADR 0020)"
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
        assert "--restricted" in cmd and "--strict-mcp-config" in cmd
        assert f"Write(/{(home / 'config.toml').resolve()})" in worker.deny, "both keep off Milo's control files"
        assert worker.workdir == home / "work"


def test_heartbeat_disabled_builds_no_runner(build):
    runtime, _ = build(cheap(**{"heartbeat.enabled": False}))
    assert runtime.heartbeat is None


@pytest.mark.parametrize("section, available", [
    ("chat", "claude_live, none"),
    ("harness", "claude, codex"),
    ("stt", "mlx_whisper, none, tones"),
    ("tts", "elevenlabs, none, omnivoice, say"),
    ("audio", "none, sounddevice, wav"),
    ("dictation", "fillers, plain"),
])
def test_a_bogus_use_name_lists_the_available_ones(build, section, available):
    with pytest.raises(ConfigError, match=rf"'bogus'; available: {available}$"):
        build(cheap(**{f"{section}.use": "bogus"}))


def test_a_bogus_fallback_voice_fails_at_build_not_when_the_primary_breaks(build):
    with pytest.raises(ConfigError, match=r"fallback.*'sya'; available: elevenlabs, none, omnivoice, say"):
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


def test_memory_is_wired_and_the_old_profile_moves_into_facts(build, tmp_path):
    from milo.adapters.embed.mlx_e5 import MlxE5
    from milo.memory.fact_profile import BACKUP

    home = tmp_path / "Milo"
    (home / "memory").mkdir(parents=True)
    (home / "memory" / "profile.md").write_text("# About the user\n\n## People\n- Anna is the user's sister.\n")
    runtime, home = build(cheap(**{"memory.recall_tokens": 500}))
    memory = runtime.memory
    assert memory is not None and memory.memory.recall_tokens == 500
    assert isinstance(memory.memory._embedder, MlxE5) and memory.memory._embedder._net is None, "loads on warm"
    assert [f.text for f in memory.memory.facts.current()] == ["Anna is the user's sister."]
    assert (home / "memory" / BACKUP).exists() and "facts.jsonl" in (home / "memory" / "profile.md").read_text()
    assert runtime.live_talk._memory is memory.turns and runtime.live_talk._profile is memory.profile
    assert memory.sleep is not None and memory.sleep.calls_per_day == 2
    assert not (home / "state" / "memory.sqlite").exists(), "the index opens on the memory thread"
    memory.executor.shutdown(wait=False)


def test_memory_can_be_switched_off_and_keeps_the_tools_server_for_it(build):
    runtime, _ = build(cheap(**{"memory.enabled": False}))
    assert runtime.memory is None and runtime.live_talk._memory is None
    runtime, _ = build(cheap(**{"connections.enabled": False, "memory.consolidate": False}))
    assert [s.name for s in runtime.harness.tool_servers] == ["milo"], "the memory tools still need it"
    assert runtime.memory.sleep is None
    runtime.memory.executor.shutdown(wait=False)
    runtime, _ = build(cheap(**{"connections.enabled": False, "memory.enabled": False}))
    assert [s.name for s in runtime.harness.tool_servers] == ["milo"], "milo_remind: helpers can't write reminders.md"


def test_a_bad_memory_setting_fails_at_build(build):
    with pytest.raises(ConfigError, match="recall_tokens"):
        build(cheap(**{"memory.recall_tokens": 99999}))
    with pytest.raises(ConfigError, match="embedder"):
        build(cheap(**{"memory.embedder": "nope"}))


def test_the_cloud_voice_and_hearing_are_built_from_config(build):
    from milo.adapters.stt.elevenlabs_scribe import ScribeRealtime
    from milo.adapters.tts.elevenlabs import ElevenLabsVoice

    text = set_key(cheap(**{"stt.talk": "elevenlabs", "stt.elevenlabs.keyterms": ["Milo"],
                            "tts.elevenlabs.voice_id": "abc"}), "tts", "use", "elevenlabs")
    runtime, home = build(text)
    assert isinstance(runtime.voice.current, ElevenLabsVoice) and runtime.voice.current.voice_id == "abc"
    assert runtime.voice.current.key_file == home / "secrets" / "elevenlabs.key"
    hearing = runtime.brain._listening._hearing
    assert isinstance(hearing._engine, ScribeRealtime) and hearing._engine.keyterms == ("Milo",)
    assert not hearing.dictation, "dictation stays on the Mac unless cloud_dictation says otherwise"
    assert len(runtime.notices) == 2


def test_with_elevenlabs_speaking_omnivoice_is_not_even_built_until_it_fails(build):
    text = set_key(cheap(**{"tts.fallback": "omnivoice"}), "tts", "use", "elevenlabs")
    runtime, home = build(text)
    (home / "secrets").mkdir(exist_ok=True)
    (home / "secrets" / "elevenlabs.key").write_text("sk_test")
    runtime.voice.warm()
    assert runtime.voice._fallback is None, "OmniVoice's GBs stay out of memory while ElevenLabs works"


def test_talk_stays_local_by_default_and_a_bogus_service_fails_at_build(build):
    runtime, _ = build(cheap())
    assert runtime.brain._listening._hearing is None
    with pytest.raises(ConfigError, match="streaming stt engine 'bogus'"):
        build(cheap(**{"stt.talk": "bogus"}))


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
    assert messages.tick in runtime.heartbeat.after_tick
    assert runtime.brain.greeting()[-1].type == "remote"


def test_a_bad_messages_setting_names_the_key(build):
    with pytest.raises(ConfigError, match="brief_at"):
        build(cheap(**{"messages.enabled": True, "messages.brief_at": "7.30am"}))
    with pytest.raises(ConfigError, match=r"messages\.telegram.*tokn_file"):
        build(cheap(**{"messages.enabled": True}).replace("token_file =", "tokn_file ="))


def test_every_busy_check_asks_attention(build):
    # A2: one place says when the user is busy; a new kind of activity is added there, not in eight lambdas.
    runtime, _ = build(cheap(**{"chat.voice_barge_in": False}))
    a = runtime.attention
    approvals = runtime.brain._approvals
    assert approvals._quiet == a.in_conversation
    assert runtime.helpers._quiet == a.in_conversation
    assert runtime.heartbeat._busy == a.answering
    assert {n._busy for n in runtime.notices} == {a.using_voice}
    assert runtime.memory.sleep._busy == a.at_work
    runtime.memory.executor.shutdown(wait=False)
    assert runtime.brain._routines._quiet == a.in_conversation
    if runtime.meetings is not None:
        assert (runtime.meetings._private, runtime.meetings._quiet) == (a.private, a.in_conversation)
    assert a.turn() is False and a.question() is False and a.helpers() is False, "every part is attached"


def test_a_step_moved_before_what_it_needs_fails_at_build_naming_the_part(build, monkeypatch):
    # A1: build() is named steps in an explicit order. A reorder used to surface as a NameError inside a
    # callback, long after start; now the build itself stops and says which part was missing.
    steps = list(compose.BUILD_STEPS)
    assert [s.__name__ for s in steps] == ["_workspace", "_engines", "_stores", "_presence", "_helpers", "_meetings",
                                           "_talk", "_messages", "_tool_socket", "_heartbeat", "_brain"]
    steps.remove(compose._talk)
    steps.insert(steps.index(compose._helpers), compose._talk)
    monkeypatch.setattr(compose, "BUILD_STEPS", tuple(steps))
    with pytest.raises(compose.BuildOrder, match="'helpers' is used before the step that builds it"):
        build(cheap())


def test_always_and_never_for_an_app_go_into_config_toml_through_settings(build):
    runtime, home = build(cheap(**{"meetings.never": "Zoom"}))
    meetings = runtime.meetings
    if meetings is None:
        pytest.skip("no transcriber with timings here, so no meeting notes")
    assert meetings.options.never == ("Zoom",)
    meetings.remember("always", "Zoom")
    meetings.remember("always", "Microsoft Teams")
    meetings.remember("always", "zoom")
    text = (home / "config.toml").read_text()
    assert 'always = "Zoom, Microsoft Teams"' in text and 'never = ""' in text
    assert meetings.options.always == ("Zoom", "Microsoft Teams") and meetings.options.never == ()
    assert meetings.options.says("ZOOM") == "always"


def test_how_long_milo_stays_on_screen_changes_without_a_restart(build):
    runtime, home = build(cheap())
    settings = runtime.brain._settings
    settings.change("ui", "hide_after_s", 300)
    assert "hide_after_s = 300" in (home / "config.toml").read_text()
    report = settings.report()
    [row] = [r for r in report.settings if (r["section"], r["key"]) == ("ui", "hide_after_s")]
    assert row["value"] == 300 and row["live"] and not report.restart
