"""MLX Whisper speech-to-text. Runs on the Apple GPU and needs no server."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from milo.core.meetings import TimedWord
from milo.core.registry import TRANSCRIBERS, AdapterContext, options_from
from milo.core.types import STT_SAMPLE_RATE, Audio

log = logging.getLogger(__name__)

MIN_SECONDS = 0.3
MIN_RMS = 0.004
CACHE_LIMIT = 256 * 2**20
"""MLX keeps freed GPU buffers for reuse, about 1 GB after a few passes. Capping that saves 800 MB of RAM
for a pass 1-2% slower, which matters on 16 GB next to OmniVoice."""

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
    preview_model: str = "mlx-community/whisper-base-mlx"  # live words while speaking; "" uses `model`
    language: str = ""
    vocabulary: str = ""


class MlxWhisper:
    """Final passes use `model`. Live passes use the much smaller `preview_model` (about 0.15 s instead of
    1.1 s on an M3), so a final pass never waits long behind one."""

    def __init__(self, model: str, *, preview_model: str = "", language: str = "", vocabulary: str = ""):
        self.model = model
        self.preview_model = preview_model or model
        self.language = language or None  # None lets Whisper detect it
        self.prompt = vocabulary or None  # names in the initial prompt bias Whisper's spelling
        self._models: dict[str, _Whisper] = {}

    def warm(self) -> None:
        """Download and load the models so the first real transcription is fast."""
        for name in dict.fromkeys((self.model, self.preview_model)):
            log.info("loading %s", name)
            self._whisper(name).run(np.zeros(STT_SAMPLE_RATE, dtype=np.float32), self.language, self.prompt)
        log.info("stt ready")

    def transcribe(self, audio: Audio) -> str:
        return self._transcribe(self.model, audio)

    def preview(self, audio: Audio) -> str:
        return self._transcribe(self.preview_model, audio)

    def words(self, audio: Audio) -> list[TimedWord]:
        """TimedTranscriber for meeting notes: the final model with word times. Skips silence and the segments
        Whisper makes up over noise."""
        if is_silent(audio):
            return []
        result = self._whisper(self.model).result(audio, self.language, self.prompt, word_timestamps=True,
                                                  hallucination_silence_threshold=2.0)
        words = []
        for n, segment in enumerate(result.get("segments") or []):
            text = str(segment.get("text", "")).strip()
            if not text or is_hallucination(text) or segment.get("compression_ratio", 0) > 2.4:
                continue
            if segment.get("no_speech_prob", 0) > 0.6 and segment.get("avg_logprob", 0) < -1.0:
                continue
            words += [TimedWord(float(w["start"]), float(w["end"]), str(w["word"]), n)
                      for w in segment.get("words") or [] if str(w.get("word", "")).strip()]
        return words

    def _transcribe(self, model: str, audio: Audio) -> str:
        if is_silent(audio):
            return ""
        text = self._run(audio, model)
        return "" if is_hallucination(text) else text

    def _run(self, audio: Audio, model: str) -> str:
        return self._whisper(model).run(audio, self.language, self.prompt)

    def _whisper(self, model: str) -> _Whisper:
        if model not in self._models:
            self._models[model] = _Whisper(model)
        return self._models[model]


class _Whisper:
    """One loaded Whisper model, run through mlx_whisper.transcribe.

    mlx_whisper detects the language with an encoder pass of its own and then encodes the same audio
    again to decode it. The encoder is nearly all of a pass (1.05 s of 1.1 s for large-v3-turbo on an
    M3), so this detects the language on exactly the window the decoder will see and keeps that
    encoding for it: one encoder pass per transcription instead of two. Not thread-safe; it runs on the
    STT thread only.
    """

    def __init__(self, repo: str):
        self.repo = repo
        self._model = None

    def run(self, audio: Audio, language: str | None, prompt: str | None) -> str:
        return str(self.result(audio, language, prompt).get("text", "")).strip()

    def result(self, audio: Audio, language: str | None, prompt: str | None, **options) -> dict:
        """mlx_whisper.transcribe's whole result: text, and segments with their words when asked."""
        import mlx.core as mx
        import mlx_whisper
        from mlx_whisper.transcribe import ModelHolder

        if self._model is None:
            from mlx_whisper.load_models import load_model

            mx.set_cache_limit(CACHE_LIMIT)
            self._model = load_model(self.repo, dtype=mx.float16)
            self._model.encoder = _LastEncoding(self._model.encoder)
        # mlx_whisper keeps one model in a class attribute and reloads it whenever the repo changes.
        ModelHolder.model, ModelHolder.model_path = self._model, self.repo
        audio = audio.astype(np.float32)
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self.repo,
            language=language or self._detect(audio),
            initial_prompt=prompt,
            condition_on_previous_text=False,
            verbose=None,
            **options,
        )
        return result

    def _detect(self, audio: Audio) -> str:
        import mlx.core as mx
        from mlx_whisper.audio import N_FRAMES, N_SAMPLES, log_mel_spectrogram, pad_or_trim

        model = self._model
        mel = log_mel_spectrogram(audio, n_mels=model.dims.n_mels, padding=N_SAMPLES)
        # The first window as transcribe() builds it for decoding: the audio's frames, then zeros.
        content = min(N_FRAMES, mel.shape[-2] - N_FRAMES)
        window = pad_or_trim(mel[:content], N_FRAMES, axis=-2).astype(mx.float16)
        _, probs = model.detect_language(model.encoder(window[None]))
        probs = probs[0] if isinstance(probs, list) else probs
        return max(probs, key=probs.get)


class _LastEncoding:
    """Wraps the Whisper encoder and returns the last result again for an equal input."""

    def __init__(self, encoder):
        self._encoder = encoder
        self._input = None
        self._output = None

    def __call__(self, mel):
        import mlx.core as mx

        last = self._input
        if last is not None and last.shape == mel.shape and last.dtype == mel.dtype and mx.array_equal(last, mel).item():
            return self._output
        self._input, self._output = mel, self._encoder(mel)
        return self._output


@TRANSCRIBERS.register("mlx_whisper")
def _mlx_whisper(options: Mapping[str, Any], ctx: AdapterContext) -> MlxWhisper:
    o = options_from(MlxWhisperOptions, options, "stt.mlx_whisper")
    return MlxWhisper(o.model, preview_model=o.preview_model, language=o.language, vocabulary=o.vocabulary)
