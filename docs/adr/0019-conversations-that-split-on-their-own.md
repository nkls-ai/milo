# 19. Conversations that split on their own, in files of their own

Date: 2026-10-30. Status: accepted. Design: [docs/design/conversations.md](../design/conversations.md). Research: [docs/research/conversations.md](../research/conversations.md).

## Context

The Milo window showed everything in one scroll from `state/transcript.jsonl`: chats, task steps, phone messages, routine runs, meeting notes. For the people Milo is for, that is a wall of text. Chat apps solve it with a "New chat" button, which nobody outside tech presses. Milo already forgets a conversation after `[chat] conversation_idle_reset_s` of silence, so the window had been hiding a boundary that was real.

## Decision

- **Milo splits conversations, the user doesn't have to.** A pure policy (`core/conversations.split`) starts a new conversation at a user turn after the chat's idle gap, when the user says so, after a pause when the turn shares no words with the conversation, or when the user switches between the Mac and the phone. Meeting notes and scheduled routine runs get conversations of their own. ⌘N is there for people who want it.
- **One file per conversation, an index as a cache.** `state/conversations/YYYY-MM/<id>.jsonl` holds a conversation's entries and its title lines; `index.jsonl` holds the headers and is rebuilt from the files when needed. Opening a conversation reads one small file. The alternative, keeping `transcript.jsonl` and storing byte offsets, breaks on tasks that finish after the next conversation started, and makes every open a seek into a file that grows for years.
- **Titles from the reply Milo writes anyway.** A word heuristic names a conversation at once; Milo's next reply carries a `<title>` tag that replaces it, at about ten output tokens and no extra call. A user's rename wins.
- **Tasks are pages.** The chat shows a card; the task's steps, result and files live on its own page.
- **Picking up an old conversation sends a recap,** at most `[chat] recap_tokens` (600), escaped like a task result, and untrusted when the conversation carried outside text, and always for meeting notes and routine runs.
- **The old transcript is migrated once,** deterministically, and kept as `transcript.before-conversations.jsonl`.

## Consequences

- The window shows the same boundaries the chat model has, so "he forgot" and "a new conversation started" are the same thing to the user.
- A topic split is a guess. Word overlap misses a follow-up that uses no word of the question ("and on Friday?" is caught by its opening "and"; "Friday works too" may not be). The cost of a wrong split is small: the old conversation is one click away and the chat model still has the context.
- Each finished entry costs two small appends (the conversation file and an index line) instead of one.
- `transcript.jsonl` is no longer written. Episode stubs still point at `transcript:<entry id>`; entry ids didn't change.
- A title from a conversation with outside text in it could carry words from that text. It is display text only, capped and stripped of tags.
