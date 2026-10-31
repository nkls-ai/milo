"""k2-fsa OmniVoice, a local zero-shot neural TTS. Needs the `omnivoice` extra; imported only on warm().

Milo always speaks with one cloned voice. Voice-design mode (`instruct`) samples a new speaker on
every call, so a reply split into chunks would switch voices mid-sentence. Instead the voice is
designed once from `instruct` + `voice_seed`, saved to <state>/voice/ref.wav, and every utterance
clones it. A short reference keeps cloning fast: ~2 s runs at 0.55-0.85x real time on an M3 at 8
steps, a 6 s one at ~2.8x.
"""

from __future__ import annotations

import io
import logging
import os
import wave
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from milo.core.registry import VOICES, AdapterContext, ConfigError, options_from
from milo.core.types import Audio

log = logging.getLogger(__name__)

MODEL = "k2-fsa/OmniVoice"
REF_TEXT = "Hi, I'm Milo. Happy to help!"  # ~2 s: long enough to carry the voice, short enough to stay fast
DESIGN_STEPS = 32  # the reference is made once, so it gets full quality
WARM_UP_TEXT = "Okay."


class SynthesisCancelled(Exception):
    """cancel() stopped a synthesis between diffusion steps."""


@dataclass(frozen=True)
class OmniVoiceOptions:
    device: str = ""  # empty: the GPU torch finds (mps, cuda), else cpu
    instruct: str = "male, young adult, high pitch"  # used once, to design the voice
    voice_seed: int = 7
    ref_audio: str = ""  # a clip to clone instead of the designed voice
    ref_text: str = ""  # its transcript; empty: OmniVoice's ASR transcribes it
    steps: int = 6  # 5 starts dropping words, 8 is no clearer and ~25% slower


def pick_device(torch) -> str:
    """The torch device for an empty `device`: Apple's GPU, then an NVIDIA one, then the CPU."""
    if torch.backends.mps.is_available():
        return "mps"
    return "cuda" if torch.cuda.is_available() else "cpu"


class OmniVoiceTTS:
    sample_rate = 24_000

    def __init__(self, voice_dir: Path, *, device: str = "", instruct: str = "male, young adult, high pitch",
                 voice_seed: int = 7, ref_audio: str = "", ref_text: str = "", steps: int = 6):
        self.voice_dir = voice_dir
        self.device = device
        self.instruct = instruct
        self.voice_seed = voice_seed
        self.ref_audio = ref_audio
        self.ref_text = ref_text
        self.steps = steps
        self._model = None
        self._clone_prompt = None
        self._started = 0  # id of the latest synthesize() call
        self._running = 0  # id of the call on the TTS thread right now, 0 if idle
        self._cancel_upto = 0  # calls with an id up to this one abort at their next step

    def warm(self) -> None:
        if self._model is not None:
            return
        import torch
        from omnivoice import OmniVoice

        self.device = self.device or pick_device(torch)
        log.info("loading OmniVoice on %s", self.device)
        dtype = torch.float16 if self.device == "mps" else torch.float32
        try:
            model = OmniVoice.from_pretrained(MODEL, device_map=self.device, dtype=dtype)
        finally:
            logging.disable(logging.NOTSET)  # OmniVoice disables INFO logging process-wide while loading
        # generate() runs the model once per diffusion step; checking before each run makes cancel() take
        # effect within one step (~0.1-0.4 s) instead of after the whole piece.
        model.register_forward_pre_hook(self._abort_if_cancelled)
        audio_path, text = self._reference(model, torch)
        log.info("cloning voice from %s", audio_path)
        prompt = model.create_voice_clone_prompt(ref_audio=str(audio_path), ref_text=text)
        if self.device == "mps" and hasattr(prompt, "ref_audio_tokens"):
            from ._gpu_decode import decode_on_gpu

            decode_on_gpu(model, prompt.ref_audio_tokens, torch, self.device)
        model.generate(text=WARM_UP_TEXT, voice_clone_prompt=prompt, num_step=self.steps)
        self._model, self._clone_prompt = model, prompt
        log.info("tts ready")

    def synthesize(self, text: str) -> Audio:
        self.warm()
        self._started += 1
        self._running = self._started
        try:
            audio = self._model.generate(text=text, voice_clone_prompt=self._clone_prompt, num_step=self.steps)[0]
        finally:
            self._running = 0
        return np.asarray(audio, dtype=np.float32).reshape(-1)

    def cancel(self) -> None:
        self._cancel_upto = self._started

    def _abort_if_cancelled(self, module, args) -> None:
        if self._running and self._running <= self._cancel_upto:
            raise SynthesisCancelled(f"synthesis {self._running} cancelled")

    def _reference(self, model, torch) -> tuple[Path, str | None]:
        """The clip to clone and its transcript (None: let OmniVoice transcribe it)."""
        if self.ref_audio:
            path = Path(self.ref_audio).expanduser()
            if not path.is_file():
                raise ConfigError(f"[tts.omnivoice] ref_audio not found: {path}")
            return path, self.ref_text.strip() or None
        wav, txt = self.voice_dir / "ref.wav", self.voice_dir / "ref.txt"
        if wav.is_file() and txt.is_file():
            return wav, txt.read_text(encoding="utf-8").strip() or None
        log.info("designing Milo's voice (%r, seed %d)", self.instruct, self.voice_seed)
        torch.manual_seed(self.voice_seed)
        audio = model.generate(text=REF_TEXT, instruct=self.instruct, num_step=DESIGN_STEPS)[0]
        self.voice_dir.mkdir(parents=True, exist_ok=True)
        _write_atomic(txt, (REF_TEXT + "\n").encode())
        _write_atomic(wav, _wav_bytes(np.asarray(audio, dtype=np.float32).reshape(-1), self.sample_rate))
        log.info("saved voice to %s; delete that folder to design a new one", self.voice_dir)
        return wav, REF_TEXT


def _wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


@VOICES.register("omnivoice")
def _omnivoice(options: Mapping[str, Any], ctx: AdapterContext) -> OmniVoiceTTS:
    o = options_from(OmniVoiceOptions, options, "tts.omnivoice")
    return OmniVoiceTTS(ctx.state_dir / "voice", device=o.device, instruct=o.instruct, voice_seed=o.voice_seed,
                        ref_audio=o.ref_audio, ref_text=o.ref_text, steps=o.steps)
