"""The routines folder: files in, files out, renames, deletes that can be undone, and the run log."""

import os
from dataclasses import replace

import pytest

from milo.core.routines import Routine, RoutineInput
from milo.memory.routines import JsonStateFile, MarkdownRoutineBook

REPORT = Routine("monday-report", "Monday report", "The weekly report.", (RoutineInput("month", "Which month?",
                                                                                     "last month"),),
                 "every Monday at 09:00", body="## Steps\n\n1. Do it.\n   Check: it's done.")


@pytest.fixture
def book(tmp_path):
    return MarkdownRoutineBook(tmp_path / "routines", tmp_path / "state" / "routine-runs.jsonl",
                               tmp_path / "state" / "routine-drafts")


def test_save_and_read_back(book):
    book.save(REPORT)
    assert (book.folder / "monday-report.md").read_text().startswith("---\nname: Monday report\n")
    assert book.all() == [REPORT] and book.get("monday-report") == REPORT
    assert book.get("nothing") is None and book.get("../etc/passwd") is None


def test_hand_edits_show_up_and_broken_files_are_reported(book):
    book.save(REPORT)
    path = book.folder / "monday-report.md"
    path.write_text(path.read_text().replace("The weekly report.", "Every week's report, by hand."))
    os.utime(path, ns=(1, 1))  # a different mtime even within one clock tick
    assert book.all()[0].description == "Every week's report, by hand."
    (book.folder / "broken.md").write_text("no front matter")
    (book.folder / ".hidden.md").write_text("---\nname: Hidden\n---\n")
    assert [r.slug for r in book.all()] == ["monday-report"]
    assert "three dashes" in book.problems()["broken"]


def test_rename_moves_the_file(book):
    book.save(REPORT)
    renamed = book.rename("monday-report", "Weekly  report")
    assert renamed.slug == "weekly-report" and renamed.name == "Weekly report"
    assert not (book.folder / "monday-report.md").exists() and book.get("weekly-report").body == REPORT.body
    book.save(replace(REPORT, slug="other", name="Other"))
    with pytest.raises(ValueError, match="already"):
        book.rename("weekly-report", "other")
    assert book.rename("weekly-report", "WEEKLY report").slug == "weekly-report"


def test_delete_moves_it_aside(book):
    book.save(REPORT)
    assert book.delete("monday-report") and book.all() == []
    book.save(REPORT)
    assert book.delete("monday-report")
    assert sorted(p.name for p in (book.folder / "deleted").iterdir()) == ["monday-report-2.md", "monday-report.md"]
    assert not book.delete("monday-report") and not book.delete("../x")


def test_update_keeps_what_the_user_wrote(book):
    book.save(REPORT)
    path = book.folder / "monday-report.md"
    path.write_text(path.read_text().replace("schedule:", "# my own note\nschedule:"))
    updated = book.update("monday-report", {"paused": "yes", "last_run": "2026-10-30 09:00, done", "schedule": ""})
    text = path.read_text()
    assert "# my own note\n" in text and "paused: yes" in text and "last_run: 2026-10-30 09:00, done" in text
    assert updated.paused and updated.schedule == "" and updated.body == REPORT.body
    assert updated.fingerprint() == REPORT.fingerprint()
    with pytest.raises(ValueError, match="yes or no"):
        book.update("monday-report", {"paused": "maybe"})
    assert book.get("monday-report").paused  # left as it was
    with pytest.raises(ValueError, match="no such"):
        book.update("nothing", {"paused": "no"})


def test_drafts(book):
    assert book.read_draft("d1") is None
    book.write_draft("d1", "---\nname: X\n---\n")
    assert book.draft_path("d1").parent == book.drafts and book.read_draft("d1").startswith("---")
    book.drop_draft("d1")
    book.drop_draft("d1")
    assert book.read_draft("d1") is None


def test_run_log(book):
    assert book.runs("monday-report") == []
    for n in range(7):
        book.record_run("monday-report" if n != 3 else "other", {"at": f"2026-10-2{n}T09:00", "outcome": "done"})
    runs = book.runs("monday-report")
    assert [r["at"] for r in runs] == [f"2026-10-2{n}T09:00" for n in (1, 2, 4, 5, 6)]
    assert runs[0]["slug"] == "monday-report"


def test_state_file(tmp_path):
    state = JsonStateFile(tmp_path / "state" / "routines.json")
    assert state.load() == {}
    state.save({"a": {"b": 1}})
    assert state.load() == {"a": {"b": 1}}
    state.path.write_text("[1, 2]")
    assert state.load() == {}
