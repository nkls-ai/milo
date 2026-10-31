"""The transcript behind the Milo window: entries, streaming, tasks with steps, history, and a restart."""

import asyncio

from milo.brain import Brain
from milo.config import UiSettings
from milo.core.events import Activity, EntryChanged, GetHistory, Helpers, History, ReplyDelta, TextInput
from milo.core.types import Emotion, HarnessError, Step, StepStatus
from milo.services.live_talk import LiveTalk
from milo.services.orchestrator import Orchestrator
from milo.services.task_runner import TASK_FAILED, TaskRunner
from milo.services.transcript import Transcript
from tests.fakes import FakeClock, FakeHarness, FakeLiveModel, MemoryConversations, RecordingSink
from tests.services.stack import Stack, settle

R, D, F = StepStatus.RUNNING, StepStatus.DONE, StepStatus.FAILED


def make(store: MemoryConversations | None = None, recent: int = 50):
    sink, clock = RecordingSink(), FakeClock()
    store = store if store is not None else MemoryConversations()
    return Transcript(sink, store, clock, recent=recent), sink, store


def test_a_user_turn_is_shown_and_saved_at_once():
    t, sink, store = make()
    id = t.user("hi Milo", "typed")
    entry = {"id": id, "ts": "2026-10-29T09:00:00", "kind": "user", "text": "hi Milo", "via": "typed",
             "conversation": f"c-{id}"}
    assert sink.events == [EntryChanged(entry)]
    assert store.saved == [entry]


def test_a_reply_streams_and_is_saved_when_finished():
    t, sink, store = make()
    id = t.reply_started(Emotion.HAPPY)
    t.reply_delta(id, "Hello ")
    t.reply_delta(id, "there.")
    assert store.saved == [], "nothing saved while it streams"
    t.reply_finished(id, "Hello there.", Emotion.HAPPY)
    assert sink.events[0].entry["done"] is False
    assert sink.events[1:3] == [ReplyDelta(id, "Hello "), ReplyDelta(id, "there.")]
    assert store.saved == [{"id": id, "ts": "2026-10-29T09:00:00", "kind": "milo", "text": "Hello there.",
                            "emotion": "happy", "done": True, "conversation": f"c-{id}"}]


def test_task_steps_update_in_place_and_unfinished_steps_end_with_the_task():
    t, sink, store = make()
    id = t.task_started("Rename the photos")
    t.task_step(id, Step("s1", "read", "Looking in your Pictures folder", "ls ~/Pictures", R))
    t.task_step(id, Step("s1", "read", "Looking in your Pictures folder", "ls ~/Pictures", D))
    t.task_step(id, Step("s2", "edit", "Moving a.jpg", "mv a.jpg b.jpg", R))
    t.task_finished(id, False, TASK_FAILED)
    assert [e.step["status"] for e in sink.of(Activity)] == ["running", "done", "running"]
    (saved,) = store.saved
    assert saved["status"] == "failed" and saved["result"] == TASK_FAILED
    assert [(s["id"], s["status"]) for s in saved["steps"]] == [("s1", "done"), ("s2", "failed")]


def test_history_is_bounded_and_survives_a_restart():
    t, _, store = make(recent=3)
    for i in range(5):
        t.user(f"turn {i}", "voice")
    assert [e["text"] for e in t.history().entries] == ["turn 2", "turn 3", "turn 4"]

    restarted, sink, _ = make(store, recent=3)
    assert [e["text"] for e in restarted.history().entries] == ["turn 2", "turn 3", "turn 4"]
    assert sink.events == []


def test_history_comes_from_memory_after_the_first_load():
    class CountingStore(MemoryConversations):
        reads = 0

        def entries(self, id, limit=None):
            self.reads += 1
            return super().entries(id, limit)

    store = CountingStore({"id": "x", "ts": "2026-10-29T08:58:00", "kind": "user", "text": "old", "via": "voice"})
    t, _, _ = make(store)
    for _ in range(3):
        t.history()
    t.user("new", "typed")
    assert [e["text"] for e in t.history().entries] == ["old", "new"], "two minutes later: the same conversation"
    assert store.reads == 1


def test_after_the_idle_gap_a_restart_starts_with_no_conversation_going_on():
    store = MemoryConversations({"id": "x", "ts": "2026-10-28T10:00:00", "kind": "user", "text": "old", "via": "voice"})
    t, _, _ = make(store)
    assert t.current is None and t.history().entries == []
    t.user("new", "typed")
    assert [e["text"] for e in t.history().entries] == ["new"] and t.current != "c-x"


def test_a_task_that_finished_after_later_turns_loads_in_start_order():
    store = MemoryConversations(
        {"id": "u2", "ts": "2026-10-29T08:59:00", "kind": "user", "text": "later", "via": "voice"},
        {"id": "t1", "ts": "2026-10-29T08:55:00", "kind": "task", "text": "long job", "status": "done",
         "result": "ok", "steps": []},
    )
    t, _, _ = make(store)
    assert [e["id"] for e in t.history().entries] == ["t1", "u2"]


# ---- wired into the services


def wired(model: FakeLiveModel | None = None, harness: FakeHarness | None = None):
    s = Stack(model=model or FakeLiveModel(), harness=harness or FakeHarness())
    sink, store = RecordingSink(), MemoryConversations()
    transcript = Transcript(sink, store, s.clock)
    tasks = Orchestrator(TaskRunner(s.harness, s.ledger, s.clock, s.context), s.speaker, s.ui, s.clock,
                         transcript=transcript, wait_s=0.05, poll_s=0.005, coalesce_s=0)
    live = LiveTalk(s.model, s.speaker, s.ui, s.context, s.clock, s.profile, s.reminders, s.ledger,
                    lambda: s.persona, s.idle_reset_s, tasks, transcript=transcript)
    tasks.on_result = live.note
    brain = Brain(s.ui, s.listening, live, s.context, s.heartbeat, UiSettings(), transcript, helpers=tasks)
    return s, brain, tasks, sink, store


def test_a_typed_turn_and_its_task_land_in_the_transcript():
    steps = [Step("item_1", "read", "Looking in your Pictures folder", "ls ~/Pictures", R),
             Step("item_1", "read", "Looking in your Pictures folder", "ls ~/Pictures", D)]
    s, brain, tasks, sink, store = wired(
        FakeLiveModel(["[happy] On it.", " <task>Rename the photos</task>"]),
        FakeHarness("Renamed 40 photos.", steps=steps))

    async def go():
        await brain.handle(TextInput("rename the photos", speak=False))
        await settle()
        await tasks.idle()
        await settle()

    asyncio.run(go())
    assert [(e["kind"], e["text"]) for e in store.saved] == [
        ("user", "rename the photos"), ("milo", "On it."), ("task", "Rename the photos")]
    assert store.saved[0]["via"] == "typed"
    assert store.saved[2]["status"] == "done" and store.saved[2]["result"] == "Renamed 40 photos."
    assert [e.step["status"] for e in sink.of(Activity)] == ["running", "done"]
    assert s.voice.spoken == ["Renamed 40 photos."], "the typed reply stayed silent, the task result is spoken"


def test_a_spoken_turn_is_marked_voice_and_speaks():
    s, brain, _, _, store = wired(FakeLiveModel(["[happy] Hello there."]))

    async def go():
        await brain._live_talk.start("hi")  # Listening starts spoken turns without `via`
        await settle()

    asyncio.run(go())
    assert store.saved[0]["via"] == "voice"
    assert s.voice.spoken == ["Hello there."]


def test_a_failed_task_is_marked_failed():
    _, brain, tasks, _, store = wired(FakeLiveModel(["[happy] Sure. <task>Do it</task>"]),
                                      FakeHarness(HarnessError("boom", transient=True)))

    async def go():
        await brain.handle(TextInput("do it"))
        await settle()
        await tasks.idle()

    asyncio.run(go())
    assert store.saved[-1]["status"] == "failed"


def test_get_history_and_connect_send_the_recent_transcript_without_calling_any_model():
    s, brain, _, _, _ = wired()
    asyncio.run(brain.handle(GetHistory()))
    assert any(isinstance(e, History) for e in brain.greeting()) and brain.greeting()[-1] == Helpers([])
    assert any(isinstance(e, History) for e in s.sink.events)
    assert s.model.turns == [] and s.harness.calls == []
