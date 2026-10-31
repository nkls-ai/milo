"""Who said what, settled once the call is over.

During the call SpeakerTracker groups voices online, one short stretch at a time: on a noisy line or a video it splits
two people into a dozen (2026-10-31, a YouTube video: 15 speakers for 2). A call diarizer (core/ports.CallDiarizer) sees
the whole call's audio at once, and `regroup` puts its voices on the transcript's lines, keeping the names the user
gave during the call on their people.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from milo.core.meetings import Track, TranscriptLine


def line_key(line: TranscriptLine) -> str:
    """How a line of the call's track is found again in the meeting's state."""
    return f"{line.start:.2f}"


def regroup(lines: Sequence[TranscriptLine], segments: Sequence[tuple[float, float, str]],
            aliases: Mapping[str, str] = {}, named: Iterable[str] = ()) -> dict[str, str]:
    """line_key -> meeting speaker for each line of the call's track, {} when the diarizer heard nobody.

    Each line takes the voice it overlaps most (the nearest one when it overlaps none). A voice that shares speech with
    a speaker the user named during the call keeps that speaker, so the name stays on its person. The other voices
    are numbered by when they first spoke, never with a number a name or a joined speaker (`aliases`) holds."""
    if not segments:
        return {}
    voice_of: dict[str, str] = {}
    first: dict[str, float] = {}
    weight: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for line in (l for l in lines if l.track is Track.THEM):
        overlap: dict[str, float] = defaultdict(float)
        for start, end, label in segments:
            if (o := min(line.end, end) - max(line.start, start)) > 0:
                overlap[label] += o
        voice = max(overlap, key=overlap.__getitem__) if overlap else min(
            segments, key=lambda s: max(s[0] - line.end, line.start - s[1], 0.0))[2]
        voice_of[line_key(line)] = voice
        first.setdefault(voice, line.start)
        weight[voice][aliases.get(line.speaker, line.speaker)] += line.end - line.start
    named = {aliases.get(s, s) for s in named}
    speaker_of: dict[str, str] = {}
    # A named speaker goes to the voice it shares most speech with, the surest pairs first; one voice each.
    for _, voice, speaker in sorted(((w, v, s) for v, by in weight.items() for s, w in by.items() if s in named),
                                    reverse=True):
        if voice not in speaker_of and speaker not in speaker_of.values():
            speaker_of[voice] = speaker
    used, n = named | set(aliases), 1
    for voice in sorted(weight, key=first.__getitem__):
        if voice not in speaker_of:
            while f"S{n}" in used:
                n += 1
            speaker_of[voice] = f"S{n}"
            used.add(f"S{n}")
    return {key: speaker_of[voice] for key, voice in voice_of.items()}


def regrouped(lines: Sequence[TranscriptLine], mapping: Mapping[str, str]) -> list[TranscriptLine]:
    """The lines with the speakers `regroup` settled on."""
    if not mapping:
        return list(lines)
    return [TranscriptLine(l.start, l.end, l.track, mapping.get(line_key(l), l.speaker), l.text)
            if l.track is Track.THEM else l for l in lines]
