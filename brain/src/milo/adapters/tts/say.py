"""macOS `say`. Instant and robotic; the fallback when nothing else works."""

from __future__ import annotations

import subprocess
import tempfile
import wave
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from milo.core.registry import VOICES, AdapterContext, options_from
from milo.core.types import Audio


@dataclass(frozen=True)
class SayOptions:
    voice: str = ""  # empty: the system voice


class MacSay:
    sample_rate = 22_050

    def __init__(self, voice: str = ""):
        self.voice = voice

    def warm(self) -> None:
        pass

    def synthesize(self, text: str) -> Audio:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "say.wav"
            cmd = ["say", "-o", str(out), "--file-format=WAVE", f"--data-format=LEI16@{self.sample_rate}"]
            if self.voice:
                cmd += ["-v", self.voice]
            subprocess.run([*cmd, "--", text], check=True, capture_output=True)
            with wave.open(str(out)) as w:
                pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return pcm.astype(np.float32) / 32768


@VOICES.register("say")
def _say(options: Mapping[str, Any], ctx: AdapterContext) -> MacSay:
    return MacSay(options_from(SayOptions, options, "tts.say").voice)
