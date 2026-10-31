"""What Milo keeps to take a task back (ADR 0026): `state/undo/<task>/record.json`, copies of the files the task
changed under `files/`, and the copies apps saved into folders of their own (Excel can't write anywhere else)."""

from __future__ import annotations

import contextlib
import ctypes
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
        self._records: dict[str, dict] | None = None
        """Every record, as on disk, by task: read once at the first use, then written through. Only this brain
        writes state/undo (one brain at a time), so nothing changes under it."""
        self._born: dict[str, float] = {}
        """Each task folder's birth time, which orders tasks made in the same second."""

    def load(self, task: str) -> dict | None:
        self._folder(task)
        record = self._all().get(task)
        return deepcopy(record) if record is not None else None  # the caller changes it before it saves

    def save(self, task: str, record: dict) -> None:
        folder = self._folder(task)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / "record.json.tmp"
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1))
        os.replace(tmp, folder / "record.json")
        records = self._all()
        if task not in records:
            self._born[task] = _born(folder)
        records[task] = deepcopy(record)

    def tasks(self) -> list[str]:
        records = self._all()
        return sorted(records, key=lambda t: (str(records[t].get("made", "")), self._born.get(t, 0.0), t))

    def drop(self, task: str) -> None:
        record = self.load(task) or {}
        for doc in record.get("docs", []):
            copy = self._app_copy(str(doc.get("copy") or ""))
            if copy is not None:
                copy.unlink(missing_ok=True)
        shutil.rmtree(self._folder(task), ignore_errors=True)
        self._all().pop(task, None)
        self._born.pop(task, None)

    def _all(self) -> dict[str, dict]:
        if self._records is not None:
            return self._records
        self._records = {}
        for folder in self._root.iterdir() if self._root.is_dir() else ():
            record = _read(folder / "record.json") if _TASK.match(folder.name) else None
            if record is not None:
                self._records[folder.name] = record
                self._born[folder.name] = _born(folder)
            elif folder.is_dir():
                shutil.rmtree(folder, ignore_errors=True)  # half written, or from an older Milo
        return self._records

    def app_folder(self, app: str) -> str | None:
        rel = APP_FOLDERS.get(app)
        folder = self._home / rel if rel else None
        return str(folder) if folder is not None and folder.is_dir() else None

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
            fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
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
            files = self._folder(task) / "files"
            files.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(files).free - info.st_size < self._min_free:
                raise ValueError("The disk is too full to keep a copy.")
            copy = files / f"{len(list(files.iterdir())) + 1}-{target.name}"
            digest = hashlib.sha256()
            out = os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(out, "wb") as copied:
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
            # Everything happens in the folder Milo opened and checked: a new file of its own there, then a rename
            # that replaces a link put at the target meanwhile instead of writing through it.
            folder = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                if _same(target.parent) != _ids(os.fstat(folder)) or self._protected.covers(target.parent):
                    raise OSError(f"{target.parent} changed into a link: not writing there.")
                tmp = f"{COPY_PREFIX}{secrets.token_hex(8)}-{target.name}"
                out = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
                try:
                    with os.fdopen(out, "wb") as written, open(source, "rb") as copy:
                        shutil.copyfileobj(copy, written)
                        info = os.stat(source)
                        os.utime(written.fileno(), ns=(info.st_atime_ns, info.st_mtime_ns))
                        os.chmod(written.fileno(), int(kept.get("mode", stat.S_IMODE(info.st_mode))))
                    _rename_in(folder, tmp, target.name)
                except BaseException:
                    with contextlib.suppress(OSError):
                        os.unlink(tmp, dir_fd=folder)
                    raise
            finally:
                os.close(folder)
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
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def _born(folder: Path) -> float:
    st = folder.stat()
    return getattr(st, "st_birthtime", st.st_mtime)


def _ids(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _same(path: Path) -> tuple[int, int] | None:
    """The file `path` names now, without following a link at its end; None if there is none."""
    try:
        return _ids(os.lstat(path))
    except OSError:
        return None


_libc = ctypes.CDLL(None, use_errno=True)


def _rename_in(folder: int, old: str, new: str) -> None:
    """rename(2) inside the open `folder`, so no link put in its path since can move the write elsewhere. Python's
    os.replace takes no folder on macOS, so this calls renameat(2) itself."""
    if _libc.renameat(folder, old.encode(), folder, new.encode()) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), new)
