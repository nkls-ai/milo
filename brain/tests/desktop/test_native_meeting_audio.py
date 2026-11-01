import threading
import time
import wave
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from milo.core.types import STT_SAMPLE_RATE
from milo.desktop.meeting_audio import BLOCK, ChunkWriter, MeetingRecorder, _QueuedSource


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def wait_for(app, predicate, timeout=2):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    assert predicate()


def test_chunk_writer_keeps_exact_boundaries_and_final_partial_chunk(tmp_path):
    events = []
    writer = ChunkWriter(tmp_path, "meeting", "me", events.append, chunk_s=0.2)
    writer.write(np.full(7200, 0.25, dtype=np.float32))
    writer.finish()
    assert [(e["index"], e["start"], e["seconds"]) for e in events] == [(1, 0, 0.2), (2, 0.2, 0.2), (3, 0.4, 0.05)]
    for event in events:
        with wave.open(event["path"], "rb") as audio:
            assert audio.getframerate() == STT_SAMPLE_RATE
            assert audio.getnchannels() == 1 and audio.getsampwidth() == 2
            assert audio.getnframes() == round(event["seconds"] * STT_SAMPLE_RATE)


def test_chunk_writer_resumes_without_overwriting_prior_audio(tmp_path):
    events = []
    writer = ChunkWriter(tmp_path, "meeting", "me", events.append, chunk_s=0.2)
    writer.write(np.ones(100, dtype=np.float32))
    writer.finish()
    original = (tmp_path / "me-0001.wav").read_bytes()
    resumed = ChunkWriter(tmp_path, "meeting", "me", events.append, chunk_s=0.2)
    resumed.write(np.zeros(100, dtype=np.float32))
    resumed.finish()
    assert events[-1]["index"] == 2 and events[-1]["start"] == 0.2
    assert (tmp_path / "me-0001.wav").read_bytes() == original


class Source:
    def __enter__(self):
        return self

    def read(self):
        time.sleep(0.02)
        return np.full(BLOCK, 0.25, dtype=np.float32)

    def __exit__(self, *exc):
        pass


def start(recorder, tmp_path):
    directory = tmp_path / "meetings" / "test" / "audio"
    recorder.record({"id": "test", "dir": str(directory), "on": True})
    return directory


def test_recorder_reports_both_tracks_and_flushes_before_stopped(app, tmp_path):
    events = []
    recorder = MeetingRecorder(tmp_path, events.append, sources=lambda _: Source())
    start(recorder, tmp_path)
    wait_for(app, lambda: any(e["type"] == "meeting_recording" and e["tracks"] == ["me", "them"] for e in events))
    time.sleep(0.06)
    recorder.record({"id": "test", "on": False})
    wait_for(app, lambda: events and events[-1]["type"] == "meeting_recording" and not events[-1]["on"])
    chunks = [e for e in events if e["type"] == "meeting_chunk"]
    assert {e["track"] for e in chunks} == {"me", "them"}
    assert all(Path(e["path"]).is_file() for e in chunks)
    assert events[-1]["tracks"] == [] and not events[-1]["error"]
    recorder.close()


def test_failed_loopback_does_not_claim_to_record_the_call(app, tmp_path):
    events = []
    def sources(track):
        if track == "them":
            raise OSError("no speaker monitor")
        return Source()
    recorder = MeetingRecorder(tmp_path, events.append, sources=sources)
    start(recorder, tmp_path)
    wait_for(app, lambda: any(e["type"] == "meeting_recording" and e["on"] for e in events))
    recording = next(e for e in events if e["type"] == "meeting_recording" and e["on"])
    assert recording["tracks"] == ["me"] and "no speaker monitor" in recording["error"]
    recorder.close()
    wait_for(app, lambda: events[-1]["type"] == "meeting_recording" and not events[-1]["on"])


def test_both_unavailable_sources_report_stopped_with_error(app, tmp_path):
    events = []
    def fail(_):
        raise OSError("no device")
    recorder = MeetingRecorder(tmp_path, events.append, sources=fail)
    start(recorder, tmp_path)
    wait_for(app, lambda: any(e["type"] == "meeting_recording" for e in events))
    assert not events[-1]["on"] and events[-1]["tracks"] == []
    assert "microphone" in events[-1]["error"] and "system audio" in events[-1]["error"]
    recorder.close()


def test_pause_writes_silence_and_preserves_the_timeline(app, tmp_path):
    events = []
    gate = threading.Event()
    class GatedSource(Source):
        def read(self):
            gate.wait(timeout=0.3)
            return super().read()
    recorder = MeetingRecorder(tmp_path, events.append, sources=lambda _: GatedSource())
    start(recorder, tmp_path)
    recorder.pause(True)
    wait_for(app, lambda: any(e.get("on") for e in events))
    gate.set()
    time.sleep(0.05)
    recorder.close()
    wait_for(app, lambda: events and events[-1]["type"] == "meeting_recording" and not events[-1]["on"])
    for event in [e for e in events if e["type"] == "meeting_chunk"]:
        with wave.open(event["path"], "rb") as audio:
            values = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
            assert np.all(values == 0)


def test_recording_cannot_write_outside_the_meetings_folder(app, tmp_path):
    events = []
    recorder = MeetingRecorder(tmp_path, events.append, sources=lambda _: Source())
    recorder.record({"id": "test", "dir": str(tmp_path / "outside"), "on": True})
    assert not events[-1]["on"] and "inside" in events[-1]["error"]
    assert not (tmp_path / "outside").exists()


def test_close_is_bounded_when_a_native_read_stalls(app, tmp_path):
    events, gate = [], threading.Event()
    class StalledSource(Source):
        def read(self):
            gate.wait(timeout=3)
            return np.zeros(BLOCK, dtype=np.float32)
    recorder = MeetingRecorder(tmp_path, events.append, sources=lambda _: StalledSource())
    start(recorder, tmp_path)
    wait_for(app, lambda: any(e.get("on") for e in events))
    began = time.monotonic()
    recorder.close()
    assert time.monotonic() - began < 0.5
    gate.set()
    wait_for(app, lambda: events and events[-1]["type"] == "meeting_recording" and not events[-1]["on"])


def test_callback_audio_captured_while_paused_stays_redacted_after_resume():
    source = _QueuedSource()
    source.pause_event.set()
    source._feed(np.ones(BLOCK, dtype=np.float32))
    source.pause_event.clear()
    assert np.all(source.read() == 0)


def test_a_native_read_crossing_pause_and_resume_is_redacted(app, tmp_path):
    events, gate = [], threading.Event()
    started = {track: threading.Event() for track in ("me", "them")}
    class CrossingSource(Source):
        def __init__(self, track):
            self.track = track
        def read(self):
            started[self.track].set()
            gate.wait(timeout=1)
            return np.ones(BLOCK, dtype=np.float32)
    recorder = MeetingRecorder(tmp_path, events.append, sources=CrossingSource)
    start(recorder, tmp_path)
    wait_for(app, lambda: all(event.is_set() for event in started.values()))
    recorder.pause(True)
    recorder.pause(False)
    recorder.record({"id": "test", "on": False})
    gate.set()
    wait_for(app, lambda: events and events[-1]["type"] == "meeting_recording" and not events[-1]["on"])
    for event in [e for e in events if e["type"] == "meeting_chunk"]:
        with wave.open(event["path"], "rb") as audio:
            assert np.all(np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2") == 0)
    recorder.close()


def test_native_close_flushes_final_commands_before_the_wire_is_disconnected(app, tmp_path):
    from milo.desktop.native import NativeBridge
    from milo.desktop._native_types import UnavailableAccessibility
    events = []
    bridge = NativeBridge(tmp_path, backend=UnavailableAccessibility("test"))
    recorder = MeetingRecorder(tmp_path, events.append, sources=lambda _: Source())
    bridge._meeting_recorder = recorder
    start(recorder, tmp_path)
    wait_for(app, lambda: any(e.get("on") for e in events))
    time.sleep(0.03)
    bridge.close()
    assert events[-1]["type"] == "meeting_recording" and not events[-1]["on"]
    assert {e["track"] for e in events if e["type"] == "meeting_chunk"} == {"me", "them"}
