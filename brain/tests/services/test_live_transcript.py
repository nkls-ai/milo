import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from milo.adapters.text.fillers import FillerCleaner
from milo.core.events import Dictation, Partial
from milo.core.types import STT_SAMPLE_RATE, Audio
from milo.services.live_transcript import LiveTranscript, PauseSegmenter, TypedDictation
from tests.fakes import MemoryHistory, RecordingSink
from tests.services.stack import InlineExecutor, settle

SR = STT_SAMPLE_RATE
# Each word is a tone with its own loudness, so the fake transcriber can tell what audio it got.
WORDS = {0.10: "alpha", 0.14: "bravo", 0.18: "charlie", 0.22: "delta"}


def tone(word: str, seconds: float) -> Audio:
    amp = next(a for a, w in WORDS.items() if w == word)
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sqrt(2) * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def quiet(seconds: float, level: float = 0.001) -> Audio:
    return np.random.default_rng(0).normal(0, level, int(seconds * SR)).astype(np.float32)


def hear(audio: Audio) -> str:
    """The words in `audio`, in order, from the RMS of each 30 ms frame. A word needs two frames in a row,
    so a frame straddling a tone's onset doesn't count as a quieter word."""
    labels: list[str | None] = []
    n = len(audio) // 480
    for frame in audio[:n * 480].reshape(n, 480):
        rms = float(np.sqrt(np.mean(np.square(frame))))
        amp = min(WORDS, key=lambda a: abs(a - rms))
        labels.append(WORDS[amp] if abs(amp - rms) < 0.015 else None)
    words: list[str] = []
    for prev, label in zip(labels, labels[1:]):
        if label is not None and label == prev and (not words or words[-1] != label):
            words.append(label)
    return " ".join(words)


def feed_in_blocks(seg: PauseSegmenter, audio: Audio, block: int = 1024) -> list[tuple[int, int]]:
    return [cut for i in range(0, len(audio), block) for cut in seg.feed(audio[i:i + block])]


# ---- PauseSegmenter


def test_a_pause_closes_a_phrase_in_the_middle_of_the_silence():
    seg = PauseSegmenter(pause_s=0.7)
    audio = np.concatenate([tone("alpha", 1), quiet(1), tone("bravo", 1)])
    cuts = feed_in_blocks(seg, audio)
    assert len(cuts) == 1
    start, end = cuts[0]
    assert start == 0
    assert 1.2 * SR <= end <= 1.5 * SR, "about pause/2 into the silence"
    assert hear(audio[start:end]) == "alpha"
    assert end <= seg.open_start <= 1.75 * SR, "the rest of the pause is trimmed to a short lead-in"
    assert seg.open_has_speech
    assert hear(audio[seg.open_start:]) == "bravo"


def test_a_short_pause_between_words_does_not_cut():
    seg = PauseSegmenter(pause_s=0.7)
    audio = np.concatenate([tone("alpha", 1), quiet(0.4), tone("bravo", 1), quiet(0.3)])
    assert feed_in_blocks(seg, audio) == []
    assert seg.open_start == 0


def test_block_size_does_not_change_the_cuts():
    audio = np.concatenate([tone("alpha", 0.8), quiet(0.9), tone("bravo", 0.6), quiet(1.2), tone("charlie", 0.5)])
    expected = feed_in_blocks(PauseSegmenter(), audio, block=len(audio))
    assert len(expected) == 2
    for block in (160, 1024, 4001):
        assert feed_in_blocks(PauseSegmenter(), audio, block=block) == expected


def test_silence_alone_never_makes_a_phrase_and_is_trimmed_to_a_short_lead():
    seg = PauseSegmenter(lead_s=0.3)
    assert feed_in_blocks(seg, quiet(5)) == []
    assert not seg.open_has_speech
    assert 4.6 * SR <= seg.open_start <= 4.71 * SR
    feed_in_blocks(seg, tone("alpha", 1))
    assert seg.open_has_speech
    assert seg.open_start <= 4.71 * SR, "speech keeps the lead-in"


def test_a_click_followed_by_silence_is_dropped():
    seg = PauseSegmenter(min_speech_s=0.2)
    audio = np.concatenate([quiet(0.5), tone("delta", 0.06), quiet(2)])
    assert feed_in_blocks(seg, audio) == []
    assert not seg.open_has_speech
    assert seg.open_start > 2 * SR


def test_a_phrase_without_pauses_is_cut_at_its_quietest_point_before_max():
    seg = PauseSegmenter(max_s=10, pause_s=0.7)
    # 7 s of talking, a 0.3 s breath (too short for a pause), then talking on.
    audio = np.concatenate([tone("alpha", 7), quiet(0.3), tone("bravo", 8)])
    cuts = feed_in_blocks(seg, audio)
    assert len(cuts) == 1
    start, end = cuts[0]
    assert 7 * SR <= end <= 7.3 * SR
    assert hear(audio[start:end]) == "alpha"
    assert seg.open_has_speech


def test_a_noisy_room_raises_the_threshold():
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 0.02, int(3 * SR)).astype(np.float32)  # well above min_rms
    speech = tone("charlie", 1) + rng.normal(0, 0.02, SR).astype(np.float32)
    seg = PauseSegmenter()
    cuts = feed_in_blocks(seg, np.concatenate([noise[:SR], speech, noise[SR:]]))
    assert len(cuts) == 1


# ---- TypedDictation


def test_typed_phrases_are_cleaned_one_by_one_and_spaced():
    sink, history = RecordingSink(), MemoryHistory()
    typed = TypedDictation(FillerCleaner(["en"]), history, sink)
    assert typed.add("um so the plan is") == "So the plan is"
    assert typed.add("uh") == ""
    assert typed.add("we ship on friday.") == "We ship on friday."
    typed.finish("Notes")
    assert sink.of(Dictation) == [Dictation("So the plan is"), Dictation(" We ship on friday.")]
    assert history.entries == [("So the plan is We ship on friday.", "Notes")]


def test_nothing_typed_leaves_no_history():
    history = MemoryHistory()
    TypedDictation(FillerCleaner(["en"]), history, RecordingSink()).finish("Notes")
    assert history.entries == []


# ---- LiveTranscript


class GrowingMic:
    """A mic whose recording the test extends by hand."""

    def __init__(self):
        self.audio = np.zeros(0, dtype=np.float32)
        self.active = True

    def start(self, on_level) -> None:
        self.active = True

    def stop(self) -> Audio:
        self.active = False
        return self.audio

    def peek(self, start: int = 0) -> Audio:
        return self.audio[start:].copy()

    def say(self, *parts: Audio) -> None:
        self.audio = np.concatenate([self.audio, *parts])


class HearingTranscriber:
    """Transcribes with hear(). Optionally blocks each pass until `release` is set (for a thread executor)."""

    def __init__(self, block: bool = False):
        self.calls: list[int] = []
        self.release = threading.Event()
        self.entered = threading.Event()
        self.block = block
        self.running = 0
        self.max_running = 0
        self._lock = threading.Lock()

    def __call__(self, audio: Audio) -> str:
        with self._lock:
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        self.calls.append(len(audio))
        self.entered.set()
        if self.block:
            self.release.wait(5)
        with self._lock:
            self.running -= 1
        return hear(audio)


def live(mic, stt, sink, typed=None, executor=None):
    return LiveTranscript(mic, stt, executor or InlineExecutor(), sink, PauseSegmenter(), typed,
                          poll_s=0, gap_s=0, min_new_s=0.5)


def test_preview_shows_the_words_so_far_and_passes_cover_only_the_open_phrase():
    mic, stt, sink = GrowingMic(), HearingTranscriber(), RecordingSink()
    lt = live(mic, stt, sink)

    async def run():
        lt.start()
        mic.say(tone("alpha", 1))
        await settle()
        mic.say(quiet(1), tone("bravo", 1.5))
        await settle()
        mic.say(quiet(1), tone("charlie", 2))
        await settle()
        await lt.close()

    asyncio.run(run())
    shown = [e.text for e in sink.of(Partial)]
    assert shown[0] == "alpha"
    assert "alpha bravo" in shown
    assert shown[-1] == "alpha bravo charlie"
    assert sink.of(Dictation) == []
    # No pass ever re-reads the whole recording: each covers one phrase plus a little silence.
    assert max(stt.calls) <= 2.8 * SR < len(mic.audio)


def test_type_mode_pastes_each_phrase_at_its_pause_and_leaves_the_tail():
    mic, stt, sink = GrowingMic(), HearingTranscriber(), RecordingSink()
    typed = TypedDictation(FillerCleaner(["en"]), None, sink)
    lt = live(mic, stt, sink, typed)

    async def run():
        lt.start()
        mic.say(tone("alpha", 1), quiet(1))
        await settle()
        assert sink.of(Dictation) == [Dictation("Alpha")], "typed while the user keeps talking"
        mic.say(tone("bravo", 1), quiet(1), tone("charlie", 1))
        await settle()
        await lt.close()

    asyncio.run(run())
    assert sink.of(Dictation) == [Dictation("Alpha"), Dictation(" Bravo")]
    assert hear(mic.audio[lt.tail_start:]) == "charlie", "only the untyped tail is left for the final pass"
    assert [e.text for e in sink.of(Partial)][-1] == "charlie", "the preview shows only what isn't typed yet"


def test_type_mode_close_waits_for_the_phrase_being_typed():
    mic, stt, sink = GrowingMic(), HearingTranscriber(block=True), RecordingSink()
    typed = TypedDictation(FillerCleaner(["en"]), None, sink)
    executor = ThreadPoolExecutor(1)
    lt = LiveTranscript(mic, stt, executor, sink, PauseSegmenter(), typed, poll_s=0.01, gap_s=0)

    async def run():
        mic.say(tone("alpha", 1), quiet(1), tone("bravo", 0.5))
        lt.start()
        while not stt.entered.is_set():
            await asyncio.sleep(0.01)
        closing = asyncio.create_task(lt.close())
        await asyncio.sleep(0.05)
        assert not closing.done()
        stt.release.set()
        await closing

    asyncio.run(run())
    executor.shutdown()
    assert sink.of(Dictation) == [Dictation("Alpha")]
    assert hear(mic.audio[lt.tail_start:]) == "bravo"
    assert len(stt.calls) == 1, "no preview pass after close"


def test_preview_close_drops_a_running_pass_at_once():
    mic, stt, sink = GrowingMic(), HearingTranscriber(block=True), RecordingSink()
    executor = ThreadPoolExecutor(1)
    lt = LiveTranscript(mic, stt, executor, sink, PauseSegmenter(), poll_s=0.01, gap_s=0)

    async def run():
        mic.say(tone("alpha", 1))
        lt.start()
        while not stt.entered.is_set():
            await asyncio.sleep(0.01)
        await asyncio.wait_for(lt.close(), 0.5)
        stt.release.set()
        await asyncio.sleep(0.05)

    asyncio.run(run())
    executor.shutdown()
    assert sink.of(Partial) == [], "the dropped pass shows nothing"


def test_never_more_than_one_pass_in_flight():
    mic, stt, sink = GrowingMic(), HearingTranscriber(), RecordingSink()
    executor = ThreadPoolExecutor(4)
    lt = LiveTranscript(mic, stt, executor, sink, PauseSegmenter(), poll_s=0.005, gap_s=0, min_new_s=0.05)

    async def run():
        lt.start()
        for word in ("alpha", "bravo", "charlie", "delta"):
            for _ in range(5):
                mic.say(tone(word, 0.2))
                await asyncio.sleep(0.01)
            mic.say(quiet(0.8))
            await asyncio.sleep(0.02)
        await lt.close()

    asyncio.run(run())
    executor.shutdown()
    assert len(stt.calls) > 4
    assert stt.max_running == 1


def test_abort_stops_without_typing_anything_more():
    mic, stt, sink = GrowingMic(), HearingTranscriber(), RecordingSink()
    typed = TypedDictation(FillerCleaner(["en"]), None, sink)
    lt = live(mic, stt, sink, typed)

    async def run():
        lt.start()
        lt.abort()
        mic.say(tone("alpha", 1), quiet(1))
        await settle()

    asyncio.run(run())
    assert sink.of(Dictation) == [] and stt.calls == []


def test_a_failing_pass_ends_live_updates_quietly():
    mic, sink = GrowingMic(), RecordingSink()

    def broken(audio):
        raise RuntimeError("mlx died")

    lt = live(mic, broken, sink)

    async def run():
        lt.start()
        mic.say(tone("alpha", 1))
        await settle()
        await lt.close()

    asyncio.run(run())
    assert sink.of(Partial) == []
