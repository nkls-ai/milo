"""dictionary.md on disk: learning keeps the user's lines and explanation, and edits are picked up (ADR 21)."""

from importlib import resources

from milo.core.dictionary import Fix
from milo.memory import dictionary as module
from milo.memory.dictionary import MarkdownDictionary

TEMPLATE = (resources.files("milo") / "workspace_template" / "dictionary.md").read_text()


def make(tmp_path, text=TEMPLATE) -> MarkdownDictionary:
    path = tmp_path / "dictionary.md"
    path.write_text(text)
    return MarkdownDictionary(path)


def test_the_template_holds_no_entries():
    assert module.parse(TEMPLATE) == module.Entries()


def test_a_new_fix_goes_at_the_end_of_the_fixes_section(tmp_path):
    d = make(tmp_path)
    assert d.learn("Cloud Code", "Claude Code") == "new"
    assert d.learn("Nicholas", "Niklas") == "new"
    text = d.path.read_text()
    assert text.startswith(TEMPLATE.rstrip("\n"))
    assert text.endswith("always counts.\n\n- Cloud Code -> Claude Code (seen 1)\n- Nicholas -> Niklas (seen 1)\n")
    assert d.entries().fixes == (Fix("Cloud Code", "Claude Code", 1), Fix("Nicholas", "Niklas", 1))


def test_a_fix_seen_again_counts_up_in_place(tmp_path):
    d = make(tmp_path, "## Fixes\n- teh -> the (seen 1)\n- Milow -> Milo\n\n## Notes\nmine\n")
    assert d.learn("teh", "the") == "again"
    assert d.path.read_text() == "## Fixes\n- teh -> the (seen 2)\n- Milow -> Milo\n\n## Notes\nmine\n"
    assert d.entries().fixes[0].applies


def test_new_fixes_go_before_the_next_section(tmp_path):
    d = make(tmp_path, "## Fixes\n- Milow -> Milo\n\n## Notes\nmine\n")
    d.learn("Nicholas", "Niklas")
    assert d.path.read_text() == "## Fixes\n- Milow -> Milo\n- Nicholas -> Niklas (seen 1)\n\n## Notes\nmine\n"


def test_undoing_a_learned_fix_forgets_it(tmp_path):
    d = make(tmp_path, "## Fixes\n- Cloud Code -> Claude Code (seen 1)\n")
    assert d.learn("Claude Code", "Cloud Code") == "undone"
    assert d.entries().fixes == ()


def test_a_fix_the_user_wrote_is_never_undone_or_replaced(tmp_path):
    d = make(tmp_path, "## Fixes\n- Cloud Code -> Claude Code\n")
    assert d.learn("Claude Code", "Cloud Code") == "kept"
    assert d.learn("Cloud Code", "Cloud Coat") == "kept"
    assert d.learn("Cloud Code", "Claude Code") == "again"
    assert d.path.read_text() == "## Fixes\n- Cloud Code -> Claude Code\n"


def test_another_meaning_replaces_a_learned_fix(tmp_path):
    d = make(tmp_path, "## Fixes\n- Nicholas -> Niklas (seen 3)\n")
    assert d.learn("Nicholas", "Nikolas") == "replaced"
    assert d.entries().fixes == (Fix("Nicholas", "Nikolas", 1),)


def test_a_missing_file_is_made(tmp_path):
    d = MarkdownDictionary(tmp_path / "dictionary.md")
    assert d.entries() == module.Entries()
    assert d.learn("Nicholas", "Niklas") == "new"
    assert d.path.read_text() == "# Dictionary\n\n## Fixes\n- Nicholas -> Niklas (seen 1)\n"


def test_invalid_and_full(tmp_path, monkeypatch):
    d = make(tmp_path)
    assert d.learn("a b c d e", "x") == "invalid"
    monkeypatch.setattr(module, "MAX_FIXES", 1)
    assert d.learn("Nicholas", "Niklas") == "new"
    assert d.learn("Cloud Code", "Claude Code") == "full"


def test_the_users_edits_are_read_again_and_changed_says_so(tmp_path):
    d = make(tmp_path)
    assert d.changed()
    d.entries()
    assert not d.changed()
    d.path.write_text(TEMPLATE.replace("like `- Milo`.\n", "like `- Milo`.\n\n- Anna Kowalski\n"))
    assert d.changed()
    assert d.entries().words == ("Anna Kowalski",)


def test_writes_replace_the_file_whole(tmp_path):
    d = make(tmp_path)
    d.learn("Nicholas", "Niklas")
    assert [p.name for p in tmp_path.iterdir()] == ["dictionary.md"], "no temporary file is left behind"
