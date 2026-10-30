"""What Milo knows about the user: <home>/memory/profile.md, plain Markdown the user can read and edit.

The live model's system prompt includes the whole file. Facts Milo learns in conversation are
appended as bullets under `## Learned`; everything else in the file is left alone.
"""

from __future__ import annotations

import os
from pathlib import Path

LEARNED = "## Learned"
MAX_FACT = 300


class MarkdownProfile:
    """ProfileMemory over profile.md."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> str:
        try:
            return self.path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    def remember(self, fact: str) -> None:
        fact = " ".join(fact.split())
        if fact.startswith(("- ", "* ")):
            fact = fact[2:].strip()
        fact = fact[:MAX_FACT].rstrip()
        if not fact:
            return
        lines = self.read().splitlines()
        if any(line.strip()[:2] in ("- ", "* ") and line.strip()[2:].strip() == fact for line in lines):
            return
        lines = _insert_learned(lines, f"- {fact}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)


def _insert_learned(lines: list[str], bullet: str) -> list[str]:
    """Add `bullet` at the end of the Learned section, creating the section at the end if missing."""
    start = next((i for i, line in enumerate(lines) if line.strip().lower() == LEARNED.lower()), None)
    if start is None:
        while lines and not lines[-1].strip():
            lines.pop()
        return [*lines, *([""] if lines else []), LEARNED, bullet]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("#")), len(lines))
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return [*lines[:end], bullet, *lines[end:]]
