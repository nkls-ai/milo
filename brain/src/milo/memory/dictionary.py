"""dictionary.md: the words dictation should get right and the fixes Milo learned (ADR 21; format in
milo.core.dictionary). The user edits it too, so writes keep every line they don't own."""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import replace
from pathlib import Path

from milo.core.dictionary import HEADING, ITEM, Entries, Fix, parse, parse_fix, valid

log = logging.getLogger("milo.dictionary")

MAX_FIXES = 300
"""More learned fixes than this is a sign something is learning junk; nothing new is added past it."""


class MarkdownDictionary:
    """`Dictionary` over dictionary.md. Re-reads only when its mtime or size changes, so asking costs one stat()."""

    def __init__(self, path: Path):
        self.path = path
        self._stamp: tuple[int, int] | None = None
        self._entries = Entries()

    def changed(self) -> bool:
        """The file changed since it was last read (by the user, or by Milo)."""
        return self._stat() != self._stamp

    def entries(self) -> Entries:
        stamp = self._stat()
        if stamp != self._stamp:
            self._entries = parse(self._read()) if stamp is not None else Entries()
            self._stamp = stamp
        return self._entries

    def learn(self, heard: str, meant: str) -> str:
        """Record that the user fixed `heard` to `meant` once. Returns what happened:

        - "new": a fix not seen before, at count 1.
        - "again": seen before, one more.
        - "replaced": the heard words had another learned meaning, which this one replaces at count 1.
        - "undone": the user put back what a learned fix had replaced; that fix is gone, nothing is learned.
        - "kept": it contradicts a fix the user wrote themselves, which stays as it is.
        - "full": MAX_FIXES learned fixes already. "invalid": not a fix (see core.dictionary.valid).
        """
        heard, meant = " ".join(heard.split()), " ".join(meant.split())
        if not valid(heard, meant):
            return "invalid"
        fixes = self.entries().fixes
        reverse = next((f for f in fixes if f.heard == meant and f.meant == heard), None)
        if reverse is not None:
            if not reverse.learned:
                return "kept"
            self._rewrite(reverse, None)
            return "undone"
        same = next((f for f in fixes if f.heard == heard), None)
        if same is not None:
            if not same.learned:
                return "again" if same.meant == meant else "kept"
            if same.meant == meant:
                self._rewrite(same, replace(same, seen=(same.seen or 0) + 1))
                return "again"
            self._rewrite(same, Fix(heard, meant, 1))
            return "replaced"
        if sum(f.learned for f in fixes) >= MAX_FIXES:
            return "full"
        self._append(Fix(heard, meant, 1))
        return "new"

    def _rewrite(self, old: Fix, new: Fix | None) -> None:
        """Change or remove the first line that holds `old`; every other line stays as it is."""
        lines = self._read().splitlines()
        for i, line in enumerate(lines):
            if parse_fix(line) == old:
                if new is None:
                    del lines[i]
                else:
                    lines[i] = new.line()
                break
        self._write("\n".join(lines) + "\n")

    def _append(self, fix: Fix) -> None:
        """At the end of the Fixes section, which is made at the end of the file if there is none."""
        lines = (self._read() or "# Dictionary\n").rstrip("\n").splitlines()
        start = next((i for i, line in enumerate(lines)
                      if (h := HEADING.match(line)) and h[1].lower().startswith("fix")), None)
        if start is None:
            lines += ["", "## Fixes"]
            start = len(lines) - 1
        end = next((i for i in range(start + 1, len(lines)) if HEADING.match(lines[i])), len(lines))
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        # A list needs a blank line after the section's explanation; after another item or the heading it doesn't.
        after_text = end > start + 1 and not ITEM.match(lines[end - 1])
        lines[end:end] = ["", fix.line()] if after_text else [fix.line()]
        self._write("\n".join(lines) + "\n")

    def _read(self) -> str:
        try:
            return self.path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    def _write(self, text: str) -> None:
        """Through a temporary file that replaces dictionary.md, so an editor or a crash never sees half a file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".dictionary-", suffix=".md")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        self._stamp = None  # re-read next time even if the mtime did not visibly change

    def _stat(self) -> tuple[int, int] | None:
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return None
        return st.st_mtime_ns, st.st_size
