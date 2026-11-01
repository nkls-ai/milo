"""state/conversations/: one file per conversation, an index that rebuilds itself, and the one-time migration of
the old transcript.jsonl without losing a line."""

import json

from milo.core.conversations import ConversationInfo, SplitRules
from milo.core.ports import ConversationStore
from milo.memory.conversations import JsonlConversationStore, migrate
from tests.fakes import MemoryConversations


def header(id="c-u1", ts="2026-10-30T09:00:00", **kw) -> ConversationInfo:
    return ConversationInfo(id, kw.pop("kind", "chat"), ts, ts, kw.pop("title", "Photos from Friday"), **kw)


def user(id, ts, text="rename the photos", via="voice") -> dict:
    return {"id": id, "ts": ts, "kind": "user", "text": text, "via": via}


def milo(id, ts, text="On it.") -> dict:
    return {"id": id, "ts": ts, "kind": "milo", "text": text, "emotion": "happy", "done": True}


def task(id, ts, text="Rename the photos", result="Renamed 40 photos.") -> dict:
    return {"id": id, "ts": ts, "kind": "task", "text": text, "status": "done", "result": result, "steps": []}


def test_both_stores_are_conversation_stores(tmp_path):
    assert isinstance(JsonlConversationStore(tmp_path), ConversationStore)
    assert isinstance(MemoryConversations(), ConversationStore)


def test_entries_go_to_their_own_file_and_come_back_after_a_restart(tmp_path):
    store = JsonlConversationStore(tmp_path)
    info = store.append(header(), user("u1", "2026-10-30T09:00:00"))
    info = store.append(info, milo("m1", "2026-10-30T09:00:03"))
    other = store.append(header("c-u9", "2026-10-30T11:00:00", title="Train"), user("u9", "2026-10-30T11:00:00", "train"))
    assert (tmp_path / "2026-10" / "c-u1.jsonl").exists() and (tmp_path / "2026-10" / "c-u9.jsonl").exists()
    assert info.turns == 1 and info.preview == "On it." and info.last == "2026-10-30T09:00:03"

    again = JsonlConversationStore(tmp_path)
    assert [c.id for c in again.all()] == ["c-u9", "c-u1"], "latest first"
    assert again.get("c-u1") == info and again.get("c-u9") == other
    assert [e["id"] for e in again.entries("c-u1")] == ["u1", "m1"]
    assert all(e["conversation"] == "c-u1" for e in again.entries("c-u1"))
    assert [e["id"] for e in again.entries("c-u1", 1)] == ["m1"]


def test_a_task_that_finishes_late_still_reads_in_start_order(tmp_path):
    store = JsonlConversationStore(tmp_path)
    info = store.append(header(), user("u1", "2026-10-30T09:00:00"))
    info = store.append(info, user("u2", "2026-10-30T09:05:00", "and the others?"))
    store.append(info, task("t1", "2026-10-30T09:00:05"))
    assert [e["id"] for e in store.entries("c-u1")] == ["u1", "t1", "u2"]


def test_titles_live_in_the_conversation_file_and_the_users_name_wins(tmp_path):
    store = JsonlConversationStore(tmp_path)
    store.append(header(), user("u1", "2026-10-30T09:00:00"))
    assert store.title("c-u1", "Friday's photos", "milo").titled_by == "milo"
    assert store.title("c-u1", "Photo day", "you").title == "Photo day"
    assert store.title("c-u1", "Something else", "milo").title == "Photo day"
    assert store.title("c-nope", "x", "you") is None
    (tmp_path / "index.jsonl").unlink()
    rebuilt = JsonlConversationStore(tmp_path).get("c-u1")
    assert (rebuilt.title, rebuilt.titled_by, rebuilt.turns) == ("Photo day", "you", 1)


def test_a_broken_or_stale_index_is_rebuilt_from_the_files(tmp_path):
    store = JsonlConversationStore(tmp_path)
    info = store.append(header(kind="meeting", source="meeting:m1", title="Weekly sync"),
                        milo("n1", "2026-10-30T09:00:00", "Notes from “Weekly sync”: launch moves."))
    (tmp_path / "index.jsonl").write_text("not json\n", encoding="utf-8")
    assert JsonlConversationStore(tmp_path).get("c-u1") == info
    # A conversation file the index never heard of (a crash between the two writes) brings it up to date.
    store = JsonlConversationStore(tmp_path)
    store.get("c-u1")
    index = (tmp_path / "index.jsonl").read_text(encoding="utf-8")
    store.append(header("c-u2", "2026-10-30T10:00:00"), user("u2", "2026-10-30T10:00:00"))
    (tmp_path / "index.jsonl").write_text(index, encoding="utf-8")
    assert {c.id for c in JsonlConversationStore(tmp_path).all()} == {"c-u1", "c-u2"}


def test_the_index_is_compacted_when_it_grows(tmp_path):
    store = JsonlConversationStore(tmp_path)
    info = store.append(header(), user("u1", "2026-10-30T09:00:00"))
    for i in range(250):
        info = store.append(info, milo(f"m{i}", "2026-10-30T09:01:00", f"reply {i}"))
    lines = (tmp_path / "index.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) < 200
    assert JsonlConversationStore(tmp_path).get("c-u1").preview == "reply 249"


def test_searching_the_words_reads_the_latest_conversations_first_within_a_budget(tmp_path):
    store = JsonlConversationStore(tmp_path)
    old = store.append(header("c-a", "2026-10-01T09:00:00"), user("a", "2026-10-01T09:00:00", "the Hetzner invoice"))
    new = store.append(header("c-b", "2026-10-30T09:00:00"), user("b", "2026-10-30T09:00:00", "where is the invoice"))
    assert [(c, e["id"]) for c, e in store.search_text(["invoice"])] == [("c-b", "b"), ("c-a", "a")]
    assert [c for c, _ in store.search_text(["hetzner", "INVOICE"])] == ["c-a"]
    assert store.search_text(["invoice"], budget_bytes=10) == []
    assert store.search_text([" "]) == []
    assert old.id != new.id


# ---- the migration


def write_transcript(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join((json.dumps(line) if isinstance(line, dict) else line) + "\n" for line in lines), encoding="utf-8")


OLD = [
    user("u1", "2026-10-28T09:00:00", "rename the photos from Friday"),
    milo("m1", "2026-10-28T09:00:02"),
    user("u2", "2026-10-28T09:01:00", "yes"),
    milo("m2", "2026-10-28T15:02:11", "Notes from “Weekly sync”: launch moves to Friday."),
    user("u3", "2026-10-29T08:00:00", "is my train on time", "message"),
    milo("m3", "2026-10-29T08:00:04", "The 8:12 is on time."),
    task("t1", "2026-10-28T09:00:03"),  # finished after later lines, written later
    "{\"id\": \"half-writ",
]


def test_the_old_transcript_becomes_conversations_without_losing_a_line(tmp_path):
    transcript, kept = tmp_path / "transcript.jsonl", tmp_path / "transcript.before-conversations.jsonl"
    write_transcript(transcript, OLD)
    original = transcript.read_bytes()
    store = JsonlConversationStore(tmp_path / "conversations")
    assert migrate(transcript, kept, store) == len(OLD)

    assert not transcript.exists() and kept.read_bytes() == original
    convs = store.all()
    assert [(c.kind, c.title, c.via) for c in convs] == [
        ("chat", "Is my train on time", ("message",)),
        ("meeting", "Weekly sync", ()),
        ("chat", "Rename the photos from Friday", ("voice",))]
    assert [e["id"] for e in store.entries("c-u1")] == ["u1", "m1", "t1", "u2"]
    assert convs[2].tasks[0].id == "t1" and convs[2].outside is False
    # Every line is somewhere, the broken one too.
    lines = [line for p in (tmp_path / "conversations").glob("*/*.jsonl") for line in p.read_text(encoding="utf-8").splitlines()]
    assert sum(1 for line in lines if '"kind"' in line and '"header"' not in line) == len(OLD) - 1
    assert any(json.loads(line).get("broken") == "{\"id\": \"half-writ" for line in lines)


def test_running_it_again_after_a_crash_gives_the_same_files(tmp_path):
    transcript, kept = tmp_path / "transcript.jsonl", tmp_path / "kept.jsonl"
    write_transcript(transcript, OLD)
    store = JsonlConversationStore(tmp_path / "conversations")
    migrate(transcript, kept, store)
    first = {p.name: p.read_text(encoding="utf-8") for p in (tmp_path / "conversations").glob("*/*.jsonl")}
    kept.rename(transcript)  # as if the crash came before the old file was moved
    migrate(transcript, kept, JsonlConversationStore(tmp_path / "conversations"))
    assert {p.name: p.read_text(encoding="utf-8") for p in (tmp_path / "conversations").glob("*/*.jsonl")} == first


def test_nothing_to_migrate_is_fine_and_a_later_transcript_is_added_to_the_kept_copy(tmp_path):
    transcript, kept = tmp_path / "transcript.jsonl", tmp_path / "kept.jsonl"
    store = JsonlConversationStore(tmp_path / "conversations")
    assert migrate(transcript, kept, store) == 0 and store.all() == []
    write_transcript(transcript, OLD[:2])
    migrate(transcript, kept, store)
    write_transcript(transcript, [user("u7", "2026-10-30T10:00:00", "hello again")])  # an older Milo ran meanwhile
    migrate(transcript, kept, store)
    assert len(kept.read_text(encoding="utf-8").splitlines()) == 3 and not transcript.exists()
    assert [c.id for c in store.all()] == ["c-u7", "c-u1"]


def test_the_migration_splits_with_the_same_rules_as_the_live_chat(tmp_path):
    transcript, kept = tmp_path / "transcript.jsonl", tmp_path / "kept.jsonl"
    write_transcript(transcript, [user("a", "2026-10-30T09:00:00", "hi"), user("b", "2026-10-30T09:02:00", "and?")])
    store = JsonlConversationStore(tmp_path / "conversations")
    migrate(transcript, kept, store, SplitRules(idle_s=60))
    assert [c.id for c in store.all()] == ["c-b", "c-a"]
