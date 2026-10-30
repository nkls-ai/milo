# 14. Scripts Milo writes himself, and short questions

Date: 2026-10-30. Status: accepted. Changes [ADR 7](0007-computer-use-through-the-brain.md). How often a question about work in an app asks, Allow always and auto mode: [ADR 22](0022-one-question-per-piece-of-work.md).

## Context

On the morning of 2026-10-30 "open Excel and make a table for the week" failed twice. Milo had looked at the screen earlier in the conversation, so the task waited for a yes, and the question was the whole task description, too long to read before it timed out. Then the worker built the table by clicking and typing through Excel, one cell at a time. Each step took a model turn, and any free-form AppleScript waited for another yes.

## Decision

- **Tools the brain writes the script for.** `sheet_write` and `sheet_read` (Excel and Numbers), `write_document` (TextEdit and Pages) and `ax_find` take plain arguments. The brain turns them into AppleScript itself (`services/sheets.py`, `services/documents.py`): every value goes in as an escaped string or number literal, never as code, so they need no question the way `run_applescript` does. One `sheet_write` call opens the app, makes a new document, fills the cells and formulas, and sets bold rows, decimals and money. Money uses the currency of the Mac's region (`defaults read -g AppleLocale`).
- **Route order** in the tool descriptions and `AGENTS.md`: these tools first, then `run_applescript`, then `ax_find` and `ax_tree`, then a screenshot with clicks.
- **What asks.** Making something new, opening apps and reading never ask. `sheet_write` into an existing document asks before it replaces filled cells ("Replace 8 filled cells in “Budget”?"), counted by a read-only script first. Every `run_applescript` asks, because a word list can't tell what a script does. Clicks on send, delete, buy, pay, share and similar words ask as before.
- **Questions are one short sentence**, at most 80 characters, ending in a question mark: "Fill column C in Budget.xlsx?", "Replace 8 filled cells in “Budget”?", "Run a script in Numbers? It's in my window." The full task or script shows under the question in the Milo window. Changes to a running task (`<steer>`) ask the same way.
- **After a look, careful instead of blocked.** A task the user asks for in a conversation that has seen the screen still starts at once, but its helper runs careful (`Helper.careful`, also set by a change to the task made in such a conversation): Approvals asks before that helper's `change` actions too, and HandsService asks once per app ("May I use Numbers for this? You'll see each step.") before the first change there. Helpers run in parallel ([ADR 11](0011-helpers-and-the-orchestrator.md)), so careful is per helper, not a switch on Approvals: `TaskRunner` hands the screen helper's flag to `hands.begin`, and `HelperQuestions` passes it to `Approvals.approve` for the connection tools. When several helpers work and the tool socket can't tell which one asks, any careful one counts. A task the chat model starts on its own after reading untrusted text still asks first, in one short sentence.

## Consequences

- A whole table is one tool call of about 2 to 15 s (most of it the app starting) instead of dozens of clicks.
- The script templates depend on each app's AppleScript dictionary. A test checks that none of them says `tab` or `linefeed` inside an app's `tell` block, because Excel's own `tab` took the place of AppleScript's and the names came back empty.
- New apps need their own templates. Until then they go through `run_applescript`, which asks.
