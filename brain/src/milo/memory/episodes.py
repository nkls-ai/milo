"""Episodes: memory/episodes/YYYY-MM.jsonl, one JSON line per episode or change, never rewritten.

A line with an id seen before is a newer version of that episode (the night's summary replacing the day's
stub). `{"id": ..., "forgotten": true}` leaves it out from then on; `"forgotten": false` brings it back.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

from milo.core.memory import Episode
from milo.core.times import local

from . import jsonl

log = logging.getLogger(__name__)


class JsonlEpisodeLog:
    """EpisodeLog over monthly files. Reads only the months a query touches."""

    def __init__(self, folder: Path, clock=None):
        self.folder = folder
        self._clock = clock

    def append(self, episode: Episode) -> None:
        jsonl.append(self._file(episode.at), episode.to_dict())

    def forget(self, id: str, reason: str) -> None:
        self._mark(id, True, reason)

    def remember(self, id: str, reason: str) -> None:
        """Undo forget()."""
        self._mark(id, False, reason)

    def between(self, start: datetime, end: datetime) -> list[Episode]:
        found = [e for e in self._latest(self._months(start, end)) if start <= e.at < end]
        return sorted(found, key=lambda e: (e.at, e.id))

    def all(self) -> list[Episode]:
        return sorted(self._latest(sorted(self.folder.glob("*.jsonl"))), key=lambda e: (e.at, e.id))

    def files(self) -> list[Path]:
        return sorted(self.folder.glob("*.jsonl"))

    def _mark(self, id: str, forgotten: bool, reason: str) -> None:
        at = self._at_of(id)
        if at is None:
            raise KeyError(id)
        now = self._clock.now() if self._clock is not None else datetime.now()
        jsonl.append(self._file(at), {"id": id, "forgotten": forgotten, "reason": reason,
                                      "on": now.isoformat(timespec="seconds")})

    def _at_of(self, id: str) -> datetime | None:
        for path in reversed(self.files()):
            for record in jsonl.read_all(path):
                if record.get("id") == id and "at" in record:
                    return local(record["at"])
        return None

    def _latest(self, paths: list[Path]) -> Iterator[Episode]:
        """The newest version of every episode in these files that isn't forgotten."""
        versions: dict[str, Episode] = {}
        forgotten: dict[str, bool] = {}
        for path in paths:
            for record in jsonl.read_all(path):
                id = record.get("id")
                if not id:
                    continue
                if "forgotten" in record:
                    forgotten[id] = bool(record["forgotten"])
                    continue
                try:
                    versions[id] = Episode.from_dict(record)
                except (KeyError, TypeError, ValueError):
                    log.warning("skipping a malformed episode in %s", path.name)
        return (e for id, e in versions.items() if not forgotten.get(id))

    def _months(self, start: datetime, end: datetime) -> list[Path]:
        paths, month = [], datetime(start.year, start.month, 1)
        while month < end:
            path = self.folder / f"{month:%Y-%m}.jsonl"
            if path.exists():
                paths.append(path)
            month = (month + timedelta(days=32)).replace(day=1)
        return paths

    def _file(self, at: datetime) -> Path:
        return self.folder / f"{at:%Y-%m}.jsonl"
