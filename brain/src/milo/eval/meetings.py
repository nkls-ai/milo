"""The meeting-notes eval: a made-up call through the real pipeline (Whisper, the diarizer, the store, the
service), scored for who-said-what, words and time. Nothing plays, nothing is recorded, nothing is sent.

    uv run python -m milo.eval.meetings                    # the 20-line script, five other voices
    uv run python -m milo.eval.meetings --repeat 25 --fast # about an hour: memory must stay flat
    uv run python -m milo.eval.meetings --realtime         # chunks arrive every 30 s, as in a call: lag

`--leak 0.3` mixes the call into the microphone, like a user on speakers. Loads Whisper large-v3-turbo and
TitaNet-small; take the model lock first (see AGENTS notes in the repo).
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import re
import resource
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from milo.core.events import MeetingChunk, MeetingRecording
from milo.core.meetings import CHUNK_S, MeetingInfo, Track
from milo.core.types import STT_SAMPLE_RATE
from milo.memory.meetings import FileMeetingStore, write_wav
from milo.services.background_stt import BackgroundStt
from milo.services.meeting_text import clean
from milo.services.meetings import MeetingService
from milo.services.ui_state import UiState

from .meeting_audio import ME, FakeMeeting, build


class _Sink:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


class TimedStore(FileMeetingStore):
    """Remembers when each pass landed, for the lag."""

    def __init__(self, root: Path):
        super().__init__(root)
        self.t0 = time.monotonic()
        self.passes: list[tuple[float, str, float]] = []  # (seconds since start, track, transcribed up to)

    def append(self, meeting_id, lines, *, track, upto):
        super().append(meeting_id, lines, track=track, upto=upto)
        self.passes.append((time.monotonic() - self.t0, track.value, upto))


class _Clock:
    def __init__(self, start: datetime):
        self.start = start
        self.t0 = time.monotonic()

    def now(self) -> datetime:
        return self.start

    def monotonic(self) -> float:
        return time.monotonic()


@dataclass
class Score:
    speakers_found: int
    speakers_true: int
    attributed: float
    wer: float
    me_lines: int
    echo_kept: int


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def wer(ref: list[str], hyp: list[str]) -> float:
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[-1] / max(1, len(ref))


def score(meeting: FakeMeeting, lines, aliases: dict) -> Score:
    them = [l for l in lines if l.track is Track.THEM]
    overlap: Counter = Counter()
    for line in them:
        for t in np.arange(line.start, line.end, 0.1):
            who = meeting.truth(t, "them")
            if who:
                overlap[(aliases.get(line.speaker, line.speaker), who)] += 1
    found = sorted({s for s, _ in overlap})
    people = sorted({l.who for l in meeting.lines if l.who != ME})
    best = 0
    for perm in itertools.permutations(people, min(len(found), len(people))):
        best = max(best, sum(overlap[(s, p)] for s, p in zip(found, perm)))
    total = sum(overlap.values())
    ref = [w for l in meeting.lines if l.who != ME for w in words(l.text)]
    hyp = [w for l in sorted(them, key=lambda l: l.start) for w in words(l.text)]
    mine = [l for l in lines if l.track is Track.ME]
    echo = sum(1 for l in mine if not meeting.truth((l.start + l.end) / 2, ME))
    return Score(len(found), len(people), best / max(1, total), wer(ref, hyp), len(mine), echo)


def write_chunks(meeting: FakeMeeting, folder: Path, upto_s: float | None = None) -> list[MeetingChunk]:
    """The chunks the app would have finished by `upto_s` (all of them for None)."""
    out = []
    n = int(np.ceil(meeting.seconds / CHUNK_S))
    for track, audio in ((Track.ME, meeting.me), (Track.THEM, meeting.them)):
        for i in range(n):
            start = i * CHUNK_S
            if upto_s is not None and start + CHUNK_S > upto_s:
                break
            piece = audio[int(start * STT_SAMPLE_RATE):int((start + CHUNK_S) * STT_SAMPLE_RATE)]
            path = folder / f"{track.value}-{i + 1:04d}.wav"
            if not path.exists():
                write_wav(path, piece)
            out.append(MeetingChunk("", track.value, i + 1, str(path), start, len(piece) / STT_SAMPLE_RATE))
    return out


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20  # macOS reports bytes


async def run(args) -> None:
    from milo.adapters.diarize.sherpa import SherpaDiarizer, SherpaOptions
    from milo.adapters.stt.mlx_whisper import MlxWhisper

    meeting = build(repeat=args.repeat, leak=args.leak, gaps=(args.gap_min, args.gap_max))
    print(f"meeting: {meeting.seconds / 60:.1f} min, {len(meeting.lines)} lines")
    root = Path(tempfile.mkdtemp(prefix="milo-meeting-eval-"))
    store = TimedStore(root)
    stt_executor = ThreadPoolExecutor(1, thread_name_prefix="stt")
    diarize_executor = ThreadPoolExecutor(1, thread_name_prefix="diarize")
    whisper = MlxWhisper("mlx-community/whisper-large-v3-turbo")
    diarizer = SherpaDiarizer(SherpaOptions(), Path(args.models).expanduser() if args.models else None)
    loop = asyncio.get_running_loop()
    t = time.monotonic()
    await loop.run_in_executor(stt_executor, whisper.warm)
    await loop.run_in_executor(diarize_executor, diarizer.warm)
    print(f"models loaded in {time.monotonic() - t:.1f}s, rss {rss_mb():.0f} MB")

    service = MeetingService(store, UiState(_Sink()), _Clock(datetime(2026, 10, 30, 14, 0)),
                             BackgroundStt(stt_executor), whisper, diarizer=diarizer,
                             diarize_executor=diarize_executor, match=diarizer.match)
    info = MeetingInfo("Eval meeting", datetime(2026, 10, 30, 14, 0), "Zoom")
    await service._begin(info, from_call=True)
    m = service.current
    folder = store.audio_dir(m.id)
    memory: list[tuple[float, float]] = []
    t0 = store.t0 = time.monotonic()
    if args.realtime:
        sent = set()
        while (elapsed := time.monotonic() - t0) < meeting.seconds + CHUNK_S:
            for chunk in write_chunks(meeting, folder, elapsed):
                if chunk.path not in sent:
                    sent.add(chunk.path)
                    service.chunk(MeetingChunk(m.id, chunk.track, chunk.index, chunk.path, chunk.start, chunk.seconds))
            await asyncio.sleep(1)
    else:
        for chunk in write_chunks(meeting, folder):
            service.chunk(MeetingChunk(m.id, chunk.track, chunk.index, chunk.path, chunk.start, chunk.seconds))
        while True:
            await asyncio.sleep(2)
            progress = store.progress(m.id)
            memory.append((min(progress.values()), rss_mb()))
            if min(progress.values()) >= meeting.seconds - 2 * CHUNK_S:
                break
    service.recording_changed(MeetingRecording(m.id, False))
    while service._finishing or service.current is not None:
        await asyncio.sleep(0.5)
    took = time.monotonic() - t0
    state = store.state(m.id)
    lines = clean(store.lines(m.id), state.get("private", ()))
    s = score(meeting, lines, state.get("aliases", {}))
    print(f"processed {meeting.seconds / 60:.1f} min in {took:.0f}s ({took / meeting.seconds:.2f}x the meeting)")
    print(f"speakers: found {s.speakers_found} of {s.speakers_true}; speech attributed right: {s.attributed:.1%}")
    print(f"word error rate on the call track: {s.wer:.1%}")
    print(f"user lines {s.me_lines}, of them echo of the call: {s.echo_kept}")
    if memory:
        print("rss by meeting minute:", ", ".join(f"{p / 60:.0f}m {mb:.0f}MB" for p, mb in memory[::max(1, len(memory) // 12)]))
    print(f"transcript: {store.folder(m.id) / 'transcript.md'}")
    if args.realtime:
        print_lag(store, meeting)


def print_lag(store: TimedStore, meeting: FakeMeeting) -> None:
    """How long after something was said it was in transcript.jsonl, sampled every second of the meeting."""
    lags = []
    for x in np.arange(0, meeting.seconds - 1, 1.0):
        done = [at for at, track, upto in store.passes if upto >= x and track == "them"]
        if done:
            lags.append(min(done) - x)
    if lags:
        print(f"lag from speech to transcript: median {np.median(lags):.0f}s, 90% {np.percentile(lags, 90):.0f}s, "
              f"max {max(lags):.0f}s")


def main() -> None:
    import logging

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s: %(message)s")
    logging.getLogger("milo.meetings").setLevel(logging.INFO)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--leak", type=float, default=0.0)
    p.add_argument("--gap-min", type=float, default=0.05)
    p.add_argument("--gap-max", type=float, default=0.5)
    p.add_argument("--realtime", action="store_true")
    p.add_argument("--models", default="", help="folder with the diarizer model (default ~/.cache/milo/models)")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
