import json

from milo.core.ports import TranscriptStore
from milo.memory import transcript as store_module
from milo.memory.transcript import JsonlTranscript
from tests.fakes import MemoryTranscript


def test_append_then_tail_in_order(tmp_path):
    store = JsonlTranscript(tmp_path / "state" / "transcript.jsonl")
    assert isinstance(store, TranscriptStore) and isinstance(MemoryTranscript(), TranscriptStore)
    assert store.tail(50) == [], "no file yet"
    for i in range(5):
        store.append({"id": str(i), "text": f"grüß {i}"})
    assert [e["id"] for e in store.tail(3)] == ["2", "3", "4"]
    assert [e["id"] for e in store.tail(50)] == ["0", "1", "2", "3", "4"]
    assert store.tail(0) == []
    assert "grüß" in store.path.read_text(encoding="utf-8")


def test_a_restart_sees_what_the_last_run_wrote(tmp_path):
    path = tmp_path / "transcript.jsonl"
    JsonlTranscript(path).append({"id": "a"})
    assert JsonlTranscript(path).tail(5) == [{"id": "a"}]


def test_tail_reads_only_the_end_of_a_big_file(tmp_path, monkeypatch):
    path = tmp_path / "transcript.jsonl"
    with path.open("w") as f:
        for i in range(20_000):
            f.write(json.dumps({"id": i, "text": "x" * 100}) + "\n")
    monkeypatch.setattr(store_module, "_BLOCK", 4096)
    reads: list[int] = []
    real_open = type(path).open

    def counting_open(self, *a, **kw):
        handle = real_open(self, *a, **kw)
        real_read = handle.read
        handle.read = lambda n=-1: reads.append(n) or real_read(n)
        return handle

    monkeypatch.setattr(type(path), "open", counting_open)
    entries = JsonlTranscript(path).tail(50)
    assert [e["id"] for e in entries] == list(range(19_950, 20_000))
    assert sum(reads) < 4096 * 3, "read a few blocks, not 2 MB"


def test_broken_lines_are_skipped(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text('{"id": "a"}\nnot json\n[1]\n{"id": "b"}\n')
    assert JsonlTranscript(path).tail(10) == [{"id": "a"}, {"id": "b"}]
