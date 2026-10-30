"""profile.md as a view over facts: migration, rendering, the remember tag and the user's own edits."""

from __future__ import annotations

from milo.memory.fact_profile import BACKUP, FactProfile, guess_topic, migrate, parse, render
from milo.memory.facts import JsonlFactStore
from tests.fakes import FakeClock

OLD_PROFILE = """\
# About the user

## Basics
- Name: Niklas
- Speaks German and English.

## Work and projects
Builds Milo in the evenings.

## Preferences

## People
* Anna is his sister.

## Routines

## Notes from the user
- Likes the window on the left.

## Learned
- The user is building Milo, the assistant, and works late at night in T3 Code.
- The user is building Milo, the assistant, and works late at night in T3 Code.
"""


def setup(tmp_path, text: str | None = OLD_PROFILE):
    profile_path = tmp_path / "memory" / "profile.md"
    profile_path.parent.mkdir(parents=True)
    if text is not None:
        profile_path.write_text(text)
    clock = FakeClock()
    facts = JsonlFactStore(tmp_path / "memory" / "facts.jsonl", clock)
    changes: list[int] = []
    profile = FactProfile(facts, profile_path, tmp_path / "state" / "profile.written.md", clock,
                          on_change=lambda: changes.append(1))
    return facts, profile, profile_path, changes


def test_migration_moves_every_line_into_facts_and_keeps_the_old_file(tmp_path):
    facts, profile, path, _ = setup(tmp_path)
    assert migrate(path, facts, FakeClock()) == 6
    got = [(f.topic, f.text) for f in facts.current()]
    assert got == [("basics", "Name: Niklas"), ("basics", "Speaks German and English."),
                   ("work", "Builds Milo in the evenings."), ("people", "Anna is his sister."),
                   ("learned", "Likes the window on the left."),
                   ("learned", "The user is building Milo, the assistant, and works late at night in T3 Code.")]
    assert (path.parent / BACKUP).read_text() == OLD_PROFILE
    assert all(f.source == "profile.md" for f in facts.current())
    assert migrate(path, facts, FakeClock()) == 0  # only once
    profile.write()
    text = path.read_text()
    assert "## People\n\n- Anna is his sister." in text and "facts.jsonl" in text


def test_no_profile_still_marks_the_migration_done(tmp_path):
    facts, _, path, _ = setup(tmp_path, None)
    assert migrate(path, facts, FakeClock()) == 0
    assert facts.path.exists() and facts.current() == []


def test_read_renders_facts_and_pinned_only_gives_the_always_on_ones(tmp_path):
    facts, profile, path, _ = setup(tmp_path)
    migrate(path, facts, FakeClock())
    assert "## People" in profile.read() and "- Anna is his sister." in profile.read()
    profile.pinned_only = True
    assert profile.read() == "## Basics\n\n- Name: Niklas\n- Speaks German and English.\n"


def test_remember_files_a_fact_by_topic_and_ignores_one_it_knows(tmp_path):
    facts, profile, path, changes = setup(tmp_path, None)
    migrate(path, facts, FakeClock())
    added = profile.remember("  - Anna is the user's sister, birthday March 3.  ")
    assert (added.topic, added.text, added.source) == ("people", "Anna is the user's sister, birthday March 3.", "chat")
    assert profile.remember("anna is the user's sister, birthday march 3.") is None
    assert profile.remember("   ") is None
    assert changes == [1]
    assert "- Anna is the user's sister" in path.read_text()


def test_topic_guesses():
    assert guess_topic("Anna is the user's sister.") == "people"
    assert guess_topic("Die Schwester heißt Anna.") == "people"
    assert guess_topic("The user's name is Niklas.") == "basics"
    assert guess_topic("Calls his mother every Sunday.") == "people"
    assert guess_topic("Goes running every morning.") == "routines"
    assert guess_topic("Works at a bank.") == "work"
    assert guess_topic("Prefers short answers.") == "preferences"
    assert guess_topic("Has a cat.") == "learned"


def test_the_users_edits_to_profile_md_become_facts(tmp_path):
    facts, profile, path, changes = setup(tmp_path)
    migrate(path, facts, FakeClock())
    profile.write()
    text = path.read_text()
    text = text.replace("- Anna is his sister.\n", "- Anna is his sister.\n- Ben is his brother.\n")
    text = text.replace("- Builds Milo in the evenings.\n", "")
    path.write_text(text)
    assert profile.sync() == 2
    current = {(f.topic, f.text) for f in facts.current()}
    assert ("people", "Ben is his brother.") in current
    assert ("work", "Builds Milo in the evenings.") not in current
    assert [c["by"] for c in facts.changes()[-2:]] == ["you", "you"]
    assert profile.sync() == 0
    assert changes == [1]


def test_parse_and_render_round_trip():
    text = render([], heading=True)
    assert parse(text) == []
    assert parse("<!-- a\nnote -->\n## People\n- Anna\n") == [("people", "Anna")]
