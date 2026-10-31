"""Barge-in in a simulated room: the mic hears Milo's playback through an echo path, plus the user.

Runs in real time (WavPlayer plays at sound-card speed into memory), so each test takes a couple of seconds.
"""

import asyncio
import time

import numpy as np

from milo.adapters.audio.wav_file import WavPlayer
from milo.core.types import STT_SAMPLE_RATE, Emotion, MiloState
from milo.services.barge_in import BargeIn, reference_for
from milo.services.echo import BLOCK, EchoCanceller, TalkDetector
from tests.fakes import FakeTranscriber
from tests.services.stack import Stack

RATE = STT_SAMPLE_RATE


def onset(audio: np.ndarray) -> float:
    """Seconds into `audio` where it first gets about as loud as it is on average: where the first syllable is."""
    blocks = audio[:len(audio) // BLOCK * BLOCK].reshape(-1, BLOCK)
    loud = np.sqrt(np.mean(blocks ** 2, axis=1)) > 0.5 * np.sqrt(np.mean(audio ** 2))
    held = loud[:-2] & loud[1:-1] & loud[2:]  # for 48 ms, so a click at the very start doesn't count
    return int(np.argmax(held)) * BLOCK / RATE


async def until(condition, seconds: float = 10.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        await asyncio.sleep(0.005)


def voiced(seconds: float, pitch: float, seed: int, level: float = 0.1, rate: int = RATE) -> np.ndarray:
    """Speech-like sound: a harmonic buzz with a moving formant, louder in syllables about 200 ms long."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * rate)) / rate
    f0 = pitch * (1 + 0.08 * np.sin(2 * np.pi * 0.7 * t + seed))
    phase = 2 * np.pi * np.cumsum(f0) / rate
    formant = 600 + 400 * np.sin(2 * np.pi * 1.3 * t + seed)
    buzz = sum(np.sin(k * phase) * np.exp(-((k * f0 - formant) / 500) ** 2) for k in range(1, 20))
    syllables = 0.2 + 0.8 * np.clip(np.sin(2 * np.pi * 2.5 * t + rng.uniform(0, 6)), 0, None) ** 0.3
    audio = buzz * syllables
    return (level * audio / (np.sqrt(np.mean(audio ** 2)) + 1e-9)).astype(np.float32)


class MiloVoice:
    """A voice that sounds like speech, so the echo canceller has something real to learn."""

    sample_rate = RATE

    def __init__(self):
        self.spoken = []

    def warm(self):
        pass

    def synthesize(self, text: str):
        self.spoken.append(text)
        return voiced(0.06 * len(text), 140, len(self.spoken))

    def cancel(self):
        pass


class Room:
    """A microphone in the room: the speaker's output through an echo path, plus the user, plus a little noise."""

    def __init__(self, player: WavPlayer, echo_gain: float = 0.3, delay_s: float = 0.02):  # -10 dB, a laptop
        self.player = player
        self.echo_gain = echo_gain
        self.delay_s = delay_s
        self.sounds: list[tuple[float, np.ndarray]] = []  # (monotonic time it starts, 16 kHz audio)
        self.started_at = None
        self._heard = np.zeros(0, np.float32)
        self.rng = np.random.default_rng(0)

    @property
    def active(self) -> bool:
        return self.started_at is not None

    def say(self, after_s: float, audio: np.ndarray) -> float:
        at = time.monotonic() + after_s
        self.sounds.append((at, audio))
        return at

    def start(self, on_level) -> None:
        self.started_at = time.monotonic()
        self._heard = np.zeros(0, np.float32)

    def stop(self):
        heard, self.started_at = self._heard, None
        return heard

    def peek(self, start: int = 0):
        if self.started_at is None:
            return np.zeros(0, np.float32)
        n = int((time.monotonic() - self.started_at) * RATE)
        if n > len(self._heard):
            t0 = self.started_at + len(self._heard) / RATE
            m = n - len(self._heard)
            rate, played = self.player.played(t0 - 1.0)
            chunk = self.echo_gain * reference_for(rate, played, t0 - self.delay_s, m)
            times = t0 + np.arange(m) / RATE
            for at, sound in self.sounds:
                idx = np.round((times - at) * RATE).astype(int)
                ok = (idx >= 0) & (idx < len(sound))
                chunk[ok] += sound[idx[ok]]
            chunk += self.rng.normal(size=m) * 1e-3
            self._heard = np.concatenate([self._heard, chunk.astype(np.float32)])
        return self._heard[start:].copy()


def stack(transcript: str = "wait, one thing", tmp_path=None):
    player = WavPlayer(tmp_path)
    s = Stack(output=player, voice=MiloVoice(), transcriber=FakeTranscriber(transcript))
    room = Room(player)
    barge_in = BargeIn(room, player, s.transcriber, s.listening._executor, s.ui, s.live_talk, s.speaker,
                       mic_busy=lambda: s.mic.active, poll_s=0.02)
    return s, room, barge_in


REPLY = "One two three four five, six seven eight nine ten. Eleven twelve thirteen, fourteen."


def test_milo_is_not_stopped_by_his_own_voice(tmp_path):
    s, room, barge_in = stack(tmp_path=tmp_path)

    async def run():
        watching = asyncio.create_task(barge_in.run())
        try:
            assert await s.speaker.say(REPLY, Emotion.NEUTRAL) is True
        finally:
            watching.cancel()

    asyncio.run(run())
    assert barge_in.barge_ins == 0 and s.voice.spoken[-1] == "fourteen."
    assert not room.active, "the mic closes when he stops talking"


def test_with_the_voice_off_the_mic_stays_closed(tmp_path):
    s, room, barge_in = stack(tmp_path=tmp_path)
    s.speaker.silent = True
    opened = []
    start = room.start
    room.start = lambda on_level: (opened.append(1), start(on_level))

    async def run():
        watching = asyncio.create_task(barge_in.run())
        try:
            assert await s.speaker.say("One two three, four five.", Emotion.NEUTRAL) is True
        finally:
            watching.cancel()

    asyncio.run(run())
    assert opened == [] and barge_in.barge_ins == 0


def test_the_user_talking_over_milo_stops_him_quickly_and_starts_a_turn(tmp_path):
    s, room, barge_in = stack(tmp_path=tmp_path)
    s.model.script.append(["[neutral] Sure, what is it?"])
    stopped = {}

    async def run():
        watching = asyncio.create_task(barge_in.run())
        speech = s.speaker.say(REPLY, Emotion.NEUTRAL)
        user = voiced(0.9, 210, 99, level=0.15)
        sounds = room.say(2.0, user)
        stopped["loud"] = onset(user)
        await until(lambda: s.speaker.held)
        stopped["after"] = time.monotonic() - sounds
        await asyncio.wait_for(speech, 5)
        await until(lambda: s.model.turns)
        await asyncio.wait_for(s.live_talk._turn, 5)
        watching.cancel()

    asyncio.run(run())
    assert barge_in.barge_ins == 1
    # After the user's first sound, and soon after their first syllable gets loud.
    assert 0 < stopped["after"] < stopped["loud"] + 0.3, f"Milo stopped {stopped['after']:.3f}s after the user started"
    assert s.model.turns[-1].endswith("wait, one thing")
    heard = s.transcriber.calls[-1]
    assert len(heard) > 0.9 * RATE, "the user's words from their first syllable on"
    assert MiloState.LISTENING in s.states() and MiloState.TRANSCRIBING in s.states()


def test_a_click_is_not_the_user_and_a_false_alarm_goes_on(tmp_path):
    s, room, barge_in = stack(transcript="", tmp_path=tmp_path)

    async def run():
        watching = asyncio.create_task(barge_in.run())
        speech = s.speaker.say(REPLY, Emotion.NEUTRAL)
        room.say(1.5, np.full(int(0.05 * RATE), 0.3, np.float32))  # a door, a click: too short to be speech
        room.say(3.0, voiced(0.3, 210, 98, level=0.1))  # a short sound that transcribes to nothing
        assert await asyncio.wait_for(speech, 15) is True
        watching.cancel()

    asyncio.run(run())
    assert barge_in.barge_ins == barge_in.false_alarms
    assert s.voice.spoken[-1].endswith("fourteen."), "he finished the reply"
    assert not s.model.turns


def test_a_transcript_of_milos_own_words_is_echo_and_he_goes_on(tmp_path):
    s, room, barge_in = stack(transcript="six seven eight nine", tmp_path=tmp_path)

    async def run():
        watching = asyncio.create_task(barge_in.run())
        speech = s.speaker.say(REPLY, Emotion.NEUTRAL)
        room.say(1.5, voiced(0.8, 210, 96, level=0.3))
        assert await asyncio.wait_for(speech, 15) is True
        watching.cancel()

    asyncio.run(run())
    assert barge_in.barge_ins >= 1 and barge_in.false_alarms == barge_in.barge_ins
    assert not s.model.turns, "Milo doesn't answer his own voice"


def test_the_talk_key_takes_the_turn_over_from_barge_in(tmp_path):
    s, room, barge_in = stack(tmp_path=tmp_path)

    async def run():
        watching = asyncio.create_task(barge_in.run())
        s.speaker.say(REPLY, Emotion.NEUTRAL)
        room.say(2.0, voiced(1.5, 210, 97, level=0.15))
        await until(lambda: s.speaker.held)
        s.mic.start(lambda level: None)  # the user pressed the talk key too
        await asyncio.sleep(0.3)
        assert not room.active, "barge-in let go of the turn"
        watching.cancel()
        s.speaker.interrupt()

    asyncio.run(run())
    assert not s.model.turns, "no second turn from barge-in"


def test_the_detector_ignores_echo_and_hears_the_user_over_it():
    milo = voiced(6.0, 140, 1)
    echo = 0.6 * np.concatenate([np.zeros(320), milo[:-320]])  # 20 ms later, a bit quieter
    user = np.zeros_like(milo)
    words = voiced(1.0, 220, 2, level=0.06)
    user[int(4 * RATE):int(5 * RATE)] = words
    starts = 4.0 + onset(words)
    detector = TalkDetector(EchoCanceller())
    fired = [i / RATE for i in range(0, len(milo) - BLOCK, BLOCK)
             if detector.process(echo[i:i + BLOCK] + user[i:i + BLOCK], milo[i:i + BLOCK])]
    assert fired and fired[0] > starts, "no false alarm on 4 s of echo"
    assert fired[0] - starts < 0.2, f"heard {fired[0] - starts:.3f}s after the user started"


def test_reference_for_lines_up_played_blocks_with_mic_samples():
    blocks = [(10.0, np.arange(24, dtype=float)), (10.001, np.arange(24, 48, dtype=float))]  # 24 kHz
    ref = reference_for(24_000, blocks, 10.0, 32)  # 2 ms of 16 kHz
    assert np.allclose(ref[:16], np.arange(16) * 1.5)
    assert np.allclose(reference_for(24_000, blocks, 11.0, 8), 0), "nothing played then"
