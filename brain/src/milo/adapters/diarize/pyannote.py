"""Who spoke when over a whole call, with pyannote's community-1 pipeline (MIT code, CC-BY-4.0 weights). Needs the
`pyannote` extra; torch loads only on warm().

On two AMI meetings (4 people each, docs/research/meetings.md) it found 5 and 4 speakers with a diarization error of
19 to 20%, where the live TitaNet voices found 42 and 30 (41 to 55%). It took about 0.13x the meeting's length on an M3
GPU. It runs once after Stop, over the call's track (services/meeting_regroup.py).

The weights are gated on Hugging Face: download them once into `model_dir` (see the [meetings.pyannote] docs in
config.toml). pyannote's usage reporting (the length of each file and the speaker counts, sent to pyannote.ai) is
switched off before it loads: nothing about a call leaves the Mac.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from milo.core.registry import CALL_DIARIZERS, AdapterContext, ConfigError, options_from
from milo.core.types import STT_SAMPLE_RATE, Audio

log = logging.getLogger(__name__)

DEFAULT_DIR = "~/.cache/milo/models/pyannote-community-1"
DEVICES = ("auto", "mps", "cuda", "cpu")


@dataclass(frozen=True)
class PyannoteOptions:
    model_dir: str = DEFAULT_DIR
    """The downloaded pipeline: config.yaml with its segmentation, embedding and plda folders."""
    device: str = "auto"
    """auto (the GPU when there is one), mps, cuda or cpu."""

    def __post_init__(self):
        if self.device not in DEVICES:
            raise ConfigError(f"[meetings.pyannote] device must be one of {', '.join(DEVICES)}")


class PyannoteDiarizer:
    def __init__(self, options: PyannoteOptions = PyannoteOptions()):
        self.options = options
        self._pipeline: Any = None
        self._lock = threading.Lock()

    def warm(self) -> None:
        with self._lock:
            if self._pipeline is not None:
                return
            folder = Path(self.options.model_dir).expanduser()
            if not (folder / "config.yaml").is_file():
                raise RuntimeError(f"pyannote's model isn't in {folder}: download "
                                   "pyannote/speaker-diarization-community-1 there once (it is gated on Hugging Face)")
            os.environ["PYANNOTE_METRICS_ENABLED"] = "false"  # read when pyannote.audio is first imported, and on use
            try:
                import torch
                from pyannote.audio import Pipeline
            except ImportError as e:
                raise RuntimeError("pyannote isn't installed: the brain needs the `pyannote` extra") from e
            pipeline = Pipeline.from_pretrained(folder)
            device = self._device(torch)
            if device != "cpu":
                pipeline.to(torch.device(device))
            self._pipeline = pipeline
            log.info("call diarizer ready: pyannote community-1 on %s", device)

    def segments(self, audio: Audio) -> list[tuple[float, float, str]]:
        self.warm()
        if len(audio) < STT_SAMPLE_RATE:
            return []
        import torch

        waveform = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32)).unsqueeze(0)
        with self._lock:
            output = self._pipeline({"waveform": waveform, "sample_rate": STT_SAMPLE_RATE})
        # community-1 also gives one voice at a time, which lines of a transcript fit better than overlapping turns.
        annotation = getattr(output, "exclusive_speaker_diarization", None) or getattr(
            output, "speaker_diarization", output)
        return [(float(turn.start), float(turn.end), str(label))
                for turn, _, label in annotation.itertracks(yield_label=True)]

    def _device(self, torch) -> str:
        if self.options.device != "auto":
            return self.options.device
        if torch.backends.mps.is_available():
            return "mps"
        return "cuda" if torch.cuda.is_available() else "cpu"


@CALL_DIARIZERS.register("pyannote")
def _pyannote(options: Mapping[str, Any], ctx: AdapterContext) -> PyannoteDiarizer:
    return PyannoteDiarizer(options_from(PyannoteOptions, options, "meetings.pyannote"))
