"""MLX Whisper speech-to-text. Runs on the Apple GPU and needs no server."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from milo.core.registry import TRANSCRIBERS, AdapterContext, options_from
from milo.core.types import STT_SAMPLE_RATE, Audio

log = logging.getLogger(__name__)

MIN_SECONDS = 0.3
MIN_RMS = 0.004

# Whisper invents these on silence or noise. Drop a transcript that is only one of them.
_HALLUCINATIONS = {
    "thank you", "thanks for watching", "thank you for watching", "you", "bye", ".",
    "untertitel im auftrag des zdf", "untertitelung des zdf", "vielen dank", "tschüss",
    "untertitel der amara.org-community", "closed captioning by www.microsoft.com",
    "subtitles by the amara.org community",
}


def is_silent(audio: Audio) -> bool:
    """Too short or too quiet to hold speech. Whisper hallucinates on these, so skip them."""
    if len(audio) < STT_SAMPLE_RATE * MIN_SECONDS:
        return True
    return float(np.sqrt(np.mean(np.square(audio)))) < MIN_RMS


def is_hallucination(text: str) -> bool:
    key = re.sub(r"[!?.,]+$", "", text.strip().lower()).strip()
    return key in _HALLUCINATIONS or key.startswith("untertitel")


@dataclass(frozen=True)
class MlxWhisperOptions:
    model: str = "mlx-community/whisper-large-v3-turbo"
    language: str = ""
    vocabulary: str = ""


class MlxWhisper:
    def __init__(self, model: str, *, language: str = "", vocabulary: str = ""):
        self.model = model
        self.language = language or None  # None lets Whisper detect it
        self.prompt = vocabulary or None  # names in the initial prompt bias Whisper's spelling

    def warm(self) -> None:
        """Download and load the model so the first real transcription is fast."""
        log.info("loading %s", self.model)
        self._run(np.zeros(STT_SAMPLE_RATE, dtype=np.float32))
        log.info("stt ready")

    def transcribe(self, audio: Audio) -> str:
        if is_silent(audio):
            return ""
        text = self._run(audio)
        return "" if is_hallucination(text) else text

    def _run(self, audio: Audio) -> str:
        import mlx_whisper

        result = mlx_whisper.transcribe(
            audio.astype(np.float32),
            path_or_hf_repo=self.model,
            language=self.language,
            initial_prompt=self.prompt,
            condition_on_previous_text=False,
            verbose=None,
        )
        return str(result.get("text", "")).strip()


@TRANSCRIBERS.register("mlx_whisper")
def _mlx_whisper(options: Mapping[str, Any], ctx: AdapterContext) -> MlxWhisper:
    o = options_from(MlxWhisperOptions, options, "stt.mlx_whisper")
    return MlxWhisper(o.model, language=o.language, vocabulary=o.vocabulary)
