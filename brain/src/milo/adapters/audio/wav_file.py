"""`[audio] use = "wav"`: Milo speaks into WAV files instead of the speakers, in real time.

The output plays at the speed a sound card would: audio fed late leaves silence, drain() waits until the
last sample "played", and interrupt() cuts at that moment. So the file is what the user would have heard,
gaps included, and timing tests and voice comparisons run without a sound ever reaching the room. The
input plays a WAV file as the microphone, from its start each time recording starts (silence when unset);
a test that writes a new file there before a recording gets it heard. If the test also writes when the key
went down (`<mic>.json`, {"pressed_at": epoch seconds}), the file plays from that moment: a mic that opens
late misses the first words, as a real one would.
"""

from __future__ import annotations

import asyncio
import io
import itertools
import json
import threading
import time
import wave
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from milo.core.ports import LevelCallback
from milo.core.registry import AUDIO_INPUTS, AUDIO_OUTPUTS, AdapterContext, options_from
from milo.core.types import STT_SAMPLE_RATE, Audio

from .sounddevice_io import level_of


@dataclass(frozen=True)
class WavOptions:
    """Shared by input and output: both factories get the whole [audio.wav] table."""

    dir: str = ""  # where each utterance is written; empty: <state>/speech
    mic: str = ""  # a 16 kHz mono WAV the microphone "hears"; empty: silence


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    path.write_bytes(buf.getvalue())


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: only 16-bit WAV files")
        pcm = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
        return pcm.reshape(-1, w.getnchannels())[:, 0], w.getframerate()


class WavPlayer:
    """An AudioOutput on a virtual sound card. Each utterance becomes `NNN.wav` plus `NNN.json` with its timings:
    when each piece was fed and where it landed, in seconds from begin()."""

    def __init__(self, directory: Path, clock=time.monotonic):
        self.directory = directory
        self._clock = clock
        self._numbers = itertools.count(1)
        self._lock = threading.Lock()
        self._current: dict | None = None
        self.written: list[Path] = []

    def played(self, since: float) -> tuple[int, list[tuple[float, Audio]]]:
        """PlaybackTap: the pieces of the open utterance, at the times they "reach the speaker"."""
        with self._lock:
            u = self._current
            if u is None:
                return 24_000, []
            now = self._played(u)
            blocks = []
            for p in u["pieces"]:
                start = int(round(p["start_s"] * u["rate"]))
                audio = p["audio"][:max(0, now - start)]
                t = u["t0"] + p["start_s"]
                if len(audio) and t + len(audio) / u["rate"] > since:
                    blocks.append((t, audio))
            return u["rate"], blocks

    def begin(self, sample_rate: int, on_level: LevelCallback) -> None:
        if self._current is not None:
            self.interrupt()
        self._current = {"rate": sample_rate, "t0": self._clock(), "pieces": [], "end": 0, "on_level": on_level,
                         "done": asyncio.Event(), "loop": asyncio.get_running_loop()}

    def feed(self, audio: Audio) -> None:
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        with self._lock:
            u = self._current
            if u is None or not len(samples):
                return
            now = self._played(u)
            start = max(now, u["end"])
            u["pieces"].append({"fed_s": now / u["rate"], "start_s": start / u["rate"], "audio": samples})
            u["end"] = start + len(samples)
        u["on_level"](level_of(samples))

    async def drain(self) -> bool:
        u = self._current
        if u is None:
            return True
        remaining = (u["end"] - self._played(u)) / u["rate"]
        if remaining > 0:
            try:
                await asyncio.wait_for(u["done"].wait(), remaining)
            except TimeoutError:
                pass
        if self._current is u:
            self._finish(u, interrupted=False)
        return not u.get("interrupted", False)

    def interrupt(self) -> None:
        u = self._current
        if u is None:
            return
        self._finish(u, interrupted=True)
        u["loop"].call_soon_threadsafe(u["done"].set)

    def _played(self, u: dict) -> int:
        return int((self._clock() - u["t0"]) * u["rate"])

    def _finish(self, u: dict, *, interrupted: bool) -> None:
        with self._lock:
            if self._current is not u:
                return
            self._current = None
            u["interrupted"] = interrupted
            end = min(u["end"], self._played(u)) if interrupted else u["end"]
        track = np.zeros(end, dtype=np.float32)
        for p in u["pieces"]:
            start = int(round(p["start_s"] * u["rate"]))
            if start < end:
                take = min(len(p["audio"]), end - start)
                track[start:start + take] = p["audio"][:take]
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{next(self._numbers):03d}.wav"
        write_wav(path, track, u["rate"])
        meta = {"interrupted": interrupted, "seconds": end / u["rate"],
                "pieces": [{k: round(v, 3) for k, v in p.items() if k != "audio"} | {"seconds": len(p["audio"]) / u["rate"]}
                           for p in u["pieces"]]}
        path.with_suffix(".json").write_text(json.dumps(meta, indent=1))
        self.written.append(path)
        u["on_level"](0.0)


class WavMicrophone:
    """An AudioInput that hears a WAV file, in real time from the moment recording starts. The file is read
    again when it changed since the last recording."""

    def __init__(self, path: Path | None, clock=time.monotonic):
        self._clock = clock
        self._path = path
        self._stamp: tuple[int, int] | None = None
        self._audio = np.zeros(0, dtype=np.float32)
        self._load()
        self._started: float | None = None
        self._skip = 0  # samples of the file said before the mic opened

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        stat = self._path.stat()
        if (stat.st_mtime_ns, stat.st_size) == self._stamp:
            return
        audio, rate = read_wav(self._path)
        if rate != STT_SAMPLE_RATE:
            raise ValueError(f"{self._path}: the microphone needs {STT_SAMPLE_RATE} Hz, not {rate}")
        self._audio, self._stamp = audio, (stat.st_mtime_ns, stat.st_size)

    @property
    def active(self) -> bool:
        return self._started is not None

    @property
    def started_at(self) -> float | None:
        return self._started

    def start(self, on_level: LevelCallback) -> None:
        if self._started is None:
            self._load()
            self._skip = int(self._late() * STT_SAMPLE_RATE)
            self._started = self._clock()

    def _late(self) -> float:
        """How long ago the key went down, if the test said so: that much of the file was said already."""
        marker = self._path.with_suffix(".json") if self._path is not None else None
        if marker is None or not marker.exists():
            return 0.0
        try:
            late = time.time() - float(json.loads(marker.read_text(encoding="utf-8"))["pressed_at"])
        except (ValueError, KeyError, TypeError):
            return 0.0
        return late if 0 < late < 60 else 0.0

    def stop(self) -> Audio:
        audio = self.peek()
        self._started = None
        return audio

    def peek(self, start: int = 0) -> Audio:
        if self._started is None:
            return np.zeros(0, dtype=np.float32)
        heard = int((self._clock() - self._started) * STT_SAMPLE_RATE)
        audio = self._audio[self._skip:self._skip + heard]
        if heard > len(audio):
            audio = np.concatenate([audio, np.zeros(heard - len(audio), dtype=np.float32)])
        return audio[start:].copy()


def _options(options: Mapping[str, Any]) -> WavOptions:
    return options_from(WavOptions, options, "audio.wav")


@AUDIO_OUTPUTS.register("wav")
def _output(options: Mapping[str, Any], ctx: AdapterContext) -> WavPlayer:
    o = _options(options)
    return WavPlayer(Path(o.dir).expanduser() if o.dir else ctx.state_dir / "speech")


@AUDIO_INPUTS.register("wav")
def _input(options: Mapping[str, Any], ctx: AdapterContext) -> WavMicrophone:
    o = _options(options)
    return WavMicrophone(Path(o.mic).expanduser() if o.mic else None)
