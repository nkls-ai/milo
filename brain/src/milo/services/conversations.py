"""The Milo window's side of conversations: the list, opening one, search, renaming, and the reminders Today
shows. The conversation going on lives in services/transcript.py; this reads the store and lays the live
headers over it. See docs/design/conversations.md.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from milo.core.conversations import ConversationInfo, cut
from milo.core.events import ConversationOpened, Conversations, RemindersList, SearchResults
from milo.core.logtext import private
from milo.core.ports import Clock, ConversationStore, EventSink, ReminderBook

from .transcript import Transcript

log = logging.getLogger("milo.conversations")

PAGE = 150
COALESCE_S = 0.3
"""The list goes out at most this often while things change (a reply streaming, steps)."""
MAX_RESULTS = 30
SNIPPET = 120
TEXT_BUDGET = 8_000_000

SearchMemory = Callable[[str], Awaitable[list[dict]]]
"""Memory.search: episodes and facts for a query, each with kind, when, text and source."""


class ConversationBrowser:
    def __init__(self, transcript: Transcript, store: ConversationStore, sink: EventSink, clock: Clock, *,
                 memory: SearchMemory | None = None, reminders: ReminderBook | None = None, page: int = PAGE,
                 coalesce_s: float = COALESCE_S):
        self._transcript = transcript
        self._store = store
        self._sink = sink
        self._clock = clock
        self._memory = memory
        self._reminders = reminders
        self._page = page
        self._coalesce_s = coalesce_s
        self._pending: asyncio.TimerHandle | None = None
        transcript.on_change.append(self.changed)

    # ---- the list

    def headers(self) -> list[ConversationInfo]:
        """Every conversation, the latest first, with this session's live changes laid over the store's."""
        merged = {c.id: c for c in self._store.all()} | self._transcript.live()
        return sorted(merged.values(), key=lambda c: (c.last, c.started), reverse=True)

    def list_event(self, before: str = "") -> Conversations:
        headers = [c for c in self.headers() if not before or c.last < before]
        page = headers[:self._page]
        return Conversations([c.to_dict() for c in page], self._transcript.current or "", len(headers) > len(page))

    def changed(self) -> None:
        """Something in the list changed: send it soon, once for a burst of changes."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._sink.emit(self.list_event())
            return
        if self._pending is None:
            self._pending = loop.call_later(self._coalesce_s, self._send)

    def _send(self) -> None:
        self._pending = None
        try:
            self._sink.emit(self.list_event())
        except Exception:
            log.exception("could not send the conversation list")

    # ---- one conversation

    def open(self, id: str) -> ConversationOpened | None:
        info = self._transcript.info(id) or self._store.get(id)
        if info is None:
            return None
        entries = self._store.entries(id)
        known = {e.get("id") for e in entries}
        entries += [e.to_dict() for e in self._transcript.running(id) if e.id not in known]
        entries.sort(key=lambda e: str(e.get("ts", "")))
        return ConversationOpened(id, info.to_dict(), entries)

    def rename(self, id: str, title: str) -> None:
        if self._transcript.rename(id, title) is None:
            log.info("no conversation %s to rename", id)

    # ---- search

    async def search(self, query: str) -> SearchResults:
        """Titles first, then what memory's index finds by meaning, then the words in the files."""
        query = " ".join(query.split())
        if not query:
            return SearchResults(query, [])
        headers = self.headers()
        by_id = {c.id: c for c in headers}
        found: dict[str, dict] = {}

        def add(info: ConversationInfo, snippet: str, at: str = "") -> None:
            if info.id not in found and len(found) < MAX_RESULTS:
                found[info.id] = {"conversation": info.id, "title": info.title, "kind": info.kind,
                                  "at": at or info.last, "snippet": cut(snippet, SNIPPET), "via": list(info.via)}

        words = query.lower().split()
        for info in headers:
            text = f"{info.title} {' '.join(t.title for t in info.tasks)}".lower()
            if all(w in text for w in words):
                add(info, info.preview)
        if self._memory is not None:
            try:
                hits = await self._memory(query)
            except Exception:
                log.exception("memory search failed")
                hits = []
            for hit in hits:
                info = self._locate(hit, headers)
                if info is not None:
                    add(info, str(hit.get("text", "")), str(hit.get("when", "")))
        try:
            matches = await asyncio.to_thread(self._store.search_text, words, limit=MAX_RESULTS,
                                              budget_bytes=TEXT_BUDGET)
        except Exception:
            log.exception("searching the conversation files failed")
            matches = []
        for id, entry in matches:
            info = by_id.get(id)
            if info is not None:
                add(info, _snippet(entry, words), str(entry.get("ts", "")))
        log.info("search %s: %d conversations", private(query), len(found))
        return SearchResults(query, list(found.values()))

    @staticmethod
    def _locate(hit: dict, headers: list[ConversationInfo]) -> ConversationInfo | None:
        """The conversation a memory hit came from: a task by its entry id, a meeting by its id, a turn by its time."""
        source = str(hit.get("source", ""))
        if source.startswith("meeting:"):
            return next((c for c in headers if c.source == source), None)
        if source.startswith("transcript:"):
            entry = source.removeprefix("transcript:")
            task = next((c for c in headers if any(t.id == entry for t in c.tasks)), None)
            if task is not None:
                return task
            when = str(hit.get("when", ""))[:16]
            if when:
                return next((c for c in headers if c.kind == "chat" and c.started[:16] <= when <= c.last[:16]), None)
        return None

    # ---- Today

    def reminders_event(self) -> RemindersList:
        if self._reminders is None:
            return RemindersList([])
        now = self._clock.now()
        until = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            items = [r for r in self._reminders.all() if not r.done and r.due < until]
        except Exception:
            log.exception("could not read the reminders")
            items = []
        items.sort(key=lambda r: r.due)
        return RemindersList([{"due": r.due.isoformat(timespec="minutes"), "text": r.text} for r in items[:8]])


def _snippet(entry: dict, words: list[str]) -> str:
    """The part of an entry's text around the first word searched for."""
    text = " ".join(f"{entry.get('text', '')} {entry.get('result', '')}".split())
    lower = text.lower()
    at = min((i for i in (lower.find(w) for w in words) if i >= 0), default=0)
    start = max(0, at - 30)
    return ("…" if start else "") + text[start:]
