"""Microphone capture and playback through PortAudio (sounddevice), with loudness levels for the character.

sounddevice is imported inside methods so loading the adapters never touches PortAudio.
"""

from __future__ import annotations

import asyncio
import threading
import time as _time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from milo.core.ports import LevelCallback
from milo.core.registry import AUDIO_INPUTS, AUDIO_OUTPUTS, AdapterContext, options_from
from milo.core.types import STT_SAMPLE_RATE, Audio

BLOCK = 1024
MIC_BLOCK = 512  # 32 ms: the level meter moves ~30 times a second, evenly, instead of in 64 ms steps


@dataclass(frozen=True)
class SounddeviceOptions:
    """Shared by input and output: both factories get the whole [audio.sounddevice] table."""

    input_device: str | int = ""  # name (or substring) or index; empty: system default
    output_device: str | int = ""


def level_of(chunk: np.ndarray) -> float:
    """Map a chunk's RMS to 0..1 for animation."""
    rms = float(np.sqrt(np.mean(np.square(chunk)))) if len(chunk) else 0.0
    return min(1.0, rms * 12)


def _device(value: str | int) -> str | int | None:
    return None if value == "" else value


class Recorder:
    """Opens the mic only while recording, so the macOS mic indicator means what it says."""

    def __init__(self, device: str | int | None = None):
        self.device = device
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self.started_at: float | None = None
        """When the first recorded sample was heard, on the monotonic clock. None until the first block."""

    @property
    def active(self) -> bool:
        return self._stream is not None

    def warm(self) -> None:
        """Start PortAudio and find the input device now, at brain start, without opening the mic. The first key
        press otherwise paid for both (about 0.1 s on Windows) and lost the first syllable."""
        import sounddevice as sd
        sd.query_devices(self.device, "input") if self.device is not None else sd.query_devices(kind="input")

    def start(self, on_level: LevelCallback) -> None:
        if self._stream is not None:
            return
        import sounddevice as sd

        self._chunks = []
        self.started_at = None

        def callback(indata, frames, time, status):
            mono = indata[:, 0].copy()
            if self.started_at is None:
                self.started_at = _heard_at(time, frames, STT_SAMPLE_RATE)
            self._chunks.append(mono)
            on_level(level_of(mono))

        stream = sd.InputStream(samplerate=STT_SAMPLE_RATE, channels=1, dtype="float32", blocksize=MIC_BLOCK,
                                latency="low", device=self.device, callback=callback)
        stream.start()
        self._stream = stream

    def stop(self) -> Audio:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)
        self._chunks = []
        return audio

    def peek(self, start: int = 0) -> Audio:
        return tail_of(self._chunks[:], start)  # a shallow copy: the audio thread only ever appends


def _heard_at(time, frames: int, rate: int) -> float:
    """The capture time of a block's first sample. PortAudio's stream clock on macOS is the host clock that
    time.monotonic() reads too; without it, the block ended about now."""
    adc = getattr(time, "inputBufferAdcTime", 0.0) or 0.0
    return adc if adc > 0 else _time.monotonic() - frames / rate


def _played_at(time, latency: float) -> float:
    dac = getattr(time, "outputBufferDacTime", 0.0) or 0.0
    return dac if dac > 0 else _time.monotonic() + latency


PLAYED_KEPT_S = 3.0  # how much played audio the tap remembers


def tail_of(chunks: list[np.ndarray], start: int) -> Audio:
    """The samples from index `start` on, of the chunks laid end to end. Copies only the chunks it needs."""
    end = sum(len(c) for c in chunks)
    picked: list[np.ndarray] = []
    for chunk in reversed(chunks):
        if end <= start:
            break
        end -= len(chunk)
        picked.append(chunk)
    if not picked:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(picked[::-1])[max(0, start - end):]


class _Stream:
    """One utterance: the PortAudio stream and the audio queued for it. Shared with the audio thread."""

    def __init__(self, loop: asyncio.AbstractEventLoop, on_level: LevelCallback):
        self.loop = loop
        self.on_level = on_level
        self.lock = threading.Lock()
        self.chunks: deque[np.ndarray] = deque()
        self.offset = 0  # samples of chunks[0] already played
        self.ended = False  # drain() was called: no more audio will be fed
        self.tail = 0  # silent samples still to play after the last audio, while the device catches up
        self.interrupted = False
        self.done = asyncio.Event()
        self.sd_stream = None
        self.latency = 0.0

    def fill(self, out: np.ndarray) -> bool:
        """Copy queued audio into `out`, zero-padding an underrun. True once everything has been handed over."""
        n, filled = len(out), 0
        with self.lock:
            while filled < n and self.chunks:
                chunk = self.chunks[0]
                take = min(n - filled, len(chunk) - self.offset)
                out[filled:filled + take] = chunk[self.offset:self.offset + take]
                filled += take
                self.offset += take
                if self.offset == len(chunk):
                    self.chunks.popleft()
                    self.offset = 0
            finished = self.ended and not self.chunks
            if finished and self.tail > 0:
                self.tail -= n - filled
                finished = self.tail <= 0
        out[filled:] = 0
        return finished

    def wake(self) -> None:
        # Must return None: sounddevice chokes on the Handle call_soon_threadsafe returns.
        self.loop.call_soon_threadsafe(self.done.set)

    def close(self) -> None:
        sd_stream, self.sd_stream = self.sd_stream, None
        if sd_stream is not None:
            sd_stream.close()  # discards pending buffers if still running, like abort()


class Player:
    """One OutputStream per utterance; chunks are fed while earlier ones play, so speech flows without gaps.

    The stream plays silence on underrun instead of stopping, because the next chunk may still be
    synthesizing. interrupt() cuts it off when the user starts talking. After the last chunk it plays the
    device's reported output latency in silence before it stops: PortAudio counts audio as played once it
    left its own buffers, and closing then would cut the end of the last word on a slow device, such as
    Bluetooth headphones.
    """

    def __init__(self, device: str | int | None = None):
        self.device = device
        self._current: _Stream | None = None
        self._rate = 24_000
        self._played: deque[tuple[float, np.ndarray]] = deque()
        self._played_lock = threading.Lock()

    def played(self, since: float) -> tuple[int, list[tuple[float, Audio]]]:
        """PlaybackTap: what reached the speaker from `since` on, block by block."""
        with self._played_lock:
            return self._rate, [(t, block) for t, block in self._played if t + len(block) / self._rate > since]

    def _remember(self, at: float, block: np.ndarray, rate: int) -> None:
        with self._played_lock:
            if rate != self._rate:
                self._played.clear()
                self._rate = rate
            self._played.append((at, block.copy()))
            while self._played and self._played[0][0] < at - PLAYED_KEPT_S:
                self._played.popleft()

    def begin(self, sample_rate: int, on_level: LevelCallback) -> None:
        import sounddevice as sd

        if self._current is not None:
            self.interrupt()
        stream = _Stream(asyncio.get_running_loop(), on_level)

        def callback(outdata, frames, time, status):
            mono = outdata[:, 0]
            finished = stream.fill(mono)
            self._remember(_played_at(time, stream.latency), mono, sample_rate)
            on_level(level_of(mono))
            if finished:
                raise sd.CallbackStop  # PortAudio plays out its buffers, then calls finished_callback

        stream.sd_stream = sd.OutputStream(samplerate=sample_rate, channels=1, dtype="float32", blocksize=BLOCK,
                                           device=self.device, callback=callback, finished_callback=stream.wake)
        stream.latency = float(getattr(stream.sd_stream, "latency", 0.0) or 0.0)
        stream.tail = int(stream.latency * sample_rate)
        self._current = stream
        stream.sd_stream.start()

    def feed(self, audio: Audio) -> None:
        stream = self._current
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if stream is None or not len(samples):
            return
        with stream.lock:
            if not stream.interrupted and not stream.ended:
                stream.chunks.append(samples)

    async def drain(self) -> bool:
        stream = self._current
        if stream is None:
            return True
        with stream.lock:
            stream.ended = True
        await stream.done.wait()
        if self._current is stream:
            self._current = None
        stream.close()
        stream.on_level(0.0)
        return not stream.interrupted

    def interrupt(self) -> None:
        stream = self._current
        if stream is None or stream.interrupted:
            return
        with stream.lock:  # released before close(): closing waits for the callback, which takes the lock
            stream.interrupted = True
            stream.chunks.clear()
        stream.close()
        stream.wake()
        stream.on_level(0.0)


@AUDIO_INPUTS.register("sounddevice")
def _input(options: Mapping[str, Any], ctx: AdapterContext) -> Recorder:
    return Recorder(_device(options_from(SounddeviceOptions, options, "audio.sounddevice").input_device))


@AUDIO_OUTPUTS.register("sounddevice")
def _output(options: Mapping[str, Any], ctx: AdapterContext) -> Player:
    return Player(_device(options_from(SounddeviceOptions, options, "audio.sounddevice").output_device))
