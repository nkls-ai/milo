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
    assert tomllib.loads(ws.config_path.read_text())["heartbeat"]["llm_calls_per_day"] == 0


def test_ensure_does_not_overwrite_user_edits(tmp_path):
    ws = Workspace(tmp_path)
    ws.ensure()
    (tmp_path / "memory/profile.md").write_text("mine")
    ws.config_path.write_text("# my config\n")
    (tmp_path / "AGENTS.md").unlink()
    ws.ensure()
    assert (tmp_path / "memory/profile.md").read_text() == "mine"
    assert ws.config_path.read_text() == "# my config\n"
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
