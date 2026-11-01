"""What Milo keeps to take a task back (ADR 0026): `state/undo/<task>/record.json`, copies of the files the task
changed under `files/`, and the copies apps saved into folders of their own (Excel can't write anywhere else)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import stat
from copy import deepcopy
from pathlib import Path

from milo import system
from milo.core.control import Protected

log = logging.getLogger("milo.undo")

APP_FOLDERS = {"Microsoft Excel": "Library/Containers/com.microsoft.Excel/Data/tmp"}
"""Where each app may save a file without asking, under the user's home: its own sandbox container. Any other folder
makes Excel show "Grant File Access" and wait."""
COPY_PREFIX = "milo-undo-"
_TASK = re.compile(r"^[\w-]{1,64}$")
_ORDER = "_shelf_order"


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
        self._records: dict[str, dict] | None = None
        """Every record, as on disk, by task: read once at the first use, then written through. Only this brain
        writes state/undo (one brain at a time), so nothing changes under it."""
        self._order: dict[str, int] = {}
        self._last_order = 0
        """Persisted creation order breaks ties in second-resolution `made` times.
        Folder mtimes change whenever record.json is replaced and cannot order tasks."""

    def load(self, task: str) -> dict | None:
        self._folder(task)
        record = self._all().get(task)
        return deepcopy(record) if record is not None else None  # the caller changes it before it saves

    def save(self, task: str, record: dict) -> None:
        folder = self._folder(task)
        records = self._all()
        order = self._order.get(task)
        if order is None:
            self._last_order += 1
            order = self._last_order
        saved = {**deepcopy(record), _ORDER: order}
        folder.mkdir(parents=True, exist_ok=True)
        self._write(folder, saved)
        self._order[task] = order
        records[task] = saved

    @staticmethod
    def _write(folder: Path, record: dict) -> None:
        tmp = folder / "record.json.tmp"
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        system.replace_file(tmp, folder / "record.json")

    def tasks(self) -> list[str]:
        records = self._all()
        return sorted(records, key=lambda t: (str(records[t].get("made", "")), self._order[t], t))

    def drop(self, task: str) -> None:
        record = self.load(task) or {}
        for doc in record.get("docs", []):
            copy = self._app_copy(str(doc.get("copy") or ""))
            if copy is not None:
                copy.unlink(missing_ok=True)
        shutil.rmtree(self._folder(task), ignore_errors=True)
        self._all().pop(task, None)
        self._order.pop(task, None)

    def _all(self) -> dict[str, dict]:
        if self._records is not None:
            return self._records
        self._records = {}
        for folder in self._root.iterdir() if self._root.is_dir() else ():
            record = _read(folder / "record.json") if _TASK.match(folder.name) else None
            if record is not None:
                self._records[folder.name] = record
                order = record.get(_ORDER)
                if type(order) is int and order > 0:
                    self._order[folder.name] = order
                    self._last_order = max(self._last_order, order)
            elif folder.is_dir():
                shutil.rmtree(folder, ignore_errors=True)  # half written, or from an older Milo
        # Older records have no reliable tie-breaker. Migrate once in a stable
        # order, then persist it so subsequent saves/restarts cannot reshuffle it.
        legacy = sorted((t for t in self._records if t not in self._order),
                        key=lambda t: (str(self._records[t].get("made", "")), t))
        for task in legacy:
            self._last_order += 1
            self._order[task] = self._last_order
            self._records[task][_ORDER] = self._last_order
        for task in legacy:
            self._write(self._folder(task), self._records[task])
        return self._records

    def app_folder(self, app: str) -> str | None:
        rel = APP_FOLDERS.get(app)
        folder = self._home / rel if rel else None
        return folder.as_posix() if folder is not None and folder.is_dir() else None

    def keep_file(self, task: str, path: str) -> dict:
        target = Path(path).expanduser()
        if not target.is_absolute():
            raise ValueError("Give the file's full path.")
        target = target.resolve()  # the file a link points to, so Undo later writes there and only there
        if self._protected.covers(target):
            raise ValueError(f"{target.name} is one of Milo's own files. Don't change it, so it needs no undo point.")
        if target.is_dir():
            raise ValueError(f"{target} is a folder. Keep an undo point for each file you change in it.")
        try:  # no link is followed after the check, and a pipe can't make the open wait
            fd = system.open_no_follow(target)
        except FileNotFoundError:
            return {"path": str(target), "copy": "", "existed": False, "digest": ""}
        except OSError as e:
            raise ValueError(f"{target.name} changed into a link or can't be read.") from e
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f"{target.name} isn't a plain file.")
            if info.st_nlink > 1:  # another name could be one of Milo's own files
                raise ValueError(f"{target.name} has more than one name, so Milo keeps no copy of it.")
            if _same(target) != (info.st_dev, info.st_ino) or self._protected.covers(target):
                raise ValueError(f"{target.name} moved while Milo looked at it. Try again.")
            if info.st_size > self._max_file:
                raise ValueError(f"{target.name} is {info.st_size // (1024 * 1024)} MB, too big to keep a copy of.")
            # Establish the shelf before creating a not-yet-recorded task folder;
            # startup cleanup must not mistake these new snapshots for crash debris.
            self._all()
            files = self._folder(task) / "files"
            files.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(files).free - info.st_size < self._min_free:
                raise ValueError("The disk is too full to keep a copy.")
            copy = files / f"{len(list(files.iterdir())) + 1}-{target.name}"
            digest = hashlib.sha256()
            out = os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(out, "wb") as copied:
                system.make_private(copied.fileno(), 0o600)
                while chunk := source.read(1 << 20):
                    digest.update(chunk)
                    copied.write(chunk)
            os.utime(copy, ns=(info.st_atime_ns, info.st_mtime_ns))
        return {"path": str(target), "copy": str(copy.relative_to(self._folder(task))), "existed": True,
                "digest": digest.hexdigest(), "mode": stat.S_IMODE(info.st_mode)}

    def put_back(self, task: str, kept: dict) -> None:
        target = Path(str(kept["path"]))
        if target.resolve() != target or self._protected.covers(target):
            raise OSError(f"{target} is a link now, or one of Milo's own files: not writing through it.")
        if kept.get("existed"):
            source = self._folder(task) / str(kept["copy"])
            target.parent.mkdir(parents=True, exist_ok=True)
            system.restore_file(source, target, int(kept.get("mode", stat.S_IMODE(source.stat().st_mode))))
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


def _read(path: Path) -> dict | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def _ids(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _same(path: Path) -> tuple[int, int] | None:
    """The file `path` names now, without following a link at its end; None if there is none."""
    try:
        return _ids(os.lstat(path))
    except OSError:
        return None
