"""Meetings on disk, one folder each under ~/Milo/meetings/<id>/:

    meeting.json      what the meeting is, its state (speakers, names, private times), done or not
    audio/            me-0001.wav, them-0001.wav, ... 30 s chunks the app writes (16 kHz mono 16-bit)
    transcript.jsonl  lines, each pass ending in a progress mark for its track
    transcript.md     the transcript to read, rendered after every pass
    notes.md          summary, decisions and to-dos, once the meeting is over

A pass appends its lines and then `{"track": "them", "upto": 57.3}` in one write. On reading, lines count only
once their mark follows, so a crash in the middle of a write neither loses nor repeats a line: the pass just
runs again. The app writes each chunk's WAV header before its audio and fixes the sizes at the end, so a chunk cut
off by a crash still reads up to its last sample.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import struct
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from milo.core.meetings import (CHUNK_S, Chunk, MeetingInfo, MeetingNotes, Track, TranscriptLine, meeting_id)
from milo.core.types import STT_SAMPLE_RATE, Audio

log = logging.getLogger(__name__)

_CHUNK = re.compile(r"^(me|them)-(\d{4,})\.wav$")
_HEADER = 44
_BYTES = 2  # 16-bit samples


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def wav_data_offset(path: Path) -> int:
    """Where the samples start. Accepts a header whose sizes were never filled in."""
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return _HEADER
    if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        return _HEADER
    pos = 12
    while pos + 8 <= len(head):
        tag, size = head[pos:pos + 4], struct.unpack("<I", head[pos + 4:pos + 8])[0]
        if tag == b"data":
            return pos + 8
        pos += 8 + size + (size & 1)
    return _HEADER


def read_wav(path: Path, start: float = 0.0, end: float | None = None) -> Audio:
    """16 kHz mono 16-bit samples from `start` to `end` seconds as float32, up to the end of the file as written
    (not as the header says: a crash leaves the header's sizes at zero)."""
    offset = wav_data_offset(path)
    first = max(0, int(round(start * STT_SAMPLE_RATE)))
    try:
        with open(path, "rb") as f:
            f.seek(offset + first * _BYTES)
            count = -1 if end is None else max(0, int(round(end * STT_SAMPLE_RATE)) - first) * _BYTES
            raw = f.read(count)
    except OSError:
        return np.zeros(0, dtype=np.float32)
    raw = raw[:len(raw) - len(raw) % _BYTES]
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def write_wav(path: Path, audio: Audio) -> None:
    """For tests and the eval: what the app writes."""
    data = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(data), b"WAVE", b"fmt ", 16, 1, 1, STT_SAMPLE_RATE,
                         STT_SAMPLE_RATE * _BYTES, _BYTES, 16, b"data", len(data))
    path.write_bytes(header + data)


class FileMeetingStore:
    """MeetingStore over plain files under `root` (~/Milo/meetings)."""

    def __init__(self, root: Path):
        self.root = root

    # ---- the meeting

    def open(self, meeting: MeetingInfo) -> str:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)  # other people's words: the user's eyes only
        base = id = meeting_id(meeting)
        n = 2
        while (self.root / id).exists():
            id, n = f"{base}-{n}", n + 1
        (self.root / id).mkdir(mode=0o700)
        (self.root / id / "audio").mkdir(mode=0o700)
        self._write_meta(id, {"info": meeting.to_dict(), "state": {}, "done": False})
        return id

    def info(self, meeting_id: str) -> MeetingInfo:
        return MeetingInfo.from_dict(self._meta(meeting_id)["info"])

    def state(self, meeting_id: str) -> dict:
        return dict(self._meta(meeting_id).get("state") or {})

    def save_state(self, meeting_id: str, state: dict) -> None:
        meta = self._meta(meeting_id)
        meta["state"] = state
        self._write_meta(meeting_id, meta)

    def folder(self, meeting_id: str) -> Path:
        return self.root / meeting_id

    def unfinished(self) -> list[str]:
        if not self.root.is_dir():
            return []
        ids = []
        for meta in sorted(self.root.glob("*/meeting.json")):
            try:
                if not json.loads(meta.read_text(encoding="utf-8")).get("done"):
                    ids.append(meta.parent.name)
            except (OSError, ValueError):
                log.warning("skipping a meeting whose meeting.json can't be read: %s", meta.parent.name)
        return ids

    def close(self, meeting_id: str, notes: MeetingNotes, markdown: str, *, keep_audio: bool = False) -> Path:
        path = self.folder(meeting_id) / "notes.md"
        write_atomic(path, markdown)
        meta = self._meta(meeting_id)
        meta |= {"done": True, "notes": notes.to_dict()}
        self._write_meta(meeting_id, meta)
        if not keep_audio:
            shutil.rmtree(self.audio_dir(meeting_id), ignore_errors=True)
        return path

    # ---- audio

    def audio_dir(self, meeting_id: str) -> Path:
        return self.folder(meeting_id) / "audio"

    def chunks(self, meeting_id: str) -> list[Chunk]:
        folder = self.audio_dir(meeting_id)
        found = []
        for path in folder.glob("*.wav") if folder.is_dir() else ():
            match = _CHUNK.match(path.name)
            if not match:
                continue
            index = int(match[2])
            try:
                size = path.stat().st_size
            except OSError:
                continue
            seconds = max(0, size - wav_data_offset(path)) // _BYTES / STT_SAMPLE_RATE
            found.append(Chunk(Track(match[1]), index, str(path), (index - 1) * CHUNK_S, seconds))
        return sorted(found, key=lambda c: (c.track.value, c.index))

    def audio(self, meeting_id: str, track: Track, start: float, end: float) -> Audio:
        parts: list[Audio] = []
        pos = start
        for chunk in (c for c in self.chunks(meeting_id) if c.track is track):
            if chunk.end <= pos or chunk.start >= end:
                continue
            if chunk.start > pos:  # a chunk is missing: keep the times right
                parts.append(np.zeros(int(round((chunk.start - pos) * STT_SAMPLE_RATE)), dtype=np.float32))
                pos = chunk.start
            piece = read_wav(Path(chunk.path), pos - chunk.start, min(end, chunk.end) - chunk.start)
            parts.append(piece)
            pos += len(piece) / STT_SAMPLE_RATE
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    # ---- transcript

    def append(self, meeting_id: str, lines: Sequence[TranscriptLine], *, track: Track, upto: float) -> None:
        text = "".join(json.dumps(line.to_dict(), ensure_ascii=False) + "\n" for line in lines)
        text += json.dumps({"track": track.value, "upto": round(upto, 3)}) + "\n"
        with open(self._transcript(meeting_id), "a", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())

    def progress(self, meeting_id: str) -> dict[Track, float]:
        return self._read(meeting_id)[1]

    def lines(self, meeting_id: str) -> list[TranscriptLine]:
        return self._read(meeting_id)[0]

    def render(self, meeting_id: str, text: str) -> None:
        write_atomic(self.folder(meeting_id) / "transcript.md", text)

    def _read(self, meeting_id: str) -> tuple[list[TranscriptLine], dict[Track, float]]:
        committed: list[TranscriptLine] = []
        pending: dict[Track, list[TranscriptLine]] = {t: [] for t in Track}
        upto: dict[Track, float] = {t: 0.0 for t in Track}
        try:
            with open(self._transcript(meeting_id), encoding="utf-8") as f:
                for raw in f:
                    try:
                        d = json.loads(raw)
                        if "upto" in d:
                            track = Track(d["track"])
                            committed += pending[track]
                            pending[track] = []
                            upto[track] = max(upto[track], float(d["upto"]))
                        else:
                            line = TranscriptLine.from_dict(d)
                            pending[line.track].append(line)
                    except (ValueError, KeyError, TypeError):
                        continue  # the half-written last line of a crash
        except FileNotFoundError:
            pass
        return committed, upto

    def _transcript(self, meeting_id: str) -> Path:
        return self.folder(meeting_id) / "transcript.jsonl"

    def _meta(self, meeting_id: str) -> dict:
        return json.loads((self.folder(meeting_id) / "meeting.json").read_text(encoding="utf-8"))

    def _write_meta(self, meeting_id: str, meta: dict) -> None:
        write_atomic(self.folder(meeting_id) / "meeting.json", json.dumps(meta, ensure_ascii=False, indent=1))


class JsonVoiceBook:
    """VoiceBook in one JSON file (~/Milo/meetings/voices.json). Voices of another embedding model are ignored:
    their numbers don't compare. Delete the file and Milo forgets every voice."""

    def __init__(self, path: Path, model: str, *, threshold: float = 0.75):
        self.path = path
        self.model = model
        self.threshold = threshold

    def match(self, voice: np.ndarray) -> str | None:
        best, name = self.threshold, None
        v = _unit(voice)
        for entry in self._voices():
            if entry.get("model") != self.model:
                continue
            score = float(v @ _unit(np.asarray(entry["voice"], dtype=np.float32)))
            if score >= best:
                best, name = score, entry["name"]
        return name

    def learn(self, name: str, voice: np.ndarray) -> None:
        voices = self._voices()
        v = _unit(voice)
        for entry in voices:
            if entry.get("model") == self.model and entry["name"].lower() == name.lower():
                count = int(entry.get("count", 1))
                mixed = _unit(np.asarray(entry["voice"], dtype=np.float32) * count + v)
                entry |= {"voice": [round(float(x), 5) for x in mixed], "count": count + 1}
                break
        else:
            voices.append({"name": name, "model": self.model, "voice": [round(float(x), 5) for x in v], "count": 1})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(self.path, json.dumps({"voices": voices}))

    def _voices(self) -> list[dict]:
        try:
            return list(json.loads(self.path.read_text(encoding="utf-8")).get("voices") or [])
        except (OSError, ValueError):
            return []


def _unit(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    return v / n if n else v
