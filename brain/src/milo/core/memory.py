"""What Milo remembers: episodes (what happened), facts (who the user is) and knowledge (the user's things).

Value types only, no I/O. docs/design/memory.md explains the layers; the ports live in milo.core.ports.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .times import local

EPISODE_KINDS = ("conversation", "task", "meeting", "dictation", "look", "note")
TOPICS = ("basics", "people", "work", "preferences", "routines", "learned")
"""Fact topics, in the order the profile and the "What Milo knows" screen list them."""
TOPIC_TITLES = {"basics": "Basics", "people": "People", "work": "Work and projects", "preferences": "Preferences",
                "routines": "Routines", "learned": "Learned"}
ITEM_KINDS = ("fact", "episode", "knowledge")

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id(at: datetime | None = None) -> str:
    """A ULID: 26 characters that sort by time (48 bits of milliseconds), then 80 random bits."""
    ms = int((at.timestamp() if at is not None else time.time()) * 1000)
    value = (ms << 80) | int.from_bytes(os.urandom(10), "big")
    return "".join(_CROCKFORD[(value >> (5 * i)) & 31] for i in reversed(range(26)))


def _time(value: Any) -> datetime:
    return local(value)


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(v) for v in value if str(v).strip())


@dataclass(frozen=True)
class Episode:
    """Something that happened. Written as a stub right away, summarized by the nightly consolidation."""

    id: str
    at: datetime
    kind: str
    """One of EPISODE_KINDS."""
    summary: str
    """One or two plain sentences."""
    people: tuple[str, ...] = ()
    apps: tuple[str, ...] = ()
    source: str = ""
    """Pointer to the raw record, e.g. "transcript:5f2a9c1e04b7"."""
    trusted: bool = True
    """False when the text came from outside (mail, web pages, files, the screen, helper output)."""

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"id": self.id, "at": self.at.isoformat(timespec="seconds"), "kind": self.kind,
                             "summary": self.summary}
        if self.people:
            d["people"] = list(self.people)
        if self.apps:
            d["apps"] = list(self.apps)
        if self.source:
            d["source"] = self.source
        if not self.trusted:
            d["trusted"] = False
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Episode:
        return cls(str(d["id"]), _time(d["at"]), str(d.get("kind") or "note"), str(d.get("summary") or ""),
                   _strings(d.get("people")), _strings(d.get("apps")), str(d.get("source") or ""),
                   d.get("trusted") is not False)


@dataclass(frozen=True)
class Fact:
    """A durable statement about the user and their world."""

    id: str
    text: str
    """"Anna is the user's sister." One line."""
    topic: str
    """One of TOPICS."""
    since: datetime
    source: str
    """Where it came from: an episode id, "chat", "profile.md", "you" (the What Milo knows screen), ..."""
    replaces: str | None = None
    """The fact this one updates. The old one stops being current."""
    retired: bool = False
    """The user deleted it, or it stopped being true."""
    pinned: bool = False
    """Always in Milo's mind: goes into the chat model's system prompt instead of being recalled per turn.
    Basics are pinned by default."""

    @property
    def always_on(self) -> bool:
        return self.pinned or self.topic == "basics"

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"id": self.id, "text": self.text, "topic": self.topic,
                             "since": self.since.isoformat(timespec="seconds"), "source": self.source}
        if self.replaces:
            d["replaces"] = self.replaces
        if self.pinned:
            d["pinned"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Fact:
        topic = str(d.get("topic") or "learned")
        return cls(str(d["id"]), " ".join(str(d["text"]).split()), topic if topic in TOPICS else "learned",
                   _time(d["since"]), str(d.get("source") or ""), d.get("replaces") or None,
                   bool(d.get("retired", False)), bool(d.get("pinned", False)))


@dataclass(frozen=True)
class Snippet:
    """A piece of the user's own things (a document, a note, an email), found by search. Always untrusted."""

    id: str
    title: str
    text: str
    source: str
    """Where it lives: a path, "notes:<id>", "mail:<id>"."""
    at: datetime | None = None


@dataclass(frozen=True)
class Document:
    """One thing a KnowledgeSource has: indexed as Snippets."""

    id: str
    title: str
    text: str
    source: str
    modified: datetime


@dataclass(frozen=True)
class IndexItem:
    """One searchable thing in the MemoryIndex: a fact, an episode or a knowledge snippet."""

    id: str
    kind: str
    """One of ITEM_KINDS."""
    text: str
    at: datetime
    people: tuple[str, ...] = ()
    apps: tuple[str, ...] = ()
    trusted: bool = True
    topic: str = ""
    source: str = ""

    @classmethod
    def of_fact(cls, f: Fact) -> IndexItem:
        return cls(f.id, "fact", f.text, f.since, topic=f.topic, source=f.source)

    @classmethod
    def of_episode(cls, e: Episode) -> IndexItem:
        return cls(e.id, "episode", e.summary, e.at, e.people, e.apps, e.trusted, e.kind, e.source)

    @classmethod
    def of_snippet(cls, s: Snippet) -> IndexItem:
        return cls(s.id, "knowledge", f"{s.title}\n{s.text}".strip(), s.at or datetime.fromtimestamp(0),
                   trusted=False, source=s.source)


@dataclass(frozen=True)
class Hit:
    item: IndexItem
    score: float
    """Reciprocal rank fusion of the text and vector ranks. Only comparable within one search."""
    text_rank: int | None = None
    vector_rank: int | None = None
    similarity: float = 0.0
    """Cosine similarity to the query, 0 if the vector search didn't find it."""
    background: float = 0.0
    """The query's similarity to unrelated text. `similarity - background` is how related the item is: cosine
    values alone run high for some questions and low for others."""

    @property
    def margin(self) -> float:
        return self.similarity - self.background if self.vector_rank is not None else 0.0


@dataclass(frozen=True)
class TurnContext:
    """What a Recaller knows about the turn besides its words."""

    now: datetime
    app: str | None = None
    exclude: frozenset[str] = frozenset()
    """Ids the model already has: pinned facts in its system prompt, things recalled earlier in this conversation."""
    include_untrusted: bool = True
    always_on: bool = True
    """Put the always-on facts first, matching or not. A plain search leaves them to match like anything else."""


@dataclass(frozen=True)
class Recall:
    facts: tuple[Fact, ...] = ()
    episodes: tuple[Episode, ...] = ()
    knowledge: tuple[Snippet, ...] = ()
    tokens: int = 0
    """Estimated size when rendered into a prompt."""

    @property
    def empty(self) -> bool:
        return not (self.facts or self.episodes or self.knowledge)

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(x.id for x in (*self.facts, *self.episodes, *self.knowledge))

    @property
    def trusted(self) -> bool:
        """False if anything in it came from outside: then the turn counts as carrying outside text."""
        return not self.knowledge and all(e.trusted for e in self.episodes)


@dataclass(frozen=True)
class FactChange:
    """One line the consolidation wrote, so a run can be read back and undone."""

    op: str
    """"add", "update" (an add that replaces another fact) or "retire"."""
    fact_id: str
    text: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ConsolidationReport:
    day: date
    run: str
    """Tags every line this run wrote ("sleep:<day>:<id>"), so it can be undone."""
    episodes: int = 0
    """Episode summaries written."""
    changes: tuple[FactChange, ...] = ()
    journal: str = ""
    """Path of the journal page, empty if none was written."""
    calls: int = 0
    skipped: str = ""
    """Why nothing ran: "nothing happened", "no budget", ..."""
    notes: tuple[str, ...] = field(default_factory=tuple)


def estimate_tokens(text: str) -> int:
    """About 4 bytes of UTF-8 per token for English and German. Cheap and on the safe side."""
    return (len(text.encode("utf-8")) + 3) // 4
