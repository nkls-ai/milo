"""The Platform for the OS the brain runs on: which engines config.toml gets when it doesn't name one.

The one place that asks what OS this is (ADR 0027). compose and the other entry points call `current()`.
"""

from __future__ import annotations

import sys
from dataclasses import replace

from milo.adapters.key_names import LINUX_KEY_NAMES, MAC_KEY_NAMES, PC_KEY_NAMES
from milo.core.platform import ANYWHERE, Platform

MACOS = Platform("macos", stt="mlx_whisper", tts="pocket", tts_fallback="say", embedder="mlx_e5",
                 connections="mac", decide="d3", computer="Mac", tool_dirs=("/opt/homebrew/bin", "/usr/local/bin"),
                 key_names=MAC_KEY_NAMES)
"""Everything local: Whisper and e5 on MLX, Pocket TTS on the CPU with the Mac's `say` behind it, d3-lite on the
GPU, and the Mac's own apps as connections."""

_DESKTOP = replace(ANYWHERE, stt="faster_whisper", tts="pocket", connections="desktop", embedder="onnx_e5",
                   ui_defaults=(("dictate_key", "right_control"), ("talk_key", "right_option")),
                   key_names=PC_KEY_NAMES)
LINUX = replace(_DESKTOP, name="linux", tool_dirs=("/home/linuxbrew/.linuxbrew/bin",), key_names=LINUX_KEY_NAMES)
WINDOWS = replace(_DESKTOP, name="windows")
"""Local speech and semantic memory on CPU; CUDA is an explicit faster-whisper option."""


def for_os(name: str) -> Platform:
    """The Platform for a `sys.platform` value."""
    if name == "darwin":
        return MACOS
    if name.startswith("win"):
        return WINDOWS
    return LINUX if name.startswith("linux") else replace(ANYWHERE, name=name)


def current() -> Platform:
    return for_os(sys.platform)
