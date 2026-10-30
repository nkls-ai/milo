"""~/Milo: where config, memory, reminders, state and logs live."""

from __future__ import annotations

from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

_DIRS = ("run", "state", "logs", "memory/journal")


class Workspace:
    """The single place that knows the workspace layout. Everything else asks it for paths."""

    def __init__(self, home: Path):
        self.home = home

    def ensure(self) -> None:
        """Copy the template in, never overwriting files the user or the agent edited, and create dirs."""
        _copy_missing(resources.files("milo") / "workspace_template", self.home)
        for sub in _DIRS:
            (self.home / sub).mkdir(parents=True, exist_ok=True)

    @property
    def config_path(self) -> Path:
        return self.home / "config.toml"

    @property
    def reminders_path(self) -> Path:
        return self.home / "reminders.md"

    @property
    def memory_dir(self) -> Path:
        return self.home / "memory"

    @property
    def profile_path(self) -> Path:
        return self.memory_dir / "profile.md"

    @property
    def persona_path(self) -> Path:
        return self.home / "persona.md"

    @property
    def state_dir(self) -> Path:
        return self.home / "state"

    @property
    def log_dir(self) -> Path:
        return self.home / "logs"

    @property
    def socket_path(self) -> Path:
        return self.home / "run" / "brain.sock"

    @property
    def hands_socket_path(self) -> Path:
        """Where the milo-mac MCP server reaches the brain."""
        return self.home / "run" / "hands.sock"

    @property
    def screens_dir(self) -> Path:
        """Screenshots the app takes for a look or the worker. The app writes and prunes them."""
        return self.state_dir / "screens"

    @property
    def usage_path(self) -> Path:
        return self.state_dir / "usage.jsonl"

    @property
    def dictation_history_path(self) -> Path:
        return self.home / "dictation-history.jsonl"

    @property
    def transcript_path(self) -> Path:
        return self.state_dir / "transcript.jsonl"

    @property
    def heartbeat_state_path(self) -> Path:
        return self.state_dir / "heartbeat.json"


def _copy_missing(src: Traversable, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        if entry.name == "__pycache__":
            continue
        target = dst / entry.name
        if entry.is_dir():
            _copy_missing(entry, target)
        elif not target.exists():
            target.write_bytes(entry.read_bytes())
