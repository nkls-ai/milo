import tomllib

from milo.memory.workspace import Workspace

FILES = ("AGENTS.md", "CLAUDE.md", "reminders.md", "memory/profile.md", "config.toml")


def test_ensure_copies_template_and_creates_dirs(tmp_path):
    ws = Workspace(tmp_path / "Milo")
    ws.ensure()
    for f in FILES:
        assert (ws.home / f).is_file(), f
    for d in ("run", "state", "logs", "memory/journal"):
        assert (ws.home / d).is_dir(), d
    assert tomllib.loads(ws.config_path.read_text(encoding="utf-8"))["heartbeat"]["llm_calls_per_day"] == 0


def test_ensure_does_not_overwrite_user_edits(tmp_path):
    ws = Workspace(tmp_path)
    ws.ensure()
    (tmp_path / "memory/profile.md").write_text("mine", encoding="utf-8")
    ws.config_path.write_text("# my config\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").unlink()
    ws.ensure()
    assert (tmp_path / "memory/profile.md").read_text(encoding="utf-8") == "mine"
    assert ws.config_path.read_text(encoding="utf-8") == "# my config\n"
    assert (tmp_path / "AGENTS.md").exists()  # missing files come back


def test_paths(tmp_path):
    ws = Workspace(tmp_path)
    assert ws.config_path == tmp_path / "config.toml"
    assert ws.reminders_path == tmp_path / "reminders.md"
    assert ws.state_dir == tmp_path / "state"
    assert ws.log_dir == tmp_path / "logs"
    assert ws.socket_path == tmp_path / "run" / "brain.sock"
    assert ws.usage_path == tmp_path / "state" / "usage.jsonl"
    assert ws.dictation_history_path == tmp_path / "dictation-history.jsonl"
    assert ws.heartbeat_state_path == tmp_path / "state" / "heartbeat.json"
    assert ws.profile_path == tmp_path / "memory" / "profile.md"
    assert ws.persona_path == tmp_path / "persona.md"


def test_an_untouched_old_persona_takes_the_new_template_and_an_edited_one_is_kept(tmp_path):
    import hashlib
    from importlib import resources
    from milo.memory import workspace as ws
    old = b"the persona as an earlier Milo shipped it\r\n"
    untouched, edited = tmp_path / "a", tmp_path / "b"
    for home, text in ((untouched, old), (edited, old + b"my own line\n")):
        home.mkdir()
        (home / "persona.md").write_bytes(text)
    shipped = {"persona.md": frozenset({hashlib.sha256(old.replace(b"\r\n", b"\n")).hexdigest()})}
    original, ws._SHIPPED = ws._SHIPPED, shipped
    try:
        Workspace(untouched).ensure()
        Workspace(edited).ensure()
    finally:
        ws._SHIPPED = original
    current = (resources.files("milo") / "workspace_template" / "persona.md").read_bytes()
    assert (untouched / "persona.md").read_bytes() == current
    assert (edited / "persona.md").read_bytes() == old + b"my own line\n", "never overwrite the user's edits"


def test_the_persona_names_the_computer_milo_runs_on():
    from importlib import resources
    from milo.services.talk_prompt import PromptParts, system_prompt
    persona = (resources.files("milo") / "workspace_template" / "persona.md").read_text(encoding="utf-8")
    on_windows = system_prompt(PromptParts(persona=persona, computer="computer"))
    assert "user's computer" in on_windows and "Mac" not in on_windows.split("##")[0]
    assert "user's Mac" in system_prompt(PromptParts(persona=persona, computer="Mac"))
