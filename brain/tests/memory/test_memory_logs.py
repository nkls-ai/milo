"""The memory logs: crash-safe JSON lines, episodes and facts, and the contracts their fakes share."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from milo.core.memory import Episode, Fact, new_id
from milo.memory import jsonl
from milo.memory.episodes import JsonlEpisodeLog
from milo.memory.facts import JsonlFactStore
from tests.fakes import MemoryEpisodeLog, MemoryFactStore

T = datetime(2026, 10, 30, 9, 0)


def fact(text: str, topic: str = "people", **kw) -> Fact:
    return Fact(new_id(T), text, topic, T, "chat", **kw)


def episode(summary: str, at: datetime = T, **kw) -> Episode:
    return Episode(new_id(at), at, "conversation", summary, **kw)


# ---- jsonl


def test_a_half_written_last_line_is_skipped_and_the_next_append_starts_fresh(tmp_path):
    path = tmp_path / "log.jsonl"
    jsonl.append(path, {"n": 1})
    with path.open("ab") as f:
        f.write(b'{"n": 2, "text": "cut off he')  # the crash
    records, offset = jsonl.read(path)
    assert records == [{"n": 1}]
    assert jsonl.read_all(path) == [{"n": 1}]
    jsonl.append(path, {"n": 3})
    assert jsonl.read_all(path) == [{"n": 1}, {"n": 3}]
    more, _ = jsonl.read(path, offset)
    assert more == [{"n": 3}]


def test_reading_from_an_offset_returns_only_new_complete_lines(tmp_path):
    path = tmp_path / "log.jsonl"
    assert jsonl.read(path) == ([], 0)
    jsonl.append(path, {"n": 1})
    first, offset = jsonl.read(path)
    jsonl.append(path, {"n": 2}, sync=True)
    second, end = jsonl.read(path, offset)
    assert (first, second) == ([{"n": 1}], [{"n": 2}])
    assert end == path.stat().st_size
    path.write_bytes(path.read_bytes() + b"not json\n[1, 2]\n")
    assert jsonl.read_all(path) == [{"n": 1}, {"n": 2}]


def test_logs_are_private_to_the_user(tmp_path):
    path = tmp_path / "log.jsonl"
    jsonl.append(path, {"n": 1})
    assert path.stat().st_mode & 0o077 == 0


# ---- EpisodeLog contract


@pytest.fixture(params=["file", "fake"])
def episodes(request, tmp_path):
    return JsonlEpisodeLog(tmp_path / "episodes") if request.param == "file" else MemoryEpisodeLog()


def test_episodes_between_are_sorted_and_bounded(episodes):
    late, early, out = episode("late", T + timedelta(hours=2)), episode("early"), episode("next day", T + timedelta(days=1))
    for e in (late, early, out):
        episodes.append(e)
    assert [e.summary for e in episodes.between(T, T + timedelta(days=1))] == ["early", "late"]


def test_a_newer_line_replaces_an_episode_and_forget_hides_it(episodes):
    stub = episode("The user said: dentist?", people=("Dr. Weber",), apps=("Mail",), source="transcript:abc",
                   trusted=False)
    episodes.append(stub)
    summary = Episode(stub.id, stub.at, stub.kind, "Asked when the dentist appointment is.", stub.people, stub.apps,
                      stub.source, stub.trusted)
    episodes.append(summary)
    [got] = episodes.between(T - timedelta(days=1), T + timedelta(days=1))
    assert got == summary
    episodes.forget(stub.id, "the user asked")
    assert episodes.between(T - timedelta(days=1), T + timedelta(days=1)) == []
    with pytest.raises(KeyError):
        episodes.forget("nope", "")


def test_episode_files_are_monthly_and_forgetting_can_be_undone(tmp_path):
    log = JsonlEpisodeLog(tmp_path)
    e1, e2 = episode("october"), episode("november", datetime(2026, 11, 2))
    log.append(e1)
    log.append(e2)
    assert [p.name for p in log.files()] == ["2026-10.jsonl", "2026-11.jsonl"]
    log.forget(e1.id, "no")
    log.remember(e1.id, "yes after all")
    assert [e.summary for e in log.all()] == ["october", "november"]
    assert Episode.from_dict(e1.to_dict()) == e1


# ---- FactStore contract


@pytest.fixture(params=["file", "fake"])
def facts(request, tmp_path):
    return JsonlFactStore(tmp_path / "facts.jsonl") if request.param == "file" else MemoryFactStore()


def test_current_facts_leave_out_retired_and_replaced_ones(facts):
    anna = fact("Anna's birthday is March 3.")
    bob = fact("Bob is a colleague.", "work")
    facts.add(anna)
    facts.add(bob)
    fixed = fact("Anna's birthday is March 4.", replaces=anna.id)
    facts.add(fixed)
    assert [f.text for f in facts.current()] == ["Bob is a colleague.", "Anna's birthday is March 4."]
    facts.retire(bob.id, "the user forgot it")
    assert [f.text for f in facts.current()] == ["Anna's birthday is March 4."]
    assert facts.get(bob.id).retired
    facts.restore(bob.id, "undo")
    assert {f.text for f in facts.current()} == {"Bob is a colleague.", "Anna's birthday is March 4."}
    assert facts.get(anna.id).text == "Anna's birthday is March 3."


def test_the_fact_log_is_append_only_and_survives_a_restart(tmp_path):
    path = tmp_path / "facts.jsonl"
    store = JsonlFactStore(path)
    anna = fact("Anna is the user's sister.", pinned=True)
    store.add(anna, by="chat")
    store.retire(anna.id, "wrong", by="you")
    store.restore(anna.id, "undo", by="you")
    assert [c["op"] for c in store.changes()] == ["add", "retire", "restore"]
    assert store.changes()[1]["by"] == "you"
    again = JsonlFactStore(path)
    assert again.current() == [anna]
    with pytest.raises(KeyError):
        again.retire("nope", "")


def test_the_store_sees_lines_another_process_appends_and_skips_a_broken_one(tmp_path):
    path = tmp_path / "facts.jsonl"
    brain, other = JsonlFactStore(path), JsonlFactStore(path)
    brain.add(fact("one"))
    assert len(brain.current()) == 1
    with path.open("ab") as f:
        f.write(b'{"op": "add", "id": "x", "te')  # a crash in the other process
    other.add(fact("two"))
    assert [f.text for f in brain.current()] == ["one", "two"]
    path.write_text("")  # replaced by hand
    assert brain.current() == []
