from __future__ import annotations

import logging
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from milo.core.clock import SystemClock
from milo.core.conversations import (MAX_TITLE, RECAP_TOKENS, ConversationInfo, Recent, SplitRules, TaskInfo, clean_title,
                                     conversation_id, files_in, recap, recent_words, split, task_title, title_from)
from milo.core.events import Activity, EntryChanged, History, ReplyDelta
from milo.core.logtext import private
from milo.core.ports import Clock, ConversationStore, EventSink
from milo.core.times import parse_local
from milo.core.types import Emotion, EntryKind, Step, StepStatus, TranscriptEntry

log = logging.getLogger("milo.transcript")

RECENT = 50
MAX_STEPS = 80
MAX_FILES = 6
TITLE_TURNS = 3
"""Milo is asked to name a conversation during its first few user turns, until he has."""


class Transcript:
    """What was said and done, for the Milo window, in conversations that split on their own: user turns, Milo's
    replies as they stream, and tasks with their steps. See docs/design/conversations.md.

    A user turn may start a new conversation (core.conversations.split). Milo's own lines and tasks join the
    conversation going on, or start one when none is. Meeting notes and routine runs on their schedule get a
    conversation of their own. An entry goes to the store when it is finished; one still running when the brain
    stops is lost.

    The last RECENT entries of any conversation live in memory, so the window's history and a task's updates
    cost no file read. `outside()` says the live chat carries outside text right now; `asking()` that Milo
    waits for a yes or no; `exists(path)` whether a file a task named is there. `on_change` hears about every
    new or changed conversation header.
    """

    def __init__(self, sink: EventSink, store: ConversationStore, clock: Clock, *, recent: int = RECENT,
                 rules: SplitRules = SplitRules(), outside: Callable[[], bool] = lambda: False,
                 asking: Callable[[], bool] = lambda: False, exists: Callable[[str], bool] = lambda path: False,
                 on_finished: Callable[[dict], None] | None = None, recap_tokens: int = RECAP_TOKENS):
        self._sink = sink
        self._store = store
        self._clock = clock
        self._limit = recent
        self.rules = rules
        self._outside = outside
        self._asking = asking
        self._exists = exists
        self._on_finished = on_finished
        self._recap_tokens = recap_tokens
        self.on_change: list[Callable[[], None]] = []
        self._recent: deque[TranscriptEntry] | None = None
        self._live: dict[str, ConversationInfo] = {}
        """Headers changed this session and not (yet) the same in the store: new ones, running tasks."""
        self._current: str | None = None
        self._texts: deque[str] = deque(maxlen=6)
        """The current conversation's last texts, for the topic rule."""
        self._fresh = False
        """The user asked for a new conversation: the next turn starts one."""
        self._picked_up = False
        """The user picked an earlier conversation up again: the next turn goes on in it."""

    # ---- reading

    @property
    def current(self) -> str | None:
        """The id of the conversation going on, if any."""
        self._entries()
        return self._current

    def history(self) -> History:
        """The current conversation's recent entries, oldest first (an older app shows only this)."""
        current = self.current
        return History([e.to_dict() for e in self._sorted() if current is not None and e.conversation == current])

    def info(self, id: str) -> ConversationInfo | None:
        return self._live.get(id) or self._store.get(id)

    def live(self) -> dict[str, ConversationInfo]:
        """Headers newer than the store's: conversations that only exist in memory so far, running tasks."""
        return dict(self._live)

    def running(self, id: str) -> list[TranscriptEntry]:
        """Entries of conversation `id` still going: a reply streaming, a task at work. The store has the rest."""
        return [e for e in self._entries() if e.conversation == id and (not e.done or e.status is StepStatus.RUNNING)]

    def entry(self, id: str) -> TranscriptEntry | None:
        """A recent entry by id, e.g. a finished task with its steps."""
        return self._find(id)

    def wants_title(self) -> bool:
        """Milo should name the current conversation: it has only a title made from its first words."""
        info = self.info(self.current) if self.current else None
        return info is not None and info.kind == "chat" and info.titled_by == "words" and info.turns <= TITLE_TURNS

    # ---- what the user said

    def user(self, text: str, via: str) -> str:
        """A user turn, `via` "voice", "typed" or "message". Finished at once. May start a new conversation."""
        now = self._clock.now()
        if self._fresh:
            why = "asked"
        elif self._picked_up:
            why = None  # the user chose this conversation, however long ago it was
        else:
            why = split(self.rules, self._recent_state(), text, via, now)
        if why is not None:
            self._start("chat", title_from(text), why=why)
        self._fresh = self._picked_up = False
        return self._add(EntryKind.USER, text, finished=True, via=via).id

    def last_via(self, within_s: float) -> str:
        """How the user's last turn in the current conversation came ("voice", "typed", "message"), if it came in
        the last `within_s` seconds; else "". Tells a task the user just asked for by voice (ADR 0032)."""
        if self._current is None:
            return ""
        last = next((e for e in reversed(self._entries())
                     if e.conversation == self._current and e.kind is EntryKind.USER), None)
        if last is None or (self._clock.now() - _time(last.ts)).total_seconds() > within_s:
            return ""
        return last.via

    def new_conversation(self) -> None:
        """The user wants a fresh start (⌘N): the next turn starts a new conversation."""
        self._entries()
        self._fresh, self._picked_up = True, False
        self._current = None
        self._texts.clear()
        self._changed()

    def resume(self, id: str) -> tuple[str, bool] | None:
        """The user picked conversation `id` up again: it becomes the current one. Returns the recap for the
        chat model and whether it is trusted, or None if there is no such conversation (or it is the current)."""
        self._entries()
        info = self.info(id)
        if info is None:
            return None
        if id == self._current and not self._fresh:
            return None
        entries = self._store.entries(id)
        self._current, self._fresh, self._picked_up = id, False, True
        self._texts.clear()
        self._texts.extend(str(e.get("text", "")) for e in entries[-6:])
        known = {e.id for e in self._entries()}
        for data in entries[-self._limit:]:
            if data.get("id") not in known:
                try:
                    self._entries().append(TranscriptEntry.from_dict(data))
                except (KeyError, TypeError, ValueError):
                    pass
        self._changed()
        return recap(info, entries + [e.to_dict() for e in self.running(id)], budget_tokens=self._recap_tokens)

    # ---- what Milo said

    def reply_started(self, emotion: Emotion) -> str:
        return self._add(EntryKind.MILO, "", emotion=emotion, done=False).id

    def reply_delta(self, id: str, text: str) -> None:
        entry = self._find(id)
        if entry is None or not text:
            return
        entry.text += text
        self._sink.emit(ReplyDelta(id, text))

    def reply_finished(self, id: str, text: str, emotion: Emotion) -> None:
        entry = self._find(id)
        if entry is None:
            return
        entry.text, entry.emotion, entry.done = text.strip(), emotion, True
        self._finish(entry)

    def say(self, text: str, emotion: Emotion) -> None:
        """A whole Milo line at once, e.g. an error he shows. Joins the conversation going on."""
        if not self._open():
            self._start("chat", title_from(text), why="milo")
        self._add(EntryKind.MILO, text, finished=True, emotion=emotion)

    def written(self, text: str) -> None:
        """Text Milo wrote for the user (<write>, ADR 0033): an entry of its own, which the window can copy."""
        if not self._open():
            self._start("chat", title_from(text), why="milo")
        self._add(EntryKind.MILO, text, finished=True, written=True)

    def titled(self, title: str) -> None:
        """Milo named the current conversation (his <title> tag). A name the user gave stays."""
        title = clean_title(title)[:MAX_TITLE]
        info = self.info(self.current) if self.current else None
        if not title or info is None or info.titled_by != "words":
            return
        self.rename(info.id, title, by="milo")

    def rename(self, id: str, title: str, *, by: str = "you") -> ConversationInfo | None:
        info = self.info(id)
        title = clean_title(title)
        if info is None or not title:
            return None
        if self._store.get(id) is not None:
            saved = self._store.title(id, title, by)
            if saved is None:
                return None
            info = replace(info, title=saved.title, titled_by=saved.titled_by)
        elif info.titled_by != "you" or by == "you":
            info = replace(info, title=title, titled_by=by)
        self._keep(info)
        return info

    def meeting(self, id: str, title: str, text: str, *, conversation: str = "",
                emotion: Emotion = Emotion.HAPPY) -> str:
        """A Milo line about meeting `id` in the meeting's own conversation, named after it: `conversation` when the
        meeting already has one (made when it started), a new one otherwise. Other people's words, so it counts as
        outside text: its recap is untrusted. Returns the entry's id."""
        if not conversation or self.info(conversation) is None:
            conversation = self._new("meeting", clean_title(title) or "Meeting notes", source=f"meeting:{id}",
                                     outside=True)
        return self._add(EntryKind.MILO, text, finished=True, emotion=emotion, conversation=conversation).id

    # ---- tasks

    def task_started(self, description: str, *, title: str = "", own: str = "") -> str:
        """A task handed to a helper. `own` = "routine": a routine run on its schedule, in a conversation of its
        own named `title`. Otherwise it joins the conversation going on."""
        if own:
            conversation = self._new(own, clean_title(title) or task_title({"text": description}),
                                     source=f"{own}:{title}")
        else:
            if not self._open():
                self._start("chat", clean_title(title) or task_title({"text": description}), why="task")
            conversation = self._current
        entry = self._add(EntryKind.TASK, description, status=StepStatus.RUNNING, conversation=conversation,
                          title=" ".join(title.split()))
        info = self.info(conversation)
        if info is not None:
            self._keep(info.with_task(TaskInfo(entry.id, task_title(entry.to_dict()), "running", entry.ts)))
        return entry.id

    def task_step(self, id: str, step: Step) -> None:
        entry = self._find(id)
        if entry is None:
            return
        for i, old in enumerate(entry.steps):
            if old.id == step.id:
                entry.steps[i] = step
                break
        else:
            if len(entry.steps) >= MAX_STEPS:
                return
            entry.steps.append(step)
        self._sink.emit(Activity(id, step.to_dict()))

    def task_finished(self, id: str, ok: bool, result: str) -> None:
        entry = self._find(id)
        if entry is None:
            return
        entry.status = StepStatus.DONE if ok else StepStatus.FAILED
        entry.result = result
        # A step the agent never reported back on didn't finish either.
        entry.steps = [s if s.status is not StepStatus.RUNNING else
                       Step(s.id, s.kind, s.title, s.detail, StepStatus.DONE if ok else StepStatus.FAILED)
                       for s in entry.steps]
        try:
            named = files_in([result, *(s.detail for s in entry.steps)])
            entry.files = [p for p in named if self._exists(p)][:MAX_FILES]
        except Exception:
            log.exception("could not check the files a task named")
        self._finish(entry)

    # ---- inside

    def _recent_state(self) -> Recent | None:
        if self._current is None:
            return None
        info = self.info(self._current)
        if info is None:
            return None
        mine = [e for e in self._entries() if e.conversation == self._current]
        last = max([_time(info.last), *(_time(e.ts) for e in mine)])
        via = next((e.via for e in reversed(mine) if e.kind is EntryKind.USER), info.via[-1] if info.via else "")
        return Recent(last, info.turns, recent_words(self._texts), via, self._asking())

    def _open(self) -> bool:
        """A conversation is going on: there is a current one and its idle gap hasn't passed."""
        state = self._recent_state()
        return state is not None and (self._clock.now() - state.last).total_seconds() <= self.rules.idle_s

    def _start(self, kind: str, title: str, *, why: str) -> str:
        self._current = self._new(kind, title)
        self._texts.clear()
        log.info("a new conversation (%s)", why)
        return self._current

    def _new(self, kind: str, title: str, *, source: str = "", outside: bool = False) -> str:
        """A conversation with nothing in it yet. Its id comes from the entry that will be its first."""
        self._next_id = uuid.uuid4().hex[:12]
        ts = self._clock.now().isoformat(timespec="seconds")
        info = ConversationInfo(conversation_id(self._next_id), kind, ts, ts, title or "A conversation", "words",
                                outside=outside, source=source)
        self._keep(info)
        return info.id

    _next_id: str | None = None

    def _add(self, kind: EntryKind, text: str, *, finished: bool = False, conversation: str | None = None,
             **fields) -> TranscriptEntry:
        self._entries()
        if conversation is None:
            if self._current is None:
                self._start("chat", title_from(text) if kind is EntryKind.USER else task_title({"text": text}),
                            why="first")
            conversation = self._current
        id, self._next_id = self._next_id or uuid.uuid4().hex[:12], None
        entry = TranscriptEntry(id, self._clock.now().isoformat(timespec="seconds"), kind, text,
                                conversation=conversation, **fields)
        self._entries().append(entry)
        if conversation == self._current and text:
            self._texts.append(text)
        if finished:
            self._finish(entry)
        else:
            self._sink.emit(EntryChanged(entry.to_dict()))
        return entry

    def _finish(self, entry: TranscriptEntry) -> None:
        data = entry.to_dict()
        self._sink.emit(EntryChanged(data))
        if entry.kind is EntryKind.MILO and entry.conversation == self._current and entry.text:
            self._texts.append(entry.text)
        info = self.info(entry.conversation)
        if info is not None:
            # Milo's replies are what can quote outside text; the user's own words never do, and the first of a new
            # conversation would otherwise catch the taint the chat model still holds from the last one.
            if (entry.kind is EntryKind.MILO and self._outside()) or (entry.kind is EntryKind.TASK and entry.result):
                info = replace(info, outside=True)
            try:
                info = self._store.append(_settled(info), data)
            except Exception:
                log.exception("could not save the transcript entry")
            else:
                self._live.pop(info.id, None)
                running = [e for e in self.running(info.id) if e.kind is EntryKind.TASK]
                for e in running:  # a task still at work keeps its place in the header
                    info = info.with_task(TaskInfo(e.id, task_title(e.to_dict()), "running", e.ts))
                if running:
                    self._live[info.id] = info
            self._changed()
        if self._on_finished is not None:
            try:
                self._on_finished(data)
            except Exception:
                log.exception("could not hand on a finished entry")

    def _keep(self, info: ConversationInfo) -> None:
        """A changed header. Saved when the store knows the conversation; running tasks stay in memory only, so
        a restart never shows a task at work that died with the old brain."""
        if self._store.get(info.id) is not None:
            try:
                self._store.save(_settled(info))
            except Exception:
                log.exception("could not save the conversation")
        if self._store.get(info.id) is None or info != _settled(info):
            self._live[info.id] = info
        else:
            self._live.pop(info.id, None)
        self._changed()

    def _changed(self) -> None:
        for listener in self.on_change:
            try:
                listener()
            except Exception:
                log.exception("a conversation listener failed")

    def _find(self, id: str) -> TranscriptEntry | None:
        return next((e for e in reversed(self._entries()) if e.id == id), None)

    def _sorted(self) -> list[TranscriptEntry]:
        # The store is in the order entries finished; a long task finishes after later turns.
        return sorted(self._entries(), key=lambda e: e.ts)

    def _entries(self) -> deque[TranscriptEntry]:
        if self._recent is None:
            self._recent = deque(maxlen=self._limit)
            try:
                latest = next((c for c in self._store.all() if c.kind == "chat"), None)
                if latest is not None and (self._clock.now() - _time(latest.last)).total_seconds() <= self.rules.idle_s:
                    self._current = latest.id
                    loaded = self._store.entries(latest.id, self._limit)
                else:
                    loaded = []
            except Exception:
                log.exception("could not read the conversations")
                loaded = []
            for data in loaded:
                try:
                    self._recent.append(TranscriptEntry.from_dict(data))
                except (KeyError, TypeError, ValueError):
                    log.warning("skipping a malformed transcript entry: %s", private(data))
                    continue
                self._texts.append(str(data.get("text", "")))
        return self._recent


def _settled(info: ConversationInfo) -> ConversationInfo:
    """The header without tasks still at work, as the store keeps it."""
    return replace(info, tasks=tuple(t for t in info.tasks if t.status != "running"))


def _time(ts: str) -> datetime:
    return parse_local(ts) or datetime.fromtimestamp(0)


class _Nowhere:
    def emit(self, event) -> None:
        pass

    def append(self, entry: dict) -> None:
        pass

    def tail(self, n: int) -> list[dict]:
        return []


NO_TRANSCRIPT = _Nowhere()
"""A TranscriptStore that keeps nothing: the episode stubs only need to see the entries go by."""


class _NoConversations:
    def append(self, conversation, entry):
        return conversation.with_entry(entry)

    def save(self, conversation) -> None:
        pass

    def title(self, id, title, by):
        return None

    def all(self):
        return []

    def get(self, id):
        return None

    def entries(self, id, limit=None):
        return []

    def search_text(self, words, *, limit=20, budget_bytes=0):
        return []


def unrecorded() -> Transcript:
    """A transcript that shows and keeps nothing, for services built without the Milo window."""
    return Transcript(_Nowhere(), _NoConversations(), SystemClock())
