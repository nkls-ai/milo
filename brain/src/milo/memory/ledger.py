"""Token usage per harness call, one JSON line each, so the user can see what Milo costs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from milo.core.ports import Clock
from milo.core.types import Usage


@dataclass(frozen=True)
class UsageTotals:
    calls: int
    usage: Usage


class JsonlUsageLedger:
    """UsageLedger appending to state/usage.jsonl. Append-only, so a crash loses at most one line."""

    def __init__(self, path: Path, clock: Clock):
        self.path = path
        self.clock = clock

    def record(self, source: str, harness: str, usage: Usage) -> None:
        entry = {
            "ts": self.clock.now().isoformat(timespec="seconds"),
            "source": source,
            "harness": harness,
            "input_tokens": usage.input_tokens,
            "cached_input_tokens": usage.cached_input_tokens,
            "output_tokens": usage.output_tokens,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def today_totals(self) -> UsageTotals:
        """Calls and tokens since local midnight. Skips lines it can't read rather than failing."""
        today = self.clock.now().date().isoformat()
        calls = inp = cached = out = 0
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            lines = []
        for line in lines:
            try:
                e = json.loads(line)
                if not str(e["ts"]).startswith(today):
                    continue
                i, c, o = int(e["input_tokens"]), int(e["cached_input_tokens"]), int(e["output_tokens"])
            except (ValueError, KeyError, TypeError):
                continue
            calls, inp, cached, out = calls + 1, inp + i, cached + c, out + o
        return UsageTotals(calls, Usage(inp, cached, out))
