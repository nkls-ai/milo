"""The Platform for the OS the brain runs on: which engines config.toml gets when it doesn't name one.

The one place that asks what OS this is (ADR 0027). compose and the other entry points call `current()`.
"""

from __future__ import annotations

import sys
from dataclasses import replace

from milo.core.platform import ANYWHERE, Platform

MACOS = Platform("macos", stt="mlx_whisper", tts="omnivoice", tts_fallback="say", embedder="mlx_e5",
                 connections="mac")
"""Everything local: Whisper and e5 on MLX, OmniVoice on the GPU with the Mac's `say` behind it, and the Mac's
own apps as connections."""

LINUX = replace(ANYWHERE, name="linux")
WINDOWS = replace(ANYWHERE, name="windows")
"""Until they have local engines: a faster-whisper or whisper.cpp transcriber, an ONNX e5, Piper as the
fallback voice, and Outlook or Evolution as connections."""


def for_os(name: str) -> Platform:
    """The Platform for a `sys.platform` value."""
    if name == "darwin":
        return MACOS
    if name.startswith("win"):
        return WINDOWS
    return LINUX if name.startswith("linux") else replace(ANYWHERE, name=name)


def current() -> Platform:
    return for_os(sys.platform)
