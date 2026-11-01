"""~/Milo/config.toml as a file Milo can change, one key at a time, with the user's comments and layout kept.

The Settings window and the menu bar's "Dictation style" both change it through here."""

from __future__ import annotations

from milo import system

import os
from pathlib import Path

import tomlkit
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Item

from .config import Config
from .core.platform import ANYWHERE, Platform
from .core.registry import ConfigError


class TomlConfigFile:
    """Changes one key at a time. A change that would make the whole file invalid is never written."""

    def __init__(self, path: Path, platform: Platform = ANYWHERE):
        self.path = path
        self.platform = platform

    def read(self) -> Config:
        return Config.load(self.path, self.platform)

    def write(self, section: str, key: str, value: str | bool | int | float | list) -> Config:
        """Set `[section] key = value` and return the config as it is now. Raises ConfigError, writing nothing."""
        return self.write_many([(section, key, value)])

    def write_many(self, changes: list[tuple[str, str, str | bool | int | float | list]]) -> Config:
        """Commit related settings together, preserving comments and validating before any write.

        A dotted section identifies nested TOML tables, such as chat.openai_compat.
        This keeps provider setup from leaving half-applied settings if validation fails.
        """
        text = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        try:
            doc = tomlkit.parse(text)
        except TOMLKitError as e:
            raise ConfigError(f"{self.path} is not valid TOML: {e}") from None
        for section, key, value in changes:
            table = doc
            for part in section.split("."):
                if not part:
                    raise ConfigError("A settings section must have a name")
                child = table.get(part)
                if child is None:
                    child = tomlkit.table()
                    table[part] = child
                elif not isinstance(child, dict):
                    raise ConfigError(f"[{section}] must be a table")
                table = child
            _set(table, key, value)
        new = tomlkit.dumps(doc)
        config = Config.parse(new, str(self.path), self.platform)
        temporary = self.path.with_name(f".{self.path.name}.saving")
        temporary.write_text(new, encoding="utf-8")
        system.replace_file(temporary, self.path)
        return config


def _set(table, key: str, value) -> None:
    """tomlkit keeps a comment at the end of the line; this keeps it in the same column too."""
    old = table.get(key)
    if isinstance(value, list) and all(isinstance(v, dict) for v in value):
        value = _inline(value)
    table[key] = value
    if isinstance(old, Item) and old.trivia.comment:
        new = table.item(key)
        width = len(old.trivia.comment_ws) + len(old.as_string()) - len(new.as_string())
        new.trivia.comment_ws = " " * max(1, width)


def _inline(tables: list[dict]):
    """A list of tables as one array of inline tables, one per line: `[{name = "Numbers", bundle = ""}]`."""
    array = tomlkit.array()
    for entry in tables:
        item = tomlkit.inline_table()
        item.update(entry)
        array.append(item)
    return array.multiline(len(tables) > 1)
