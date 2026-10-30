"""Milo's control files (ADR 0020): which paths count, however they are written."""

from milo.core.control import CONTROL_FILES, CONTROL_FOLDERS, Protected


def test_every_control_file_and_everything_in_a_control_folder_is_covered(tmp_path):
    home = tmp_path / "Milo"
    (home / "work").mkdir(parents=True)
    p = Protected(home)
    for name in CONTROL_FILES:
        assert p.covers(home / name), name
    for name in CONTROL_FOLDERS:
        assert p.covers(home / name) and p.covers(home / name / "deep" / "x.md"), name
    assert p.covers(home / "Config.TOML") and p.covers(home / "ROUTINES" / "a.md"), "APFS ignores case"
    assert p.covers(home / "work" / ".." / "persona.md")
    assert not p.covers(home / "work" / "report.md") and not p.covers(home / "config.toml.bak")
    assert not p.covers(home / "routines-old" / "a.md") and not p.covers(tmp_path / "config.toml")


def test_a_link_to_a_control_file_counts_as_the_file(tmp_path):
    home = tmp_path / "Milo"
    (home / "work").mkdir(parents=True)
    (home / "config.toml").write_text("")
    (home / "work" / "notes.txt").symlink_to(home / "config.toml")
    (home / "work" / "mem").symlink_to(home / "memory", target_is_directory=True)
    p = Protected(home)
    assert p.covers(home / "work" / "notes.txt") and p.covers(home / "work" / "mem" / "facts.jsonl")


def test_scripts_are_checked_for_full_and_tilde_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    home = tmp_path / "Milo"
    p = Protected(home)
    assert p.mentioned_in('do shell script "echo >> ~/Milo/config.toml"') == [home / "config.toml"]
    assert p.mentioned_in(f"cp x {home}/ROUTINES/a.md") == [home / "routines"]
    assert p.mentioned_in(f"cat {home}/config.toml.bak; ls {home}/work; ls {home}/routines-old") == []


def test_claudes_deny_rules_name_every_control_path_and_hide_the_secrets(tmp_path):
    home = tmp_path / "Milo"
    rules = Protected(home).deny_rules()
    root = f"/{home.resolve()}"
    assert f"Edit({root}/config.toml)" in rules and f"Write({root}/memory/**)" in rules
    assert f"Read({root}/secrets/**)" in rules
    assert len(rules) == 2 * (len(CONTROL_FILES) + len(CONTROL_FOLDERS)) + 1
