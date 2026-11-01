from milo.core.ports import ProfileMemory
from milo.memory.profile import MAX_FACT, MarkdownProfile
from milo.memory.workspace import Workspace


def test_missing_profile_reads_empty_and_remember_creates_it(tmp_path):
    profile = MarkdownProfile(tmp_path / "memory" / "profile.md")
    assert isinstance(profile, ProfileMemory)
    assert profile.read() == ""
    profile.remember("Prefers tea over coffee")
    assert profile.read() == "## Learned\n- Prefers tea over coffee\n"


def test_remember_appends_under_learned_and_keeps_the_rest(tmp_path):
    path = tmp_path / "profile.md"
    path.write_text("# About the user\n\n## Basics\n- Name: Niklas\n\n## People", encoding="utf-8")  # no final newline
    profile = MarkdownProfile(path)
    profile.remember("Works on Milo")
    profile.remember("  Has a dog\n  named   Bo  ")
    assert path.read_text(encoding="utf-8") == (
        "# About the user\n\n## Basics\n- Name: Niklas\n\n## People\n\n## Learned\n- Works on Milo\n- Has a dog named Bo\n"
    )
    assert not list(tmp_path.glob("*.tmp"))


def test_remember_inserts_into_an_existing_learned_section(tmp_path):
    path = tmp_path / "profile.md"
    path.write_text("# About\n\n## Learned\n- one\n\n## Notes\nfree text\n", encoding="utf-8")
    MarkdownProfile(path).remember("two")
    assert path.read_text(encoding="utf-8") == "# About\n\n## Learned\n- one\n- two\n\n## Notes\nfree text\n"


def test_remember_skips_duplicates_and_empty_and_caps_length(tmp_path):
    path = tmp_path / "profile.md"
    path.write_text("## Basics\n- Name: Niklas\n", encoding="utf-8")
    profile = MarkdownProfile(path)
    profile.remember("Name: Niklas")  # already a bullet elsewhere in the file
    profile.remember("   \n ")
    profile.remember("- Likes jazz")
    profile.remember("Likes   jazz")
    assert path.read_text(encoding="utf-8") == "## Basics\n- Name: Niklas\n\n## Learned\n- Likes jazz\n"
    profile.remember("x" * 1000)
    assert path.read_text(encoding="utf-8").splitlines()[-1] == "- " + "x" * MAX_FACT


def test_template_profile_gets_a_learned_section(tmp_path):
    ws = Workspace(tmp_path)
    ws.ensure()
    profile = MarkdownProfile(ws.profile_path)
    before = profile.read()
    profile.remember("Lives in Berlin")
    assert profile.read() == before.rstrip("\n") + "\n\n## Learned\n- Lives in Berlin\n"
