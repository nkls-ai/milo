"""profile.md as a view over the FactStore, and the one-time move of an old profile.md into facts.

Milo writes memory/profile.md from the current facts after every change, so it stays plain Markdown the user
can read. The user may still edit it: a new line becomes a fact, a deleted line is forgotten. Milo tells the
two apart by comparing the file with the copy he last wrote (state/profile.written.md).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from milo.core.memory import TOPIC_TITLES, TOPICS, Fact, new_id
from milo.core.ports import Clock

from . import jsonl
from .facts import JsonlFactStore

log = logging.getLogger(__name__)

MAX_FACT = 300
NOTE = ("<!-- Milo writes this file from what he remembers (memory/facts.jsonl). You can edit it: a new line "
        "becomes something he knows, a deleted line is forgotten. -->")
BACKUP = "profile.before-facts.md"

_HEADINGS = {title.lower(): topic for topic, title in TOPIC_TITLES.items()} | {
    "work": "work", "projects": "work", "family": "people", "friends": "people", "habits": "routines",
    "likes": "preferences", "about": "basics", "basic": "basics"}

# Plain words that say what a fact is about. The nightly consolidation files facts properly; this is the
# first guess for a <remember> from the chat model.
_TOPIC_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("people", ("sister", "brother", "mother", "father", "mom", "mum", "dad", "wife", "husband", "partner",
                "girlfriend", "boyfriend", "friend", "colleague", "boss", "son", "daughter", "grandma", "grandpa",
                "aunt", "uncle", "cousin", "neighbour", "neighbor", "birthday", "schwester", "bruder", "mutter",
                "vater", "mama", "papa", "frau", "mann", "freund", "freundin", "kollege", "kollegin", "chef",
                "chefin", "sohn", "tochter", "oma", "opa", "tante", "onkel", "geburtstag", "nachbar")),
    ("basics", ("name is", "called", "lives in", "born", "years old", "speaks", "language", "heißt", "wohnt",
                "geboren", "jahre alt", "spricht", "sprache")),
    ("routines", ("every ", "each ", "usually", "always", "mornings", "evenings", "weekends", "mondays",
                  "tuesdays", "wednesdays", "thursdays", "fridays", "saturdays", "sundays", "jeden", "immer",
                  "morgens", "abends", "montags", "dienstags", "mittwochs", "donnerstags", "freitags",
                  "samstags", "sonntags", "wochenende")),
    ("work", ("work", "job", "project", "company", "office", "client", "team", "meeting", "arbeit", "projekt",
              "firma", "büro", "kunde", "beruf")),
    ("preferences", ("like", "love", "prefer", "hate", "dislike", "favorite", "favourite", "enjoy", "rather",
                     "mag ", "liebt", "lieber", "hasst", "lieblings", "gern")),
)


def guess_topic(text: str) -> str:
    """Words of four letters or more match as the start of a word ("works", "Kollegen"), short ones whole."""
    lower = f" {text.lower()} "
    for topic, words in _TOPIC_WORDS:
        for w in words:
            end = r"\s" if w.endswith(" ") else (r"" if len(w) >= 4 else r"\b")
            if re.search(r"\b" + re.escape(w.strip()) + end, lower):
                return topic
    return "learned"


def clean(text: str) -> str:
    text = " ".join(text.split())
    if text.startswith(("- ", "* ")):
        text = text[2:].strip()
    return text[:MAX_FACT].rstrip()


class FactProfile:
    """ProfileMemory backed by the FactStore.

    `read()` renders current facts as Markdown; with `pinned_only`, just the always-on ones, which is what the
    chat model's system prompt gets (everything else is recalled per turn). `remember()` adds a fact.
    `on_change` hears about every change, e.g. to tell the app.
    """

    def __init__(self, facts: JsonlFactStore, path: Path, snapshot: Path, clock: Clock, *, pinned_only: bool = False,
                 on_change: Callable[[], None] | None = None):
        self.facts = facts
        self.path = path
        self.snapshot = snapshot
        self._clock = clock
        self.pinned_only = pinned_only
        self.on_change = on_change
        self._written: tuple[int, int] | None = None  # (mtime_ns, size) of the file as Milo last wrote it

    def read(self) -> str:
        self.sync()
        facts = [f for f in self.facts.current() if f.always_on or not self.pinned_only]
        return render(facts, heading=not self.pinned_only)

    def remember(self, fact: str, *, topic: str = "", source: str = "chat", by: str = "chat",
                 always_on: bool = True) -> Fact | None:
        """Add a fact. Returns None for an empty line or one Milo already knows. `always_on=False` keeps it out of
        the basics, which go into every system prompt."""
        text = clean(fact)
        if not text:
            return None
        self.sync()
        if any(f.text.lower() == text.lower() for f in self.facts.current()):
            return None
        topic = topic if topic in TOPICS else guess_topic(text)
        if topic == "basics" and not always_on:
            topic = "learned"
        new = Fact(new_id(self._clock.now()), text, topic, self._clock.now(), source)
        self.facts.add(new, by=by)
        self.changed()
        return new

    def changed(self) -> None:
        """Facts changed: write profile.md again and tell whoever listens."""
        self.write()
        if self.on_change is not None:
            self.on_change()

    def write(self) -> None:
        text = render(self.facts.current(), heading=True, note=True)
        _write_atomic(self.path, text)
        _write_atomic(self.snapshot, text)
        st = self.path.stat()
        self._written = (st.st_mtime_ns, st.st_size)

    def sync(self) -> int:
        """Take in the user's own edits to profile.md. Returns how many facts changed."""
        try:
            st = self.path.stat()
        except FileNotFoundError:
            self.write()
            return 0
        if self._written == (st.st_mtime_ns, st.st_size):
            return 0
        try:
            before = self.snapshot.read_text(encoding="utf-8")
        except FileNotFoundError:
            self.write()  # nothing to compare with: start comparing from now
            return 0
        now = self.path.read_text(encoding="utf-8", errors="replace")
        old, new = set(parse(before)), set(parse(now))
        added, removed = new - old, old - new
        current = {(f.topic, f.text.lower()): f for f in self.facts.current()}
        for topic, text in sorted(removed):
            fact = current.get((topic, text.lower()))
            if fact is not None:
                self.facts.retire(fact.id, "deleted from profile.md", by="you")
        known = {f.text.lower() for f in self.facts.current()}
        for topic, text in sorted(added):
            if text.lower() not in known:
                self.facts.add(Fact(new_id(self._clock.now()), text, topic, self._clock.now(), "profile.md"), by="you")
        if added or removed:
            log.info("profile.md was edited: %d line(s) added, %d removed", len(added), len(removed))
        self.changed() if (added or removed) else self.write()
        return len(added) + len(removed)


def render(facts: list[Fact], *, heading: bool = True, note: bool = False) -> str:
    """Facts as Markdown, one section per topic. Empty sections stay, so the user sees where things go."""
    lines = ["# About the user", ""] if heading else []
    if note:
        lines += [NOTE, ""]
    for topic in TOPICS:
        bullets = [f"- {f.text}" for f in facts if f.topic == topic]
        if not bullets and not heading:
            continue
        lines += [f"## {TOPIC_TITLES[topic]}", "", *bullets, ""]
    return "\n".join(lines).rstrip() + "\n" if lines else ""


def parse(markdown: str) -> list[tuple[str, str]]:
    """(topic, text) for every line that says something: bullets, and plain lines under a section."""
    topic = "learned"
    out: list[tuple[str, str]] = []
    in_comment = False
    for raw in markdown.splitlines():
        line = raw.strip()
        if in_comment or line.startswith("<!--"):
            in_comment = "-->" not in line
            continue
        if not line:
            continue
        if line.startswith("#"):
            title = line.lstrip("#").strip().lower()
            if line.startswith("# ") and not line.startswith("## "):
                continue  # the page title
            topic = _HEADINGS.get(title, "learned")
            continue
        text = clean(line)
        if text:
            out.append((topic, text))
    return out


def migrate(profile: Path, facts: JsonlFactStore, clock: Clock) -> int:
    """Move an old profile.md into facts.jsonl, once. Keeps a copy of the old file. Returns facts added."""
    if facts.path.exists():
        return 0
    added = 0
    if profile.exists():
        backup = profile.with_name(BACKUP)
        if not backup.exists():
            shutil.copy2(profile, backup)
            os.chmod(backup, 0o600)
        when = datetime.fromtimestamp(profile.stat().st_mtime)
        seen: set[str] = set()
        for topic, text in parse(profile.read_text(encoding="utf-8", errors="replace")):
            if text.lower() in seen:
                continue
            seen.add(text.lower())
            facts.add(Fact(new_id(when), text, topic, when, "profile.md"), by="migration")
            added += 1
        log.info("moved %d line(s) of profile.md into memory/facts.jsonl (old file kept as %s)", added, BACKUP)
    facts.path.parent.mkdir(parents=True, exist_ok=True)
    facts.path.touch()
    return added


def _write_atomic(path: Path, text: str) -> None:
    jsonl.write_private(path, text)
