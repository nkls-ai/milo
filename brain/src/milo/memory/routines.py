"""~/Milo/routines: one Markdown recipe per routine, and a JSONL log of their runs in state/."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import replace
from pathlib import Path

from milo.core.routines import RecipeError, Routine, parse, render, slugify

log = logging.getLogger(__name__)

DELETED = "deleted"
"""Deleted routines go to routines/deleted/, so a mistake can be put back by hand."""


class MarkdownRoutineBook:
    """RoutineBook over a folder of `<slug>.md` files. A file is parsed again only when its mtime or size
    changes, so listing the routines before every chat message costs a few stat() calls."""

    def __init__(self, folder: Path, runs_path: Path):
        self.folder = folder
        self.runs_path = runs_path
        self._cache: dict[Path, tuple[tuple[int, int], Routine | RecipeError]] = {}

    def all(self) -> list[Routine]:
        return sorted((r for r in self._read_all().values() if isinstance(r, Routine)), key=lambda r: r.name.lower())

    def problems(self) -> dict[str, str]:
        return {slug: str(r) for slug, r in self._read_all().items() if isinstance(r, RecipeError)}

    def get(self, slug: str) -> Routine | None:
        found = self._read(self._path(slug)) if _safe(slug) else None
        return found if isinstance(found, Routine) else None

    def save(self, routine: Routine) -> Routine:
        if not _safe(routine.slug):
            raise ValueError(f"not a routine file name: {routine.slug!r}")
        self.folder.mkdir(parents=True, exist_ok=True)
        _write(self._path(routine.slug), render(routine))
        return routine

    def rename(self, slug: str, name: str) -> Routine:
        old = self.get(slug)
        if old is None:
            raise ValueError("there is no such routine")
        name = " ".join(name.split())
        new_slug = slugify(name)
        if new_slug != slug and self._path(new_slug).exists():
            raise ValueError(f"there is a routine called {name} already")
        renamed = replace(old, slug=new_slug, name=name)
        self.save(renamed)
        if new_slug != slug:
            self._path(slug).unlink(missing_ok=True)
        return renamed

    def delete(self, slug: str) -> bool:
        path = self._path(slug)
        if not _safe(slug) or not path.exists():
            return False
        aside = self.folder / DELETED
        aside.mkdir(exist_ok=True)
        target = aside / path.name
        n = 1
        while target.exists():
            n += 1
            target = aside / f"{slug}-{n}.md"
        os.replace(path, target)
        self._cache.pop(path, None)
        return True

    def record_run(self, slug: str, run: dict) -> None:
        self.runs_path.parent.mkdir(parents=True, exist_ok=True)
        with self.runs_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({**run, "slug": slug}, ensure_ascii=False) + "\n")

    def runs(self, slug: str, n: int = 5) -> list[dict]:
        try:
            lines = self.runs_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        out = []
        for line in reversed(lines):
            try:
                run = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(run, dict) and run.get("slug") == slug:
                out.append(run)
                if len(out) >= n:
                    break
        return out[::-1]

    def _path(self, slug: str) -> Path:
        return self.folder / f"{slug}.md"

    def _read_all(self) -> dict[str, Routine | RecipeError]:
        try:
            paths = sorted(p for p in self.folder.glob("*.md") if p.is_file() and not p.name.startswith("."))
        except OSError:
            return {}
        for gone in set(self._cache) - set(paths):
            del self._cache[gone]
        out: dict[str, Routine | RecipeError] = {}
        for path in paths:
            found = self._read(path)
            if found is not None:
                out[path.stem] = found
        return out

    def _read(self, path: Path) -> Routine | RecipeError | None:
        try:
            st = path.stat()
        except OSError:
            self._cache.pop(path, None)
            return None
        key = (st.st_mtime_ns, st.st_size)
        cached = self._cache.get(path)
        if cached is not None and cached[0] == key:
            return cached[1]
        try:
            found: Routine | RecipeError = parse(path.read_text(encoding="utf-8"), path.stem)
        except RecipeError as e:
            log.warning("routine %s doesn't read: %s", path.name, e)
            found = e
        except (OSError, UnicodeDecodeError) as e:
            found = RecipeError(f"it can't be read ({e.__class__.__name__})")
        self._cache[path] = (key, found)
        return found


class JsonStateFile:
    """StateFile: one JSON object, written atomically."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, data: dict) -> None:
        _write(self.path, json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _safe(slug: str) -> bool:
    return bool(slug) and slug == slugify(slug)
