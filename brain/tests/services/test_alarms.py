"""Milo's alarms (ADR 0038).

The user's story: "Wake me at 7" should ring at 7, loud enough to wake them, and keep ringing until they stop it:
the talk key, a typed word, Stop, "okay, I'm up", or "five more minutes". Setting one never asks, shows a card
with Undo, and survives a restart of the brain. Asleep, the computer can't ring at all, which Milo says once.
Made-up connections and a fake clock; the voice and the speaker are fakes, so nothing sounds.
"""

import asyncio
from datetime import datetime
from pathlib import Path

from milo.adapters.connect.fake import World
from milo.core.events import ActionDone, Confirm, ListenCancel, ListenStart, StopAll, TextInput
from milo.core.types import ListenMode
from milo.services.alarms import Alarms, chime
from tests.fakes import FakeClock, FakeLiveModel, MemoryState
from tests.services.stack import Stack, settle, until


def stack(tmp_path: Path, *turns, **kw) -> Stack:
    World(tmp_path / "world").save({"events": [], "reminders": []})
    return Stack(model=FakeLiveModel(*turns), world=tmp_path / "world", home=tmp_path / "home", **kw)


async def say(s: Stack, *texts: str) -> None:
    for text in texts:
        await s.live_talk.start(text)
        await settle()
        await s.quick.idle()
        await s.undo.idle()
        await settle()


def said(s: Stack) -> str:
    return " ".join(s.voice.spoken)


def cards(s: Stack) -> list[ActionDone]:
    return s.sink.of(ActionDone)


def test_wake_me_at_7_sets_an_alarm_with_a_card_and_says_once_that_asleep_it_cant_ring(tmp_path):
    s = stack(tmp_path, ['[happy] <alarm at="2026-10-30T07:00"/>'], ['[happy] <alarm at="2026-10-30T07:30">Train</alarm>'],
              ["[happy] ok."])
    asyncio.run(say(s, "wake me at 7 tomorrow", "and at half past for the train", "thanks"))
    assert said(s) == ("Alarm set for tomorrow at 7 am. I can only ring while the Mac is awake. "
                       "Train: alarm set for tomorrow at 7:30 am. ok."), "the sleep line comes once"
    assert not s.sink.of(Confirm), "Milo's own business: never asks"
    first, second = cards(s)
    assert (first.kind, first.title, first.when, first.app) == ("alarm", "Alarm", "2026-10-30T07:00", "Milo")
    assert first.undo and second.title == "Train"
    assert [(a["at"], a["title"]) for a in s.alarm_state.data["alarms"]] == [("2026-10-30T07:00", ""),
                                                                            ("2026-10-30T07:30", "Train")]
    assert s.alarm_state.data["told_sleep"] is True
    assert "Alarms: a1 Fri 2026-10-30 07:00; a2 Fri 2026-10-30 07:30 Train." in s.model.turns[2]


def test_an_alarm_survives_a_restart_of_the_brain(tmp_path):
    state = MemoryState()
    clock = FakeClock()
    s = stack(tmp_path, ['[happy] <alarm at="2026-10-30T07:00"/>'], alarm_state=state, clock=clock)
    asyncio.run(say(s, "wake me at 7"))
    again = Alarms(state, s.speaker, clock)
    [alarm] = again.all()
    assert alarm.at == datetime(2026, 10, 30, 7, 0) and alarm.lang == "en"


def test_it_rings_with_a_sound_and_his_voice_until_the_talk_key_stops_it_then_snoozes(tmp_path):
    s = stack(tmp_path, ['[happy] <alarm at="2026-10-30T07:00"/>'], ['[happy] <alarm do="snooze" minutes="5"/>'],
              alarm_ring_s=30)

    async def run():
        await say(s, "wake me at 7")
        s.clock.advance(hours=22)  # 07:00 the next day
        s.alarms.check()
        await until(lambda: s.voice.spoken.count("It's time: your alarm at 7 am.") >= 2)
        assert s.alarms.ringing is not None and s.alarms.all() == []
        assert "Alarm ringing now: 07:00." in s.quick.today.render()[0]
        assert any(len(chime(s.voice.sample_rate)) in stream["chunks"] for stream in s.output.streams), \
            "a chime before the words"
        await s.brain.handle(ListenStart(ListenMode.TALK))
        assert s.alarms.ringing is None, "the talk key stops it at once"
        rounds = len(s.voice.spoken)
        await asyncio.sleep(0.05)
        assert len(s.voice.spoken) == rounds, "and it stays quiet"
        assert "Alarm that just rang: 07:00, stopped." in s.quick.today.render()[0]
        await s.brain.handle(ListenCancel())  # they speak, and their words come as a turn
        await say(s, "five more minutes")

    asyncio.run(run())
    assert said(s).endswith("I'll ring again in 5 minutes.")
    [again] = s.alarms.all()
    assert again.at == datetime(2026, 10, 30, 7, 5)
    card = cards(s)[-1]
    assert (card.kind, card.detail, card.when) == ("alarm", "Snoozed", "2026-10-30T07:05")
    assert s.alarms.recent() is None, "snoozed: no longer \"just rang\""


def test_okay_im_up_ends_it_and_typing_or_stop_end_it_too(tmp_path):
    s = stack(tmp_path, ['[happy] <alarm at="2026-10-29T09:30"/>'], ['[happy] <alarm do="stop"/>'],
              ['[happy] <alarm at="2026-10-29T10:00"/>'], ['[happy] <alarm do="stop"/>'], alarm_ring_s=30)

    async def ring_at(minutes: int):
        s.clock.advance(minutes=minutes)
        s.alarms.check()
        await until(lambda: s.alarms.ringing is not None and s.voice.spoken[-1].startswith("It's time"))

    async def run():
        await say(s, "alarm at half past nine")
        await ring_at(30)
        await s.brain.handle(TextInput("okay I'm up", True, ""))
        assert s.alarms.ringing is None, "a typed message is the user being there"
        await settle()
        await s.quick.idle()
        await settle()
        assert said(s).endswith("Alarm off.")
        await say(s, "another at ten")
        await ring_at(30)
        await s.brain.handle(StopAll())
        assert s.alarms.ringing is None, "the Stop button"
        await say(s, "stop")

    asyncio.run(run())
    assert said(s).endswith("Alarm off."), "the one Stop just ended counts as the one to stop"
    assert not s.sink.of(Confirm)


def test_nobody_stops_it_and_it_stops_by_itself(tmp_path):
    s = stack(tmp_path, ['[happy] <alarm at="2026-10-29T09:30"/>'], alarm_ring_s=0.1)

    async def run():
        await say(s, "alarm at half past nine")
        s.clock.advance(minutes=30)
        s.alarms.check()
        await until(lambda: s.alarms.ringing is not None)
        await until(lambda: s.alarms.ringing is None)

    asyncio.run(run())
    assert s.voice.spoken.count("It's time: your alarm at 9:30 am.") >= 1
    assert s.alarms.recent()[1] is False


def test_it_waits_while_the_user_speaks_into_the_microphone(tmp_path):
    s = stack(tmp_path, ['[happy] <alarm at="2026-10-29T09:30">Tea</alarm>'], alarm_ring_s=30)

    async def run():
        await say(s, "alarm at half past nine for the tea")
        s.mic.start(lambda level: None)
        s.clock.advance(minutes=30)
        s.alarms.check()
        await asyncio.sleep(0.05)
        assert s.alarms.ringing is not None and "It's time: Tea." not in s.voice.spoken
        s.mic.stop()
        await until(lambda: "It's time: Tea." in s.voice.spoken)
        s.alarms.hush()

    asyncio.run(run())


def test_cancel_my_alarm_takes_it_back_and_undo_sets_it_again(tmp_path):
    s = stack(tmp_path, ['[happy] <alarm at="2026-10-30T07:00"/>'], ['[happy] <alarm at="2026-10-30T08:00">Gym</alarm>'],
              ['[happy] <alarm do="cancel"/>'], ['[happy] <alarm do="cancel" title="gym"/>'], ["[happy] <undo/>"])
    asyncio.run(say(s, "wake me at 7", "gym alarm at 8", "cancel my alarm"))
    assert said(s).endswith("Which alarm: “tomorrow at 7 am” or “Gym”?"), "two are set: Milo asks which"
    asyncio.run(say(s, "cancel the gym alarm"))
    assert said(s).endswith("Gym: alarm is off.")
    assert [a.title for a in s.alarms.all()] == [""]
    card = cards(s)[-1]
    assert (card.kind, card.title, card.detail, card.when) == ("alarm", "Gym", "Cancelled", "2026-10-30T08:00")
    asyncio.run(say(s, "undo that"))
    assert [(a.title, a.at) for a in s.alarms.all()] == [("", datetime(2026, 10, 30, 7, 0)),
                                                          ("Gym", datetime(2026, 10, 30, 8, 0))]


def test_an_alarm_set_by_mistake_is_undone_and_none_set_says_so(tmp_path):
    s = stack(tmp_path, ['[happy] <alarm at="2026-10-30T07:00"/>'], ["[happy] <undo/>"],
              ['[happy] <alarm do="cancel"/>'], ['[happy] <alarm do="snooze"/>'])
    asyncio.run(say(s, "wake me at 7", "undo that"))
    assert s.alarms.all() == []
    asyncio.run(say(s, "cancel my alarm", "five more minutes"))
    assert said(s).endswith("No alarm is set. No alarm is ringing.")


def test_seven_oclock_at_night_means_the_next_seven_and_the_past_or_far_future_are_refused(tmp_path):
    s = stack(tmp_path, ['[happy] <alarm at="2026-10-29T07:00"/>'], ['[happy] <alarm at="06:30"/>'],
              ['[happy] <alarm at="2026-10-20T07:00"/>'], ['[happy] <alarm at="2026-11-20T07:00"/>'])
    asyncio.run(say(s, "wake me at 7", "and at 6:30", "an alarm last week", "an alarm next month"))
    assert [a.at for a in s.alarms.all()] == [datetime(2026, 10, 30, 6, 30), datetime(2026, 10, 30, 7, 0)], \
        "at 9 am, today's 7:00 has passed: the model meant tomorrow's"
    assert said(s).endswith("That didn't work: that time has passed already. "
                            "That didn't work: an alarm can be up to a week ahead.")


def test_german(tmp_path):
    s = stack(tmp_path, ['[happy] <alarm at="2026-10-29T09:30"/>'], ['[happy] <alarm do="snooze" minutes="10"/>'],
              alarm_ring_s=30)

    async def run():
        await say(s, "stell mir einen Wecker auf halb zehn")
        s.clock.advance(minutes=30)
        s.alarms.check()
        await until(lambda: "Es ist so weit: dein Wecker um 09:30." in s.voice.spoken)
        await s.brain.handle(ListenStart(ListenMode.TALK))
        await s.brain.handle(ListenCancel())
        await say(s, "noch zehn Minuten bitte")

    asyncio.run(run())
    assert said(s).startswith("Wecker gestellt, heute um 09:30.")
    assert said(s).endswith("Ich klingle in 10 Minuten wieder.")


def test_an_alarm_the_computer_slept_through_doesnt_ring_late_and_milo_says_he_missed_it(tmp_path):
    s = stack(tmp_path, ['[happy] <alarm at="2026-10-30T07:00"/>'])

    async def run():
        await say(s, "wake me at 7")
        s.clock.advance(hours=24)  # woke at 9:00
        s.alarms.check()
        await settle()

    asyncio.run(run())
    assert said(s).endswith("I missed your alarm at 7 am: the Mac was asleep.")
    assert s.alarms.ringing is None and s.alarms.all() == []
    assert "It's time" not in said(s)


def test_the_loop_watches_the_wall_clock(tmp_path):
    """The loop's own clock stops while the computer sleeps; the wall clock doesn't."""
    s = stack(tmp_path, ['[happy] <alarm at="2026-10-29T09:30"/>'], alarm_ring_s=30)

    async def run():
        await say(s, "alarm at half past nine")
        loop = asyncio.create_task(s.alarms.run())
        await asyncio.sleep(0.03)
        assert s.alarms.ringing is None
        s.clock.advance(minutes=30)
        await until(lambda: s.alarms.ringing is not None)
        s.alarms.hush()
        loop.cancel()

    asyncio.run(run())
