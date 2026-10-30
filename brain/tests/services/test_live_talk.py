import asyncio
from datetime import datetime

from milo.core.events import Bubble, EmotionChanged, Heard, Level, StateChanged
from milo.core.types import Emotion, HarnessError, MiloState, Reminder, Usage
from milo.services.live_talk import HICCUP
from tests.fakes import FakeAudioOutput, FakeHarness, FakeLiveModel, ListReminders, MemoryProfile
from tests.services.stack import Stack, settle


def talk(s: Stack, *texts: str) -> None:
    async def run():
        for text in texts:
            await s.live_talk.start(text)
            await settle()

    asyncio.run(run())


def test_a_turn_streams_into_speech_and_records_usage():
    s = Stack(model=FakeLiveModel(["[happy] Sure thing, ", "it is nine. ", "Anything else?"]))
    s.context.update("Xcode", 0)
    talk(s, "what time is it")
    flow = [e for e in s.sink.events if not isinstance(e, Level)]
    assert flow == [
        Heard("what time is it"),
        StateChanged(MiloState.THINKING),
        EmotionChanged(Emotion.THINKING),
        EmotionChanged(Emotion.HAPPY),
        StateChanged(MiloState.SPEAKING),
        Bubble("Sure thing, it is nine."),
        Bubble("Sure thing, it is nine. Anything else?"),
        StateChanged(MiloState.IDLE),
    ]
    assert s.voice.spoken == ["Sure thing, it is nine.", "Anything else?"]
    assert s.model.turns == ["[Thursday 2026-10-29 09:00, frontmost app: Xcode]\nwhat time is it"]
    assert s.ledger.entries == [("chat", "fake-live", Usage(600, 0, 3))]
    assert not s.live_talk.busy and not s.ui.thinking


def test_first_speech_starts_before_the_stream_finishes():
    gate = asyncio.Event()
    s = Stack(model=FakeLiveModel(["[excited] Oh, that is a great question, ", "let me think."], gate=gate))

    async def run():
        turn = s.live_talk.start("hi")
        await settle()
        assert s.voice.spoken == ["Oh, that is a great question,"], "spoken while the model is still paused"
        assert s.ui.state is MiloState.SPEAKING and s.live_talk.busy
        gate.set()
        await turn

    asyncio.run(run())
    assert s.voice.spoken == ["Oh, that is a great question,", "let me think."]
    assert len(s.output.streams) == 1


def test_the_system_prompt_has_persona_rules_profile_and_open_reminders():
    s = Stack(profile=MemoryProfile("# About the user\n- Name: Niklas\n"),
              reminders=ListReminders(Reminder("a", datetime(2026, 10, 30, 9, 0), "Call mom", False),
                                      Reminder("b", datetime(2026, 10, 28, 9, 0), "Old one", True)))
    talk(s, "hi")
    [system] = s.model.system_prompts
    assert system.startswith("You are Milo, a test persona.")
    assert "[happy]" in system and "<remember>" in system and "<task>" in system
    assert "- Name: Niklas" in system
    assert "- 2026-10-30 09:00 Call mom" in system and "Old one" not in system


def test_conversation_continues_and_restarts_after_idle_with_a_fresh_profile():
    s = Stack(model=FakeLiveModel(["[happy] Noted. <remember>Drinks tea</remember>"], ["[happy] Hi."],
                                  ["[happy] Hi again."]))

    async def run():
        await s.live_talk.start("I drink tea")
        s.clock.advance(seconds=599)
        await s.live_talk.start("hello")
        s.clock.advance(seconds=601)
        await s.live_talk.start("hello later")

    asyncio.run(run())
    assert len(s.model.system_prompts) == 2
    assert "Drinks tea" not in s.model.system_prompts[0]
    assert "- Drinks tea" in s.model.system_prompts[1]


def test_a_warmed_conversation_is_kept_unless_its_prompt_changed():
    s = Stack()

    async def run():
        await s.live_talk.warm()
        s.clock.advance(hours=2)
        await s.live_talk.start("hi")
        s.profile.remember("Likes jazz")
        s.clock.advance(hours=2)
        await s.live_talk.warm()

    asyncio.run(run())
    assert len(s.model.system_prompts) == 2, "warm, then a restart only after idle"


def test_persona_edits_apply_on_the_next_conversation():
    s = Stack()

    async def run():
        await s.live_talk.warm()
        s.persona = "You are Milo, now grumpy."
        await s.live_talk.start("hi")

    asyncio.run(run())
    assert s.model.system_prompts[-1].startswith("You are Milo, now grumpy.")


def test_tags_are_applied_and_never_spoken():
    s = Stack(model=FakeLiveModel(["[happy] On it, I will remind you. ",
                                   "<remember>Has a dentist, Dr. Lee</remember>",
                                   "<reminder>2026-10-30 09:00 Call the dentist</reminder>",
                                   "<task>Find Dr. Lee's phone number</task>"]),
              harness=FakeHarness("Dr. Lee is at 555-0100."))

    async def run():
        await s.live_talk.start("remind me to call the dentist tomorrow at nine")
        await s.tasks.idle()
        await settle()

    asyncio.run(run())
    assert s.voice.spoken[0] == "On it, I will remind you."
    assert not any("<" in text or "Lee's" in text for text in s.voice.spoken[:1])
    assert s.profile.facts == ["Has a dentist, Dr. Lee"]
    assert [(r.due, r.text) for r in s.reminders.items] == [(datetime(2026, 10, 30, 9, 0), "Call the dentist")]
    assert s.harness.calls[0][0].endswith("\nFind Dr. Lee's phone number")
    assert s.voice.spoken[-1] == "Dr. Lee is at 555-0100.", "the task result is spoken after the turn"
    assert [src for src, _, _ in s.ledger.entries] == ["chat", "task"]


def test_a_finished_task_result_reaches_the_next_turn():
    s = Stack(model=FakeLiveModel(["[happy] On it. <task>check the weather</task>"], ["[happy] Sunny."]),
              harness=FakeHarness("It's sunny."))

    async def run():
        await s.live_talk.start("weather?")
        await s.tasks.idle()
        await s.live_talk.start("so?")

    asyncio.run(run())
    assert "[Background task done: check the weather -> It's sunny.]\nso?" in s.model.turns[1]


def test_interrupt_mid_reply_stops_the_model_and_the_audio_at_once():
    gate = asyncio.Event()
    s = Stack(model=FakeLiveModel(["[happy] Let me tell you a story, ", "a long one. <remember>x</remember>"],
                                  gate=gate),
              output=FakeAudioOutput(block=True))

    async def run():
        turn = s.live_talk.start("tell me a story")
        await settle()
        assert s.ui.state is MiloState.SPEAKING
        s.live_talk.interrupt()
        assert s.ui.state is MiloState.IDLE and not s.ui.speaking and not s.ui.thinking
        await asyncio.gather(turn, return_exceptions=True)
        await settle()
        assert turn.cancelled()

    asyncio.run(run())
    assert s.model.interrupts == 1 and s.output.interrupts == 1
    assert s.voice.spoken == ["Let me tell you a story,"]
    assert s.profile.facts == [], "an interrupted reply applies nothing"
    assert s.states() == [MiloState.THINKING, MiloState.SPEAKING, MiloState.IDLE]


def test_a_new_turn_interrupts_the_running_one():
    gate = asyncio.Event()
    s = Stack(model=FakeLiveModel(["[happy] The first answer goes on, ", "and on."], ["[sad] Second."], gate=gate))

    async def run():
        first = s.live_talk.start("one")
        await settle()
        gate.set()
        second = s.live_talk.start("two")
        await asyncio.gather(first, second, return_exceptions=True)
        await settle()

    asyncio.run(run())
    assert s.model.interrupts == 1
    assert s.voice.spoken == ["The first answer goes on,", "Second."]
    assert s.bubbles()[-1] == "Second."
    assert s.ui.state is MiloState.IDLE


def test_harness_error_shows_confused_and_starts_fresh_next_turn():
    s = Stack(model=FakeLiveModel(HarnessError("claude died", transient=True), ["[happy] Back."]))
    talk(s, "hi", "again")
    assert s.bubbles() == [HICCUP, "Back."]
    assert EmotionChanged(Emotion.CONFUSED) in s.sink.events
    assert s.states() == [MiloState.THINKING, MiloState.IDLE, MiloState.THINKING, MiloState.SPEAKING,
                          MiloState.IDLE]
    assert len(s.model.system_prompts) == 2, "a fresh conversation after the error"
    assert not s.live_talk.busy and not s.ui.thinking


def test_empty_reply_just_rests_with_its_emotion():
    s = Stack(model=FakeLiveModel(["[sleepy]"]))
    talk(s, "hm")
    assert s.voice.spoken == [] and s.bubbles() == []
    assert s.sink.of(EmotionChanged)[-1] == EmotionChanged(Emotion.SLEEPY)
    assert s.states() == [MiloState.THINKING, MiloState.IDLE]


def test_tag_only_reply_applies_the_tag_and_rests():
    s = Stack(model=FakeLiveModel(["[happy] <remember>Is left-handed</remember>"]))
    talk(s, "fyi I'm left-handed")
    assert s.profile.facts == ["Is left-handed"]
    assert s.voice.spoken == [] and s.states() == [MiloState.THINKING, MiloState.IDLE]


def test_a_reply_without_an_emotion_tag_is_neutral():
    s = Stack(model=FakeLiveModel(["Fine, I guess so."]))
    talk(s, "ok?")
    assert s.sink.of(EmotionChanged)[-1] == EmotionChanged(Emotion.NEUTRAL)
    assert s.voice.spoken == ["Fine, I guess so."]
