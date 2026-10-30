"""~/Milo/config.toml as a file Milo can change, one key at a time, with the user's comments and layout kept.

The Settings window and the menu bar's "Dictation style" both change it through here."""

from __future__ import annotations

import os
from pathlib import Path

import tomlkit
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Item

from .config import Config
from .core.registry import ConfigError


class TomlConfigFile:
    """Changes one key at a time. A change that would make the whole file invalid is never written."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> Config:
        return Config.load(self.path)

    def write(self, section: str, key: str, value: str | bool | int | float) -> Config:
        """Set `[section] key = value` and return the config as it is now. Raises ConfigError, writing nothing."""
        text = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        try:
            doc = tomlkit.parse(text)
        except TOMLKitError as e:
            raise ConfigError(f"{self.path} is not valid TOML: {e}") from None
        table = doc.get(section)
        if table is None:
            table = tomlkit.table()
            doc[section] = table
        elif not isinstance(table, dict):
            raise ConfigError(f"[{section}] must be a table")
        _set(table, key, value)
        new = tomlkit.dumps(doc)
        config = Config.parse(new, str(self.path))
        temporary = self.path.with_name(f".{self.path.name}.saving")
        temporary.write_text(new, encoding="utf-8")
        os.replace(temporary, self.path)
        return config


def _set(table, key: str, value) -> None:
    """tomlkit keeps a comment at the end of the line; this keeps it in the same column too."""
    old = table.get(key)
    table[key] = value
    if isinstance(old, Item) and old.trivia.comment:
        new = table.item(key)
        width = len(old.trivia.comment_ws) + len(old.as_string()) - len(new.as_string())
        new.trivia.comment_ws = " " * max(1, width)
