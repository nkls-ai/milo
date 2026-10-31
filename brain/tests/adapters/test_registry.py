import subprocess
import sys

import pytest

from milo.adapters import load_builtin
from milo.core.registry import (AUDIO_INPUTS, AUDIO_OUTPUTS, HARNESSES, LIVE_MODELS, TEXT_CLEANERS, TRANSCRIBERS,
                                VOICES, ConfigError)

EXPECTED = [
    (HARNESSES, "codex"), (HARNESSES, "claude"),
    (LIVE_MODELS, "claude_live"),
    (TRANSCRIBERS, "mlx_whisper"),
    (VOICES, "omnivoice"), (VOICES, "say"),
    (AUDIO_INPUTS, "sounddevice"), (AUDIO_OUTPUTS, "sounddevice"),
    (TEXT_CLEANERS, "fillers"), (TEXT_CLEANERS, "plain"),
]

# Every table in workspace_template/config.toml, keyed by registry and name.
TEMPLATE_OPTIONS = {
    (HARNESSES, "codex"): {"binary": "/bin/echo", "model": "", "light_model": "gpt-6-luna", "reasoning_effort": "low",
                           "sandbox": "workspace-write", "timeout_s": 180},
    (HARNESSES, "claude"): {"binary": "/bin/echo", "model": "", "light_model": "", "permission_mode": "acceptEdits",
                            "timeout_s": 180},
    (LIVE_MODELS, "claude_live"): {"binary": "/bin/echo", "model": "claude-sonnet-5-5", "effort": "low"},
    (TRANSCRIBERS, "mlx_whisper"): {"model": "mlx-community/whisper-large-v3-turbo",
                                    "preview_model": "mlx-community/whisper-base-mlx", "language": "",
                                    "vocabulary": "Milo, Codex, Claude"},
    (VOICES, "omnivoice"): {"device": "mps", "instruct": "male, young adult, high pitch", "voice_seed": 7,
                            "ref_audio": "", "ref_text": "", "steps": 8},
    (VOICES, "say"): {"voice": ""},
    (AUDIO_INPUTS, "sounddevice"): {"input_device": "", "output_device": ""},
    (AUDIO_OUTPUTS, "sounddevice"): {"input_device": "", "output_device": ""},
    (TEXT_CLEANERS, "fillers"): {"languages": ["en", "de"]},
    (TEXT_CLEANERS, "plain"): {},
}

IDS = [f"{r.kind}:{n}" for r, n in EXPECTED]


@pytest.mark.parametrize("registry, name", EXPECTED, ids=IDS)
def test_registered_after_load_builtin(registry, name):
    assert name in registry.names()


def test_load_builtin_is_idempotent():
    load_builtin()
    load_builtin()
    assert HARNESSES.names() == ["claude", "codex"]


@pytest.mark.parametrize("registry, name", EXPECTED, ids=IDS)
def test_template_options_are_accepted(registry, name, ctx):
    assert registry.create(name, TEMPLATE_OPTIONS[(registry, name)], ctx) is not None


@pytest.mark.parametrize("registry, name", EXPECTED, ids=IDS)
def test_typo_key_raises_config_error(registry, name, ctx):
    with pytest.raises(ConfigError, match="unknown key.*tmeout_s"):
        registry.create(name, {"tmeout_s": 1}, ctx)


def test_template_tables_match_the_options_dataclasses():
    """Guards against config.toml and the adapters drifting apart."""
    import tomllib
    from importlib.resources import files

    config = tomllib.loads(files("milo").joinpath("workspace_template/config.toml").read_text())
    sections = {HARNESSES: "harness", LIVE_MODELS: "chat", TRANSCRIBERS: "stt", VOICES: "tts", AUDIO_INPUTS: "audio",
                AUDIO_OUTPUTS: "audio", TEXT_CLEANERS: "dictation"}
    for (registry, name), options in TEMPLATE_OPTIONS.items():
        assert set(config[sections[registry]].get(name, {})) == set(options), f"{sections[registry]}.{name}"


def test_load_builtin_does_not_import_heavy_modules():
    code = (
        "import sys, milo.adapters\n"
        "milo.adapters.load_builtin()\n"
        "heavy = [m for m in ('torch', 'omnivoice', 'mlx', 'mlx_whisper', 'sounddevice') if m in sys.modules]\n"
        "print(','.join(heavy))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""
