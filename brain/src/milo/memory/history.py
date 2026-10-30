"""Every dictation, so text that went into the wrong window is never lost."""

from __future__ import annotations

import json
from pathlib import Path

from milo.core.ports import Clock


class JsonlDictationHistory:
    """DictationHistory appending one JSON line per dictation. Keeps non-ASCII readable in the file."""

    def __init__(self, path: Path, clock: Clock):
        self.path = path
        self.clock = clock

    def append(self, text: str, app: str | None) -> None:
        entry = {"ts": self.clock.now().isoformat(timespec="seconds"), "app": app, "text": text}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
