"""Local Whisper on CPU or CUDA. Heavy CTranslate2 imports and downloads are lazy.

Like the MLX engine, all inference runs on the brain's single STT executor.
Cancellation is checked between decoded segments; a CTranslate2 encoder call
already running cannot be interrupted safely.

`device = "auto"` uses an NVIDIA GPU when one is there and its CUDA 12 / cuDNN 9 libraries can be loaded
(the `cuda` extra installs them into the environment), else the CPU. `model`, `preview_model` and
`compute_type` = "auto" then pick what suits that device: large-v3-turbo with a small preview on the GPU
(about 0.25 s a pass on an RTX 2070), small with a base preview on the CPU. A GPU that fails to load or run
falls back to the CPU by itself.
"""
from __future__ import annotations

import glob
import logging
import os
import sys
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from milo.core.meetings import TimedWord
from milo.core.registry import TRANSCRIBERS, AdapterContext, ConfigError, options_from
from milo.core.types import Audio, Interrupted, STT_SAMPLE_RATE

from ._whisper_common import is_hallucination, is_silent, vocabulary_prompt

log = logging.getLogger(__name__)

AUTO = {  # device -> (model, preview_model, compute_type)
    "cuda": ("large-v3-turbo", "small", "int8_float16"),
    "cpu": ("small", "base", "int8"),
}


@dataclass(frozen=True)
class FasterWhisperOptions:
    model: str = "auto"
    preview_model: str = "auto"
    device: str = "auto"
    compute_type: str = "auto"
    language: str = ""
    vocabulary: str = ""
    cpu_threads: int = 0

    def __post_init__(self):
        for name in ("model", "preview_model", "device", "compute_type", "language", "vocabulary"):
            if not isinstance(getattr(self, name), str):
                raise ConfigError(f"[stt.faster_whisper] {name} must be text")
        if not self.model or self.device not in ("cpu", "cuda", "auto"):
            raise ConfigError("[stt.faster_whisper] model must be nonempty and device must be cpu, cuda or auto")
        if isinstance(self.cpu_threads, bool) or not isinstance(self.cpu_threads, int) or self.cpu_threads < 0:
            raise ConfigError("[stt.faster_whisper] cpu_threads must be a nonnegative integer")


_cuda_lock = threading.Lock()
_cuda_checked: str | None = None  # "" when usable, else why not


def _nvidia_dirs() -> list[str]:
    """The CUDA libraries the `cuda` extra installs (nvidia-cublas-cu12, nvidia-cudnn-cu12)."""
    found = []
    for root in dict.fromkeys(sys.path):
        base = os.path.join(root, "nvidia")
        if os.path.isdir(base):
            found += glob.glob(os.path.join(base, "*", "bin" if sys.platform == "win32" else "lib"))
    return found


def cuda_unavailable() -> str:
    """"" if CTranslate2 can run on an NVIDIA GPU here, else the reason. Loads the CUDA libraries once.

    A missing cuDNN on Windows doesn't raise: CTranslate2 aborts the whole process at the first inference.
    So the libraries are loaded here first, where a failure is only an exception."""
    global _cuda_checked
    with _cuda_lock:
        if _cuda_checked is not None:
            return _cuda_checked
        _cuda_checked = _check_cuda()
        return _cuda_checked


def _check_cuda() -> str:
    import ctypes
    if sys.platform not in ("win32", "linux"):
        return "CUDA runs on Windows and Linux only"
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() < 1:
            return "no NVIDIA GPU"
    except Exception as e:
        return f"CTranslate2 can't see CUDA: {e}"
    dirs = _nvidia_dirs()
    if sys.platform == "win32":
        for directory in dirs:
            os.add_dll_directory(directory)
        os.environ["PATH"] = os.pathsep.join([*dirs, os.environ.get("PATH", "")])
        names = ["cublas64_12.dll", "cublasLt64_12.dll", "cudnn64_9.dll", "cudnn_ops64_9.dll", "cudnn_cnn64_9.dll"]
        loader = ctypes.WinDLL
    else:
        names = ["libcublasLt.so.12", "libcublas.so.12", "libcudnn.so.9", "libcudnn_ops.so.9", "libcudnn_cnn.so.9"]
        loader = lambda name: ctypes.CDLL(name, mode=ctypes.RTLD_GLOBAL)  # noqa: E731
    for name in names:
        candidates = [os.path.join(d, name) for d in dirs if os.path.exists(os.path.join(d, name))] or [name]
        for candidate in candidates:
            try:
                loader(candidate)
                break
            except OSError:
                continue
        else:
            if getattr(sys, "frozen", False):
                return f"{name} is missing: this packaged build carries no CUDA libraries"
            return f"{name} is missing (uv sync --extra desktop --extra cuda installs it)"
    return ""


class FasterWhisper:
    def __init__(self, model: str = "auto", *, preview_model: str = "auto", device: str = "auto",
                 compute_type: str = "auto", language: str = "", vocabulary: str = "", cpu_threads: int = 0):
        self._wanted = (model, preview_model, device, compute_type)
        self.model = self.preview_model = self.device = self.compute_type = ""
        self._resolve(device)
        self.language = language or None
        self.vocabulary = vocabulary
        self.prompt = vocabulary or None
        self.cpu_threads = cpu_threads
        self._models: dict[str, Any] = {}
        self._warmed: set[str] = set()
        self._stop = threading.Event()
        self._last_language = ""

    def _resolve(self, device: str) -> None:
        """Fills in the "auto" choices for `device` ("auto" stays unresolved until the first load)."""
        model, preview, _, compute = self._wanted
        self.device = device
        defaults = AUTO.get(device, AUTO["cpu"])
        self.model = defaults[0] if model == "auto" else model
        self.preview_model = (defaults[1] if preview == "auto" else preview) or self.model
        self.compute_type = defaults[2] if compute == "auto" else compute
        if device == "cpu" and self.compute_type in ("float16", "int8_float16", "bfloat16", "int8_bfloat16"):
            self.compute_type = "int8"  # a GPU setting carried over to the CPU fallback

    def _pick_device(self) -> None:
        if self.device != "auto":
            return
        why = cuda_unavailable()
        if why:
            log.info("local speech on the CPU: %s", why)
        self._resolve("cpu" if why else "cuda")

    def _load(self, name: str):
        if name not in self._models:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise RuntimeError("Local speech needs the desktop extra: uv sync --extra desktop") from e
            self._pick_device()
            if self.device == "cuda" and cuda_unavailable():
                raise RuntimeError(f"[stt.faster_whisper] device = \"cuda\", but {cuda_unavailable()}")
            log.info("loading local speech model %s (%s, %s)", name, self.device, self.compute_type)
            try:
                self._models[name] = WhisperModel(name, device=self.device, compute_type=self.compute_type,
                                                  cpu_threads=self.cpu_threads)
            except Exception:
                if self.device != "cuda" or self._wanted[2] != "auto":
                    raise
                log.warning("the GPU couldn't load %s; local speech goes on the CPU", name, exc_info=True)
                final = name == self.model
                self._fall_back()
                return self._load(self.model if final else self.preview_model)
        return self._models[name]

    def _fall_back(self) -> None:
        self._models.clear()
        self._warmed.clear()
        self._resolve("cpu")

    def warm(self) -> None:
        """Loads both models and runs each once, so the first recording doesn't pay for CUDA's start-up."""
        self._pick_device()
        noise = (np.random.default_rng(0).standard_normal(STT_SAMPLE_RATE // 2) * 0.01).astype(np.float32)
        for name in dict.fromkeys((self.model, self.preview_model)):
            if name in self._warmed:
                continue
            model = self._load(name)
            try:
                segments, _ = model.transcribe(noise, language="en", beam_size=1, vad_filter=False,
                                               without_timestamps=True, condition_on_previous_text=False)
                list(segments)
                self._warmed.add(name)
            except Exception:
                if self.device != "cuda" or self._wanted[2] != "auto":
                    raise
                log.warning("the GPU failed a first pass; local speech goes on the CPU", exc_info=True)
                self._fall_back()
                return self.warm()

    def wake(self) -> None:
        self._stop.clear()

    def interrupt(self) -> None:
        self._stop.set()

    def use_vocabulary(self, words: Sequence[str]) -> None:
        self.prompt = vocabulary_prompt(self.vocabulary, words) or None

    @property
    def heard_language(self) -> str:
        return self._last_language

    def transcribe(self, audio: Audio, before: str = "", *, quick: bool = False) -> str:
        language = self.language
        if language is None and before and len(audio) < 3 * STT_SAMPLE_RATE:
            language = self._last_language or None
        segments, _ = self._run(self.model, audio, language=language, quick=quick)
        return " ".join(s.text.strip() for s in segments).strip()

    def preview(self, audio: Audio) -> str:
        # Live words only: the language the last full pass heard spares a detection pass each time.
        segments, _ = self._run(self.preview_model, audio, language=self.language or self._last_language or None,
                                quick=True)
        return " ".join(s.text.strip() for s in segments).strip()

    def _run(self, name: str, audio: Audio, *, language: str | None = None, quick: bool = False,
             timestamps: bool = False):
        self._stop.clear()
        if is_silent(audio):
            return [], None
        final = name == self.model
        self._pick_device()  # "auto" names resolve with the device
        model = self._load(self.model if final else self.preview_model)
        if self._stop.is_set():
            raise Interrupted()
        segments, info = model.transcribe(np.asarray(audio, dtype=np.float32), language=language,
                                          beam_size=1 if quick else 5, initial_prompt=self.prompt,
                                          condition_on_previous_text=False, word_timestamps=timestamps,
                                          without_timestamps=not timestamps, vad_filter=True)
        kept = []
        for segment in segments:
            if self._stop.is_set():
                raise Interrupted()
            text = segment.text.strip()
            if not text or is_hallucination(text) or segment.compression_ratio > 2.4:
                continue
            if segment.no_speech_prob > 0.6 and segment.avg_logprob < -1.0:
                continue
            kept.append(segment)
        if self._stop.is_set():
            raise Interrupted()
        if final and getattr(info, "language_probability", 0) >= 0.8:
            self._last_language = info.language
        return kept, info

    def words(self, audio: Audio, language: str | None = None) -> list[TimedWord]:
        segments, info = self._run(self.model, audio, language=self.language or language, timestamps=True)
        spoken = getattr(info, "language", self.language or language or "")
        return [TimedWord(float(w.start), float(w.end), w.word, index, spoken)
                for index, segment in enumerate(segments) for w in segment.words or [] if w.word.strip()]

    def spoken_language(self, audio: Audio) -> str:
        if self.language:
            return self.language
        _, info = self._run(self.model, audio, quick=True)
        return info.language if info is not None and info.language_probability >= 0.8 else ""


@TRANSCRIBERS.register("faster_whisper")
def _faster_whisper(options: Mapping[str, Any], ctx: AdapterContext) -> FasterWhisper:
    o = options_from(FasterWhisperOptions, options, "stt.faster_whisper")
    return FasterWhisper(**vars(o))
