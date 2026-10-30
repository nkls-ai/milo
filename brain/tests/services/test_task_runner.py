import asyncio

from milo.core.events import Bubble, EmotionChanged
from milo.core.types import Emotion, HarnessError, ListenMode, MiloState, Reply, Usage
from milo.services.task_runner import TASK_FAILED
from tests.fakes import FakeAudioOutput, FakeHarness, FakeLiveModel
from tests.services.stack import Stack, settle


def run_tasks(s: Stack, *descriptions: str) -> None:
    async def run():
        for d in descriptions:
            s.tasks.submit(d)
        await s.tasks.idle()
        await settle()

    asyncio.run(run())


def test_runs_tasks_one_at_a_time_on_the_harness_session_and_speaks_each_result():
    s = Stack(harness=FakeHarness("Sorted your downloads.", "Found three flights.", delay_s=0.01))
    s.context.update("Finder", 0)
    run_tasks(s, "sort downloads", "find flights")
    assert [p.split("\n", 1)[1] for p, _ in s.harness.calls] == ["sort downloads", "find flights"]
    assert [sid for _, sid in s.harness.calls] == [None, "s1"], "the agent keeps context across tasks"
    assert "frontmost app: Finder" in s.harness.calls[0][0]
    assert s.voice.spoken == ["Sorted your downloads.", "Found three flights."]
    assert [src for src, _, _ in s.ledger.entries] == ["task", "task"]
    assert s.ui.state is MiloState.IDLE and not s.tasks.busy


def test_a_failed_task_shows_a_short_bubble_and_the_next_one_still_runs():
    s = Stack(harness=FakeHarness(HarnessError("codex not found", transient=False), "Done."))
    run_tasks(s, "broken", "fine")
    assert s.bubbles() == [TASK_FAILED, "Done."]
    assert EmotionChanged(Emotion.CONFUSED) in s.sink.events
    assert s.voice.spoken == ["Done."]


def test_an_empty_result_says_nothing():
    s = Stack(harness=FakeHarness(Reply(Emotion.HAPPY, "", Usage(), "s1")))
    run_tasks(s, "quiet work")
    assert s.sink.events == []


def test_the_result_waits_for_a_live_turn_to_finish_instead_of_cutting_milo_off():
    gate = asyncio.Event()
    s = Stack(model=FakeLiveModel(["[happy] Let me explain this to you, ", "slowly."], gate=gate),
              harness=FakeHarness("Task done."), wait_s=5)

    async def run():
        turn = s.live_talk.start("explain")
        await settle()
        s.tasks.submit("background")
        await asyncio.sleep(0.03)
        assert s.voice.spoken == ["Let me explain this to you,"], "the result waits"
        gate.set()
        await turn
        await s.tasks.idle()

    asyncio.run(run())
    assert s.voice.spoken == ["Let me explain this to you,", "slowly.", "Task done."]


def test_while_the_user_keeps_talking_the_result_is_only_shown():
    s = Stack(output=FakeAudioOutput(block=True), harness=FakeHarness("Task done."))

    async def run():
        s.listening.start(ListenMode.DICTATE)
        s.tasks.submit("background")
        await s.tasks.idle()

    asyncio.run(run())
    assert s.voice.spoken == [] and s.sink.of(Bubble) == [Bubble("Task done.")]
    assert s.ui.state is MiloState.DICTATING
