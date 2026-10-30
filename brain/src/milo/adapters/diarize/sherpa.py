"""Telling voices apart with sherpa-onnx (Apache-2.0), on the CPU, no torch.

Whisper's segments and pauses say where one stretch of speech ends; this embeds each stretch's voice with NVIDIA
NeMo TitaNet-small (CC-BY-4.0, 40 MB, downloaded on first use and checked against a pinned hash). MeetingService
groups the voices into people. On generated meetings this got every line's speaker right, where sherpa's own
pyannote segmentation plus clustering got 58% and took half the meeting's length to run. docs/research/meetings.md
has the comparison, also of the CAM++, ERes2Net and WeSpeaker embeddings.
"""

from __future__ import annotations

import hashlib
import logging
import os
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from milo.core.meetings import Turn
from milo.core.registry import DIARIZERS, AdapterContext, ConfigError, options_from
from milo.core.types import STT_SAMPLE_RATE, Audio

log = logging.getLogger(__name__)

_RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
EMBEDDINGS = {
    # name: (file, sha256, default match threshold)
    "titanet_small": ("nemo_en_titanet_small.onnx",
                      "ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e", 0.6),
    "eres2net": ("3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx",
                 "c59158379255ad66e161679cca6af8d52d51e389e3224ab7d7a7baae295c2db5", 0.55),
}
MIN_SECONDS = 0.3
"""Shorter spans carry too little voice; their words go to the nearest turn."""
SPAN_MAX_S = 12.0
"""A long span is embedded from its first this-many seconds: plenty for a voice, and bounded time."""


@dataclass(frozen=True)
class SherpaOptions:
    embedding: str = "titanet_small"
    """titanet_small (default, CC-BY-4.0) or eres2net (Apache-2.0, 9x slower)."""
    match: float = 0.0
    """How alike two stretches of speech must sound to count as one person. 0: the embedding's own default."""
    threads: int = 1
    models_dir: str = ""
    """Where the model goes. Empty: ~/.cache/milo/models."""

    def __post_init__(self):
        if self.embedding not in EMBEDDINGS:
            raise ConfigError(f"[meetings.sherpa_onnx] embedding must be one of {', '.join(EMBEDDINGS)}")
        if not 0 <= self.match < 1:
            raise ConfigError("[meetings.sherpa_onnx] match must be from 0 to 1")
        if self.threads < 1:
            raise ConfigError("[meetings.sherpa_onnx] threads must be 1 or more")


def fetch(folder: Path, name: str, url: str, sha256: str) -> Path:
    """The model file, downloaded once. A file whose hash doesn't match is never used."""
    path = folder / name
    if path.exists():
        return path
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{name}.part"
    log.info("downloading %s", name)
    with urllib.request.urlopen(url, timeout=60) as response, open(tmp, "wb") as f:
        digest = hashlib.sha256()
        while block := response.read(1 << 16):
            digest.update(block)
            f.write(block)
    if digest.hexdigest() != sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{name} didn't match its pinned hash; not using it")
    os.replace(tmp, path)
    return path


class SherpaDiarizer:
    def __init__(self, options: SherpaOptions = SherpaOptions(), models_dir: Path | None = None):
        self.options = options
        self._file, self._sha, default_match = EMBEDDINGS[options.embedding]
        self.model = options.embedding
        self.match = options.match or default_match
        self._dir = models_dir or Path(options.models_dir or "~/.cache/milo/models").expanduser()
        self._extractor = None

    def warm(self) -> None:
        if self._extractor is not None:
            return
        import sherpa_onnx as so

        path = fetch(self._dir, self._file, _RELEASES + self._file, self._sha)
        config = so.SpeakerEmbeddingExtractorConfig(model=str(path), num_threads=self.options.threads)
        if not config.validate():
            raise RuntimeError("sherpa-onnx refused the voice model")
        self._extractor = so.SpeakerEmbeddingExtractor(config)
        log.info("diarizer ready (%s)", self.model)

    def speakers(self, audio: Audio, spans: Sequence[tuple[float, float]]) -> list[Turn]:
        self.warm()
        turns = []
        for i, (start, end) in enumerate(spans):
            if end - start < MIN_SECONDS:
                continue
            piece = audio[int(start * STT_SAMPLE_RATE):int(min(end, start + SPAN_MAX_S) * STT_SAMPLE_RATE)]
            if len(piece) >= MIN_SECONDS * STT_SAMPLE_RATE:
                turns.append(Turn(start, end, i, self.voice(piece)))
        return turns

    def voice(self, audio: Audio) -> np.ndarray:
        stream = self._extractor.create_stream()
        stream.accept_waveform(STT_SAMPLE_RATE, np.ascontiguousarray(audio, dtype=np.float32))
        stream.input_finished()
        v = np.asarray(self._extractor.compute(stream), dtype=np.float32)
        n = float(np.linalg.norm(v))
        return v / n if n else v


@DIARIZERS.register("sherpa_onnx")
def _sherpa(options: Mapping[str, Any], ctx: AdapterContext) -> SherpaDiarizer:
    return SherpaDiarizer(options_from(SherpaOptions, options, "meetings.sherpa_onnx"))
