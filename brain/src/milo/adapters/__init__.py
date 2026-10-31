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
    "harness.openai_compat",
    "stt.mlx_whisper",
    "stt.elevenlabs_scribe",
    "stt.tones",
    "tts.say",
    "tts.omnivoice",
    "tts.elevenlabs",
    "audio.sounddevice_io",
    "audio.wav_file",
    "text.fillers",
    "text.plain",
    "connect.mac",
    "connect.fake",
    "headless.none",
    "embed.mlx_e5",
    "embed.hashing",
    "channel.telegram",
    "channel.imessage",
    "diarize.sherpa",
)


def load_builtin() -> None:
    """Import every built-in adapter so it registers. Idempotent: Python imports each module once."""
    for name in BUILTIN:
        importlib.import_module(f"{__name__}.{name}")
