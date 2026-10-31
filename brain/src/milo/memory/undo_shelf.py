"""What Milo keeps to take a task back (ADR 0024): `state/undo/<task>/record.json`, copies of the files the task
changed under `files/`, and the copies apps saved into folders of their own (Excel can't write anywhere else)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from pathlib import Path

from milo.core.control import Protected

log = logging.getLogger("milo.undo")

APP_FOLDERS = {"Microsoft Excel": "Library/Containers/com.microsoft.Excel/Data/tmp"}
"""Where each app may save a file without asking, under the user's home: its own sandbox container. Any other folder
makes Excel show "Grant File Access" and wait."""
COPY_PREFIX = "milo-undo-"
_TASK = re.compile(r"^[\w-]{1,64}$")


class FileUndoShelf:
    """The UndoShelf on disk. `home` is the user's home, where the apps' own folders are; `root` is state/undo.
    `protected` is Milo's workspace: nothing in its control files and folders (secrets, state, config) is kept or
    put back, so an undo point can't hand a worker a copy of a key or write over Milo's settings."""

    def __init__(self, root: Path, home: Path, *, protected: Protected, max_file_mb: int = 200,
                 min_free_mb: int = 2048):
        self._root = root
        self._home = home
        self._protected = protected
        self._max_file = max_file_mb * 1024 * 1024
        self._min_free = min_free_mb * 1024 * 1024

    def load(self, task: str) -> dict | None:
        try:
            return json.loads((self._folder(task) / "record.json").read_text())
        except (OSError, ValueError):
            return None

    def save(self, task: str, record: dict) -> None:
        folder = self._folder(task)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / "record.json.tmp"
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1))
        os.replace(tmp, folder / "record.json")

    def tasks(self) -> list[str]:
        if not self._root.is_dir():
            return []
        found = []
        for folder in self._root.iterdir():
            record = self.load(folder.name) if _TASK.match(folder.name) else None
            if record is not None:  # the folder's birth time orders tasks made in the same second
                found.append((str(record.get("made", "")), _born(folder), folder.name))
            elif folder.is_dir():
                shutil.rmtree(folder, ignore_errors=True)  # half written, or from an older Milo
        return [task for *_, task in sorted(found)]

    def drop(self, task: str) -> None:
        record = self.load(task) or {}
        for doc in record.get("docs", []):
            copy = self._app_copy(str(doc.get("copy") or ""))
            if copy is not None:
                copy.unlink(missing_ok=True)
        shutil.rmtree(self._folder(task), ignore_errors=True)

    def app_folder(self, app: str) -> str | None:
        rel = APP_FOLDERS.get(app)
        folder = self._home / rel if rel else None
        return str(folder) if folder is not None and folder.is_dir() else None

    def keep_file(self, task: str, path: str) -> dict:
        target = Path(path).expanduser()
        if not target.is_absolute():
            raise ValueError("Give the file's full path.")
        if self._protected.covers(target):
            raise ValueError(f"{target.name} is one of Milo's own files. Don't change it, so it needs no undo point.")
        target = target.resolve()  # the file a link points to, so Undo later writes there and only there
        if target.is_dir():
            raise ValueError(f"{target} is a folder. Keep an undo point for each file you change in it.")
        if not target.exists():
            return {"path": str(target), "copy": "", "existed": False, "digest": ""}
        size = target.stat().st_size
        if size > self._max_file:
            raise ValueError(f"{target.name} is {size // (1024 * 1024)} MB, too big to keep a copy of.")
        files = self._folder(task) / "files"
        files.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(files).free - size < self._min_free:
            raise ValueError("The disk is too full to keep a copy.")
        copy = files / f"{len(list(files.iterdir())) + 1}-{target.name}"
        shutil.copy2(target, copy)
        return {"path": str(target), "copy": str(copy.relative_to(self._folder(task))), "existed": True,
                "digest": self.digest(str(target))}

    def put_back(self, task: str, kept: dict) -> None:
        target = Path(str(kept["path"]))
        if target.resolve() != target or self._protected.covers(target):
            raise OSError(f"{target} is a link now, or one of Milo's own files: not writing through it.")
        if kept.get("existed"):
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(f".{target.name}.milo-undo")
            shutil.copy2(self._folder(task) / str(kept["copy"]), tmp)
            os.replace(tmp, target)  # replaces a link put there meanwhile instead of writing through it
        elif target.exists():
            trash = self._home / ".Trash"
            trash.mkdir(exist_ok=True)
            dest, n = trash / target.name, 1
            while dest.exists():
                n += 1
                dest = trash / f"{target.stem} {n}{target.suffix}"
            shutil.move(str(target), dest)

    def digest(self, path: str) -> str:
        try:
            with open(path, "rb") as f:
                return hashlib.file_digest(f, "sha256").hexdigest()
        except OSError:
            return ""

    def used(self) -> int:
        total = 0
        if self._root.is_dir():
            total += sum(p.stat().st_size for p in self._root.rglob("*") if p.is_file())
        for rel in APP_FOLDERS.values():
            folder = self._home / rel
            if folder.is_dir():
                total += sum(p.stat().st_size for p in folder.glob(f"{COPY_PREFIX}*") if p.is_file())
        return total

    def _folder(self, task: str) -> Path:
        if not _TASK.match(task):
            raise ValueError(f"not a task id: {task!r}")
        return self._root / task

    def _app_copy(self, path: str) -> Path | None:
        """`path` if it is one of Milo's copies in an app's folder, so drop() deletes nothing else."""
        if not path:
            return None
        p = Path(path)
        if not p.name.startswith(COPY_PREFIX):
            return None
        folders = {os.path.normpath(self._home / rel) for rel in APP_FOLDERS.values()}
        return p if os.path.normpath(p.parent) in folders else None


def _born(folder: Path) -> float:
    st = folder.stat()
    return getattr(st, "st_birthtime", st.st_mtime)
