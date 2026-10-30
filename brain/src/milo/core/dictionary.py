"""The dictation dictionary: words to spell right, and fixes Milo learned from the user's corrections (ADR 21).
Pure: no I/O. The file is `~/Milo/dictionary.md` (milo.memory.dictionary):

    ## Words
    - Milo

    ## Fixes
    - Cloud Code -> Claude Code (seen 1)

Words are names Whisper should spell right. A fix is `heard -> meant`: what Whisper wrote and what the user
meant. Milo learns fixes when the user corrects a word he pasted; those carry `(seen N)`. A fix the user writes
without `(seen N)` is certain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_WORDS_PER_SIDE = 4
MAX_CHARS = 60

HEADING = re.compile(r"^\s*#{1,6}\s*(.+?)\s*$")
ITEM = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
_ARROW = re.compile(r"\s*(?:->|→)\s*")
_SEEN = re.compile(r"\s*\(\s*seen\s+(\d+)[^)]*\)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Fix:
    heard: str
    meant: str
    seen: int | None = None
    """How often Milo saw the user make this fix. None: the user wrote it, so it is certain."""

    @property
    def learned(self) -> bool:
        return self.seen is not None

    @property
    def applies(self) -> bool:
        """Sure enough to replace dictated text before the paste. Every fix's meant words go to the transcribers'
        vocabulary at once; replacing needs the user's own line, a second sighting, or a name."""
        return self.seen is None or self.seen >= 2 or looks_like_a_name(self.heard, self.meant)

    def line(self) -> str:
        return f"- {self.heard} -> {self.meant}" + (f" (seen {self.seen})" if self.seen is not None else "")


def looks_like_a_name(heard: str, meant: str) -> bool:
    """One fix is enough when the meant words have a capital and the heard words aren't one lowercase word. One
    lowercase word ("cloud") is likely an ordinary word that means something else in another sentence."""
    one_lowercase_word = len(heard.split()) == 1 and heard == heard.lower()
    return any(c.isupper() for c in meant) and not one_lowercase_word


def valid(heard: str, meant: str) -> bool:
    """A fix worth keeping: a few words on each side, on one line, and not the same."""
    return all(text.strip() and len(text) <= MAX_CHARS and len(text.split()) <= MAX_WORDS_PER_SIDE
               and "\n" not in text and "->" not in text and "→" not in text for text in (heard, meant)) \
        and " ".join(heard.split()) != " ".join(meant.split())


@dataclass(frozen=True)
class Entries:
    words: tuple[str, ...] = ()
    fixes: tuple[Fix, ...] = ()

    def vocabulary(self) -> list[str]:
        """What the transcribers should know: the Words section, then the fixes' meant words, most seen first."""
        fixes = sorted(self.fixes, key=lambda f: -(f.seen if f.seen is not None else 1_000))
        return list(dict.fromkeys([*self.words, *(f.meant for f in fixes)]))


def parse(markdown: str) -> Entries:
    """Items under a "Words" heading are words; `heard -> meant` items anywhere are fixes. Other lines are skipped."""
    words: list[str] = []
    fixes: list[Fix] = []
    section = ""
    for line in markdown.splitlines():
        if heading := HEADING.match(line):
            section = heading[1].lower()
            continue
        if (fix := parse_fix(line)) is not None:
            fixes.append(fix)
        elif section.startswith("word") and (item := ITEM.match(line)):
            word = " ".join(item[1].strip("`").split())
            if word and len(word) <= MAX_CHARS:
                words.append(word)
    return Entries(tuple(dict.fromkeys(words)), tuple(fixes))


def parse_fix(line: str) -> Fix | None:
    """`- heard -> meant (seen N)` as a Fix, None for any other line."""
    item = ITEM.match(line)
    if not item:
        return None
    text = item[1].strip("`")
    seen_match = _SEEN.search(text)
    if seen_match:
        text = text[:seen_match.start()]
    parts = _ARROW.split(text, maxsplit=1)
    if len(parts) != 2:
        return None
    heard, meant = (" ".join(p.strip("`").split()) for p in parts)
    if not valid(heard, meant):
        return None
    return Fix(heard, meant, max(1, int(seen_match[1])) if seen_match else None)


class Replacements:
    """The fixes that apply, as whole-word replacements, longest heard words first. Each matches in its own case
    or with its first letter capitalized, at a sentence start ("teh" also fixes "Teh" to "The")."""

    def __init__(self, fixes: tuple[Fix, ...]):
        rules: list[tuple[re.Pattern[str], str]] = []
        for fix in sorted((f for f in fixes if f.applies), key=lambda f: -len(f.heard)):
            words = [re.escape(w) for w in fix.heard.split()]
            first = words[0]
            if fix.heard[:1].islower():
                first = f"[{re.escape(fix.heard[0])}{re.escape(fix.heard[0].upper())}]{re.escape(fix.heard.split()[0][1:])}"
            pattern = r"\s+".join([first, *words[1:]])
            rules.append((re.compile(rf"(?<![\w-]){pattern}(?![\w-])"), fix.meant))
        self._rules = rules

    def __bool__(self) -> bool:
        return bool(self._rules)

    def apply(self, text: str) -> str:
        for pattern, meant in self._rules:
            text = pattern.sub(lambda m, meant=meant: _cased(m.group(0), meant), text)
        return text


def _cased(found: str, meant: str) -> str:
    """The meant words, with a capital first letter where the heard words had one and the meant ones don't."""
    if found[:1].isupper() and meant[:1].islower():
        return meant[0].upper() + meant[1:]
    return meant
