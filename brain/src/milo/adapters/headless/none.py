"""`use = "none"` for [stt], [tts], [audio] and [chat]: no model loads, no device opens, nothing is ever heard
and Milo never answers. For workspaces that test one part of him, like dictation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from milo.core.ports import LevelCallback
from milo.core.registry import (AUDIO_INPUTS, AUDIO_OUTPUTS, LIVE_MODELS, TRANSCRIBERS, VOICES, AdapterContext,
                                options_from)
from milo.core.types import Audio, STT_SAMPLE_RATE, Usage


class NoTranscriber:
    def warm(self) -> None:
        pass

    def wake(self) -> None:
        pass

    def transcribe(self, audio: Audio) -> str:
        return ""


class SilentVoice:
    sample_rate = STT_SAMPLE_RATE

    def warm(self) -> None:
        pass

    def synthesize(self, text: str) -> Audio:
        return np.zeros(1, dtype=np.float32)

    def cancel(self) -> None:
        pass


class NoMicrophone:
    @property
    def active(self) -> bool:
        return False

    def start(self, on_level: LevelCallback) -> None:
        raise OSError("this Milo has no microphone")

    def stop(self) -> Audio:
        return np.zeros(0, dtype=np.float32)

    def peek(self, start: int = 0) -> Audio:
        return np.zeros(0, dtype=np.float32)


class NoSpeaker:
    def begin(self, sample_rate: int, on_level: LevelCallback) -> None:
        pass

    def feed(self, audio: Audio) -> None:
        pass

    async def drain(self) -> bool:
        return True

    def interrupt(self) -> None:
        pass


@dataclass(frozen=True)
class NoOptions:
    pass


@TRANSCRIBERS.register("none")
def _stt(options: Mapping[str, Any], ctx: AdapterContext) -> NoTranscriber:
    options_from(NoOptions, options, "stt.none")
    return NoTranscriber()


@VOICES.register("none")
def _tts(options: Mapping[str, Any], ctx: AdapterContext) -> SilentVoice:
    options_from(NoOptions, options, "tts.none")
    return SilentVoice()


@AUDIO_INPUTS.register("none")
def _mic(options: Mapping[str, Any], ctx: AdapterContext) -> NoMicrophone:
    options_from(NoOptions, options, "audio.none")
    return NoMicrophone()


@AUDIO_OUTPUTS.register("none")
def _speaker(options: Mapping[str, Any], ctx: AdapterContext) -> NoSpeaker:
    return NoSpeaker()


class NoChat:
    """A chat model that never says anything."""

    name = "none"

    def __init__(self):
        self.last_usage = Usage()

    async def start(self, system_prompt: str) -> None:
        pass

    async def turn(self, text: str, images=()):
        return
        yield

    async def interrupt(self) -> None:
        pass

    async def close(self) -> None:
        pass


@LIVE_MODELS.register("none")
def _chat(options: Mapping[str, Any], ctx: AdapterContext) -> NoChat:
    options_from(NoOptions, options, "chat.none")
    return NoChat()
