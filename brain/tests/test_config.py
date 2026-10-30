import logging
from importlib import resources
from pathlib import Path

import pytest

from milo.config import (PLUGGABLE, ChatSettings, Config, DictationSettings, HarnessSettings, HeartbeatSettings,
                         TtsSettings, UiSettings)
from milo.core.registry import ConfigError

TEMPLATE = Path(str(resources.files("milo") / "workspace_template" / "config.toml"))

# Shaped like a config written before [chat] existed, which ~/Milo may still have.
MINIMAL = """
[harness]
use = "codex"
[stt]
use = "mlx_whisper"
[tts]
use = "say"
[audio]
use = "sounddevice"
[dictation]
use = "plain"
"""


def test_the_shipped_template_loads():
    config = Config.load(TEMPLATE)
    assert config.chat == ChatSettings(conversation_idle_reset_s=600)
    assert config.harness == HarnessSettings()
    assert config.tts == TtsSettings(fallback="say")
    assert config.dictation == DictationSettings(keep_history=True)
    assert config.ui == UiSettings(dictate_key="fn", talk_key="right_option")
    assert config.heartbeat == HeartbeatSettings(enabled=True)
    assert config.section("heartbeat")["tick_s"] == 30
    assert config.section("heartbeat")["morning"] == {"after_hour": 5, "before_hour": 12}


@pytest.mark.parametrize("section, name, key, value", [
    ("chat", "claude_live", "model", "claude-sonnet-5-5"),
    ("harness", "codex", "reasoning_effort", "low"),
    ("stt", "mlx_whisper", "model", "mlx-community/whisper-large-v3-turbo"),
    ("tts", "omnivoice", "steps", 6),
    ("audio", "sounddevice", "input_device", ""),
    ("dictation", "fillers", "languages", ["en", "de"]),
])
def test_pluggable_returns_the_use_name_and_its_table(section, name, key, value):
    use, options = Config.load(TEMPLATE).pluggable(section)
    assert use == name
    assert options[key] == value
    assert "use" not in options


def test_pluggable_tables_belong_to_their_implementation_only():
    use, options = Config.load(TEMPLATE).pluggable("harness")
    assert set(options) == {"binary", "model", "reasoning_effort", "sandbox", "timeout_s"}
    use, options = Config.load(TEMPLATE).pluggable("chat")
    assert "conversation_idle_reset_s" not in options


def test_pluggable_without_a_table_is_empty():
    config = Config.parse(MINIMAL)
    for section in PLUGGABLE:
        assert config.pluggable(section)[1] == {}


def test_missing_optional_tables_fall_back_to_defaults():
    config = Config.parse(MINIMAL)
    assert config.chat == ChatSettings()
    assert config.harness == HarnessSettings()
    assert config.tts == TtsSettings()
    assert config.dictation == DictationSettings()
    assert config.ui == UiSettings()
    assert config.heartbeat == HeartbeatSettings()
    assert config.section("heartbeat") == {}


def test_a_config_without_chat_talks_with_claude_live():
    assert Config.parse(MINIMAL).pluggable("chat") == ("claude_live", {})


def test_the_old_harness_idle_reset_is_ignored_with_a_warning(caplog):
    caplog.set_level(logging.WARNING, logger="milo.config")
    config = Config.parse(MINIMAL.replace('use = "codex"', 'use = "codex"\nconversation_idle_reset_s = 90'))
    assert config.harness == HarnessSettings() and config.chat == ChatSettings()
    assert "conversation_idle_reset_s" in caplog.text and "[chat]" in caplog.text


def test_the_old_hands_confirm_timeout_is_ignored_with_a_warning(caplog):
    caplog.set_level(logging.WARNING, logger="milo.config")
    config = Config.parse(MINIMAL + "[hands]\nconfirm_timeout_s = 30\n")
    assert config.hands.enabled
    assert "confirm_timeout_s" in caplog.text and "[approvals] timeout_s" in caplog.text


def with_chat(text: str, body: str) -> str:
    return text.replace("[harness]", f"[chat]\n{body}\n[harness]", 1)


def test_settings_values_come_from_the_file():
    config = Config.parse(with_chat(MINIMAL, "conversation_idle_reset_s = 90")
                          .replace('use = "say"', 'use = "say"\nfallback = ""')
                          .replace('use = "plain"', 'use = "plain"\nkeep_history = false')
                          + '[ui]\ndictate_key = "right_command"\ntalk_key = "right_control"\n'
                          + "[heartbeat]\nenabled = false\ntick_s = 5\n")
    assert config.chat.conversation_idle_reset_s == 90
    assert config.tts.fallback == ""
    assert config.dictation.keep_history is False
    assert config.ui == UiSettings("right_command", "right_control")
    assert Config.parse(MINIMAL + '[ui]\ncharacter = "classic"\n').ui.character == "classic"
    assert config.heartbeat.enabled is False
    assert config.section("heartbeat")["tick_s"] == 5


@pytest.mark.parametrize("section", [*PLUGGABLE, "ui"])
def test_an_unknown_top_level_key_names_the_key(section):
    text = TEMPLATE.read_text().replace(f"[{section}]\n", f"[{section}]\nfrobnicate = 1\n", 1)
    with pytest.raises(ConfigError, match=rf"\[{section}\].*frobnicate"):
        Config.parse(text)


def test_an_unknown_section_names_it():
    with pytest.raises(ConfigError, match="hartbeat"):
        Config.parse(MINIMAL + "[hartbeat]\nenabled = true\n")


@pytest.mark.parametrize("extra, key", [
    ("[heartbeat]\nenabled = \"no\"\n", "enabled"),
    ("[ui]\ndictate_key = \"caps_lock\"\n", "dictate_key"),
    ("[ui]\ndictate_key = \"right_option\"\n", "same key"),
    ("[ui]\nwhats_this_key = \"m\"\n", "whats_this_key"),
    ("[ui]\nwhats_this_key = \"ctrl+\"\n", "whats_this_key"),
    ("[hands]\nenabled = \"yes\"\n", "enabled"),
    ("[hands]\nconfirm = 3\n", "confirm"),
    ("[ui]\ncharacter = \"robot\"\n", "character"),
    ("[ui]\nvoice = \"loud\"\n", "voice"),
    ("[chat]\nupdates = \"often\"\n", "updates"),
])
def test_bad_values_are_errors(extra, key):
    with pytest.raises(ConfigError, match=key):
        Config.parse(MINIMAL + extra)


@pytest.mark.parametrize("old, new, key", [
    ("[harness]", '[chat]\nconversation_idle_reset_s = "long"\n[harness]', "conversation_idle_reset_s"),
    ('use = "plain"', 'use = "plain"\nkeep_history = 1', "keep_history"),
    ('use = "say"', 'use = "say"\nfallback = false', "fallback"),
])
def test_wrong_types_name_the_key(old, new, key):
    with pytest.raises(ConfigError, match=key):
        Config.parse(MINIMAL.replace(old, new))


def test_ints_pass_as_floats():
    config = Config.parse(with_chat(MINIMAL, "conversation_idle_reset_s = 30"))
    assert config.chat.conversation_idle_reset_s == 30


def test_a_section_without_use_is_an_error():
    config = Config.parse(MINIMAL.replace('use = "sounddevice"', ""))
    with pytest.raises(ConfigError, match=r"\[audio\] needs use"):
        config.pluggable("audio")


def test_a_non_table_section_is_an_error():
    with pytest.raises(ConfigError, match=r"\[ui\] must be a table"):
        Config.parse('ui = "fn"\n' + MINIMAL)


def test_invalid_toml_names_the_file():
    with pytest.raises(ConfigError, match="my.toml is not valid TOML"):
        Config.parse("[harness\n", "my.toml")


def test_hands_and_the_whats_this_key_have_defaults_and_can_be_changed():
    config = Config.parse(MINIMAL)
    assert config.hands.enabled and config.hands.applescript
    assert config.ui.whats_this_key == "ctrl+option+m"
    changed = Config.parse(MINIMAL + "[ui]\nwhats_this_key = \"cmd+shift+F12\"\n[hands]\napplescript = false\n")
    assert changed.ui.whats_this_key == "cmd+shift+F12" and not changed.hands.applescript
    assert Config.parse(MINIMAL + "[ui]\nwhats_this_key = \"\"\n").ui.whats_this_key == ""
