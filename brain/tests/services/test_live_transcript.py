import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from milo.adapters.text.fillers import FillerCleaner
from milo.core.events import Dictation, Partial
from milo.core.types import STT_SAMPLE_RATE, Audio, Interrupted
from milo.services.dictation import TypedDictation
from milo.services.live_transcript import LiveTranscript, PauseSegmenter, join_phrases
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
    start, end, speech_end = cuts[0]
    assert start == 0
    assert 1.2 * SR <= end <= 1.5 * SR, "about pause/2 into the silence"
    assert 0.98 * SR <= speech_end <= 1.02 * SR
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
    start, end, _ = cuts[0]
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


def test_the_segmenter_knows_where_speech_ended_and_how_long_it_has_been_quiet():
    seg = PauseSegmenter()
    feed_in_blocks(seg, np.concatenate([quiet(0.5), tone("alpha", 1), quiet(0.4)]))
    assert 1.45 * SR <= seg.speech_end <= 1.53 * SR
    assert 0.35 <= seg.silence_s <= 0.42
    assert feed_in_blocks(seg, tone("bravo", 0.3)) == [] and seg.silence_s == 0


def test_a_long_phrase_closes_at_a_shorter_pause():
    seg = PauseSegmenter(pause_s=0.7, long_s=8, long_pause_s=0.4)
    short = np.concatenate([tone("alpha", 3), quiet(0.5), tone("bravo", 3)])
    assert feed_in_blocks(seg, short) == [], "half a second is no pause early in a phrase"
    cuts = feed_in_blocks(seg, np.concatenate([tone("charlie", 3), quiet(0.5), tone("delta", 1)]))
    assert len(cuts) == 1
    assert hear(np.concatenate([short, tone("charlie", 3), quiet(0.5)])[cuts[0][0]:cuts[0][1]]) == "alpha bravo charlie"


# ---- TypedDictation


def test_typed_phrases_are_cleaned_one_by_one_and_spaced():
    sink, history = RecordingSink(), MemoryHistory()
    typed = TypedDictation(FillerCleaner(["en"]), history, sink)
    assert typed.add("um so the plan is") == "So the plan is"
    assert typed.add("uh") == ""
    assert typed.add("we ship on friday.") == "we ship on friday.", "goes on mid-sentence: no capital"
    assert typed.add("Then we rest.") == "Then we rest."
    assert typed.add("and party") == "And party", "a new sentence starts with a capital"
    typed.finish("Notes")
    assert sink.of(Dictation) == [Dictation("So the plan is"), Dictation(" we ship on friday."),
                                  Dictation(" Then we rest."), Dictation(" And party")]
    assert history.entries == [("So the plan is we ship on friday. Then we rest. And party", "Notes")]


def test_nothing_typed_leaves_no_history():
    history = MemoryHistory()
    TypedDictation(FillerCleaner(["en"]), history, RecordingSink()).finish("Notes")
    assert history.entries == []


# ---- join_phrases


def test_phrases_join_with_spaces_and_a_sentence_that_goes_on_loses_its_stop():
    assert join_phrases(["Hi Anna.", "", "Thanks for the reply.", "especially the numbers.", "Bye..."]) == \
        "Hi Anna. Thanks for the reply especially the numbers. Bye..."
    assert join_phrases(["Wait...", "then go"]) == "Wait... then go"
    assert join_phrases([]) == ""


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


class HearingStt:
    """The full model hears in capitals, the preview model in lower case, so a test can tell which one
    produced a text. `log` records every pass in order: ("full", "quick" or "preview", seconds of audio,
    before). With `block`, full-model passes wait for `release` (for a thread executor); interrupt() ends
    a waiting pass with Interrupted."""

    def __init__(self, block: bool = False, fail_preview: bool = False):
        self.log: list[tuple[str, float, str]] = []
        self.release = threading.Event()
        self.entered = threading.Event()
        self.block = block
        self.fail_preview = fail_preview
        self.running = 0
        self.max_running = 0
        self.interrupted = 0
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def warm(self) -> None:
        pass

    def transcribe(self, audio: Audio, before: str = "", *, quick: bool = False) -> str:
        with self._lock:
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        self.log.append(("quick" if quick else "full", len(audio) / SR, before))
        self.entered.set()
        try:
            if self.block:
                self.release.wait(5)
            if self._stop.is_set():
                self._stop.clear()
                self.interrupted += 1
                raise Interrupted()
        finally:
            with self._lock:
                self.running -= 1
        return hear(audio).upper()

    def interrupt(self) -> None:
        self._stop.set()
        self.release.set()

    def preview(self, audio: Audio) -> str:
        with self._lock:
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        self.log.append(("preview", len(audio) / SR, ""))
        with self._lock:
            self.running -= 1
        if self.fail_preview:
            raise RuntimeError("mlx died")
        return hear(audio)

    def full(self) -> list[tuple[float, str]]:
        """Passes of the full model, quick or not."""
        return [(secs, before) for kind, secs, before in self.log if kind != "preview"]

    def kinds(self) -> list[str]:
        return [kind for kind, _, _ in self.log]


def live(mic, stt, sink, on_phrase=None, executor=None, **kw):
    kw = {"poll_s": 0, "gap_s": 0, "min_new_s": 0.5, **kw}
    return LiveTranscript(mic, stt, executor or InlineExecutor(), sink, PauseSegmenter(), on_phrase=on_phrase, **kw)


def test_closed_phrases_are_committed_by_the_full_model_while_the_open_one_is_previewed():
    mic, stt, sink = GrowingMic(), HearingStt(), RecordingSink()
    lt = live(mic, stt, sink)

    async def run():
        lt.start()
        mic.say(tone("alpha", 1))
        await settle()
        mic.say(quiet(1), tone("bravo", 1.5))
        await settle()
        assert lt.phrases == ["ALPHA"], "committed at the pause, by the full model"
        mic.say(quiet(1), tone("charlie", 2))
        await settle()
        return await lt.finish(mic.stop())

    assert asyncio.run(run()) == "ALPHA BRAVO CHARLIE"
    shown = [e.text for e in sink.of(Partial)]
    assert shown[0] == "alpha"
    assert "ALPHA bravo" in shown and "ALPHA BRAVO charlie" in shown
    assert sink.of(Dictation) == []
    # No pass ever reads the whole recording: each covers one phrase plus a little silence.
    assert max(secs for _, secs, _ in stt.log) <= 2.8 < len(mic.audio) / SR


def test_each_phrase_gets_the_text_before_it():
    mic, stt, sink = GrowingMic(), HearingStt(), RecordingSink()
    lt = live(mic, stt, sink)

    async def run():
        lt.start()
        mic.say(tone("alpha", 1), quiet(1), tone("bravo", 1), quiet(1), tone("charlie", 1))
        await settle()
        return await lt.finish(mic.stop())

    assert asyncio.run(run()) == "ALPHA BRAVO CHARLIE"
    assert [before for _, before in stt.full()] == ["", "ALPHA", "ALPHA BRAVO"]


def test_release_after_falling_silent_needs_no_pass_at_all():
    mic, stt, sink = GrowingMic(), HearingStt(), RecordingSink()
    lt = live(mic, stt, sink, settle_s=0.3)

    async def run():
        lt.start()
        mic.say(tone("alpha", 1), quiet(1), tone("bravo", 1.5), quiet(0.4))
        await settle()
        assert [e.text for e in sink.of(Partial)][-1] == "ALPHA BRAVO", "the guess shows as soon as it is there"
        passes = len(stt.log)
        text = await lt.finish(mic.stop())
        assert len(stt.log) == passes, "the guess for the open phrase is the end"
        return text

    assert asyncio.run(run()) == "ALPHA BRAVO"


def test_speaking_again_drops_the_guess():
    mic, stt, sink = GrowingMic(), HearingStt(), RecordingSink()
    lt = live(mic, stt, sink, settle_s=0.3)

    async def run():
        lt.start()
        mic.say(tone("alpha", 1), quiet(0.4))
        await settle()
        mic.say(tone("bravo", 0.6))
        await settle()
        return await lt.finish(mic.stop())

    assert asyncio.run(run()) == "ALPHA BRAVO"
    assert [secs for secs, _ in stt.full()][-1] >= 2.0, "the last pass covers the whole open phrase again"


def test_while_recording_a_phrase_is_committed_at_full_accuracy_even_after_a_guess():
    mic, stt, sink = GrowingMic(), HearingStt(), RecordingSink()
    lt = live(mic, stt, sink, settle_s=0.3)

    async def run():
        lt.start()
        mic.say(tone("alpha", 1), quiet(0.4))
        await settle()
        mic.say(quiet(0.6), tone("bravo", 1))
        await settle()
        assert lt.phrases == ["ALPHA"]
        return await lt.finish(mic.stop())

    assert asyncio.run(run()) == "ALPHA BRAVO"
    assert [k for k in stt.kinds() if k != "preview"] == ["quick", "full", "quick"], \
        "guess, then the commit at full accuracy, then the tail after the release"


def test_type_mode_hands_over_each_phrase_in_order_and_previews_only_the_open_one():
    mic, stt, sink = GrowingMic(), HearingStt(), RecordingSink()
    phrases: list[str] = []
    lt = live(mic, stt, sink, phrases.append)

    async def run():
        lt.start()
        mic.say(tone("alpha", 1), quiet(1))
        await settle()
        assert phrases == ["ALPHA"], "handed over while the user keeps talking"
        mic.say(tone("bravo", 1), quiet(1), tone("charlie", 1))
        await settle()
        shown = [e.text for e in sink.of(Partial)][-1]
        return shown, await lt.finish(mic.stop())

    shown, text = asyncio.run(run())
    assert shown == "charlie", "the live words show only what isn't typed yet"
    assert phrases == ["ALPHA", "BRAVO", "CHARLIE"] and text == "ALPHA BRAVO CHARLIE"


def test_commits_and_guesses_go_before_previews():
    mic, stt, sink = GrowingMic(), HearingStt(), RecordingSink()
    lt = live(mic, stt, sink)

    async def run():
        lt.start()
        mic.say(tone("alpha", 1))
        await settle()
        mic.say(quiet(1), tone("bravo", 1))
        await settle()
        await lt.finish(mic.stop())

    asyncio.run(run())
    kinds = [kind for kind, _, _ in stt.log]
    assert kinds[:3] == ["preview", "full", "preview"], kinds


def test_no_preview_starts_once_the_speaker_falls_quiet():
    mic, stt, sink = GrowingMic(), HearingStt(), RecordingSink()
    lt = live(mic, stt, sink, settle_s=0.4, min_new_s=0.1)

    async def run():
        lt.start()
        mic.say(tone("alpha", 1))
        await settle()
        mic.say(quiet(0.3))  # quiet for longer than settle/2, not yet settle: the guess is about to come
        await settle()
        lt.abort()

    asyncio.run(run())
    assert [kind for kind, _, _ in stt.log] == ["preview"]


def test_previews_leave_the_gpu_idle_for_a_gap_but_commits_do_not_wait():
    mic, stt, sink = GrowingMic(), HearingStt(), RecordingSink()
    lt = live(mic, stt, sink, gap_s=60)

    async def run():
        lt.start()
        mic.say(tone("alpha", 1))
        await settle()
        mic.say(quiet(1), tone("bravo", 1))
        await settle()
        lt.abort()

    asyncio.run(run())
    assert [kind for kind, _, _ in stt.log] == ["preview", "full"]


def test_the_release_interrupts_a_commit_in_flight_and_does_the_rest_quickly_in_order():
    mic, stt, sink = GrowingMic(), HearingStt(block=True), RecordingSink()
    executor = ThreadPoolExecutor(1)
    phrases: list[str] = []
    lt = live(mic, stt, sink, phrases.append, executor=executor, poll_s=0.01)

    async def run():
        mic.say(tone("alpha", 1), quiet(1), tone("bravo", 0.5))
        lt.start()
        while not stt.entered.is_set():
            await asyncio.sleep(0.01)
        stt.block = False  # passes after the release run straight through
        return await lt.finish(mic.stop())

    assert asyncio.run(run()) == "ALPHA BRAVO"
    executor.shutdown()
    assert phrases == ["ALPHA", "BRAVO"]
    assert stt.kinds() == ["full", "quick", "quick"], "the commit in flight was interrupted and done again quickly"
    assert stt.interrupted == 1


def test_never_more_than_one_pass_in_flight():
    mic, stt, sink = GrowingMic(), HearingStt(), RecordingSink()
    executor = ThreadPoolExecutor(4)
    lt = live(mic, stt, sink, executor=executor, poll_s=0.005, min_new_s=0.05)

    async def run():
        lt.start()
        for word in ("alpha", "bravo", "charlie", "delta"):
            for _ in range(5):
                mic.say(tone(word, 0.2))
                await asyncio.sleep(0.01)
            mic.say(quiet(0.8))
            await asyncio.sleep(0.02)
        return await lt.finish(mic.stop())

    assert asyncio.run(run()) == "ALPHA BRAVO CHARLIE DELTA"
    executor.shutdown()
    assert len(stt.log) > 4
    assert stt.max_running == 1


def test_abort_stops_without_handing_over_anything_more():
    mic, stt, sink = GrowingMic(), HearingStt(), RecordingSink()
    phrases: list[str] = []
    lt = live(mic, stt, sink, phrases.append)

    async def run():
        lt.start()
        lt.abort()
        mic.say(tone("alpha", 1), quiet(1))
        await settle()

    asyncio.run(run())
    assert phrases == [] and stt.log == []


def test_a_failing_live_pass_ends_live_updates_and_the_release_still_transcribes():
    mic, stt, sink = GrowingMic(), HearingStt(fail_preview=True), RecordingSink()
    lt = live(mic, stt, sink)

    async def run():
        lt.start()
        mic.say(tone("alpha", 1))
        await settle()
        mic.say(quiet(1), tone("bravo", 1))
        await settle()
        return await lt.finish(mic.stop())

    assert asyncio.run(run()) == "ALPHA BRAVO"
    assert sink.of(Partial)[-1] == Partial("ALPHA BRAVO")


def test_a_voice_too_quiet_for_the_segmenter_still_gets_one_pass_over_everything():
    mic, stt, sink = GrowingMic(), HearingStt(), RecordingSink()
    lt = live(mic, stt, sink)

    async def run():
        lt.start()
        mic.say(quiet(2))
        await settle()
        return await lt.finish(mic.stop())

    assert asyncio.run(run()) == ""
    assert stt.log == [("quick", 2.0, "")]
