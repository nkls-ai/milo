"""A small JSON state file (state/sleep.json), written whole in one step."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import jsonl

log = logging.getLogger(__name__)


class JsonState:
    def __init__(self, path: Path):
        self.path = path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError):
            log.warning("could not read %s; starting it over", path.name)
            data = {}
        self.data: dict = data if isinstance(data, dict) else {}

    def save(self) -> None:
        jsonl.write_private(self.path, json.dumps(self.data, indent=1, sort_keys=True))
