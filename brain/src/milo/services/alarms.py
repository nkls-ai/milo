"""Milo's alarms (ADR 0038): "wake me at 7" rings at 7, with a sound and his voice, until the user stops it.

The talker writes `<alarm at="2026-11-01T07:00"/>` and QuickActions sets it here. Alarms are kept in
`state/alarms.json`, so they survive a restart of the brain, and `run` watches the wall clock rather than a timer on
the event loop: the loop's clock stops while the computer sleeps, the wall clock doesn't, so an alarm due while it
slept is found the moment it wakes.

Ringing is a chime and one line ("It's time: your alarm at 7 am."), again every `gap_s`, for at most `ring_s`. It
rings over whatever Milo was saying and whatever the user is doing, except while they speak into the microphone.
It stops when the user presses a Milo key, types to him or presses Stop (`hush`, from Brain), says "stop" or "I'm up"
(`<alarm do="stop"/>`) or "five more minutes" (`<alarm do="snooze"/>`, which sets it again).

Nothing can ring while the computer sleeps: waking it takes root (`pmset schedule wake`). An alarm found more than
`late_s` after its time doesn't ring; Milo says once that he missed it. The first time an alarm is set more than an
hour ahead he says so in one short line (`told`).
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from milo.core.ports import Clock, StateFile
from milo.core.times import local
from milo.core.types import Emotion
from milo.core.words import dates, say

from .speaker import Speaker, Utterance
from .transcript import Transcript, unrecorded

log = logging.getLogger("milo.alarms")

RING_S = 4 * 60.0
"""How long an alarm nobody stops rings."""
GAP_S = 12.0
"""The quiet between two rings."""
LATE_S = 10 * 60.0
"""An alarm found later than this after its time (the computer slept, Milo wasn't running) doesn't ring."""
TICK_S = 30.0
"""How often `run` looks at the wall clock when no alarm is near."""
SNOOZE_MIN = 5
RECENT_S = 30 * 60.0
"""How long after it rang an alarm can still be snoozed or said to be off."""
POLL_S = 0.1
FAR_S = 3600.0
"""An alarm further ahead than this gets the line about sleep, the first time."""


@dataclass(frozen=True)
class Alarm:
    id: str
    at: datetime
    title: str = ""
    lang: str = "en"


class Alarms:
    """`state` keeps the alarms (state/alarms.json); `quiet` says the user is speaking into the microphone, so a
    ring waits; `computer` is what the platform calls the machine ("Mac")."""

    def __init__(self, state: StateFile, speaker: Speaker, clock: Clock, *, transcript: Transcript | None = None,
                 quiet: Callable[[], bool] = lambda: False, computer: str = "computer", ring_s: float = RING_S,
                 gap_s: float = GAP_S, late_s: float = LATE_S, tick_s: float = TICK_S, poll_s: float = POLL_S):
        self._state = state
        self._speaker = speaker
        self._clock = clock
        self._transcript = transcript or unrecorded()
        self._quiet = quiet
        self.computer = computer
        self._ring_s, self._gap_s, self._late_s, self._tick_s, self._poll_s = ring_s, gap_s, late_s, tick_s, poll_s
        self._alarms: dict[str, Alarm] = {}
        data = state.load()
        for item in data.get("alarms") or []:
            try:
                alarm = Alarm(str(item["id"]), local(item["at"]), str(item.get("title") or ""),
                              str(item.get("lang") or "en"))
            except (KeyError, TypeError, ValueError):
                log.warning("skipping an alarm I can't read in alarms.json")
                continue
            self._alarms[alarm.id] = alarm
        self._told = bool(data.get("told_sleep"))
        self.ringing: Alarm | None = None
        self._rang: tuple[Alarm, datetime] | None = None
        """The alarm that rang last and when it stopped ringing."""
        self._utterance: Utterance | None = None
        self._hushed = asyncio.Event()
        self._wake = asyncio.Event()
        self._rings: set[asyncio.Task] = set()

    # ---- what QuickActions and Today use

    def all(self) -> list[Alarm]:
        """The alarms still to ring, soonest first."""
        return sorted(self._alarms.values(), key=lambda a: a.at)

    def set(self, at: datetime, title: str = "", lang: str = "en") -> Alarm:
        alarm = Alarm("al-" + uuid.uuid4().hex[:8], at.replace(second=0, microsecond=0), title, lang)
        self._alarms[alarm.id] = alarm
        self._save()
        self._wake.set()
        return alarm

    def cancel(self, id: str) -> Alarm | None:
        alarm = self._alarms.pop(id, None)
        if alarm is not None:
            self._save()
        return alarm

    def first_far(self, alarm: Alarm) -> bool:
        """True once: the first alarm set more than an hour ahead, so Milo says it can't ring while asleep."""
        if self._told or (alarm.at - self._clock.now()).total_seconds() < FAR_S:
            return False
        self._told = True
        self._save()
        return True

    def recent(self) -> tuple[Alarm, bool] | None:
        """The alarm ringing now (True), or the one that rang in the last `RECENT_S` (False), for <today>, a snooze
        and a stop."""
        if self.ringing is not None:
            return self.ringing, True
        if self._rang is not None and (self._clock.now() - self._rang[1]).total_seconds() <= RECENT_S:
            return self._rang[0], False
        return None

    def hush(self) -> bool:
        """Stop the ringing now: a Milo key, a typed message, the Stop button, "stop". Whether one rang."""
        alarm = self.ringing
        if alarm is None:
            return False
        log.info("the alarm was stopped")
        self.ringing = None
        self._rang = (alarm, self._clock.now())
        self._hushed.set()
        if self._utterance is not None and self._speaker.current is self._utterance:
            self._speaker.interrupt()
        return True

    def forget_recent(self) -> None:
        """A stop or a snooze dealt with the one that rang: it is no longer "just rang"."""
        self._rang = None

    # ---- ringing

    async def run(self) -> None:
        """Ring each alarm when its time comes, forever."""
        while True:
            self.check()
            self._wake.clear()
            # While one rings, the next due waits for it to end (`_wake`), not in a busy loop.
            ahead = [] if self._busy_ringing() else [(a.at - self._clock.now()).total_seconds()
                                                       for a in self._alarms.values()]
            wait = min([self._tick_s, *ahead])
            try:
                await asyncio.wait_for(self._wake.wait(), max(0.05, wait))
            except TimeoutError:
                pass

    def check(self) -> None:
        """Ring what is due; say once what was missed. One alarm rings at a time; the next waits its turn."""
        now = self._clock.now()
        for alarm in self.all():
            if alarm.at > now:
                break
            late = (now - alarm.at).total_seconds()
            if late <= self._late_s and self._busy_ringing():
                break  # rings after the one ringing now
            self._alarms.pop(alarm.id, None)
            self._save()
            if late > self._late_s:
                log.info("an alarm was missed by %.0f minutes", late / 60)
                text = say("acts.alarm_missed", alarm.lang, time=_clock_time(alarm.at, alarm.lang),
                           computer=self.computer)
                self._transcript.say(text, Emotion.CONCERNED)
                self._keep(self._speaker.say(text, Emotion.CONCERNED, speak=not self._quiet()))
                continue
            self._keep(asyncio.create_task(self._ring(alarm)))

    def _busy_ringing(self) -> bool:
        return self.ringing is not None or any(not t.done() for t in self._rings)

    def _keep(self, task: asyncio.Task) -> None:
        self._rings.add(task)
        task.add_done_callback(self._rings.discard)

    async def _ring(self, alarm: Alarm) -> None:
        loop = asyncio.get_running_loop()
        self.ringing = alarm
        self._hushed.clear()
        log.info("an alarm rings")
        line = say("acts.alarm_ring_named" if alarm.title else "acts.alarm_ring", alarm.lang, title=alarm.title,
                   clock=dates.clock(alarm.at, alarm.lang))
        self._transcript.say(line, Emotion.EXCITED)
        until = loop.time() + self._ring_s
        try:
            while self.ringing is alarm and loop.time() < until:
                if self._quiet():  # the user speaks into the microphone: not over them
                    await asyncio.sleep(self._poll_s)
                    continue
                u = self._utterance = self._speaker.utterance(Emotion.EXCITED)
                u.interject("", chime(self._speaker.voice.sample_rate))
                u.add(line)
                await u.finish()
                if self.ringing is not alarm:
                    break
                try:
                    await asyncio.wait_for(self._hushed.wait(), self._gap_s)
                except TimeoutError:
                    pass
        finally:
            self._utterance = None
            if self.ringing is alarm:
                log.info("nobody stopped the alarm; it stops by itself")
                self.ringing = None
                self._rang = (alarm, self._clock.now())
            self._wake.set()  # the next one due may ring now

    def _save(self) -> None:
        try:
            self._state.save({"alarms": [{"id": a.id, "at": a.at.isoformat(timespec="minutes"), "title": a.title,
                                          "lang": a.lang} for a in self.all()], "told_sleep": self._told})
        except OSError:
            log.exception("could not keep the alarms")


def chime(sample_rate: int, *, rings: int = 3) -> np.ndarray:
    """A bright two-note chime, `rings` times: about 0.8 s each, soft at its edges so it doesn't click."""
    out = []
    for _ in range(rings):
        for freq, length in ((1046.5, 0.18), (1318.5, 0.32)):  # C6, E6
            t = np.arange(int(sample_rate * length)) / sample_rate
            tone = np.sin(2 * math.pi * freq * t) + 0.3 * np.sin(4 * math.pi * freq * t)
            fade = np.minimum(1.0, np.minimum(t, length - t) / 0.01)
            out.append((0.35 * tone * fade * np.exp(-3 * t)).astype(np.float32))
        out.append(np.zeros(int(sample_rate * 0.3), np.float32))
    return np.concatenate(out)


def _clock_time(t: datetime, lang: str) -> str:
    """"7 am", "7 Uhr": a clock time without "at"."""
    return dates.clock(t, lang).split(" ", 1)[1]
