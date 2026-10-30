# Conversations, tasks and a home view: research

Written 2026-10-30 for [design/conversations.md](../design/conversations.md). The question: the Milo window is one endless scroll of chats, task steps, helper updates, phone messages and routine runs. What would a person who has never used ChatGPT understand without being told?

## What others do

| Product | Structure | What to take | What to leave |
|---|---|---|---|
| Apple Messages | One thread per person, newest on top, a preview line and a time. Time stamps appear only after a pause. | The list row: name, one line of preview, a short time. People already read it without help. | One endless thread per person: that is the problem we have. |
| Apple Notes | Folders, then notes grouped "Today", "Previous 7 Days", "Previous 30 Days", then months. The first line is the title. | The day grouping, and "the first line is the title" as the fallback before anything smarter. | Folders: nobody files chats. |
| ChatGPT, Claude, Open WebUI | A sidebar of conversations grouped by "Today", "Yesterday", "Previous 7 Days"; a small model writes the title after the first exchange, the user can rename. Open WebUI documents the grouping and the task-model title ([docs](https://docs.openwebui.com/features/chat-features/history-search)). | Auto titles, renaming, day groups, search across chats, "New chat" on ⌘N (Claude) or ⇧⌘O (ChatGPT). | The user has to start new chats by hand, or everything piles into one. Milo has to split on his own. |
| Raycast AI chat | Chats in a side list, "New chat" after a while of quiet is offered automatically, presets per chat. | Starting fresh after a pause without asking. | Presets and models in the UI. |
| Things 3 | "Today" first: what is due now, then the rest. Calm white space, one accent colour, a small check animation. | A home view that answers "what needs me now?" before any list. The delight of one small, good animation on completion. | Areas and projects. |
| Linear inbox | One list of things that need you, each opens the item on the right; keyboard first (j/k, Enter, Esc). | "Waiting for you" as its own section, keyboard first, open on the right. | Triage states and density. |
| Arc spaces | Separate contexts side by side, switched with a gesture, each in its colour. | The colour of the context (here: the skin's theme) carried through every surface. | User-made spaces: too much to manage. |
| Granola | Meetings as a list by date, each with its notes; the meeting is the unit, not the transcript. | Meetings as their own entries with their own title and summary. | |

## Prior art for splitting

- **Time gaps.** Slack and IRC chat segmentation work (e.g. ACL 2017 on Slack threads) uses the time between messages as the strongest single signal. A PR in `embabel/dice` ([#59](https://github.com/embabel/dice/pull/59)) warns that "a new conversation after N minutes" alone is weak for chats people answer later, and cuts long runs at their largest gap. For Milo the gap matches what already happens: after `[chat] conversation_idle_reset_s` (600 s) the chat model forgets the conversation and starts fresh, so the window splitting there shows the user the truth.
- **Topic shifts.** `roboticus-agent` ([topic.rs](https://docs.rs/crate/roboticus-agent/latest/source/src/topic.rs)) compares a new message's embedding with the recent replies and starts a new topic below a threshold. Research on long-term memory ([arXiv 2502.05589](https://arxiv.org/html/2502.05589v2)) segments conversations into topical units with a model. Memory's own measurements ([design/memory.md](../design/memory.md)) show e5-small puts nearly every pair of sentences between 0.7 and 0.85, so a fixed embedding threshold would be fragile here; word overlap plus a pause plus explicit cues ("something else", "anderes Thema") is cheap, testable and predictable. Embeddings can come later behind the same policy.
- **Titles.** ChatGPT and Open WebUI ask a small model after the first exchange. Milo already has a model writing every reply, so the cheapest title is a tag in the reply it writes anyway (`<title>`), with a word heuristic until it arrives.

## What this means for Milo

1. Conversations split by themselves. Nobody has to press "New chat", though they can (⌘N).
2. The list reads like Messages: a title, one preview line, a time, an icon for how it happened (phone, meeting, routine).
3. A home view comes first, like Things' Today: what Milo is doing, what waits for you, reminders, what got done.
4. Work is a card in the chat and a page of its own, like a Linear issue: status, steps, result, files.
5. Keyboard first: ⌘N, ⌘F, ⌘1, ↑ ↓ Return, Esc.
