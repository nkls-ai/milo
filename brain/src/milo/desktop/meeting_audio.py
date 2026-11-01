"""Meeting capture behind AudioSource: microphone and OS loopback, on dedicated threads.

Both tracks use the existing 16 kHz mono PCM16, 30-second chunk protocol. Native
callbacks never touch widgets; commands are marshalled to Qt's GUI thread.
"""
from __future__ import annotations

import ctypes as C
import ctypes.util
import math
import queue
import sys
import threading
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
from PySide6.QtCore import QObject, Signal

from milo.core.meetings import CHUNK_S
from milo.core.types import STT_SAMPLE_RATE
from ._native_types import NativeError

BLOCK = STT_SAMPLE_RATE // 10


class AudioSource(Protocol):
    def __enter__(self) -> AudioSource: ...
    def read(self) -> np.ndarray: ...
    def __exit__(self, *exc) -> None: ...


class _QueuedSource:
    def __init__(self):
        self._queue: queue.Queue[np.ndarray | Exception] = queue.Queue(maxsize=30)
        self._overflow = False
        self.pause_event = threading.Event()

    def _feed(self, audio: np.ndarray) -> None:
        if self.pause_event.is_set():
            audio = np.zeros_like(audio)
        try:
            self._queue.put_nowait(audio)
        except queue.Full:
            self._overflow = True

    def read(self) -> np.ndarray:
        if self._overflow:
            raise NativeError("Meeting audio fell behind; the recording device could not be read fast enough.")
        try:
            audio = self._queue.get(timeout=0.1)
        except queue.Empty:
            # WASAPI loopback sends no packets while the speaker is silent.
            return np.zeros(BLOCK, dtype=np.float32)
        if isinstance(audio, Exception):
            raise audio
        return audio


class MicrophoneSource(_QueuedSource):
    def __enter__(self):
        import sounddevice as sd
        def receive(data, frames, timing, status):
            if status.input_overflow:
                self._overflow = True
            self._feed(data[:, 0].copy())
        self._stream = sd.InputStream(samplerate=STT_SAMPLE_RATE, channels=1, dtype="float32",
                                      blocksize=BLOCK, callback=receive)
        self._stream.start()
        return self

    def __exit__(self, *exc):
        self._stream.stop()
        self._stream.close()


class WasapiLoopbackSource(_QueuedSource):
    def __enter__(self):
        import pyaudiowpatch as pa
        from scipy.signal import resample_poly

        self._manager = pa.PyAudio()
        try:
            device = self._manager.get_default_wasapi_loopback()
            rate = round(device["defaultSampleRate"])
            channels = max(1, int(device["maxInputChannels"]))
            divisor = math.gcd(rate, STT_SAMPLE_RATE)
            def receive(data, frames, timing, status):
                if status:
                    self._overflow = True
                audio = np.frombuffer(data, dtype="<f4").reshape(-1, channels).mean(axis=1)
                if rate != STT_SAMPLE_RATE:
                    audio = resample_poly(audio, STT_SAMPLE_RATE // divisor, rate // divisor).astype(np.float32)
                self._feed(audio)
                return None, pa.paContinue
            self._stream = self._manager.open(format=pa.paFloat32, channels=channels, rate=rate,
                input=True, input_device_index=int(device["index"]), frames_per_buffer=rate // 10,
                stream_callback=receive)
            return self
        except BaseException:
            self._manager.terminate()
            raise

    def __exit__(self, *exc):
        try:
            self._stream.stop_stream()
            self._stream.close()
        finally:
            self._manager.terminate()


class _SampleSpec(C.Structure):
    _fields_ = [("format", C.c_int), ("rate", C.c_uint32), ("channels", C.c_uint8)]


class _BufferAttr(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in ("maxlength", "tlength", "prebuf", "minreq", "fragsize")]


class PulseMonitorSource:
    def __enter__(self):
        path = ctypes.util.find_library("pulse-simple")
        if not path:
            raise NativeError("System audio needs libpulse-simple (PulseAudio or PipeWire's PulseAudio service).")
        self._lib = C.CDLL(path)
        p, s, i = C.c_void_p, C.c_char_p, C.c_int
        self._lib.pa_simple_new.restype = p
        self._lib.pa_simple_new.argtypes = [s, s, i, s, s, C.POINTER(_SampleSpec), p,
                                           C.POINTER(_BufferAttr), C.POINTER(i)]
        self._lib.pa_simple_read.argtypes = [p, p, C.c_size_t, C.POINTER(i)]
        self._lib.pa_simple_read.restype = i
        self._lib.pa_simple_free.argtypes = [p]
        spec = _SampleSpec(5, STT_SAMPLE_RATE, 1)  # PA_SAMPLE_FLOAT32LE
        attributes = _BufferAttr(0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, BLOCK * 4)
        error = i()
        self._handle = self._lib.pa_simple_new(None, b"Milo", 2, b"@DEFAULT_MONITOR@", b"Meeting audio",
                                              C.byref(spec), None, C.byref(attributes), C.byref(error))
        if not self._handle:
            raise NativeError(f"The default speaker monitor could not be opened (PulseAudio error {error.value}).")
        return self

    def read(self) -> np.ndarray:
        audio = np.empty(BLOCK, dtype="<f4")
        error = C.c_int()
        if self._lib.pa_simple_read(self._handle, audio.ctypes.data, audio.nbytes, C.byref(error)) < 0:
            raise NativeError(f"The speaker monitor stopped (PulseAudio error {error.value}).")
        return audio

    def __exit__(self, *exc):
        self._lib.pa_simple_free(self._handle)


def source_for(track: str) -> AudioSource:
    if track == "me":
        return MicrophoneSource()
    if sys.platform == "win32":
        return WasapiLoopbackSource()
    if sys.platform.startswith("linux"):
        return PulseMonitorSource()
    raise NativeError("Use the native macOS app for meeting audio on this platform.")


class ChunkWriter:
    """Writes bounded chunks as they arrive, retaining valid WAV headers after each block."""
    def __init__(self, directory: Path, meeting_id: str, track: str, send: Callable[[dict], None],
                 *, chunk_s: float = CHUNK_S):
        self.directory, self.id, self.track, self.send = directory, meeting_id, track, send
        self.chunk_frames = round(chunk_s * STT_SAMPLE_RATE)
        self.index, self.frames, self.total = 0, 0, 0
        self._file = None
        self._wave = None
        directory.mkdir(parents=True, exist_ok=True)
        from milo import system
        system.make_private(directory, 0o700)
        existing = [int(path.stem.split("-")[-1]) for path in directory.glob(f"{track}-*.wav")
                    if path.stem.split("-")[-1].isdigit()]
        self.index = max(existing, default=0)
        self.total = self.index * self.chunk_frames

    def write(self, audio: np.ndarray) -> None:
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        offset = 0
        while offset < len(samples):
            if self._wave is None:
                self.index += 1
                self.path = self.directory / f"{self.track}-{self.index:04d}.wav"
                self._file = self.path.open("xb")
                self._wave = wave.open(self._file, "wb")
                self._wave.setnchannels(1)
                self._wave.setsampwidth(2)
                self._wave.setframerate(STT_SAMPLE_RATE)
            count = min(len(samples) - offset, self.chunk_frames - self.frames)
            pcm = (np.clip(samples[offset:offset + count], -1, 1) * 32767).astype("<i2").tobytes()
            self._wave.writeframes(pcm)
            self._file.flush()
            self.frames += count
            self.total += count
            offset += count
            if self.frames == self.chunk_frames:
                self.finish()

    def finish(self) -> None:
        if self._wave is None:
            return
        self._wave.close()
        self._file.close()
        self._wave, self._file = None, None
        self.send({"type": "meeting_chunk", "id": self.id, "track": self.track, "index": self.index,
                   "path": str(self.path), "start": (self.total - self.frames) / STT_SAMPLE_RATE,
                   "seconds": self.frames / STT_SAMPLE_RATE})
        self.frames = 0


@dataclass
class _Session:
    id: str
    directory: Path
    began: float = field(default_factory=time.monotonic)
    stop: threading.Event = field(default_factory=threading.Event)
    paused: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    pending: int = 2
    live: set[str] = field(default_factory=set)
    errors: dict[str, str] = field(default_factory=dict)
    threads: list[threading.Thread] = field(default_factory=list)
    redaction_epoch: int = 0


class MeetingRecorder(QObject):
    command = Signal(dict)

    def __init__(self, home: Path, send: Callable[[dict], None], *, sources=source_for, parent=None):
        super().__init__(parent)
        self.home, self._sources = home.resolve(), sources
        self.command.connect(send)
        self._session: _Session | None = None

    def record(self, event: dict) -> None:
        meeting_id = str(event.get("id", ""))
        if not event.get("on"):
            if self._session and (not meeting_id or meeting_id == self._session.id):
                self._session.stop.set()
            else:
                self.command.emit({"type": "meeting_recording", "id": meeting_id, "on": False,
                                   "tracks": [], "error": ""})
            return
        if self._session and not self._session.stop.is_set():
            if meeting_id == self._session.id:
                self._report(self._session)
                return
            self._session.stop.set()
        directory = Path(str(event.get("dir", ""))).resolve()
        if not meeting_id or not directory.is_relative_to(self.home / "meetings"):
            self.command.emit({"type": "meeting_recording", "id": meeting_id, "on": False, "tracks": [],
                               "error": "The recording folder must be inside Milo's meetings folder."})
            return
        session = _Session(meeting_id, directory)
        self._session = session
        for track in ("me", "them"):
            thread = threading.Thread(target=self._track, args=(session, track),
                                      name=f"meeting-{track}", daemon=True)
            session.threads.append(thread)
            thread.start()

    def pause(self, on: bool) -> None:
        if self._session:
            self._session.redaction_epoch += 1
            self._session.paused.set() if on else self._session.paused.clear()

    def _report(self, session: _Session) -> None:
        with session.lock:
            if session.pending:
                return
            tracks = sorted(session.live)
            errors = " ".join(session.errors[track] for track in ("me", "them") if track in session.errors)
        self.command.emit({"type": "meeting_recording", "id": session.id, "on": bool(tracks),
                           "tracks": tracks, "error": errors})

    def _track(self, session: _Session, track: str) -> None:
        writer = None
        started = False
        try:
            writer = ChunkWriter(session.directory, session.id, track, self.command.emit)
            source = self._sources(track)
            # Callback sources redact at capture time too, so queued audio from a
            # paused period cannot reappear when the user resumes the notes.
            if hasattr(source, "pause_event"):
                source.pause_event = session.paused
            with source:
                with session.lock:
                    session.live.add(track)
                    session.pending -= 1
                    started = True
                self._report(session)
                # Both tracks begin on the same clock, even if one device opens slowly.
                elapsed = min(10.0, max(0.0, time.monotonic() - session.began))
                writer.write(np.zeros(round(elapsed * STT_SAMPLE_RATE), dtype=np.float32))
                while not session.stop.is_set():
                    epoch = session.redaction_epoch
                    audio = source.read()
                    private = session.paused.is_set() or epoch != session.redaction_epoch
                    writer.write(np.zeros_like(audio) if private else audio)
        except Exception as e:
            with session.lock:
                label = "The microphone" if track == "me" else "The call's system audio"
                session.errors[track] = f"{label} could not be recorded: {e}"
                if not started:
                    session.pending -= 1
            self._report(session)
        finally:
            try:
                if writer is not None:
                    writer.finish()
            except Exception as e:
                with session.lock:
                    session.errors[track] = f"The final {track} audio chunk could not be saved: {e}"
            with session.lock:
                session.live.discard(track)
            self._report(session)

    def close(self) -> None:
        if self._session:
            self._session.stop.set()
            # Native audio reads run in daemon threads. Never hold the GUI up on a
            # disconnected device; normal 100ms reads finish and flush promptly.
            deadline = time.monotonic() + 0.3
            for thread in self._session.threads:
                thread.join(timeout=max(0.0, deadline - time.monotonic()))
