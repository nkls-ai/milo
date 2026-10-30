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


BEFORE_CHARS = 200
"""How much of what was said before a phrase goes into Whisper's prompt: enough for spelling, casing and
the language to carry over, short enough that Whisper doesn't start repeating it."""

SHORT_PHRASE_S = 3.0
"""Language detection on a phrase shorter than this is a guess ("okay" sounds like many languages), so a
phrase that continues a recording keeps the language its earlier phrases had."""


class MlxWhisper:
    """Final passes use `model`. Live passes use the much smaller `preview_model`, so a final pass never
    waits long behind one. Both encode only as much audio as there is (see `_Whisper`)."""

    def __init__(self, model: str, *, preview_model: str = "", language: str = "", vocabulary: str = ""):
        self.model = model
        self.preview_model = preview_model or model
        self.language = language or None  # None lets Whisper detect it
        self.prompt = vocabulary or None  # names in the initial prompt bias Whisper's spelling
        self._models: dict[str, _Whisper] = {}
        self._last_language: str | None = None

    def warm(self) -> None:
        """Download and load the models so the first real transcription is fast."""
        for name in dict.fromkeys((self.model, self.preview_model)):
            log.info("loading %s", name)
            self._whisper(name).warm(self.language, self.prompt)
        log.info("stt ready")

    def transcribe(self, audio: Audio, before: str = "") -> str:
        language = self.language
        if language is None and before and len(audio) < SHORT_PHRASE_S * STT_SAMPLE_RATE:
            language = self._last_language
        prompt = " ".join(p for p in (self.prompt, before[-BEFORE_CHARS:].strip()) if p) or None
        return self._transcribe(self.model, audio, language, prompt)

    def preview(self, audio: Audio) -> str:
        return self._transcribe(self.preview_model, audio, self.language, self.prompt)

    def _transcribe(self, model: str, audio: Audio, language: str | None, prompt: str | None) -> str:
        if is_silent(audio):
            return ""
        text = self._run(audio, model, language, prompt)
        return "" if is_hallucination(text) else text

    def _run(self, audio: Audio, model: str, language: str | None, prompt: str | None) -> str:
        whisper = self._whisper(model)
        text = whisper.run(audio, language, prompt)
        if model == self.model and whisper.language:
            self._last_language = whisper.language
        return text

    def _whisper(self, model: str) -> _Whisper:
        if model not in self._models:
            self._models[model] = _Whisper(model)
        return self._models[model]


PAD_S = 1.0
MIN_WINDOW_S = 10.0
"""Whisper is trained on 30 s windows, and its encoder costs the same for 2 s of speech as for 30 s,
because the audio is padded with silence to the full window. `_Whisper` encodes only the audio plus
`PAD_S` of silence, but never less than `MIN_WINDOW_S`: with a shorter window the decoder no longer knows
where speech ends and repeats itself ("Okay. Okay. Okay."). Measured on 48 phrases of 1-12 s in English
and German: same words as the full window, 3 times faster, no repeats at 10 s (several at 6 and 8 s)."""

TOKENS_PER_S = 8
"""Far more than anyone speaks (about 4 a second). A decode that runs past this for its audio is looping."""


def repeats(text: str) -> bool:
    """Whisper looping, not speech: the same sentence twice in a row, a run of four or more words twice,
    or of two or more words three times ("Okay. Okay.", "I Milo. I Milo.")."""
    sentences = [w for w in (_words(p) for p in re.split(r"[.!?]+", text)) if w]
    if any(a == b for a, b in zip(sentences, sentences[1:])):
        return True
    words = _words(text)
    for size, times in ((4, 2), (2, 3)):
        for k in range(size, len(words) // times + 1):
            for i in range(len(words) - k * times + 1):
                if all(words[i:i + k] == words[i + j * k:i + (j + 1) * k] for j in range(1, times)):
                    return True
    return False


def _words(text: str) -> list[str]:
    return re.sub(r"[^\w\s']", " ", text.lower()).split()


class _Whisper:
    """One loaded Whisper model. Not thread-safe; it runs on the STT thread only.

    Audio that fits one window takes the short path: encode just the audio (see MIN_WINDOW_S), detect the
    language on that encoding and decode it without timestamps. If that decode looks wrong (it loops, ran
    past TOKENS_PER_S, or Whisper itself is unsure), the same audio goes through the full path:
    mlx_whisper.transcribe over padded 30 s windows. Whisper's own transcribe() detects the language with
    an encoder pass and then encodes the same window again to decode it, so the full path detects on
    exactly the window the decoder will see and keeps that encoding: one encoder pass instead of two.
    """

    def __init__(self, repo: str):
        self.repo = repo
        self.language: str | None = None
        """The language of the last pass."""
        self._model = None
        self._short = True

    def warm(self, language: str | None, prompt: str | None) -> None:
        """Load the model and run both paths once, so neither compiles during a real pass."""
        model, silence = self._load(), np.zeros(STT_SAMPLE_RATE, dtype=np.float32)
        self._run_short(model, silence, language, prompt)
        self._run_full(model, silence, language, prompt)

    def run(self, audio: Audio, language: str | None, prompt: str | None) -> str:
        audio = audio.astype(np.float32)
        model = self._load()
        if self._short and len(audio) + PAD_S * STT_SAMPLE_RATE <= 30 * STT_SAMPLE_RATE:
            try:
                text = self._run_short(model, audio, language, prompt)
            except (AttributeError, AssertionError, TypeError):
                # mlx_whisper changed inside; the full path still works.
                log.exception("short whisper pass failed; using full windows from now on")
                self._short = False
                text = None
            if text is not None:
                return text
        return self._run_full(model, audio, language, prompt)

    def _load(self):
        if self._model is None:
            import mlx.core as mx
            from mlx_whisper.load_models import load_model

            mx.set_cache_limit(CACHE_LIMIT)
            self._model = load_model(self.repo, dtype=mx.float16)
            self._model.encoder = _Encoder(self._model.encoder, self._model.dims.n_audio_state)
        return self._model

    def _run_short(self, model, audio: Audio, language: str | None, prompt: str | None) -> str | None:
        """Decode from an encoding of just the audio. None: the result can't be trusted."""
        import mlx.core as mx
        from mlx_whisper.audio import HOP_LENGTH, N_FRAMES, log_mel_spectrogram
        from mlx_whisper.decoding import DecodingOptions, DecodingTask

        window = max(len(audio) + int(PAD_S * STT_SAMPLE_RATE), int(MIN_WINDOW_S * STT_SAMPLE_RATE))
        frames = min(N_FRAMES, window // HOP_LENGTH) // 2 * 2  # the encoder halves the frames
        mel = log_mel_spectrogram(audio, n_mels=model.dims.n_mels, padding=max(0, window - len(audio)))
        features = model.encoder.short(mel[None, :frames].astype(mx.float16))
        if language is None:
            _, probs = model.detect_language(features)
            probs = probs[0] if isinstance(probs, list) else probs
            language = max(probs, key=probs.get)
        tokens = None
        if prompt:
            from mlx_whisper.tokenizer import get_tokenizer

            tokenizer = get_tokenizer(model.is_multilingual, num_languages=model.num_languages,
                                      language=language, task="transcribe")
            tokens = tokenizer.encode(" " + prompt.strip())
        limit = min(model.dims.n_text_ctx // 2, int(10 + TOKENS_PER_S * len(audio) / STT_SAMPLE_RATE))
        options = DecodingOptions(language=language, without_timestamps=True, fp16=True, prompt=tokens,
                                  sample_len=limit)
        result = DecodingTask(model, options).run(features)[0]
        self.language = language
        if result.no_speech_prob > 0.6 and result.avg_logprob < -1.0:
            return ""
        text = result.text.strip()
        if len(result.tokens) >= limit or result.compression_ratio > 2.4 or result.avg_logprob < -1.0 \
                or repeats(text):
            log.info("short whisper pass looks wrong (%d tokens, ratio %.1f, logprob %.2f); full window",
                     len(result.tokens), result.compression_ratio, result.avg_logprob)
            return None
        return text

    def _run_full(self, model, audio: Audio, language: str | None, prompt: str | None) -> str:
        import mlx_whisper
        from mlx_whisper.transcribe import ModelHolder

        # mlx_whisper keeps one model in a class attribute and reloads it whenever the repo changes.
        ModelHolder.model, ModelHolder.model_path = model, self.repo
        self.language = language or self._detect(model, audio)
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self.repo,
            language=self.language,
            initial_prompt=prompt,
            condition_on_previous_text=False,
            verbose=None,
        )
        return str(result.get("text", "")).strip()

    @staticmethod
    def _detect(model, audio: Audio) -> str:
        import mlx.core as mx
        from mlx_whisper.audio import N_FRAMES, N_SAMPLES, log_mel_spectrogram, pad_or_trim

        mel = log_mel_spectrogram(audio, n_mels=model.dims.n_mels, padding=N_SAMPLES)
        # The first window as transcribe() builds it for decoding: the audio's frames, then zeros.
        content = min(N_FRAMES, mel.shape[-2] - N_FRAMES)
        window = pad_or_trim(mel[:content], N_FRAMES, axis=-2).astype(mx.float16)
        _, probs = model.detect_language(model.encoder(window[None]))
        probs = probs[0] if isinstance(probs, list) else probs
        return max(probs, key=probs.get)


class _Encoder:
    """Wraps the Whisper encoder. A full window's result is kept and returned again for an equal input
    (the full path encodes for language detection, then transcribe() asks again). Input that is already
    encoded passes through, so the decoder can take a short encoding."""

    def __init__(self, encoder, n_state: int):
        self._encoder = encoder
        self._n_state = n_state
        self._input = None
        self._output = None

    def __call__(self, mel):
        import mlx.core as mx

        if mel.shape[-1] == self._n_state:
            return mel
        last = self._input
        if last is not None and last.shape == mel.shape and last.dtype == mel.dtype and mx.array_equal(last, mel).item():
            return self._output
        self._input, self._output = mel, self._encoder(mel)
        return self._output

    def short(self, mel):
        """Encode fewer than 3000 mel frames, with the matching slice of the positional embedding."""
        import mlx.nn as nn

        e = self._encoder
        x = nn.gelu(e.conv2(nn.gelu(e.conv1(mel))))
        x = x + e._positional_embedding[: x.shape[1]]
        for block in e.blocks:
            x, _, _ = block(x)
        return e.ln_post(x)


@TRANSCRIBERS.register("mlx_whisper")
def _mlx_whisper(options: Mapping[str, Any], ctx: AdapterContext) -> MlxWhisper:
    o = options_from(MlxWhisperOptions, options, "stt.mlx_whisper")
    return MlxWhisper(o.model, preview_model=o.preview_model, language=o.language, vocabulary=o.vocabulary)
