import asyncio
import math

from milo.core.events import Bubble
from milo.core.types import Emotion, HarnessError, ListenMode, MiloState, Nudge, Signals
from tests.fakes import CountingBudget, FakeHarness, FakeLiveModel, ScriptedEngine
from tests.services.stack import Stack, settle

STRETCH = Nudge("focus_break", Emotion.HAPPY, "Time to stretch.", speak=True, llm_prompt="Suggest a stretch.")
REMINDER = Nudge("reminder", Emotion.EXCITED, "Call the dentist.", speak=True)


def deliver(s: Stack, *nudges: Nudge) -> None:
    async def run():
        s.engine.queue.append(list(nudges))
        await s.heartbeat.tick()
        await settle()

    asyncio.run(run())


def test_delivers_a_template_nudge_aloud():
    s = Stack()
    s.context.update("Xcode", 5)
    deliver(s, REMINDER)
    assert s.voice.spoken == ["Call the dentist."]
    assert s.states() == [MiloState.SPEAKING, MiloState.IDLE]


def test_muted_skips_nudges_but_not_reminders():
    s = Stack()
    s.heartbeat.muted = True
    deliver(s, STRETCH, REMINDER)
    assert s.bubbles() == ["Call the dentist."]


def test_budget_zero_never_calls_the_harness():
    s = Stack(engine=ScriptedEngine(CountingBudget(0)))
    deliver(s, STRETCH)
    assert s.harness.calls == []
    assert s.bubbles() == ["Time to stretch."]


def test_budget_allows_llm_wording_once_and_spends_it():
    s = Stack(harness=FakeHarness("Stand up and reach for the sky!", "unused"),
              engine=ScriptedEngine(CountingBudget(1)))
    deliver(s, STRETCH)
    deliver(s, STRETCH)
    assert len(s.harness.calls) == 1 and s.harness.calls[0][1] is None
    assert s.harness.calls[0][0].endswith("\nSuggest a stretch.")
    assert s.bubbles()[0] == "Stand up and reach for the sky!" and s.bubbles()[-1] == "Time to stretch."
    assert [src for src, _, _ in s.ledger.entries] == ["proactive"]
    assert s.conversation.session_id is None


def test_harness_error_falls_back_to_the_template():
    s = Stack(harness=FakeHarness(HarnessError("offline", transient=True)),
              engine=ScriptedEngine(CountingBudget(5)))
    deliver(s, STRETCH)
    assert s.bubbles() == ["Time to stretch."]


def test_no_llm_wording_while_a_chat_turn_is_in_flight_and_no_speech():
    s = Stack(engine=ScriptedEngine(CountingBudget(5)))
    s.ui.thinking = True
    deliver(s, STRETCH)
    assert s.harness.calls == []
    assert s.voice.spoken == [] and s.bubbles() == ["Time to stretch."]


def test_a_nudge_waits_for_the_live_turn_instead_of_cutting_milo_off():
    gate = asyncio.Event()
    s = Stack(model=FakeLiveModel(["[happy] Here is my answer, ", "all of it."], gate=gate),
              engine=ScriptedEngine(CountingBudget(5)), wait_s=5)

    async def run():
        turn = s.live_talk.start("question")
        await settle()
        s.engine.queue.append([REMINDER])
        tick = asyncio.create_task(s.heartbeat.tick())
        await asyncio.sleep(0.02)
        assert not tick.done() and s.voice.spoken == ["Here is my answer,"]
        gate.set()
        await turn
        await tick
        await settle()

    asyncio.run(run())
    assert s.voice.spoken == ["Here is my answer,", "all of it.", "Call the dentist."]


def test_a_nudge_during_a_long_live_turn_is_shown_silently_without_llm_wording():
    gate = asyncio.Event()
    s = Stack(model=FakeLiveModel(["[happy] Thinking hard", " still."], gate=gate),
              engine=ScriptedEngine(CountingBudget(5)), wait_s=0.01)

    async def run():
        turn = s.live_talk.start("question")
        await settle()
        s.engine.queue.append([STRETCH])
        await s.heartbeat.tick()
        gate.set()
        await asyncio.gather(turn, return_exceptions=True)

    asyncio.run(run())
    assert s.harness.calls == []
    assert s.bubbles()[0] == "Time to stretch." and s.voice.spoken == ["Thinking hard still."]


def test_does_not_speak_while_recording():
    s = Stack()

    async def run():
        s.listening.start(ListenMode.DICTATE)
        s.engine.queue.append([REMINDER])
        await s.heartbeat.tick()
        await settle()

    asyncio.run(run())
    assert s.voice.spoken == [] and s.sink.of(Bubble) == [Bubble("Call the dentist.")]
    assert s.ui.state is MiloState.DICTATING


def test_idle_estimate_ages_the_last_report():
    s = Stack()
    s.context.update("Safari", 10)
    s.clock.advance(seconds=30)
    signals = s.heartbeat.signals()
    assert signals == Signals(now=s.clock.now(), idle_s=40, app="Safari")


class PresenceEngine(ScriptedEngine):
    """Nudges only when someone is at the Mac, like the real non-reminder rules."""

    def tick(self, signals):
        self.seen.append(signals)
        return [STRETCH] if signals.idle_s < 60 else []


def test_no_context_for_120s_means_nobody_is_there_and_no_nudges():
    s = Stack(engine=PresenceEngine())

    async def run():
        await s.heartbeat.tick()  # never reported
        s.context.update("Xcode", 0)
        s.clock.advance(seconds=121)
        await s.heartbeat.tick()  # report went stale
        await settle()

    asyncio.run(run())
    assert [sig.idle_s for sig in s.engine.seen] == [math.inf, math.inf]
    assert s.sink.events == []


def test_run_loop_ticks_every_tick_s_and_survives_errors():
    class Flaky(ScriptedEngine):
        def tick(self, signals):
            self.seen.append(signals)
            if len(self.seen) == 1:
                raise RuntimeError("bad rule")
            return []

    s = Stack(engine=Flaky(tick_s=0.001))

    async def run():
        task = asyncio.create_task(s.heartbeat.run())
        await asyncio.sleep(0.05)
        task.cancel()

    asyncio.run(run())
    assert len(s.engine.seen) >= 2
