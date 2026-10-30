"""OmniVoice's audio decoder on the GPU, in pieces short enough for MPS to get right.

OmniVoice leaves its 200M-parameter audio decoder on the CPU, where turning a piece's audio tokens into a
waveform took 0.3 to 1.1 s of every piece (measured on an M3, 2026-10-30). On MPS the same decoder is about
twice as fast, but its output is garbage once a call produces more than 65,536 samples (2.7 s): that is the
longest convolution MPS computes correctly. So the tokens are decoded in windows of FRAMES frames with CONTEXT
frames of overlap on each side, and only each window's middle is kept, which matches the CPU's output to within
-110 dB. A self-check at load time compares the two, and keeps the CPU if they differ.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import numpy as np

log = logging.getLogger(__name__)

FRAMES = 40
CONTEXT = 12  # (FRAMES + 2 * CONTEXT) * 960 samples per frame stays under MPS's 65,536
CHECK_FRAMES = 70  # long enough to cross window edges
MAX_ERROR_DB = -40.0


class WindowedDecoder:
    def __init__(self, decode, torch, samples_per_frame: int):
        self._decode = decode
        self._torch = torch
        self._spf = samples_per_frame

    def __call__(self, codes):
        """codes: [1, codebooks, frames] on the decoder's device. Returns what the decoder returns, on the CPU."""
        torch, spf = self._torch, self._spf
        frames = codes.shape[-1]
        parts = []
        with torch.inference_mode():
            for start in range(0, frames, FRAMES):
                lo, hi = max(0, start - CONTEXT), min(frames, start + FRAMES + CONTEXT)
                audio = self._decode(codes[..., lo:hi]).audio_values
                keep = (min(start + FRAMES, frames) - start) * spf
                parts.append(audio[..., (start - lo) * spf:(start - lo) * spf + keep].float().cpu())
        return SimpleNamespace(audio_values=torch.cat(parts, dim=-1))


def decode_on_gpu(model, sample_codes, torch, device: str) -> bool:
    """Move the decoder to `device` and decode in windows there, if it gives the CPU's waveform. True if it does.

    `sample_codes` is [codebooks, frames] of real audio tokens (the voice reference), repeated as needed.
    """
    tokenizer = getattr(model, "audio_tokenizer", None)
    if tokenizer is None:
        return False
    original = tokenizer.decode
    codes = sample_codes
    while codes.shape[-1] < CHECK_FRAMES:
        codes = torch.cat([codes, sample_codes], dim=-1)
    codes = codes[..., :CHECK_FRAMES].unsqueeze(0)
    try:
        with torch.inference_mode():
            want = original(codes.to(tokenizer.device)).audio_values.float().cpu().numpy().reshape(-1)
            tokenizer.to(device)
            windowed = WindowedDecoder(original, torch, len(want) // CHECK_FRAMES)
            got = windowed(codes.to(device)).audio_values.numpy().reshape(-1)
        n = min(len(want), len(got))
        error_db = 10 * np.log10(np.mean((want[:n] - got[:n]) ** 2) / (np.mean(want[:n] ** 2) + 1e-12) + 1e-12)
    except Exception:
        log.exception("decoding audio on %s failed; staying on the CPU", device)
        tokenizer.to("cpu")
        return False
    if len(want) != len(got) or error_db > MAX_ERROR_DB:
        log.warning("decoding audio on %s differs from the CPU (%.0f dB); staying on the CPU", device, error_db)
        tokenizer.to("cpu")
        return False
    tokenizer.decode = windowed
    log.info("decoding audio on %s (matches the CPU to %.0f dB)", device, error_db)
    return True
