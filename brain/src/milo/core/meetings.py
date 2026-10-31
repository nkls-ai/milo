"""Value types for meeting notes. No I/O. See docs/design/meetings.md."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum

import numpy as np

from .times import local

CHUNK_S = 30.0
"""The app writes each track in chunks this long."""

ME = "me"
"""The speaker of every line on the user's own track."""


class Track(StrEnum):
    ME = "me"  # the user's microphone
    THEM = "them"  # the call's audio: everybody else


@dataclass(frozen=True)
class TimedWord:
    """One word Whisper heard, seconds from the start of the audio it was given. `segment` numbers Whisper's
    segments (about a sentence each): a new speaker almost always starts a new one."""

    start: float
    end: float
    text: str
    segment: int = 0
    language: str = ""
    """What Whisper heard it as, like "de". Whisper picks one language per pass."""


@dataclass(frozen=True)
class Turn:
    """Someone spoke from `start` to `end` (seconds into the audio). `voice` is the unit speaker embedding of what
    they said there. `local` numbers the turns of one piece of audio; turns that share it share the voice."""

    start: float
    end: float
    local: int
    voice: np.ndarray = field(compare=False, repr=False)


@dataclass(frozen=True)
class TranscriptLine:
    """One stretch of speech in a meeting. Times are seconds since the meeting started.

    `speaker` is ME on the user's track, and "S1", "S2", ... on the call's track (named later through the
    meeting's speaker names). Text came from other people's voices: it is untrusted data.
    """

    start: float
    end: float
    track: Track
    speaker: str
    text: str

    def to_dict(self) -> dict:
        return {"start": round(self.start, 2), "end": round(self.end, 2), "track": self.track.value,
                "speaker": self.speaker, "text": self.text}

    @staticmethod
    def from_dict(d: dict) -> TranscriptLine:
        return TranscriptLine(float(d["start"]), float(d["end"]), Track(d["track"]), str(d["speaker"]),
                              str(d["text"]))


@dataclass(frozen=True)
class MeetingInfo:
    """What Milo knows about a meeting when it starts."""

    title: str
    started: datetime
    app: str = ""
    attendees: tuple[str, ...] = ()
    """Names from the calendar invite, without the user."""

    def to_dict(self) -> dict:
        return {"title": self.title, "started": self.started.isoformat(timespec="seconds"), "app": self.app,
                "attendees": list(self.attendees)}

    @staticmethod
    def from_dict(d: dict) -> MeetingInfo:
        return MeetingInfo(str(d.get("title") or "Meeting"), local(d["started"]),
                           str(d.get("app") or ""), tuple(str(a) for a in d.get("attendees") or ()))


@dataclass(frozen=True)
class Todo:
    text: str
    owner: str = ""
    """Who said they'd do it, "" if nobody did. "me" is the user."""
    due: str = ""
    """As said in the meeting ("Friday"), "" if nobody said."""

    @property
    def mine(self) -> bool:
        return self.owner == ME


@dataclass(frozen=True)
class MeetingNotes:
    """What came out of a meeting, for notes.md and the user's to-dos."""

    summary: str
    decisions: tuple[str, ...] = ()
    todos: tuple[Todo, ...] = ()
    followup: str = ""
    """A short follow-up mail to the others, written for the user to send. "" if there's nothing to follow up."""

    def to_dict(self) -> dict:
        return {"summary": self.summary, "decisions": list(self.decisions),
                "todos": [asdict(t) for t in self.todos], "followup": self.followup}


@dataclass(frozen=True)
class Chunk:
    """A finished (or, while it's written, growing) piece of one track on disk.

    `start` is seconds since the meeting started; `seconds` is how much audio it holds.
    """

    track: Track
    index: int
    path: str
    start: float
    seconds: float

    @property
    def end(self) -> float:
        return self.start + self.seconds


_SLUG = re.compile(r"[^a-z0-9]+")


def meeting_id(info: MeetingInfo) -> str:
    """A sortable folder name: `2026-10-30-1400-weekly-sync`."""
    slug = _SLUG.sub("-", info.title.lower()).strip("-")[:40].strip("-") or "meeting"
    return f"{info.started:%Y-%m-%d-%H%M}-{slug}"


def clock(seconds: float) -> str:
    """Seconds into the meeting as `12:05`, or `1:02:05` past an hour."""
    s = max(0, int(seconds))
    h, m, s = s // 3600, s // 60 % 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
