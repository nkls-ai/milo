"""Memory survives a crash: a writer killed mid-line leaves logs that still read, appends that still land on a
line of their own, and an index that builds again from them."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from datetime import datetime

from milo.adapters.embed.hashing import HashEmbedder
from milo.core.memory import Episode, Fact, new_id
from milo.memory.episodes import JsonlEpisodeLog
from milo.memory.facts import JsonlFactStore
from milo.memory.index import SqliteMemoryIndex

WRITER = textwrap.dedent("""
    import sys
    from datetime import datetime
    from pathlib import Path
    from milo.core.memory import Episode, Fact, new_id
    from milo.memory.episodes import JsonlEpisodeLog
    from milo.memory.facts import JsonlFactStore

    root = Path(sys.argv[1])
    facts, episodes = JsonlFactStore(root / "facts.jsonl"), JsonlEpisodeLog(root / "episodes")
    n = 0
    while True:
        at = datetime(2026, 10, 1 + n % 28, 12)
        facts.add(Fact(new_id(at), f"Fact number {n}, " + "padding " * 40, "learned", at, "chat"))
        episodes.append(Episode(new_id(at), at, "conversation", f"Episode {n}: " + "words " * 60))
        n += 1
        if n == 50:
            print("going", flush=True)
""")


def test_a_writer_killed_mid_write_leaves_logs_that_read_and_an_index_that_rebuilds(tmp_path):
    writer = subprocess.Popen([sys.executable, "-c", WRITER, str(tmp_path)], stdout=subprocess.PIPE, text=True)
    try:
        assert writer.stdout.readline().strip() == "going"
        time.sleep(0.2)
    finally:
        os.kill(writer.pid, signal.SIGKILL)
        writer.wait()
    # The kill may land between lines; cut one in half too, as a crash inside a write would.
    month = tmp_path / "episodes" / "2026-10.jsonl"
    with month.open("ab") as f:
        f.write(b'{"id": "01HALFWRITTEN", "summary": "Epis')
    with (tmp_path / "facts.jsonl").open("ab") as f:
        f.write(b'{"op": "add", "fact": {"id": "01HALF')

    facts, episodes = JsonlFactStore(tmp_path / "facts.jsonl"), JsonlEpisodeLog(tmp_path / "episodes")
    known, happened = len(facts.current()), len(episodes.all())
    assert known >= 50 and happened >= 50
    assert all(e.summary.startswith("Episode") for e in episodes.all())

    at = datetime(2026, 10, 30, 9)
    facts.add(Fact(new_id(at), "Written after the crash.", "learned", at, "chat"))
    episodes.append(Episode(new_id(at), at, "conversation", "After the crash."))
    again_facts, again_episodes = JsonlFactStore(tmp_path / "facts.jsonl"), JsonlEpisodeLog(tmp_path / "episodes")
    assert len(again_facts.current()) == known + 1 and len(again_episodes.all()) == happened + 1

    index = SqliteMemoryIndex(tmp_path / "memory.sqlite", HashEmbedder(), again_facts, again_episodes)
    index.refresh()
    assert index.count() == known + 1 + happened + 1
    assert index.search("after the crash", limit=1)[0].item.text == "After the crash."
    index.close()


def test_a_damaged_index_file_is_built_again_from_the_logs(tmp_path):
    facts, episodes = JsonlFactStore(tmp_path / "facts.jsonl"), JsonlEpisodeLog(tmp_path / "episodes")
    at = datetime(2026, 10, 30, 9)
    facts.add(Fact(new_id(at), "Anna is the user's sister.", "people", at, "chat"))
    episodes.append(Episode(new_id(at), at, "conversation", "Booked the flight to Lisbon."))
    path = tmp_path / "memory.sqlite"
    index = SqliteMemoryIndex(path, HashEmbedder(), facts, episodes)
    index.refresh()
    index.close()
    path.write_bytes(b"\0garbage" * 512)
    for suffix in ("-wal", "-shm"):
        (tmp_path / f"memory.sqlite{suffix}").unlink(missing_ok=True)
    index = SqliteMemoryIndex(path, HashEmbedder(), facts, episodes)
    index.refresh()
    assert index.count() == 2
    assert index.search("Lisbon flight", limit=1)[0].item.text == "Booked the flight to Lisbon."
    path.unlink()
    index.close()
    index = SqliteMemoryIndex(path, HashEmbedder(), facts, episodes)
    index.refresh()
    assert index.count() == 2
