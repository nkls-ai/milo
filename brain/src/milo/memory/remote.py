"""state/messages.json: whose phone is paired, whether remote is paused, when the last morning brief went."""

from __future__ import annotations

from milo import system

import json
import logging
import os
from pathlib import Path

log = logging.getLogger("milo.memory")


class JsonRemoteState:
    """The `RemoteState` the MessageService keeps. Readable by the user only (0600): the owner's chat id
    decides who may talk to Milo, so nobody else on the Mac should read or write it."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            log.exception("could not read %s, starting unpaired", self.path.name)
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.chmod(tmp, 0o600)
        system.replace_file(tmp, self.path)
