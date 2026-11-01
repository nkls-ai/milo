"""Concrete engines. Each module registers itself in a milo.core.registry registry by name.

Importing a module here must stay cheap: torch, omnivoice, mlx_whisper and sounddevice are
imported inside methods, so the brain starts fast and runs without the optional extras.
"""

from __future__ import annotations

import importlib

BUILTIN = (
    "harness.codex",
    "harness.claude",
    "harness.claude_live",
    "harness.codex_live",
    "harness.openai_compat",
    "stt.mlx_whisper",
    "stt.faster_whisper",
    "stt.elevenlabs_scribe",
    "stt.tones",
    "tts.say",
    "tts.omnivoice",
    "tts.pocket",
    "tts.elevenlabs",
    "audio.sounddevice_io",
    "audio.wav_file",
    "text.fillers",
    "text.plain",
    "connect.mac",
    "connect.outlook",
    "connect.caldav",
    "connect.desktop",
    "connect.fake",
    "headless.none",
    "embed.mlx_e5",
    "embed.onnx_e5",
    "embed.hashing",
    "channel.telegram",
    "channel.imessage",
    "home.home_assistant",
    "home.apple_home",
    "home.auto",
    "diarize.sherpa",
    "diarize.pyannote",
    "weather.open_meteo",
    "decide.d3",
)


def load_builtin() -> None:
    """Import every built-in adapter so it registers. Idempotent: Python imports each module once."""
    for name in BUILTIN:
        importlib.import_module(f"{__name__}.{name}")
