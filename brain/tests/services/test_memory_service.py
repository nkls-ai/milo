"""Memory in the brain: recall with each live turn, episode stubs, the worker's requests and the facts screen."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from milo.core.events import Confirm, Facts
from milo.core.memory import Episode, Fact, TurnContext, new_id
from milo.core.routines import Routine, RoutineInput
from milo.core.types import ScreenCapture
from milo.services.episode_stubs import EpisodeDictations, EpisodeEyes, EpisodeTranscript, RoutineEpisodes
from milo.services.memory import MEMORY_RULES
from milo.services.memory_requests import MemoryRequests
from milo.services.transcript import Transcript
from tests.fakes import FakeEyes, FakeHarness, FakeLiveModel, MemoryConversations, MemoryRoutineBook, MemoryTranscript
from tests.services.stack import Stack, settle

ANNA = "Anna is the user's sister. Her birthday is March 3."


def stack(**kw) -> Stack:
    s = Stack(with_memory=True, **kw)
    s.facts.add(Fact("01JBF6Z3Q8M2X4K7N9P0R5T6VW", "The user's name is Niklas.", "basics", s.clock.now(), "chat"))
    s.facts.add(Fact(new_id(s.clock.now()), ANNA, "people", s.clock.now(), "chat"))
    s.index.refresh()
    return s


def talk(s: Stack, *texts: str) -> None:
    async def run():
        for text in texts:
            await s.live_talk.start(text)
            await settle()

    asyncio.run(run())


def test_a_turn_carries_what_it_needs_and_the_system_prompt_stays_put():
    s = stack()
    talk(s, "When is Anna's birthday?", "And when is Anna's birthday again?")
    [system] = s.model.system_prompts
    assert MEMORY_RULES.strip() in system
    first, second = s.model.turns
    assert first.index("<memory>") < first.index("When is Anna's birthday?")
    assert ANNA in first
    assert "Niklas" not in first, "always-on facts are in the system prompt, not repeated per turn"
    assert "<memory>" not in second, "the conversation already has it"
    s.clock.advance(seconds=601)
    talk(s, "When is Anna's birthday?")
    assert len(s.model.system_prompts) == 2 and ANNA in s.model.turns[-1]


def test_a_turn_with_nothing_to_remember_goes_in_plain():
    s = stack()
    talk(s, "hi there")
    assert s.model.turns == ["[Thursday 2026-10-29 09:00]\nhi there"]


def test_recalled_outside_text_makes_later_tags_ask_first():
    s = stack(model=FakeLiveModel(["[neutral] She asked to move dinner."],
                                  ["[happy] Noted. <remember>The user likes dinner on Fridays.</remember>"]))
    mail = Episode(new_id(s.clock.now()), s.clock.now() - timedelta(days=1), "task",
                   "Task: read Anna's email. Result: she asks to move dinner to Friday.", trusted=False)
    s.episodes.append(mail)
    s.index.refresh()
    talk(s, "What did Anna write about dinner?")
    assert "From outside" in s.model.turns[0]

    async def run():
        await s.live_talk.start("ok, remember I like Friday dinners")
        await settle()
        assert s.sink.of(Confirm)[-1].question.startswith("Should I remember this")

    asyncio.run(run())


def test_memory_that_is_too_slow_is_skipped():
    s = stack()
    s.memory._recall_timeout_s = 0.01

    def slow(turn, context, budget):
        import time
        time.sleep(0.05)
        raise AssertionError("never used")

    s.memory._recaller.recall = slow

    async def run():
        from concurrent.futures import ThreadPoolExecutor
        s.memory._executor = ThreadPoolExecutor(1)
        recall = await s.memory.recall("Anna", TurnContext(s.clock.now()))
        assert recall.empty

    asyncio.run(run())


def test_a_recall_still_running_on_the_memory_thread_is_not_queued_behind(caplog):
    # M6: the memory thread is real here. A recall that timed out keeps the thread; the next turn mustn't wait
    # out its own timeout behind it (each turn's reply would start that much later, for no memory anyway).
    import time
    import threading
    from concurrent.futures import ThreadPoolExecutor

    s = stack()
    s.memory._recall_timeout_s = 0.3
    release, calls = threading.Event(), []
    real = s.memory._recaller.recall

    def stuck_once(turn, context, budget):
        calls.append(turn)
        if len(calls) == 1:
            release.wait(5)
            raise RuntimeError("the embedder was paged out")
        return real(turn, context, budget)

    s.memory._recaller.recall = stuck_once

    async def run():
        s.memory._executor = ThreadPoolExecutor(1)
        first = await s.memory.recall("Anna", TurnContext(s.clock.now()))
        started = time.monotonic()
        second = await s.memory.recall("Anna", TurnContext(s.clock.now()))
        assert time.monotonic() - started < 0.1, "the second turn didn't wait for the stuck one"
        release.set()
        await asyncio.sleep(0.1)
        third = await s.memory.recall("Anna", TurnContext(s.clock.now()))
        s.memory._executor.shutdown(wait=True)
        return first, second, third

    first, second, third = asyncio.run(run())
    assert first.empty and second.empty
    assert calls == ["Anna", "Anna"], "the second turn queued nothing behind the stuck one"
    assert [f.text for f in third.facts if f.text == ANNA] == [ANNA], "once it ends, recall works again"
    assert "still running" in caplog.text


def test_turns_and_tasks_become_episode_stubs():
    s = stack()
    store = MemoryTranscript()
    outside = [False]
    stubs = EpisodeTranscript(store, s.memory.record, now=s.clock.now, app=lambda: "Mail",
                              people=s.memory.people_in, outside=lambda: outside[0])
    stubs.append({"id": "u1", "ts": "2026-10-29T09:00:00", "kind": "user", "text": "Call Anna about dinner",
                  "via": "voice"})
    stubs.append({"id": "m1", "ts": "2026-10-29T09:00:02", "kind": "milo", "text": "I'll remind you.", "done": True})
    stubs.append({"id": "u2", "ts": "2026-10-29T09:01:00", "kind": "user", "text": "yes", "via": "voice"})
    outside[0] = True
    stubs.append({"id": "u3", "ts": "2026-10-29T09:02:00", "kind": "user", "text": "what did it say", "via": "typed"})
    stubs.append({"id": "t1", "ts": "2026-10-29T09:03:00", "kind": "task", "text": "Read Anna's email",
                  "status": "done", "result": "She asks to move dinner."})
    assert len(store.entries) == 5
    episodes = s.episodes.between(datetime(2026, 10, 29), datetime(2026, 10, 30))
    assert [(e.kind, e.trusted, e.source) for e in episodes] == [
        ("conversation", True, "transcript:u1"), ("conversation", False, "transcript:u3"),
        ("task", False, "transcript:t1")]
    first = episodes[0]
    assert first.summary == "The user said: “Call Anna about dinner” Milo answered: “I'll remind you.”"
    assert first.people == ("Anna",) and first.apps == ("Mail",)
    assert episodes[2].summary == "Task: Read Anna's email Result: She asks to move dinner."


def test_a_routine_run_is_one_task_episode_named_after_the_routine():
    report = Routine("monday-report", "Monday report", inputs=(RoutineInput("month", "Which month?"),),
                     apps=("Numbers",), body="1. Sum the sales.\n   Check: one total.")
    s = stack(routine_book=MemoryRoutineBook(report), harness=FakeHarness("Sent Anna the October total."))
    s.routines._state = {"approved": {report.slug: report.fingerprint()}}
    # Wired as compose.py does: the transcript's task stub leaves routine runs to RoutineEpisodes.
    stubs = EpisodeTranscript(MemoryTranscript(), s.memory.record, now=s.clock.now, people=s.memory.people_in,
                              elsewhere=s.routines.is_run)
    s.tasks._transcript = Transcript(s.ui, MemoryConversations(), s.clock, on_finished=stubs.append)
    s.routines.on_episode = RoutineEpisodes(s.memory.record, people=s.memory.people_in)

    async def go():
        assert s.routines.run("Monday report", "October")
        await settle()
        await s.routines.idle()
        await s.tasks.idle()

    asyncio.run(go())
    [helper] = s.tasks.helpers
    [episode] = s.episodes.between(datetime(2026, 10, 29), datetime(2026, 10, 30))
    assert episode.kind == "task" and not episode.trusted and episode.source == f"transcript:{helper.id}"
    assert episode.summary == "Routine “Monday report” for month October. Result: Sent Anna the October total."
    assert episode.apps == ("Numbers",) and episode.people == ("Anna",)
    assert not s.routines.is_run(helper.id)

    async def task():
        s.tasks.submit("Tidy the desktop")  # an ordinary task still gets the transcript's stub
        await s.tasks.idle()

    asyncio.run(task())
    episodes = s.episodes.between(datetime(2026, 10, 29), datetime(2026, 10, 30))
    assert sorted(e.summary for e in episodes) == [episode.summary, "Task: Tidy the desktop Result: ok"]


def test_dictations_into_one_app_make_one_episode():
    s = stack()
    stubs = EpisodeDictations(None, s.memory.record, now=s.clock.now)
    stubs.append("Dear Anna,", "Mail")
    s.clock.advance(seconds=20)
    stubs.append("dinner on Friday works.", "Mail")
    s.clock.advance(minutes=10)
    stubs.append("fix the build", "Slack")
    got = s.episodes.between(datetime(2026, 10, 29), datetime(2026, 10, 30))
    assert [(e.summary, e.apps) for e in got] == [("Dear Anna, dinner on Friday works.", ("Mail",)),
                                                  ("fix the build", ("Slack",))]


def test_looks_are_noted_without_what_was_on_screen():
    s = stack()
    eyes = EpisodeEyes(FakeEyes(ScreenCapture(app="Safari", window="Bank login", text="secret numbers")),
                       s.memory.record, now=s.clock.now)
    asyncio.run(eyes.look())
    [look] = s.episodes.between(datetime(2026, 10, 29), datetime(2026, 10, 30))
    assert look.kind == "look" and not look.trusted and "secret" not in look.summary and "Safari" in look.summary


def test_the_worker_searches_freely_but_remembering_and_forgetting_ask():
    s = stack()
    added: list = []
    requests = MemoryRequests(s.memory, s.approvals, lambda text, **kw: added.append((text, kw)))

    async def run():
        found = await requests.handle("memory.search", {"query": "Anna birthday"})
        assert found["ok"] and found["result"]["results"][0]["text"] == ANNA
        asking = asyncio.create_task(requests.handle("memory.remember", {"text": "Anna moved to Berlin.",
                                                                        "topic": "people"}))
        await settle()
        assert s.sink.of(Confirm)[-1].question == "Should I remember this?\n› Anna moved to Berlin."
        s.approvals.answer(s.sink.of(Confirm)[-1].id, True)
        assert (await asking)["ok"] and added == [("Anna moved to Berlin.", {"topic": "people", "source": "worker",
                                                                             "by": "worker", "always_on": False})]
        anna = next(f for f in s.facts.current() if f.topic == "people")
        asking = asyncio.create_task(requests.handle("memory.forget", {"id": anna.id}))
        await settle()
        assert s.sink.of(Confirm)[-1].question == f"Should I forget this?\n› {ANNA}"
        s.approvals.answer(s.sink.of(Confirm)[-1].id, False)
        assert not (await asking)["ok"] and anna in s.facts.current()
        assert not (await requests.handle("memory.forget", {"id": "nope"}))["ok"]
        assert not (await requests.handle("memory.remember", {"text": "x", "topic": "gossip"}))["ok"]
        assert not (await requests.handle("memory.remember", {"text": "x", "topic": "basics"}))["ok"]

    asyncio.run(run())


def test_forgetting_and_editing_tell_the_app():
    s = stack()
    anna = next(f for f in s.facts.current() if f.topic == "people")
    new = s.memory.edit_fact(anna.id, "Anna is the user's older sister.")
    assert new.replaces == anna.id and s.sink.of(Facts)[-1].facts[-1]["text"] == "Anna is the user's older sister."
    assert s.memory.edit_fact(anna.id, "again") is None  # not current any more
    assert s.memory.forget(new.id, "test") == "Anna is the user's older sister."
    assert [f["topic"] for f in s.sink.of(Facts)[-1].facts] == ["basics"]
