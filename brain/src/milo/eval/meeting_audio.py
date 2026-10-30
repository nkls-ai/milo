"""Made-up meetings for tests and the eval: lines spoken by `say` voices, rendered to files (nothing plays), laid
out on two tracks the way the app records them: the user's microphone and the call's audio."""

from __future__ import annotations

import hashlib
import random
import subprocess
import tempfile
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from milo.core.types import STT_SAMPLE_RATE

ME = "me"

# Voices by person; each person keeps one voice. Picked to be installed on every recent macOS.
VOICES = {"me": "Daniel", "Anna": "Anna", "Sam": "Samantha", "Fred": "Fred", "Moira": "Moira", "Rishi": "Rishi"}

SCRIPT: tuple[tuple[str, str], ...] = (
    ("Anna", "Guten Morgen zusammen. Lasst uns mit dem Budget für das nächste Quartal anfangen."),
    ("me", "Morning. I looked at the numbers yesterday, and we are about ten percent over on travel."),
    ("Sam", "That matches what I saw. Most of it is the trade fair in Munich."),
    ("Fred", "Yes, exactly."),
    ("Anna", "Dann schlage ich vor, dass wir die Messe auf zwei Personen begrenzen."),
    ("Sam", "Fine with me. Who should go?"),
    ("me", "I think Anna and Fred, they know the customers best."),
    ("Fred", "Okay. I can book the hotel this week."),
    ("Moira", "Before we move on, the release date. Are we still on for the fourteenth?"),
    ("Sam", "Not quite. The tests on the payment page are still failing, so I would push it by one week."),
    ("Moira", "One week is fine, but we need to tell the customer by Friday."),
    ("me", "I will write to them today and copy all of you."),
    ("Rishi", "Can you also mention that the new invoice layout comes with the release?"),
    ("me", "Sure, I will add that."),
    ("Anna", "Gut. Dann ist das entschieden: Release eine Woche später, am einundzwanzigsten."),
    ("Fred", "And the budget question is settled too, two people for the fair."),
    ("Rishi", "One more thing. The design review moved to Thursday afternoon."),
    ("Moira", "Thursday works for me."),
    ("Sam", "For me too. I will send the invite."),
    ("Anna", "Prima. Dann sind wir für heute durch. Danke euch allen."),
)


@dataclass(frozen=True)
class Spoken:
    who: str
    text: str
    start: float
    end: float


@dataclass
class FakeMeeting:
    me: np.ndarray
    them: np.ndarray
    lines: list[Spoken]

    @property
    def seconds(self) -> float:
        return max(len(self.me), len(self.them)) / STT_SAMPLE_RATE

    def truth(self, t: float, track: str) -> str | None:
        for line in self.lines:
            if (line.who == ME) == (track == ME) and line.start <= t < line.end:
                return line.who
        return None


def render(voice: str, text: str, cache: Path) -> np.ndarray:
    """`say` into a 16 kHz WAV file. Rendering to a file never plays sound."""
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:16]
    path = cache / f"{key}.wav"
    if not path.exists():
        tmp = cache / f".{key}.wav"
        subprocess.run(["/usr/bin/say", "-v", voice, "-o", str(tmp), "--data-format=LEI16@16000", text],
                       check=True, capture_output=True, timeout=60)
        tmp.rename(path)
    with wave.open(str(path)) as w:
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
    # say leaves silence around the words; trim it so pauses come from the script, like in a real conversation
    loud = np.flatnonzero(np.abs(samples) > 0.01)
    return samples[loud[0]:loud[-1] + 1] if len(loud) else samples


def build(script: Sequence[tuple[str, str]] = SCRIPT, *, repeat: int = 1, gaps: tuple[float, float] = (0.05, 0.5),
          seed: int = 7, cache: Path | None = None, voices: dict[str, str] = VOICES,
          leak: float = 0.0) -> FakeMeeting:
    """A meeting from `script`, said `repeat` times over. Pauses between lines are drawn from `gaps` (seconds).
    `leak` mixes that much of the call into the microphone, like a user without headphones."""
    cache = cache or Path(tempfile.gettempdir()) / "milo-say-cache"
    rng = random.Random(seed)
    clips = {(who, text): render(voices[who], text, cache) for who, text in dict.fromkeys(script)}
    lines, t = [], 1.0
    for _ in range(repeat):
        for who, text in script:
            clip = clips[(who, text)]
            lines.append(Spoken(who, text, t, t + len(clip) / STT_SAMPLE_RATE))
            t = lines[-1].end + rng.uniform(*gaps)
    total = int((t + 1.0) * STT_SAMPLE_RATE)
    me, them = np.zeros(total, np.float32), np.zeros(total, np.float32)
    for line in lines:
        clip = clips[(line.who, line.text)]
        at = int(line.start * STT_SAMPLE_RATE)
        (me if line.who == ME else them)[at:at + len(clip)] += clip
    if leak:
        me += them * leak
    return FakeMeeting(np.clip(me, -1, 1), np.clip(them, -1, 1), lines)
