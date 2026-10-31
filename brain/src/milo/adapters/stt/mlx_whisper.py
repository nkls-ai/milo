"""MLX Whisper speech-to-text. Runs on the Apple GPU and needs no server."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from milo.core.meetings import TimedWord
from milo.core.registry import TRANSCRIBERS, AdapterContext, options_from
from milo.core.types import STT_SAMPLE_RATE, Audio, Interrupted

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


LEARNED_CHARS = 400
"""Learned words in the prompt, at most (about 100 tokens; Whisper's prompt holds 224). Whisper copies the
prompt's style, so a long list could cost punctuation; the first words are the user's own and the most seen."""


def vocabulary_prompt(configured: str, words: Sequence[str]) -> str:
    """`[stt.mlx_whisper] vocabulary`, then the words it doesn't already name, comma-separated, cut at LEARNED_CHARS."""
    known = {w.strip().lower() for w in configured.split(",") if w.strip()}
    extra: list[str] = []
    size = 0
    for word in words:
        word = " ".join(word.split())
        if not word or word.lower() in known:
            continue
        if size + len(word) + 2 > LEARNED_CHARS:
            break
        known.add(word.lower())
        extra.append(word)
        size += len(word) + 2
    return ", ".join(p for p in (configured.strip().rstrip(","), *extra) if p)


SHORT_PHRASE_S = 3.0
"""Language detection on a phrase shorter than this is a guess ("okay" sounds like many languages), so a
phrase that continues a recording keeps the language its earlier phrases had."""


class MlxWhisper:
    """Passes use `model`; live words use the much smaller `preview_model`. A quick pass and every preview
    encode only as much audio as there is (see `_Whisper`). The text said before a phrase is not put in
    Whisper's prompt: on 12 test dictations that made more errors (2.8% of words against 2.2%), since
    Whisper copies the prompt's style and drops full stops once one phrase lacks one."""

    def __init__(self, model: str, *, preview_model: str = "", language: str = "", vocabulary: str = ""):
        self.model = model
        self.preview_model = preview_model or model
        self.language = language or None  # None lets Whisper detect it
        self.vocabulary = vocabulary
        self.prompt = vocabulary or None  # names in the initial prompt bias Whisper's spelling
        self._models: dict[str, _Whisper] = {}
        self._last_language: str | None = None
        self._stop = threading.Event()

    def use_vocabulary(self, words: Sequence[str]) -> None:
        """Vocabulary: the dictionary's words go after `vocabulary` in the prompt, up to LEARNED_CHARS. Read by the
        next pass; a str attribute is swapped whole, so the STT thread never sees half of it."""
        self.prompt = vocabulary_prompt(self.vocabulary, words) or None

    def warm(self) -> None:
        """Download and load the models so the first real transcription is fast."""
        for name in dict.fromkeys((self.model, self.preview_model)):
            log.info("loading %s", name)
            self._whisper(name).warm(self.language, self.prompt)
        log.info("stt ready")

    def wake(self) -> None:
        """A short pass over a second of silence on each loaded model touches all their weights."""
        started = time.monotonic()
        self._stop.clear()  # an interrupt left over from the last recording's release
        for name in dict.fromkeys((self.model, self.preview_model)):
            if (whisper := self._models.get(name)) is not None:
                whisper.wake(self.language)
        if (took := time.monotonic() - started) > 0.5:
            log.info("woke the speech models in %.2fs (paged out while idle)", took)

    def transcribe(self, audio: Audio, before: str = "", *, quick: bool = False) -> str:
        language = self.language
        if language is None and before and len(audio) < SHORT_PHRASE_S * STT_SAMPLE_RATE:
            language = self._last_language
        return self._transcribe(self.model, audio, language, quick)

    def preview(self, audio: Audio) -> str:
        """Live words only: the next pass replaces them, so an unsure short pass is shown as it is instead of
        being done again over full windows. Those retries were all of them in the dictation e2e run."""
        return self._transcribe(self.preview_model, audio, self.language, True, retry=False)

    def interrupt(self) -> None:
        self._stop.set()

    def words(self, audio: Audio, language: str | None = None) -> list[TimedWord]:
        """TimedTranscriber for meeting notes: the final model with word times. Skips silence and the segments
        Whisper makes up over noise. interrupt() ends it with Interrupted, as it does a pass."""
        self._stop.clear()
        if is_silent(audio):
            return []
        result = self._whisper(self.model).result(audio, self.language or language, self.prompt,
                                                  word_timestamps=True)
        spoken = str(result.get("language") or self.language or language or "")
        words = []
        for n, segment in enumerate(result.get("segments") or []):
            text = str(segment.get("text", "")).strip()
            if not text or is_hallucination(text) or segment.get("compression_ratio", 0) > 2.4:
                continue
            if segment.get("no_speech_prob", 0) > 0.6 and segment.get("avg_logprob", 0) < -1.0:
                continue
            words += [TimedWord(float(w["start"]), float(w["end"]), str(w["word"]), n, spoken)
                      for w in segment.get("words") or [] if str(w.get("word", "")).strip()]
        return words

    def spoken_language(self, audio: Audio) -> str:
        if self.language:
            return self.language
        self._stop.clear()
        whisper = self._whisper(self.model)
        return whisper._detect(whisper._load(), audio.astype(np.float32))

    def _transcribe(self, model: str, audio: Audio, language: str | None, quick: bool, *, retry: bool = True) -> str:
        self._stop.clear()
        if is_silent(audio):
            return ""
        text = self._run(audio, model, language, quick, retry=retry)
        return "" if is_hallucination(text) else text

    def _run(self, audio: Audio, model: str, language: str | None, quick: bool, *, retry: bool = True) -> str:
        whisper = self._whisper(model)
        text = whisper.run(audio, language, self.prompt, quick=quick, retry=retry)
        if model == self.model and whisper.language:
            self._last_language = whisper.language
        return text

    def _whisper(self, model: str) -> _Whisper:
        if model not in self._models:
            self._models[model] = _Whisper(model, self._stop)
        return self._models[model]


PAD_S = 1.0
MIN_WINDOW_S = 10.0
"""Whisper is trained on 30 s windows, and its encoder costs the same for 2 s of speech as for 30 s,
because the audio is padded with silence to the full window. `_Whisper` encodes only the audio plus
`PAD_S` of silence, but never less than `MIN_WINDOW_S`: with a shorter window the decoder no longer knows
where speech ends and repeats itself ("Okay. Okay. Okay."). Measured on 48 phrases of 1-12 s in English
and German: 3 times faster than the full window, no repeats at 10 s (several at 6 and 8 s), but a few
more wrong words (2.7% against 1.7%), so only quick passes take it."""

TOKENS_PER_S = 8
"""Far more than anyone speaks (about 4 a second). A decode that runs past this for its audio is looping."""


def repeats(text: str) -> bool:
    """Whisper looping, not speech: the same sentence twice in a row, a run of three or more words twice,
    or of two or more words three times ("Okay. Okay.", "um 8 Uhr um 8 Uhr")."""
    sentences = [w for w in (_words(p) for p in re.split(r"[.!?]+", text)) if w]
    if any(a == b for a, b in zip(sentences, sentences[1:])):
        return True
    words = _words(text)
    for size, times in ((3, 2), (2, 3)):
        for k in range(size, len(words) // times + 1):
            for i in range(len(words) - k * times + 1):
                if all(words[i:i + k] == words[i + j * k:i + (j + 1) * k] for j in range(1, times)):
                    return True
    return False


def doubt(text: str, tokens: int, limit: int, ratio: float, logprob: float) -> str:
    """What is wrong with a short pass's decode: "" nothing, "loops" (it repeats or ran past TOKENS_PER_S), or
    "unsure" (Whisper's own confidence is low)."""
    if tokens >= limit or ratio > 2.4 or repeats(text):
        return "loops"
    return "unsure" if logprob < -1.0 else ""


def _words(text: str) -> list[str]:
    return re.sub(r"[^\w\s']", " ", text.lower()).split()


class _Whisper:
    """One loaded Whisper model. Not thread-safe; it runs on the STT thread only. Setting `stop` ends the
    pass at the next few encoder layers with Interrupted.

    A quick pass on audio that fits one window takes the short path: encode just the audio (see
    MIN_WINDOW_S), detect the language on that encoding and decode it without timestamps. If that decode
    looks wrong (it loops, ran past TOKENS_PER_S, or Whisper itself is unsure), the same audio goes through
    the full path. Every other pass takes the full path: mlx_whisper.transcribe over padded 30 s windows,
    the most accurate. Whisper's own transcribe() detects the language with an encoder pass and then
    encodes the same window again to decode it, so the full path detects on exactly the window the decoder
    will see and keeps that encoding: one encoder pass instead of two.
    """

    def __init__(self, repo: str, stop: threading.Event | None = None):
        self.repo = repo
        self._stop = stop or threading.Event()
        self.language: str | None = None
        """The language of the last pass."""
        self._model = None
        self._short = True

    def warm(self, language: str | None, prompt: str | None) -> None:
        """Load the model and run both paths once, so neither compiles during a real pass."""
        model, silence = self._load(), np.zeros(STT_SAMPLE_RATE, dtype=np.float32)
        self._run_short(model, silence, language, prompt)
        self._run_full(model, silence, language, prompt)

    def wake(self, language: str | None) -> None:
        if self._model is not None:
            self._run_short(self._model, np.zeros(STT_SAMPLE_RATE, dtype=np.float32), language or "en", None)

    def run(self, audio: Audio, language: str | None, prompt: str | None, *, quick: bool = False,
            retry: bool = True) -> str:
        """`retry=False`: an unsure short pass is kept as it is, and one that loops gives "", instead of doing the
        audio again over full windows (for live words)."""
        audio = audio.astype(np.float32)
        model = self._load()
        if quick and self._short and len(audio) + PAD_S * STT_SAMPLE_RATE <= 30 * STT_SAMPLE_RATE:
            try:
                text = self._run_short(model, audio, language, prompt, retry=retry)
            except Interrupted:
                raise
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
            self._model.encoder = _Encoder(self._model.encoder, self._model.dims.n_audio_state, self._stop)
            self._model.decoder = _Decoder(self._model.decoder, self._stop)
        return self._model

    def _run_short(self, model, audio: Audio, language: str | None, prompt: str | None, *,
                   retry: bool = True) -> str | None:
        """Decode from an encoding of just the audio. None: the result can't be trusted (only with `retry`)."""
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
        wrong = doubt(text, len(result.tokens), limit, result.compression_ratio, result.avg_logprob)
        if not wrong:
            return text
        if not retry:
            return "" if wrong == "loops" else text
        log.info("short whisper pass looks wrong (%s, %d tokens, ratio %.1f, logprob %.2f); full window",
                 self.repo.rsplit("/", 1)[-1], len(result.tokens), result.compression_ratio, result.avg_logprob)
        return None

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

    def result(self, audio: Audio, language: str | None, prompt: str | None, **options) -> dict:
        """mlx_whisper.transcribe's whole result over full windows: text, and segments with their words when
        asked (`word_timestamps=True`). For meeting passes."""
        import mlx_whisper
        from mlx_whisper.transcribe import ModelHolder

        audio = audio.astype(np.float32)
        model = self._load()
        ModelHolder.model, ModelHolder.model_path = model, self.repo
        language = language or self._detect(model, audio)
        return mlx_whisper.transcribe(audio, path_or_hf_repo=self.repo, language=language, initial_prompt=prompt,
                                      condition_on_previous_text=False, verbose=None, **options)

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
    encoded passes through, so the decoder can take a short encoding. The layers run a few at a time, and
    `stop` ends the encoding between them with Interrupted: the encoder is nearly all of a pass."""

    LAYERS_PER_STEP = 4

    def __init__(self, encoder, n_state: int, stop: threading.Event):
        self._encoder = encoder
        self._n_state = n_state
        self._stop = stop
        self._input = None
        self._output = None

    def __call__(self, mel):
        import mlx.core as mx

        if mel.shape[-1] == self._n_state:
            return mel
        last = self._input
        if last is not None and last.shape == mel.shape and last.dtype == mel.dtype and mx.array_equal(last, mel).item():
            return self._output
        self._input, self._output = None, None
        output = self.short(mel)
        self._input, self._output = mel, output
        return output

    def short(self, mel):
        """Encode up to 3000 mel frames, with the matching slice of the positional embedding."""
        import mlx.core as mx
        import mlx.nn as nn

        e = self._encoder
        x = nn.gelu(e.conv2(nn.gelu(e.conv1(mel))))
        x = x + e._positional_embedding[: x.shape[1]]
        for i, block in enumerate(e.blocks):
            if i % self.LAYERS_PER_STEP == 0:
                mx.eval(x)
                if self._stop.is_set():
                    raise Interrupted()
            x, _, _ = block(x)
        return e.ln_post(x)


class _Decoder:
    """Wraps the Whisper decoder so `stop` also ends decoding and word alignment, between two tokens: a long
    meeting pass then gives way to the user's dictation at once, not only while it encodes."""

    def __init__(self, decoder, stop: threading.Event):
        self._decoder = decoder
        self._stop = stop

    def __call__(self, *args, **kwargs):
        if self._stop.is_set():
            raise Interrupted()
        return self._decoder(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._decoder, name)


@TRANSCRIBERS.register("mlx_whisper")
def _mlx_whisper(options: Mapping[str, Any], ctx: AdapterContext) -> MlxWhisper:
    o = options_from(MlxWhisperOptions, options, "stt.mlx_whisper")
    return MlxWhisper(o.model, preview_model=o.preview_model, language=o.language, vocabulary=o.vocabulary)
