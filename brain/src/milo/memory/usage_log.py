"""Reads state/usage.jsonl and dictation-history.jsonl back for the Usage page.

Both files only grow, one short line per call or dictation. A read scans each file once and parses only the lines
inside the span: a year of heavy use is some tens of thousands of lines, a few milliseconds."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

from milo.core.times import local
from milo.core.types import Usage
from milo.core.usage import Call, Dictated


class JsonlUsageHistory:
    """UsageHistory over the two files. Skips lines it can't read rather than failing, like the ledger."""

    def __init__(self, usage_path: Path, dictation_path: Path):
        self.usage_path = usage_path
        self.dictation_path = dictation_path

    def calls(self, since: date) -> list[Call]:
        out = []
        for e, at in _entries(self.usage_path, since):
            try:
                usage = Usage(int(e["input_tokens"]), int(e["cached_input_tokens"]), int(e["output_tokens"]))
            except (KeyError, TypeError, ValueError):
                continue
            out.append(Call(at, str(e.get("source") or "other"), str(e.get("harness") or ""), usage))
        return out

    def dictations(self, since: date) -> list[Dictated]:
        return [Dictated(at, str(e.get("app") or ""), len(str(e.get("text") or "").split()))
                for e, at in _entries(self.dictation_path, since)]

    def first_day(self) -> date | None:
        days = [d for d in (_first_day(self.usage_path), _first_day(self.dictation_path)) if d is not None]
        return min(days, default=None)


def _entries(path: Path, since: date) -> Iterator[tuple[dict, datetime]]:
    """Each line from `since` on, with its time. Lines start with {"ts": "YYYY-MM-DD..., so older ones are skipped
    by a string compare before any parsing."""
    floor = since.isoformat()
    try:
        f = path.open(encoding="utf-8")
    except FileNotFoundError:
        return
    with f:
        for line in f:
            head = line[8:18]
            if line.startswith('{"ts": "') and head < floor:
                continue
            try:
                e = json.loads(line)
                at = local(e["ts"])
            except (ValueError, KeyError, TypeError):
                continue
            if at.date() >= since:
                yield e, at


def _first_day(path: Path) -> date | None:
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    return local(json.loads(line)["ts"]).date()
                except (ValueError, KeyError, TypeError):
                    continue
    except FileNotFoundError:
        pass
    return None
