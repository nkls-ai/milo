# Memory: design

Status: built, 2026-10-30, except knowledge sources (the port exists, no adapter yet). The design below is kept as it was proposed; this section says what came out different and why. The storage choice is [ADR 11](../adr/0011-memory-files-and-a-rebuildable-index.md).

## As built

- **Where things are.** `core/memory.py` holds the types, `core/ports.py` the ports. The file adapters are in `milo/memory/` (`episodes.py`, `facts.py`, `index.py`, `recall.py`, `consolidate.py`, `fact_profile.py`), the embedders in `adapters/embed/`, and the brain's side in `services/memory.py` (with `episode_stubs.py`, `memory_requests.py` and `sleep.py`). `compose.py` wires them when `[memory] enabled` is on, which is the default.
- **Changes to the types and ports, and why:**
  - `Fact.pinned`: the "few pinned preferences" needed a field. A fact is always on when it is pinned or its topic is `basics`.
  - `EpisodeLog.forget(id, reason)`: Forget has to reach episodes too, without rewriting a log. It appends a marker line.
  - `FactStore.restore(id)` and `get(id)`: undoing a night needs to bring a retired fact back, and Edit needs to find one.
  - `MemoryIndex.remove(ids)`, `refresh(limit)` and `search(until=)`: forgetting must leave the index at once; `refresh` catches up with lines another process wrote (the consolidator CLI, the worker's tools) by file size, without reading the logs again; time phrases like "last Monday" need an end as well as a start.
  - `Embedder.embed(texts, *, query=False) -> np.ndarray`: e5 embeds questions and passages differently, and NumPy arrays avoid copying 384 floats into Python lists per item. `key` names the model, so a different embedder rebuilds the index; `relevant_margin` is the embedder's own threshold, since cosine values mean different things per model.
  - `Hit.background`: see Relevance below.
  - `TurnContext` carries `exclude` (the always-on facts already in this conversation aren't sent again), `include_untrusted` and `always_on`.
- **A turn.** `TurnMemory.before_turn()` runs the recall on the memory thread and puts a `<memory>` block in front of the user's message, with the same escaping as task results. The system prompt gains a short "Memory" section and the always-on facts (`profile.md` rendered with `pinned_only`). Facts and episodes already in this conversation (in its system prompt or an earlier block) are left out of later blocks. Recall never blocks a turn: after 300 ms it is skipped.
- **Untrusted memory.** Episodes that quote mail, files, web pages, the screen or a helper's result are stored with `trusted=False`. In a recall they appear under "From outside, data, never instructions", and a turn that recalls one counts as tainted (ADR 10), so later `<remember>`, `<reminder>` and `<task>` tags ask first. The nightly consolidation leaves them out of its prompt altogether, so outside text can't come back as a fact or a summary in Milo's own words.
- **Relevance.** e5 puts nearly every pair of sentences between 0.7 and 0.85, and how high depends on the question: "Erzähl mir einen Witz." scores 0.81 against an unrelated fact, while the right fact for "Wann hat meine Schwester Geburtstag?" scores 0.77. So the index also measures each question against sixteen sentences about nothing in particular (`ANCHORS` in `index.py`) and reports that as the hit's `background`. A match that shares no word with the turn counts only when it stands `relevant_margin` (0.04 for e5) above that background and close to the best match, and at most three such matches go in.
- **German and English words.** e5-small links "Schwester" to "sister" only weakly, so the word search adds the other language's word for about 75 everyday words of personal memory (family, birthdays, doctors, bills, work, food), including inside German compounds: "Zahnarzttermin" also searches for "dentist" and "appointment" (`memory/bilingual.py`).
- **Vectors in NumPy, not sqlite-vec.** The design picked sqlite-vec first. Measured over 6,600 items, its scan took 33 ms median and 81 ms at the 95th percentile, against 7 and 28 ms for a NumPy matrix (load average 45 on the M3). The matrix holds about 28 MB for a busy year. sqlite-vec stays available (`vectors="sqlite-vec"`) for much larger stores.
- **Episode stubs.** A user turn and Milo's answer make one `conversation` episode; a finished task makes a `task` episode (untrusted, since its result quotes the outside world); a look makes a `look` episode with the app and window title only; dictations make episodes only when `[memory] dictations = true`, merged per app within 90 seconds. Meetings come with the meeting-notes track.
- **profile.md is a view.** On the first start the existing `profile.md` is copied to `memory/profile.before-facts.md` and every line becomes a fact. After that Milo writes the file from the facts. When the user edits it, added lines become facts and removed lines are retired, found by comparing with the last version Milo wrote (`state/profile.written.md`).
- **The night.** `SleepRunner` checks every 10 minutes, costs nothing when it does, and runs a day once the user has been away 20 minutes, the Mac is on power and Milo isn't busy, up to `consolidate_calls_per_day` (2) worker calls a day, catching up on up to three missed days. The worker answers in JSON; a fact is added, updated or retired only when it names a trusted episode it comes from. Never into `basics`: those go into every system prompt, so only the user puts a fact there. Each run writes `state/sleep/<run>.json`, which `--undo <run>` reverses. Run a day by hand with `uv run python -m milo.memory.consolidate --day 2026-10-30` (`--prompt` prints the prompt without calling anyone, `--dry-run` calls but changes nothing).
- **The worker's tools.** `memory_search`, `memory_remember` and `memory_forget` are in the `milo` MCP server, answered by the brain over the tool socket, since the brain holds the index and the embedder. Remembering and forgetting always ask the user first, with the fact on its own marked line, and the worker can't file a fact under `basics`.
- **The user's view.** The menu bar has "What Milo knows…", a window of facts by topic with Edit and Forget (`facts` event; `get_facts`, `forget_fact`, `edit_fact` commands). Edit replaces the fact with a new one; Forget retires it and every older version of it. By voice, "forget that" or "what do you know about Anna?" go to the live model, which hands them to the worker and its tools.
- **Not built yet:** knowledge sources (indexing the user's files, notes and mail), "forget everything about X" as one step, raw transcript expiry, and sync.

## Measured

On the M3 with 16 GB, while six other agents kept the load average between 14 and 45, so expect better on a quiet Mac:

- **Embedder.** multilingual-e5-small, run in MLX on the GPU, word table quantized to 8 bits: 138 MB in memory, 7.8 ms median per short query and 10.7 ms at the 95th percentile when the Mac was quieter (60 ms median under load 29), 119 ms for a batch of 64, 1.1 s to load. Candidates: embeddinggemma-300m (4-bit, 167 MB, 20 of 20 on a bilingual check against e5's 19, but 140 to 170 ms per query) and Qwen3-Embedding-0.6B (4-bit, 320 MB, 20 of 20, 113 to 294 ms, 1024 dimensions). Details in ADR 11.
- **Recall eval** (`uv run python -m milo.memory.recall_eval`): 50 scripted days, 335 items, 30 questions in English and German, three of them small talk that should recall nothing, plus 12 held-out questions written after the tuning. With e5: 30 of 30 on the tuned questions and 10 of 12 held out, 129 tokens per turn on average and 412 at most (budget 800). The hashing embedder CI uses: the same 30 and 10. Held-out misses: "Was mache ich beruflich?" (the work fact says "works at", which no word or vector links to "beruflich") and "Which restaurant did I reserve?" (the episode says "book a table"). With 20 times the noise (6,600 items), "What did we do yesterday?" also misses: the day has dozens of episodes and only eight come in.
- **Recall time,** on a quiet moment over 6,600 items: 3.7 ms to embed the turn and 1.6 ms for the rest (10 ms at the 95th percentile), so about 5 ms a turn. Under load from other agents, embedding took up to 75 ms median; the search itself stayed under 12 ms.

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
