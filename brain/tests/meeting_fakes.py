"""Fakes for meeting notes. Audio is made of words a fake transcriber can read back exactly: each word is a block
of one constant sample value that encodes its line, with the sign flipping from word to word. A line's speaker is
looked up by the fake diarizer, which gives every speaker a one-hot voice."""

from __future__ import annotations

import random
import string
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from milo.core.meetings import CHUNK_S, TimedWord, Track, Turn
from milo.core.types import STT_SAMPLE_RATE, Interrupted
from milo.memory.meetings import write_wav

SR = STT_SAMPLE_RATE
WORD_S = 0.5
BASE = 0.05
STEP = 0.0005


def level(line: int) -> float:
    return BASE + STEP * line


def line_of(value: float) -> int:
    return int(round((abs(value) - BASE) / STEP))


def tag(line: int) -> str:
    """Six letters of its own per line, so no two lines read alike (alike lines look like echo of the call)."""
    return "".join(random.Random(line).choices(string.ascii_lowercase, k=6))


def word(line: int, index: int) -> str:
    return f"{tag(line)}{index}"


_LINES = {tag(n): n for n in range(1, 2000)}


def line_of_word(text: str) -> int:
    return _LINES[text.strip().rstrip("0123456789.,")]


@dataclass
class Said:
    line: int
    who: str
    start: float
    words: int

    @property
    def end(self) -> float:
        return self.start + self.words * WORD_S

    def text(self) -> str:
        return " ".join(word(self.line, i) for i in range(self.words))


@dataclass
class Script:
    """Who says what when, on which track. `who` is "me" for the user."""

    said: list[Said] = field(default_factory=list)

    @staticmethod
    def conversation(people: Sequence[str], lines: int, *, words: int = 6, gap: float = 0.7,
                     start: float = 1.0) -> Script:
        script, t = Script(), start
        for n in range(lines):
            script.said.append(Said(n + 1, people[n % len(people)], t, words))
            t = script.said[-1].end + gap
        return script

    @property
    def seconds(self) -> float:
        return max(s.end for s in self.said) + 1.0

    def track(self, track: Track) -> np.ndarray:
        audio = np.zeros(int(self.seconds * SR) + SR, np.float32)
        for s in self.said:
            if (s.who == "me") != (track is Track.ME):
                continue
            for i in range(s.words):
                a = int((s.start + i * WORD_S) * SR)
                audio[a:a + int(WORD_S * SR)] = level(s.line) * (1 if i % 2 == 0 else -1)
        return audio

    def speaker_of_line(self) -> dict[int, str]:
        return {s.line: s.who for s in self.said}


def write_chunks(script: Script, folder: Path, upto: float | None = None) -> list[tuple[Track, int, str, float, float]]:
    """The 30 s chunks the app would have written by `upto` seconds (all of them for None)."""
    out = []
    for track in Track:
        audio = script.track(track)
        for i in range(int(np.ceil(len(audio) / SR / CHUNK_S))):
            start = i * CHUNK_S
            if upto is not None and start + CHUNK_S > upto:
                break
            piece = audio[int(start * SR):int((start + CHUNK_S) * SR)]
            path = folder / f"{track.value}-{i + 1:04d}.wav"
            write_wav(path, piece)
            out.append((track, i + 1, str(path), start, len(piece) / SR))
    return out


class WordReader:
    """TimedTranscriber over Script audio: every run of one sample value is a word."""

    def __init__(self, *, delay_s: float = 0.0, skip_lines: Sequence[int] = ()):
        self.calls: list[tuple[float, str | None]] = []
        self.delay_s = delay_s
        self.skip_lines = set(skip_lines)
        """Lines this "Whisper" skips the first time it hears them, like the real one sometimes does."""

    def words(self, audio, language=None) -> list[TimedWord]:
        self.calls.append((len(audio) / SR, language))
        if self.delay_s:
            time.sleep(self.delay_s)
        q = np.round(audio, 5)
        words, i, n = [], 0, len(q)
        changes = np.flatnonzero(np.diff(q)) + 1
        bounds = [0, *changes.tolist(), n]
        for a, b in zip(bounds, bounds[1:]):
            v = float(q[a])
            if abs(v) < BASE / 2 or b - a < SR * 0.1:
                continue
            line = line_of(v)
            if line in self.skip_lines and len(audio) > 20 * SR:
                continue
            index = sum(1 for w in words if w.text.startswith(f" {tag(line)}"))
            words.append(TimedWord(a / SR, b / SR, f" {word(line, index)}", line, "en"))
        return words

    def spoken_language(self, audio) -> str:
        return "en"


class GivingWay(WordReader):
    """Whisper for dictation and meetings on one thread, like MlxWhisper. It holds its first meeting pass until
    interrupt() (or 5 s), then raises Interrupted, and logs what ran in which order."""

    def __init__(self, dictated: str):
        super().__init__()
        self.dictated = dictated
        self.log: list[str] = []
        self.holding = threading.Event()
        self._stop = threading.Event()

    def words(self, audio, language=None) -> list[TimedWord]:
        self._stop.clear()  # as the adapter does: an interrupt left over from before isn't for this pass
        self.log.append("meeting pass")
        if not self.holding.is_set():
            self.holding.set()
            if self._stop.wait(5):
                self.log.append("gave way")
                raise Interrupted()
        return super().words(audio, language)

    def spoken_language(self, audio) -> str:
        return "en"

    def warm(self) -> None:
        pass

    def wake(self) -> None:
        self._stop.clear()
        self.log.append("wake")

    def transcribe(self, audio, before: str = "", *, quick: bool = False) -> str:
        self._stop.clear()
        self.log.append("dictation")
        return self.dictated

    def preview(self, audio) -> str:
        return ""

    def interrupt(self) -> None:
        self._stop.set()


class LineVoices:
    """Diarizer that knows each line's speaker: a one-hot voice per person."""

    model = "fake"
    match = 0.6

    def __init__(self, by_line: dict[int, str]):
        self.by_line = by_line
        self.people = sorted(set(by_line.values()))
        self.calls = 0

    def warm(self) -> None:
        pass

    def speakers(self, audio, spans) -> list[Turn]:
        self.calls += 1
        turns = []
        for i, (a, b) in enumerate(spans):
            piece = audio[int(a * SR):int(b * SR)]
            loud = piece[np.abs(piece) > BASE / 2]
            if not len(loud):
                continue
            who = self.by_line[line_of(float(loud[0]))]
            voice = np.zeros(len(self.people) + 1, np.float32)
            voice[self.people.index(who)] = 1.0
            turns.append(Turn(a, b, i, voice))
        return turns


class FakeVoiceBook:
    def __init__(self, known: dict[str, np.ndarray] | None = None):
        self.known = dict(known or {})
        self.learned: list[str] = []

    def match(self, voice):
        for name, v in self.known.items():
            if float(np.dot(v, voice)) > 0.9:
                return name
        return None

    def learn(self, name, voice):
        self.learned.append(name)
        self.known[name] = np.asarray(voice)


class SummaryModel:
    """LiveModel that answers the summary prompt with fixed JSON and remembers what it was sent."""

    name = "summary"

    def __init__(self, reply: str):
        self.reply = reply
        self.system = ""
        self.prompts: list[str] = []
        self.closed = False

    async def start(self, system_prompt: str) -> None:
        self.system = system_prompt

    async def turn(self, text: str, images=()):
        self.prompts.append(text)
        yield self.reply

    async def interrupt(self) -> None:
        pass

    async def close(self) -> None:
        self.closed = True
