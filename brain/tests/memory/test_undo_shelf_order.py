"""Undo retention depends on persisted task creation order, not directory timestamps."""
import json
import os

from milo.core.control import Protected
from milo.memory.undo_shelf import FileUndoShelf


MADE = "2026-11-01T10:00:00"


def shelf(tmp_path):
    return FileUndoShelf(tmp_path / "Milo" / "state" / "undo", tmp_path,
                         protected=Protected(tmp_path / "Milo"), min_free_mb=0)


def record(title):
    return {"made": MADE, "title": title, "state": "ready", "docs": []}


def test_same_second_order_survives_saves_coarse_timestamps_and_reload(tmp_path):
    first = shelf(tmp_path)
    first.save("z-older", record("Older"))
    first.save("a-newer", record("Newer"))
    root = tmp_path / "Milo" / "state" / "undo"
    for folder in root.iterdir():
        os.utime(folder, (1, 1))  # exactly tied filesystem times, regardless of filesystem precision
    assert first.tasks() == ["z-older", "a-newer"]

    # Updating an older task must not make it newer, even if its folder mtime advances.
    first.save("z-older", record("Older, updated"))
    assert first.tasks() == ["z-older", "a-newer"]
    later = shelf(tmp_path)
    assert later.tasks() == ["z-older", "a-newer"]
    assert later.load("z-older")["title"] == "Older, updated"
    later.save("z-older", record("Updated after restart"))
    later.save("b-newest", record("Newest"))
    assert shelf(tmp_path).tasks() == ["z-older", "a-newer", "b-newest"]


def test_save_preserves_original_sequence_even_when_caller_omits_or_changes_metadata(tmp_path):
    first = shelf(tmp_path)
    first.save("z-older", record("Older"))
    first.save("a-newer", record("Newer"))
    order = first.load("z-older")["_shelf_order"]
    first.save("z-older", {**record("Edited"), "_shelf_order": 999999})
    assert first.load("z-older")["_shelf_order"] == order
    assert shelf(tmp_path).tasks() == ["z-older", "a-newer"]


def test_legacy_records_migrate_once_to_a_persisted_deterministic_order(tmp_path):
    root = tmp_path / "Milo" / "state" / "undo"
    for task in ("z-legacy", "a-legacy"):
        folder = root / task
        folder.mkdir(parents=True)
        (folder / "record.json").write_text(json.dumps(record(task)), encoding="utf-8")
    expected = ["a-legacy", "z-legacy"]
    assert shelf(tmp_path).tasks() == expected
    for index, task in enumerate(reversed(expected), 1):
        os.utime(root / task, (index, index))
        data = json.loads((root / task / "record.json").read_text(encoding="utf-8"))
        assert type(data["_shelf_order"]) is int
    assert shelf(tmp_path).tasks() == expected


def test_first_save_after_direct_snapshot_does_not_clean_up_its_own_copy(tmp_path):
    user_file = tmp_path / "Budget.txt"
    user_file.write_text("Before", encoding="utf-8")
    first = shelf(tmp_path)
    kept = first.keep_file("new-task", str(user_file))
    first.save("new-task", {**record("Budget"), "files": [kept]})
    copy = tmp_path / "Milo" / "state" / "undo" / "new-task" / kept["copy"]
    assert copy.read_text(encoding="utf-8") == "Before"
    assert shelf(tmp_path).load("new-task")["files"] == [kept]
