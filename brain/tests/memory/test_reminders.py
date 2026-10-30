import os
from datetime import datetime

from milo.memory.reminders import MarkdownReminders, parse


def test_parse_reminders():
    items = parse(
        "# Reminders\n"
        "- [ ] 2026-10-30 09:00 Call the dentist\n"
        "* [x] 2026-10-30 9:30 Done thing\n"
        "- [ ] 2026-13-40 09:00 invalid date\n"
        "- [ ] tomorrow buy milk\n"
    )
    assert [(r.due, r.text, r.done) for r in items] == [
        (datetime(2026, 10, 30, 9, 0), "Call the dentist", False),
        (datetime(2026, 10, 30, 9, 30), "Done thing", True),
    ]
    assert len({r.id for r in items}) == 2


def test_ids_are_stable_and_depend_on_date_time_and_text():
    a = parse("- [ ] 2026-10-30 09:00 one\n")[0]
    assert parse("# moved\n\n- [ ] 2026-10-30 09:00 one\n")[0].id == a.id
    assert parse("- [x] 2026-10-30 09:00 one\n")[0].id == a.id
    assert parse("- [ ] 2026-10-30 09:01 one\n")[0].id != a.id
    assert len(a.id) == 12


def test_rereads_only_when_mtime_changes(tmp_path):
    path = tmp_path / "reminders.md"
    source = MarkdownReminders(path)
    assert source.all() == []
    path.write_text("- [ ] 2026-10-30 09:00 one\n")
    os.utime(path, ns=(1, 1_000_000_000))
    assert len(source.all()) == 1
    # Same mtime: the cached parse is kept even though the content changed.
    path.write_text("- [ ] 2026-10-30 09:00 one\n- [ ] 2026-10-30 10:00 two\n")
    os.utime(path, ns=(1, 1_000_000_000))
    assert len(source.all()) == 1
    os.utime(path, ns=(1, 2_000_000_000))
    assert [r.text for r in source.all()] == ["one", "two"]


def test_deleted_file_means_no_reminders(tmp_path):
    path = tmp_path / "reminders.md"
    path.write_text("- [ ] 2026-10-30 09:00 one\n")
    source = MarkdownReminders(path)
    assert len(source.all()) == 1
    path.unlink()
    assert source.all() == []


def test_template_reminders_file_has_no_live_entries():
    from importlib import resources

    text = (resources.files("milo") / "workspace_template" / "reminders.md").read_text()
    assert parse(text) == []


def test_add_appends_a_line_and_returns_what_all_reports(tmp_path):
    path = tmp_path / "reminders.md"
    path.write_text("# Reminders\n- [ ] 2026-10-30 09:00 one")  # no final newline
    book = MarkdownReminders(path)
    assert len(book.all()) == 1
    added = book.add(datetime(2026, 10, 31, 7, 5), "  Call\nthe   dentist ")
    assert (added.due, added.text, added.done) == (datetime(2026, 10, 31, 7, 5), "Call the dentist", False)
    assert path.read_text() == "# Reminders\n- [ ] 2026-10-30 09:00 one\n- [ ] 2026-10-31 07:05 Call the dentist\n"
    assert book.all()[-1] == added
    assert [r.text for r in book.all()] == ["one", "Call the dentist"]


def test_add_creates_the_file_and_rejects_empty_text(tmp_path):
    import pytest

    book = MarkdownReminders(tmp_path / "sub" / "reminders.md")
    reminder = book.add(datetime(2026, 11, 1, 18, 0), "Gym")
    assert book.all() == [reminder]
    with pytest.raises(ValueError):
        book.add(datetime(2026, 11, 1, 18, 0), " \n ")
