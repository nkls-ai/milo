# Memory: design

Status: proposed, 2026-10-30. Nothing here is built yet. The next round builds it against these interfaces.

## Why

A coworker who forgets everything after ten minutes isn't a coworker. Today Milo keeps one open conversation in the chat model and starts fresh after `conversation_idle_reset_s` (600 s) of silence. A fresh start loads the persona, the whole `memory/profile.md` and the open reminders into the system prompt. Nothing else comes back: `state/transcript.jsonl` records every turn, but no code reads it into a conversation, and the journal is never read in chat. The worker reads memory files only when it decides to.

This breaks in two ways as Milo gets used:

1. He forgets episodes. "What did I ask you about the dentist last week?" has no answer.
2. The profile grows without limit and goes into every system prompt, so turns get slower and more expensive the more he knows.

## Goals

- Milo remembers what happened (episodes), who the user is (facts) and the user's own things (knowledge), for years.
- Each turn carries only the memory that's relevant to it, within a fixed token budget. Retrieval is local and takes under 50 ms, with no LLM call.
- The user can read, fix and delete everything Milo knows, in plain words.
- Nothing is lost when the app, the brain or the Mac crashes.
- Memory can sync between devices later, end-to-end encrypted, without changing the format.

## Four layers

| Layer | What it holds | Source of truth | Example |
|---|---|---|---|
| Working | The current conversation, live helper state, the last look at the screen | The chat model's session plus brain state | "the Excel task is on step 3" |
| Episodes | Things that happened, each with time, people, app, a summary and a link to the raw record | `memory/episodes/YYYY-MM.jsonl`, append-only | "Oct 30, asked for a budget table in Excel, it failed on permissions" |
| Facts | Durable statements about the user and their world | `memory/facts.jsonl`, append-only log of changes; `memory/profile.md` rendered from it | "Anna is the user's sister, birthday March 3" |
| Knowledge | The user's documents, notes, mail, meeting notes | The original files and apps; Milo only keeps an index | "the electricity bill PDF from September" |

Two rules hold for every layer:

- **Files are the truth, the index is a cache.** Episodes and facts live in append-only JSON lines and Markdown. The search index (`state/memory.sqlite`) can be deleted and rebuilt from them at any time. This makes crashes harmless (a half-written line is skipped on read), keeps everything readable by hand, and makes sync simple: devices exchange log lines, never a database.
- **Untrusted text stays marked.** Text that came from outside (mail, web pages, documents, screen captures, helper output) carries `trusted: false` through every layer and is quoted as data in prompts, never as instructions (ADR 0010).

## Data model

```python
@dataclass(frozen=True)
class Episode:
    id: str                    # sortable, e.g. a ULID
    at: datetime
    kind: str                  # "conversation" | "task" | "meeting" | "dictation" | "look" | "note"
    summary: str               # one or two plain sentences
    people: tuple[str, ...] = ()
    apps: tuple[str, ...] = ()
    source: str = ""           # pointer to the raw record, e.g. "transcript:5f2a9c1e04b7" or "meeting:2026-10-30-1400"
    trusted: bool = True

@dataclass(frozen=True)
class Fact:
    id: str
    text: str                  # "Anna is the user's sister."
    topic: str                 # "people" | "work" | "preferences" | "routines" | "basics" | "learned"
    since: datetime
    source: str                # the episode it came from
    replaces: str | None = None    # the fact this one updates
    retired: bool = False          # the user deleted it, or it stopped being true

@dataclass(frozen=True)
class Recall:
    facts: tuple[Fact, ...]
    episodes: tuple[Episode, ...]
    knowledge: tuple[Snippet, ...]
    tokens: int                # estimated size when rendered into a prompt
```

## Ports

All in `milo.core.ports`, next to the existing ones. Adapters register like every other adapter, and only `compose.py` picks the concrete ones.

```python
class EpisodeLog(Protocol):
    def append(self, episode: Episode) -> None: ...
    def between(self, start: datetime, end: datetime) -> list[Episode]: ...

class FactStore(Protocol):
    def current(self) -> list[Fact]:
        """Facts that are neither retired nor replaced."""
    def add(self, fact: Fact) -> None: ...
    def retire(self, id: str, reason: str) -> None: ...

class Embedder(Protocol):
    """Turns text into vectors for search. Local, runs on its own single-thread executor like STT and TTS."""
    dimensions: int
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

class MemoryIndex(Protocol):
    """Search over facts, episodes and knowledge. A cache: rebuild() recreates it from the logs."""
    def upsert(self, items: Sequence[IndexItem]) -> None: ...
    def search(self, query: str, *, kinds: Collection[str] = (), since: datetime | None = None,
               limit: int = 20) -> list[Hit]: ...
    def rebuild(self) -> None: ...

class Recaller(Protocol):
    """Picks what memory a turn needs, within a token budget. No LLM call."""
    def recall(self, turn: str, context: TurnContext, budget_tokens: int) -> Recall: ...

class Consolidator(Protocol):
    """The nightly "sleep": turns the day's raw records into episodes and facts."""
    async def consolidate(self, day: date) -> ConsolidationReport: ...

class KnowledgeSource(Protocol):
    """One place the user's things live: a folder, Notes, Mail, meeting notes."""
    name: str
    def changed_since(self, since: datetime) -> Iterable[Document]: ...
```

`ProfileMemory` stays as it is for now. It becomes a view over `FactStore`: `read()` renders current facts as today's Markdown, and `remember()` adds a fact.

## How a turn uses memory

1. The turn text arrives (typed, or the committed transcript from listening).
2. `Recaller.recall()` runs hybrid search: full-text (SQLite FTS5) and vector search (embeddings) together, merged with reciprocal rank fusion, then filtered by recency and the current app and people. Always-on facts (the user's name, language, a handful of pinned preferences) come first.
3. The result is rendered into a small "What you remember right now" block, at most `[memory] recall_tokens` (default 800).
4. The block goes in with the turn as a user-side context message, not into the system prompt. The system prompt stays the same between turns, so prompt caching keeps working and the first token stays fast.

The worker gets the same `Recall` for its task, plus read access to the memory tools (`memory_search`, `memory_remember`) through the existing `milo` MCP server, so it can look further when the task needs it.

## Writing memory

- **During the day, cheap.** Every conversation turn, task, dictation and meeting appends an episode stub right away (`kind`, time, app, people, a pointer to the raw record). The live model's existing `remember` tag adds a fact at once, after the approvals check that ADR 0010 requires once untrusted results are in the conversation.
- **At night, thorough.** The `Consolidator` runs once a day when the Mac is idle and on power, under the heartbeat's budget rules. It reads the day's raw records and asks the worker model to: write a summary for each episode, extract new facts, replace facts that changed, retire ones that stopped being true, write the journal page, and note patterns ("calls his mother on Sundays"). It writes only through `EpisodeLog` and `FactStore`, so every change is a logged, reversible line. It's a few calls a day at most, which keeps the zero-token heartbeat promise for everything else.

## The user's view

A "What Milo knows" screen in the Milo window lists current facts by topic, in plain sentences. Each has Edit and Forget. "Forget" retires the fact and removes it from the index. "Forget everything about X" retires the matching facts and episodes. By voice: "Milo, forget that", "what do you know about Anna?".

## Local stack

- SQLite with FTS5 for text search, and `sqlite-vec` for vectors (one file, no server). Fallback if `sqlite-vec` is a problem: vectors in a NumPy array next to the database, which is fast enough for 100k items.
- A small multilingual embedding model (German and English), run with MLX. Candidates to measure: multilingual-e5-small, bge-m3 (bigger), and whatever fits under ~200 MB of memory and 10 ms per short text on the M3. RAM is tight with Whisper and OmniVoice loaded, so size wins over the last bit of quality.
- New items get indexed in the background; a full rebuild runs on demand or after an embedder change.

## Sync later

Each device appends to its own logs (`episodes/<device>/…`, `facts/<device>.jsonl`). Sync copies log lines between devices, encrypted on the device with a key the server never sees. Each device rebuilds its own index from all logs. Conflicts between facts resolve by time, and the consolidator merges duplicates. The first step can be iCloud Drive with the same files, before a Milo account exists.

## Tests

- Port contracts with in-memory fakes, like the existing ones.
- A recall eval: about 50 scripted days of conversations and tasks, then questions ("when is Anna's birthday?", "what did I ask about the dentist?", "what was the Excel problem?"). Score hits and token use. Run it in CI with a fake embedder and on demand with the real one.
- Crash tests: kill the brain mid-write, then check that every log still reads and the index rebuilds.

## Open questions

- Does the user approve each new fact, or only see a list they can fix? (Suggested: no approval, a visible "Milo learned" line in the window, easy Forget.)
- How long to keep raw transcripts before only the episode summaries remain? (Suggested: 90 days, setting.)
- Which knowledge sources get indexed by default? (Suggested: none until the user turns them on per source.)
