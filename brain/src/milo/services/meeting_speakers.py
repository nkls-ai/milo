"""Who is who across a whole meeting.

The diarizer gives a voice for each stretch of speech in a pass of about 30 s. SpeakerTracker keeps a voice per
meeting speaker ("S1", "S2", ...) and puts each stretch with the one it sounds most like (cosine similarity of unit
embeddings), online, the way diart's incremental clustering does: a stretch that sounds like nobody known, and is
long enough to be sure, becomes a new speaker; only long stretches update a known voice. At the end `merge()` joins
speakers whose voices turned out to be one person.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from milo.core.meetings import Turn

MATCH = 0.6
"""A local voice at least this alike a known one is that speaker (TitaNet-small; measured in docs/research)."""
MERGE = 0.75
"""Two meeting speakers this alike at the end are one person."""
NEW_AFTER_S = 1.0
"""A voice nobody matched becomes a new speaker only with this much speech; shorter goes to the closest one."""
UPDATE_AFTER_S = 2.0
"""Only this much speech in a pass changes a known voice."""
WEIGHT_CAP_S = 120.0
"""A voice is an average over at most this much speech, so it follows a speaker whose sound drifts."""


@dataclass
class Voice:
    vector: np.ndarray
    seconds: float


def unit(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    return v / n if n else v


class SpeakerTracker:
    def __init__(self, *, match: float = MATCH):
        self.match = match
        self.voices: dict[str, Voice] = {}

    def assign(self, turns: Sequence[Turn], *, learn: bool = True) -> dict[int, str]:
        """Map each local voice of one pass to a meeting speaker, longest first. learn=False only looks."""
        locals_: dict[int, tuple[np.ndarray, float]] = {}
        for turn in turns:
            vector, seconds = locals_.get(turn.local, (unit(turn.voice), 0.0))
            locals_[turn.local] = (vector, seconds + max(0.0, turn.end - turn.start))
        mapping: dict[int, str] = {}
        for local in sorted(locals_, key=lambda l: -locals_[l][1]):
            vector, seconds = locals_[local]
            ids = list(self.voices)
            sims = [float(vector @ self.voices[s].vector) for s in ids]
            best = int(np.argmax(sims)) if ids else -1
            if ids and sims[best] >= self.match:
                speaker = ids[best]
                if learn and seconds >= UPDATE_AFTER_S:
                    self._update(speaker, vector, seconds)
            elif learn and (not ids or seconds >= NEW_AFTER_S):
                speaker = self._add(vector, seconds)
            else:
                speaker = ids[best] if ids else "S1"
            mapping[local] = speaker
        return mapping

    def merge(self, threshold: float = MERGE) -> dict[str, str]:
        """Join speakers that sound like one person. Returns old id -> kept id for each one merged away."""
        merged: dict[str, str] = {}
        while True:
            ids = list(self.voices)
            best, pair = threshold, None
            for a, b in itertools.combinations(ids, 2):
                score = float(self.voices[a].vector @ self.voices[b].vector)
                if score >= best:
                    best, pair = score, (a, b)
            if pair is None:
                return merged
            keep, gone = sorted(pair, key=lambda s: -self.voices[s].seconds)
            k, g = self.voices[keep], self.voices.pop(gone)
            k.vector = unit(k.vector * k.seconds + g.vector * g.seconds)
            k.seconds += g.seconds
            merged = {old: (keep if new == gone else new) for old, new in merged.items()}
            merged[gone] = keep

    def _add(self, vector: np.ndarray, seconds: float) -> str:
        n = 1
        while f"S{n}" in self.voices:
            n += 1
        self.voices[f"S{n}"] = Voice(vector, seconds)
        return f"S{n}"

    def _update(self, speaker: str, vector: np.ndarray, seconds: float) -> None:
        voice = self.voices[speaker]
        weight = min(voice.seconds, WEIGHT_CAP_S)
        voice.vector = unit(voice.vector * weight + vector * seconds)
        voice.seconds += seconds

    # ---- kept in the meeting's state, so a restarted brain knows the voices

    def to_state(self) -> dict:
        return {s: {"voice": [round(float(x), 5) for x in v.vector], "seconds": round(v.seconds, 2)}
                for s, v in self.voices.items()}

    @staticmethod
    def from_state(state: dict, *, match: float = MATCH) -> SpeakerTracker:
        tracker = SpeakerTracker(match=match)
        for speaker, v in (state or {}).items():
            tracker.voices[speaker] = Voice(unit(np.asarray(v["voice"], dtype=np.float32)), float(v["seconds"]))
        return tracker

