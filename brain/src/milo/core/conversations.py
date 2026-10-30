"""Conversations: where one ends and the next begins, what each is called, and the recap that lets Milo pick an
old one up again. All pure, so the rules have their own tests. See docs/design/conversations.md.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from .memory import estimate_tokens

KINDS = ("chat", "routine", "meeting")

MAX_TITLE = 48
MAX_PREVIEW = 90
RECAP_TOKENS = 600
"""What a recap may cost, under memory's 800 for a turn."""


@dataclass(frozen=True)
class TaskInfo:
    """A task in a conversation's header, for the list and Today: its entry id, short title and status."""

    id: str
    title: str
    status: str
    """running, done or failed."""
    at: str

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "status": self.status, "at": self.at}

    @staticmethod
    def from_dict(d: dict) -> TaskInfo:
        return TaskInfo(str(d["id"]), str(d.get("title", "")), str(d.get("status", "done")), str(d.get("at", "")))


@dataclass(frozen=True)
class ConversationInfo:
    """A conversation's header: what the list shows without opening it."""

    id: str
    kind: str
    """chat, routine (a run on its schedule) or meeting (its notes)."""
    started: str
    """Local ISO time of the first entry, like "2026-10-30T09:12:03"."""
    last: str
    title: str = ""
    titled_by: str = "words"
    """words (the heuristic), milo (his <title> tag) or you (a rename)."""
    via: tuple[str, ...] = ()
    """How the user's turns came, in order of first use: voice, typed, message."""
    turns: int = 0
    """User turns."""
    preview: str = ""
    """Milo's latest line, short."""
    tasks: tuple[TaskInfo, ...] = ()
    outside: bool = False
    """It carried outside text (task results, the screen): its recap is untrusted."""
    source: str = ""
    """meeting:<id> or routine:<name>, for conversations of their own."""

    @property
    def month(self) -> str:
        return self.started[:7]

    def to_dict(self) -> dict:
        d: dict = {"id": self.id, "kind": self.kind, "started": self.started, "last": self.last, "title": self.title,
                   "titled_by": self.titled_by, "via": list(self.via), "turns": self.turns, "preview": self.preview,
                   "tasks": [t.to_dict() for t in self.tasks]}
        if self.outside:
            d["outside"] = True
        if self.source:
            d["source"] = self.source
        return d

    @staticmethod
    def from_dict(d: dict) -> ConversationInfo:
        kind = str(d.get("kind") or "chat")
        return ConversationInfo(
            str(d["id"]), kind if kind in KINDS else "chat", str(d["started"]), str(d.get("last") or d["started"]),
            str(d.get("title", "")), str(d.get("titled_by") or "words"), tuple(str(v) for v in d.get("via") or ()),
            int(d.get("turns") or 0), str(d.get("preview", "")),
            tuple(TaskInfo.from_dict(t) for t in d.get("tasks") or () if isinstance(t, dict) and "id" in t),
            d.get("outside") is True, str(d.get("source") or ""))

    def with_entry(self, entry: dict) -> ConversationInfo:
        """The header after `entry` finished in this conversation."""
        kind = entry.get("kind")
        ts = str(entry.get("ts") or self.last)
        info = replace(self, last=max(self.last, ts))
        if kind == "user":
            via = str(entry.get("via") or "voice")
            info = replace(info, turns=info.turns + 1, via=info.via if via in info.via else (*info.via, via))
        elif kind == "milo":
            text = " ".join(str(entry.get("text", "")).split())
            if text:
                info = replace(info, preview=cut(text, MAX_PREVIEW))
        elif kind == "task":
            info = info.with_task(TaskInfo(str(entry["id"]), task_title(entry), str(entry.get("status", "done")), ts))
            result = " ".join(str(entry.get("result", "")).split())
            if result and entry.get("status") != "running":
                info = replace(info, preview=cut(result, MAX_PREVIEW))
        return info

    def with_task(self, task: TaskInfo) -> ConversationInfo:
        tasks = [t for t in self.tasks if t.id != task.id]
        if len(tasks) == len(self.tasks):
            return replace(self, tasks=(*self.tasks, task))
        return replace(self, tasks=tuple(task if t.id == task.id else t for t in self.tasks))


def conversation_id(first_entry_id: str) -> str:
    """A conversation is named after its first entry, so the same transcript always migrates to the same files."""
    return f"c-{first_entry_id}"


def cut(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1].rstrip(" ,.;:") + "…"


# ---- when to split


@dataclass(frozen=True)
class SplitRules:
    idle_s: float = 600.0
    """[chat] conversation_idle_reset_s: the chat model starts fresh after this much quiet, so does the window."""
    topic_gap_s: float = 120.0
    """A topic or channel split needs at least this pause."""
    topic_turns: int = 2
    """...and a conversation with at least this many user turns."""
    min_gap_s: float = 5.0
    """Nothing splits a conversation faster than this, not even "something else"."""


@dataclass(frozen=True)
class Recent:
    """What the split rules need to know about the conversation going on."""

    last: datetime
    """When its latest entry happened."""
    turns: int
    words: frozenset[str] = frozenset()
    """Content words of its last few turns and replies (content_words)."""
    via: str = ""
    """The channel of its latest user turn."""
    asking: bool = False
    """Milo waits for a yes or no in it."""


ANSWERS = frozenset({"yes", "no", "ja", "nein", "ok", "okay", "sure", "klar", "stop", "thanks", "danke"})

_ASKED = re.compile(
    r"\b(new topic|different topic|another topic|something else|different question|another question|change of "
    r"subject|unrelated|anderes thema|neues thema|was anderes|etwas anderes|andere frage|ganz was anderes)\b",
    re.IGNORECASE)
_FOLLOW_UP = re.compile(
    r"^\s*(and|also|but|or|so|then|what about|how about|it|its|it's|that|this|those|these|they|them|he|she|why|"
    r"same|again|more|another|instead|und|auch|aber|oder|also|dann|noch|was ist mit|wie wäre|es|das|die|der|"
    r"dies|warum|wieder|nochmal|mehr|stattdessen)\b", re.IGNORECASE)


def split(rules: SplitRules, current: Recent | None, text: str, via: str, at: datetime) -> str | None:
    """Why the user's turn `text` (said `via` voice, typed or message, at `at`) starts a new conversation:
    "first", "gap", "asked", "topic" or "channel". None: it goes on in `current`."""
    if current is None:
        return "first"
    pause = (at - current.last).total_seconds()
    if pause > rules.idle_s:
        return "gap"
    words = text.lower().strip(" .!?,")
    if current.asking or words in ANSWERS or pause < rules.min_gap_s:
        return None
    if current.turns and _ASKED.search(text):
        return "asked"
    if pause < rules.topic_gap_s or current.turns < rules.topic_turns:
        return None
    if current.via and via != current.via and "message" in (via, current.via):
        return "channel"
    if _FOLLOW_UP.match(text):
        return None
    mine = content_words(text)
    if len(mine) >= 2 and current.words and not (mine & current.words):
        return "topic"
    return None


_STOP = frozenset("""
a an the and or but if then so of to in on at by for with from about into over after before is are was were be been
am do does did have has had can could would should will shall may might must not no yes this that these those it its
i me my you your we our they them their he him his she her what which who whom when where why how there here please
just some any all very really much more most also than too well like want need get got make made let lets know think
tell show give take look find put set one two milo hey hi hello okay ok thanks thank sure today tomorrow
der die das den dem des ein eine einen einem einer und oder aber wenn dann so von zu im in am an auf bei für mit aus
über ist sind war waren sein bin hast hat habe haben kann kannst könnte würde soll will wird nicht kein keine ja
nein dies diese dieser es ich mich mir mein meine du dich dir dein deine wir uns unser ihr sie er ihm sein seine was
welche wer wann wo warum wie da hier bitte nur noch auch mal mehr sehr viel gut danke heute morgen hallo hey
""".split())
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def content_words(text: str) -> frozenset[str]:
    """The words that carry the topic, lowercased and roughly stemmed: "photos" and "photo" are one word."""
    return frozenset(_stem(w) for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in _STOP)


def _stem(word: str) -> str:
    for suffix in ("ings", "ing", "ies", "es", "en", "er", "s", "e", "n"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def recent_words(texts: Iterable[str], limit: int = 6) -> frozenset[str]:
    """Content words of the last `limit` texts of a conversation."""
    words: set[str] = set()
    for text in list(texts)[-limit:]:
        words |= content_words(text)
    return frozenset(words)


# ---- titles

_LEAD = re.compile(
    r"^\s*((hey|hi|hello|hallo|ok|okay|so|um|uh|äh|ähm|also|na)\b[\s,!.]*)*(milo\b[\s,!.:]*)?"
    r"((can|could|would|will) you( please)?|please|i (want|need|would like) you to|i('d| would) like to|"
    r"i (want|need) to|help me( to)?|let's|lets|(kannst|könntest|würdest) du( bitte| mal)*|bitte|"
    r"ich (möchte|will|brauche)|hilf mir)?\b[\s,]*", re.IGNORECASE)
_TRAILING = re.compile(r"[\s,;:.!]+$")


def title_from(text: str, *, words: int = 8, limit: int = 42) -> str:
    """A title from the user's first words: greetings and politeness off, a few words, capitalised.
    "can you rename the photos from Friday" -> "Rename the photos from Friday"."""
    first = re.split(r"(?<=[.!?])\s|\n", " ".join(text.split()), maxsplit=1)[0] if text.strip() else ""
    rest = _LEAD.sub("", first, count=1).strip()
    rest = rest if rest.strip(" .,!?:;") else first.strip()
    question = rest.endswith("?")
    all_words = rest.rstrip("?").split()
    picked = all_words[:words]
    while len(" ".join(picked)) > limit and len(picked) > 1:
        picked.pop()
    if len(picked) < len(all_words):
        while len(picked) > 2 and picked[-1].lower().strip(",") in _STOP:  # not "Is my train to Hamburg on"
            picked.pop()
        title = _TRAILING.sub("", " ".join(picked))
    else:
        title = _TRAILING.sub("", " ".join(picked)) + ("?" if question else "")
    title = cut(title, limit + 1)
    return clean_title(title[:1].upper() + title[1:]) or "A conversation"


def clean_title(title: str) -> str:
    """Display text only: one line, no tags, at most MAX_TITLE characters."""
    title = re.sub(r"<[^<>]*>", "", str(title)).replace("<", "").replace(">", "")
    title = " ".join(title.split()).strip(" \"'“”„.")
    return cut(title, MAX_TITLE)


def task_title(entry: dict) -> str:
    """A task's short title from its description: its first sentence, cut."""
    text = str(entry.get("title") or entry.get("text") or "")
    first = re.split(r"(?<=[.!?:])\s|\n", text.strip(), maxsplit=1)[0]
    return cut(first.rstrip(".") or "A task", 60)


# ---- picking one up again


def recap(info: ConversationInfo, entries: Sequence[dict], *, budget_tokens: int = RECAP_TOKENS) -> tuple[str, bool]:
    """The <earlier_conversation> block for a conversation the user picked up again, and whether it is trusted.

    Newest lines first until the budget is spent, then shown oldest first. Everything is made inert like a
    task result. Untrusted when the conversation carried outside text or a task's result is in it, and always
    for meeting notes and routine runs: what other people said, and what a run read.
    """
    lines: list[str] = []
    trusted = info.kind == "chat" and not info.outside
    for entry in entries:
        kind = entry.get("kind")
        text = _inert(" ".join(str(entry.get("text", "")).split()))
        if kind == "user" and text:
            lines.append(f"User: {cut(text, 400)}")
        elif kind == "milo" and text:
            lines.append(f"Milo: {cut(text, 400)}")
        elif kind == "task":
            status = {"running": "still running", "failed": "failed"}.get(str(entry.get("status")), "done")
            line = f"Task ({status}): {cut(text, 200)}"
            result = _inert(" ".join(str(entry.get("result", "")).split()))
            if result:
                line += f" Result: {cut(result, 300)}"
                trusted = False
            lines.append(line)
    when = _when(info.started)
    head = (f'<earlier_conversation title="{_inert(info.title).replace(chr(34), "")}" when="{when}">\n'
            "The user picked this earlier conversation up again. What was said, oldest first:\n")
    tail = "</earlier_conversation>"
    spent = estimate_tokens(head + tail) + 12
    kept: list[str] = []
    for line in reversed(lines):
        cost = estimate_tokens(line) + 1
        if spent + cost > budget_tokens:
            break
        kept.append(line)
        spent += cost
    kept.reverse()
    left_out = len(lines) - len(kept)
    body = ([f"({left_out} earlier line{'' if left_out == 1 else 's'} left out.)"] if left_out else []) + kept
    return head + "\n".join(body) + "\n" + tail, trusted


def _inert(text: str) -> str:
    return text.replace("<", "‹").replace(">", "›")


def _when(ts: str) -> str:
    try:
        at = datetime.fromisoformat(ts)
    except ValueError:
        return ts
    return f"{at:%A} {at.day} {at:%B}, {at:%H:%M}"


# ---- files a task touched

_PATH = re.compile(r"(?:~|/Users/[^/\s]+|/Volumes/[^/\s]+)(?:/[^\s/'\"`<>|;:,()\[\]{}]+(?: [^\s/~'\"`<>|;:,()\[\]{}]+)*)+"
                   r"\.[A-Za-z0-9]{1,8}\b")


def files_in(texts: Iterable[str], limit: int = 12) -> list[str]:
    """Paths of files named in a task's result and steps, first mention first: "~/Reports/October.numbers"."""
    seen: dict[str, None] = {}
    for text in texts:
        for match in _PATH.finditer(str(text)):
            seen.setdefault(match.group(0).rstrip(".,"), None)
            if len(seen) >= limit:
                return list(seen)
    return list(seen)


@dataclass
class Draft:
    """Scratch for building conversations from a list of entries (the migration)."""

    info: ConversationInfo
    entries: list[dict] = field(default_factory=list)
