"""A text file read again only when it changed, for files read on every press of the talk key (persona.md,
profile.md): a stat instead of a read."""

from __future__ import annotations

from pathlib import Path


class TextFile:
    """`read()` is the file's text, "" while it doesn't exist. It reads the file again only when its modification
    time or size changed. Raises OSError when the file can't be read."""

    def __init__(self, path: Path):
        self.path = path
        self._seen: tuple[int, int] | None = None
        self._text = ""

    def read(self) -> str:
        try:
            info = self.path.stat()
        except FileNotFoundError:
            self._seen, self._text = None, ""
            return ""
        if (info.st_mtime_ns, info.st_size) != self._seen:
            self._text = self.path.read_text(encoding="utf-8", errors="replace")
            self._seen = (info.st_mtime_ns, info.st_size)
        return self._text
