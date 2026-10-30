# Conversations, tasks and Today: design

Status: proposed and built, 2026-10-30. Research in [research/conversations.md](../research/conversations.md). The decision is [ADR 19](../adr/0019-conversations-that-split-on-their-own.md). Pictures: [conversations/](conversations/).

## The problem

The Milo window was one endless scroll: chats, task steps, helper updates, phone messages, routine runs and meeting notes, all in one column. After a week nobody finds Tuesday's answer about the dentist, a running task's steps push the conversation off screen, and a routine that ran at 7 in the morning sits between two chats as if it belonged to them.

## What the user sees

```
┌────────────────────┬──────────────────────────────────────────────┐
│ 🔍 Search      ⌘F  │  Thursday, 30 October                         │
│                    │  Good morning.                                │
│ ☀ Today        ⌘1  │                                               │
│                    │  MILO IS WORKING ON                           │
│ TODAY              │  ● Budget table in Excel ▓▓▓▓░░ step 4        │
│ ●─ Dentist on Thu  │                                               │
│ │  4:12 PM  "Just… │  WAITING FOR YOU                              │
│ ●─ 📱 Train times  │  Send the draft to Anna?        [No] [Yes]    │
│ │  ☐ 1 task        │                                               │
│ ○─ 👥 Weekly sync  │  REMINDERS                                    │
│ YESTERDAY          │  15:30  Leave for the dentist                 │
│ ●─ ↻ Monday report │                                               │
│ THIS WEEK          │  DONE TODAY                                   │
│ ●─ Photos from Fri │  ✓ Renamed 40 photos           Show in Finder │
│                    │                                               │
│ + New conversation │  [ Type to Milo                       ] 🔈    │
└────────────────────┴──────────────────────────────────────────────┘
```

- **Today** is home: what Milo is doing now, what waits for an answer (questions and recipe drafts), today's reminders, what got done today, and the conversation from a moment ago to carry on. The window opens here unless a conversation is still going.
- **Usage** sits under Today: headline numbers for the range (tokens, model calls, dictations, active days), a bar per day for tokens or words dictated, where the tokens and the words went, and the accounts Milo uses with their plan. See ARCHITECTURE.md, Usage.
- **Conversations** split on their own. Each has a short title Milo writes, a preview line and a time, grouped under Today, Yesterday, This week, This month and then by month. An icon says how it happened: a phone for messages from the phone, two people for meeting notes, a circle arrow for a routine that ran on its schedule. The rows hang on a thread with a bead each, like a task's steps: the conversation going on now has a breathing ring.
- **A conversation** shows what was said, with each task as a compact card: what it is, its status, how many steps, a thin progress line. Clicking the card opens the task.
- **A task page**: status, the description, every step on the thread (the raw command on request), the result, the files it touched with "Show in Finder", Stop while it runs, and a link back to the conversation that asked for it.
- **Search** (⌘F) finds conversations by title, by what was said, and through memory's index by meaning ("the thing about the insurance").
- **Picking an old conversation up again:** typing in an old conversation continues it. Milo gets a short recap of it, so "and what about the other one?" makes sense.

Keyboard: ⌘1 Today, ⌘2 Usage, ⌘N new conversation, ⌘F search, ⌘[ back, ⌥⌘↑ / ⌥⌘↓ the previous and next conversation, ⌘L the text field, Esc closes search or goes back. Below 600 points of width the sidebar folds away behind a button (⌘0), so the old narrow window still works.

## Where things are

```
core/conversations.py        types (ConversationInfo, TaskInfo), SplitRules + split(), title_from(), recap(), files_in()
core/ports.py                ConversationStore
memory/conversations.py      JsonlConversationStore (state/conversations/), migrate() from state/transcript.jsonl
services/transcript.py       Transcript: the live conversation, splits, titles, tasks, resuming one
services/conversations.py    ConversationBrowser: list, open, search, rename, reminders for the window
services/reply_stream.py     the <title> tag
services/live_talk.py        asks for a title on a new conversation; takes a recap when one is picked up
```

## Files

```
state/conversations/
  index.jsonl                   one line per change of a conversation's header; the last line per id wins
  2026-10/c-5f2a9c1e04b7.jsonl  that conversation's entries in the order they finished, plus title lines
state/transcript.before-conversations.jsonl   the old transcript, kept as it was
```

The conversation files are the truth. `index.jsonl` is a cache: when it is missing or broken the store rebuilds it from the files. A title Milo or the user gives is a line in the conversation's own file (`{"title": "Dentist on Thursday", "by": "milo"}`), so a rebuild loses nothing. The index is read once at start and rewritten whole when it holds four times more lines than conversations. Opening a conversation reads its one file, never the others.

A conversation's id is `c-` and the id of its first entry. That makes the migration a pure function of the old file: run twice, it writes the same files.

## Ports

```python
class ConversationStore(Protocol):
    def append(self, conversation: ConversationInfo, entry: dict) -> None:
        """A finished entry of `conversation`. Updates its header."""
    def save(self, conversation: ConversationInfo) -> None:
        """A changed header without a new entry: a title, a task's status."""
    def title(self, id: str, title: str, by: str) -> ConversationInfo | None:
    def all(self) -> list[ConversationInfo]:
        """Every conversation, newest first. From the index in memory."""
    def get(self, id: str) -> ConversationInfo | None:
    def entries(self, id: str, limit: int | None = None) -> list[dict]:
        """A conversation's entries, oldest first; the last `limit`."""
    def search_text(self, words: Sequence[str], *, limit: int, budget_bytes: int) -> list[tuple[str, dict]]:
        """(conversation id, entry) whose text has every word, newest conversations first, reading at most
        `budget_bytes` of files."""
```

```python
@dataclass(frozen=True)
class ConversationInfo:
    id: str
    kind: str              # "chat" | "routine" | "meeting"
    started: str           # local ISO time of the first entry
    last: str              # of the latest entry
    title: str
    titled_by: str         # "words" (the heuristic) | "milo" (the <title> tag) | "you"
    via: tuple[str, ...]   # how the user's turns came: "voice", "typed", "message"
    turns: int             # user turns
    preview: str           # Milo's last line, cut to 90 characters
    tasks: tuple[TaskInfo, ...]
    outside: bool          # carried outside text (task results, the screen): a recap of it taints
    source: str = ""       # "meeting:<id>" or "routine:<slug>"
```

## When a conversation splits

`split(rules, current, turn) -> str | None` in `core/conversations.py` is pure and has its own tests. It gets the current conversation's recent state (last entry time, user turns, recent words, channel, whether Milo is asking) and the new user turn, and answers why to start a new conversation, or None.

| Rule | Default | Why |
|---|---|---|
| **gap**: more than `idle_s` since the conversation's last entry | 600 s, `[chat] conversation_idle_reset_s` | The chat model starts fresh at the same point, so the window shows what Milo actually remembers. |
| **asked**: the user says "new topic", "something else", "anderes Thema", "neues Thema", "different question" | any pause | They said so. |
| **topic**: no content word in common with the last turns, after a pause of `topic_gap_s`, in a conversation with at least `topic_turns` user turns, and the turn doesn't start like a follow-up ("and", "also", "what about", "und", "noch", "it", "that") | 120 s, 2 turns | Two unrelated questions a few minutes apart are two conversations; a quick follow-up never splits. |
| **channel**: the turn comes from the phone and the conversation was at the Mac, or the other way round, after `topic_gap_s` | 120 s | "From the train" is its own conversation, with the phone icon. |
| never | | while Milo waits for a yes or no, for a bare yes/no, or within a few seconds |

Only a user turn splits a conversation. Milo's own lines (a meeting's notes, an approval's question, a routine's report) join the conversation going on, or start one if none is. Two kinds always get their own conversation: **meeting notes** (titled with the meeting, source `meeting:<id>`) and **routine runs on their schedule** (titled with the routine). A routine run the user asks for in a chat stays in that chat, as a task card.

A topic split doesn't restart the chat model: it still knows the last minutes, which is harmless. ⌘N does restart it, so a new conversation the user asked for really starts clean. A split never moves entries: a task finishing later lands in the conversation that asked for it.

## Titles

1. **Words, at once.** `title_from(text)` takes the first user turn, drops greetings and politeness ("hey Milo", "can you", "please", "kannst du", "bitte"), keeps up to six words and 42 characters and capitalises it: "can you rename the photos from Friday" becomes "Rename the photos from Friday". A conversation that starts with a task uses the task's short title; a meeting or routine its own name.
2. **Milo, for free.** While a conversation has no title from Milo and fewer than four user turns, LiveTalk adds one line to the message: name the conversation with `<title>two to four words</title>`. The tag is never spoken, costs about ten output tokens, and needs no extra model call. It replaces the words title.
3. **You.** Renaming in the window (`rename_conversation`) wins over both, for good.

A title is display text only: at most 48 characters, without `<` or `>`.

## Picking a conversation up again

Typing in an old conversation sends `text` with its `conversation` id. The brain makes it the current one, and LiveTalk gets a recap in front of the next message:

```
<earlier_conversation title="Dentist on Thursday" when="Tuesday 28 October, 14:05">
The user picked this earlier conversation up again. What was said, oldest first:
User: Do I have anything on Thursday?
Milo: Just the dentist at four.
</earlier_conversation>
```

`recap()` keeps the newest lines that fit `[chat] recap_tokens` (600, under memory's 800 for a turn), says how many older lines were left out, and escapes everything like a task result. Only Milo's replies mark a conversation as carrying outside text: LiveTalk says when its model conversation has seen any (`carries_outside`), whether memory is on or not. A conversation that carried outside text (a task result, the screen, untrusted memory), and every meeting or routine run, gives an untrusted recap, which taints the conversation as a task result does (ADR 10). Talking to Milo with the key after picking one up goes on in it too, since it is now the current conversation.

## Search

`search_conversations {query}` answers `search_results`, newest first within each kind of match:

1. titles and previews in the index (instant),
2. memory's index when memory is on: `Memory.search` returns episodes with their `source`; a task episode points at its task id, a meeting at `meeting:<id>`, a turn at its time, which falls inside one conversation,
3. the words in the conversation files, newest first, reading at most 8 MB.

## Protocol

Brain to app:

- `conversations {conversations, current, more}`: headers newest first, at most 150 a page; sent on connect, on `get_conversations` and after every change (coalesced to every 0.3 s while a reply streams).
- `conversation {id, info, entries}`: one conversation, on `open_conversation`.
- `search_results {query, results}`: each {conversation, title, kind, at, snippet}.
- `reminders {reminders}`: open reminders of the next two days ({due, text}), for Today.
- `entry` and `history` entries gain `conversation` and, for tasks, `files`.

App to brain:

- `get_conversations {before?}`, `open_conversation {id}`, `search_conversations {query}`, `rename_conversation {id, title}`, `new_conversation`, and `text {..., conversation?}`.

`history` stays what it was, the current conversation's entries, so an older app keeps working.

## The migration

At the first start with this build, `migrate()` reads `state/transcript.jsonl` from the start, sorts the entries by time, cuts them with the gap rule, writes each conversation's file with an atomic replace, rebuilds the index, and moves the old file to `state/transcript.before-conversations.jsonl`. Every line comes over as it was, with its `conversation` added. A broken line is kept in a conversation file as a `{"broken": "..."}` line, so nothing is lost. A crash halfway runs it again, with the same result. If an older Milo wrote a new `transcript.jsonl` afterwards, the next start migrates those lines too and appends them to the kept copy.

## The app

- `TranscriptModel` stays the window's model and gains the list, the current id, opened conversations, search results and reminders. A user turn with an unknown conversation id makes that conversation the current one at once; the list that says so comes a moment later.
- `WindowRoute` is where the window is (Today, the conversation going on, another conversation, a task), the way back for ⌘[, and which side the last move came from. `WindowActions` is what the window asks of the brain: open, search, rename, new, older, send, and Show in Finder.
- `Views/ConversationView` is the root: the sidebar and a divider, then the page. Below 600 pt the sidebar folds away and ⌘0 or the sidebar button lays it over the page. `Views/ConversationsSidebar`, `Views/TodayView`, `Views/ConversationPage` (the old transcript list inside, tasks as cards), `Views/TaskPage` (`TaskCard`, `StatusSeal`, the page). The question bar and the input bar are the same components as before; their look belongs to track 13.
- Motion: pages slide in from the side they come from with the skin's spring, Today's cards float in one after another, the selection is one card that glides from row to row, the bead of the conversation going on breathes. Under Reduce Motion every move is a short fade and nothing breathes.
- Colours from the active theme only; task status colours stay the same under every skin.
- Renders: `MILO_RENDER_DIR=/tmp/milo-window swift test --filter WindowRender`. The images before this change are in [conversations/before](conversations/before), after in [conversations/after](conversations/after).

## Not built yet

Embeddings for topic splits, merging two conversations by hand, deleting a conversation, pinning, and the window's own search within a long conversation.
