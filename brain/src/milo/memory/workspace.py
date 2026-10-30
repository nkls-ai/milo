"""~/Milo: where config, memory, reminders, state and logs live."""

from __future__ import annotations

from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

_DIRS = ("run", "state", "logs", "memory/journal", "memory/episodes", "routines")
_PRIVATE_DIRS = ("secrets",)


class Workspace:
    """The single place that knows the workspace layout. Everything else asks it for paths."""

    def __init__(self, home: Path):
        self.home = home

    def ensure(self) -> None:
        """Copy the template in, never overwriting files the user or the agent edited, and create dirs."""
        _copy_missing(resources.files("milo") / "workspace_template", self.home)
        for sub in _DIRS:
            (self.home / sub).mkdir(parents=True, exist_ok=True)
        for sub in _PRIVATE_DIRS:
            (self.home / sub).mkdir(mode=0o700, parents=True, exist_ok=True)

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
    def lock_path(self) -> Path:
        """Held by the running brain for its whole life, so a second one can't load the models too."""
        return self.home / "run" / "brain.lock"

    @property
    def tools_socket_path(self) -> Path:
        """Where helper processes (the app-connections server) ask the brain for approvals and app work."""
        return self.home / "run" / "tools.sock"

    @property
    def usage_path(self) -> Path:
        return self.state_dir / "usage.jsonl"

    @property
    def dictation_history_path(self) -> Path:
        return self.home / "dictation-history.jsonl"

    @property
    def transcript_path(self) -> Path:
        """The old one-scroll transcript. Migrated into conversations_dir once, then no longer written."""
        return self.state_dir / "transcript.jsonl"

    @property
    def transcript_kept_path(self) -> Path:
        """transcript.jsonl as it was before the migration, kept."""
        return self.state_dir / "transcript.before-conversations.jsonl"

    @property
    def conversations_dir(self) -> Path:
        """One JSONL file per conversation in month folders, plus index.jsonl. See memory/conversations.py."""
        return self.state_dir / "conversations"

    @property
    def routines_dir(self) -> Path:
        """One Markdown recipe per routine, readable and editable by hand."""
        return self.home / "routines"

    @property
    def routine_runs_path(self) -> Path:
        return self.state_dir / "routine-runs.jsonl"

    @property
    def routine_state_path(self) -> Path:
        """Which recipe versions the user saw, schedule bookkeeping, drafts waiting for a look."""
        return self.state_dir / "routines.json"

    @property
    def routine_drafts_dir(self) -> Path:
        return self.state_dir / "routine-drafts"

    @property
    def meetings_dir(self) -> Path:
        """One folder per meeting: audio chunks, transcript and notes. See memory/meetings.py."""
        return self.home / "meetings"

    @property
    def heartbeat_state_path(self) -> Path:
        return self.state_dir / "heartbeat.json"

    @property
    def episodes_dir(self) -> Path:
        """memory/episodes/YYYY-MM.jsonl: what happened, append-only."""
        return self.memory_dir / "episodes"

    @property
    def facts_path(self) -> Path:
        """memory/facts.jsonl: every change to what Milo knows, append-only. profile.md is rendered from it."""
        return self.memory_dir / "facts.jsonl"

    @property
    def journal_dir(self) -> Path:
        return self.memory_dir / "journal"

    @property
    def memory_index_path(self) -> Path:
        """The search index over memory. A cache: deleting it is safe, Milo builds it again."""
        return self.state_dir / "memory.sqlite"

    @property
    def profile_snapshot_path(self) -> Path:
        """profile.md as Milo last wrote it, to tell the user's edits from his own."""
        return self.state_dir / "profile.written.md"

    @property
    def sleep_state_path(self) -> Path:
        """Which days the nightly consolidation has done, and its call budget."""
        return self.state_dir / "sleep.json"

    @property
    def secrets_dir(self) -> Path:
        """Tokens like the Telegram bot's, readable by the user only. Never sent anywhere, never shared."""
        return self.home / "secrets"

    @property
    def remote_state_path(self) -> Path:
        """Whose phone may reach Milo by message, and whether that is paused (0600)."""
        return self.state_dir / "messages.json"


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
