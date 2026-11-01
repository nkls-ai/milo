"""Portable desktop connections. Unavailable integrations are represented by None.

Files reuse the common scope, protected-workspace and non-overwriting move
policies. No model or desktop session is needed to construct this adapter.
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from milo.core.control import Protected
from milo.core.ports import Connections, ConnectionIdentity
from milo.core.registry import CONNECTIONS, AdapterContext, ConfigError, options_from
from milo.core.types import ToolError

from . import _files, _portable_text

log = logging.getLogger(__name__)

# These hold application state, credentials or installed dependencies, rather
# than the user's documents. Hidden directories and reparse links are excluded too.
PRIVATE_DIRS = frozenset({"appdata", "library", "windows", "program files", "program files (x86)",
                         "programdata", "$recycle.bin", "system volume information", "node_modules",
                         "__pycache__"})
SOURCE_TEXT = frozenset({".toml", ".rst", ".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".scss",
                         ".c", ".cpp", ".h", ".hpp", ".java", ".rs", ".go", ".sql", ".sh", ".ps1"})
READABLE = _files.PLAIN | SOURCE_TEXT | _portable_text.SUFFIXES | {".xlsx", ".eml"}


def _limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ToolError("The number of files must be zero or a positive number.")
    return min(value, 100)


def _linked(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


@dataclass(frozen=True)
class DesktopOptions:
    files_scope: str = "~"


class LocalFiles:
    identity = ConnectionIdentity("Files")
    """A bounded local filesystem implementation of the Files port."""
    def __init__(self, scope: Path, protected: Protected | None = None, *, max_entries: int = 30_000,
                 max_search_s: float = 3.0):
        self.scope = Path(scope).expanduser().resolve()
        self.protected = protected
        self._max_entries = max(1, max_entries)
        self._max_search_s = max(0.01, max_search_s)

    def _allowed(self, path: Path) -> bool:
        if not _files.allowed(path, self.scope, protected=self.protected):
            return False
        try:
            relative = path.absolute().relative_to(self.scope)
            real = path.resolve().relative_to(self.scope)
            for parts in (relative.parts, real.parts):
                if any(part.startswith(".") or part.casefold() in PRIVATE_DIRS for part in parts):
                    return False
            # Do not follow a link even when it points back into the allowed scope.
            current = path
            while current != self.scope:
                if _linked(current):
                    return False
                current = current.parent
            return True
        except (ValueError, OSError):
            return False

    def _checked(self, path: str) -> Path:
        original = Path(path).expanduser()
        original = original if original.is_absolute() else self.scope / original
        found = _files.checked(path, self.scope, self.protected)
        if not self._allowed(original) or not self._allowed(found):
            raise ToolError(_files.OUTSIDE)
        return found

    def _folder(self, path: str, *, must_exist: bool = True) -> Path:
        original = Path(path).expanduser()
        original = original if original.is_absolute() else self.scope / original
        found = _files.folder(path, self.scope, must_exist=must_exist, protected=self.protected)
        if not self._allowed(original) or not self._allowed(found):
            raise ToolError(_files.OUTSIDE)
        return found

    def _newest(self, paths, limit: int) -> list[dict]:
        rows = []
        for path in paths:
            try:
                if self._allowed(path) and path.is_file():
                    rows.append((path.stat().st_mtime, _files.describe(path, self.scope)))
            except OSError:
                continue  # The user may move or remove a file during the scan.
        rows.sort(key=lambda item: (item[0], item[1]["name"].casefold()), reverse=True)
        return [row for _, row in rows[:limit]]

    def find(self, name: str, limit: int = 20) -> list[dict]:
        limit = _limit(limit)
        if not limit:
            return []
        query = name.casefold()
        return self._newest((p for p in self._all() if query in p.name.casefold()), limit)

    def search(self, text: str, limit: int = 20) -> list[dict]:
        limit = _limit(limit)
        words = text.casefold().split()
        if not words or not limit:
            return []
        deadline = time.monotonic() + self._max_search_s
        hits = []
        examined = 0
        for path in self._all():
            if time.monotonic() >= deadline or examined >= 256:
                break
            if path.suffix.casefold() not in READABLE:
                continue
            try:
                if path.stat().st_size > 2 * 1024 * 1024:
                    continue
                examined += 1
                content = (path.name + " " + self.read(str(path), 50_000)["text"]).casefold()
            except (OSError, ToolError):
                continue
            if all(word in content for word in words):
                hits.append(path)
        return self._newest(hits, limit)

    def read(self, path: str, max_chars: int = 20000) -> dict:
        try:
            return self._read(path, max_chars)
        except OSError as error:
            raise ToolError("That file could not be read. It may have moved or its permissions may have changed.") from error

    def _read(self, path: str, max_chars: int) -> dict:
        if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
            raise ToolError("The text length must be a positive number.")
        max_chars = min(max_chars, _portable_text.MAX_CHARS)
        found = self._checked(path)
        if found.stat().st_size > _portable_text.MAX_FILE_BYTES:
            raise ToolError("That file is too large to read at once.")
        suffix = found.suffix.casefold()
        if suffix in _portable_text.SUFFIXES:
            return _portable_text.read(found, max_chars)
        if suffix in SOURCE_TEXT:
            with found.open("r", encoding="utf-8", errors="replace") as stream:
                text = stream.read(max_chars + 1)
            return {"path": str(found), "name": found.name, "text": text[:max_chars], "truncated": len(text) > max_chars}
        if suffix in READABLE:
            return _files.read(found, max_chars)
        raise ToolError("This desktop reads text, PDF, DOCX, ODT, HTML, XLSX and EML files. "
                        "Save an older office document in one of those formats first.")

    def list(self, folder: str, name: str = "", limit: int = 20) -> list[dict]:
        limit = _limit(limit)
        where = self._folder(folder)
        query = name.casefold()
        if not limit:
            return []
        candidates = []
        try:
            with os.scandir(where) as entries:
                for index, entry in enumerate(entries):
                    if index >= self._max_entries:
                        break
                    if query in entry.name.casefold() and entry.is_file(follow_symlinks=False):
                        candidates.append(Path(entry.path))
        except OSError as error:
            raise ToolError("That folder could not be listed.") from error
        return self._newest(candidates, limit)

    def move(self, paths: list[str], folder: str) -> dict:
        files = [str(self._checked(path)) for path in paths]
        destination = self._folder(folder, must_exist=False)
        return _files.move(files, str(destination), self.scope, self.protected)

    def _all(self):
        if not self.scope.is_dir():
            return
        deadline = time.monotonic() + self._max_search_s
        pending = [(self.scope, 0)]
        visited = 0
        while pending:
            root, depth = pending.pop()
            try:
                with os.scandir(root) as entries:
                    for entry in entries:
                        visited += 1
                        if visited > self._max_entries or time.monotonic() >= deadline:
                            log.debug("Local files scan reached its bounded search budget")
                            return
                        if entry.name.startswith(".") or entry.name.casefold() in PRIVATE_DIRS:
                            continue
                        path = Path(entry.path)
                        if not self._allowed(path):
                            continue
                        if entry.is_dir(follow_symlinks=False) and depth < 32:
                            pending.append((path, depth + 1))
                        elif entry.is_file(follow_symlinks=False):
                            yield path
            except OSError:
                continue


@CONNECTIONS.register("desktop")
def _desktop(options: Mapping[str, Any], ctx: AdapterContext) -> Connections:
    parsed = options_from(DesktopOptions, options, "connections.desktop")
    if not isinstance(parsed.files_scope, str) or not parsed.files_scope.strip():
        raise ConfigError("[connections.desktop] files_scope must name a folder")
    return Connections(files=LocalFiles(Path(parsed.files_scope), Protected(ctx.home)))
