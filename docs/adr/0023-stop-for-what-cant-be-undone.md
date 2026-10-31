# 23. Stop for what can't be undone, and auto by default

Date: 2026-10-31. Status: accepted. Changes [ADR 9](0009-approvals-and-action-levels.md) and [ADR 22](0022-one-question-per-piece-of-work.md).

## Context

ADR 9 and ADR 22 decided by the kind of action: a delete asked, whatever was deleted. Moving last year's copy of a budget to the Trash asked the same question as emptying the Trash. Money was `never`: Milo refused to buy anything, even when asked.

The user's rule: "He should stop before buying or anything involving money or destructive, and ask. Maybe irreversibly destructive he has to ask, otherwise it can be annoying."

The same night, "make the whole Excel red" asked twice in the default mode (`task`). First Milo asked whether to start the task, because it came from a reply to a look (ADR 14). Then the careful helper asked "May I use Microsoft Excel for this?". The user: "maybe have no ask except for payment and destructive the default mode (like the auto mode from Claude basically)".

## Decision

**The line is whether it can be undone.**

Always asks, in every mode. A task Allow, Allow always and auto mode never cover these:

- **Destroying something for good:** emptying the Trash (⇧⌘⌫, ⌥⇧⌘⌫, "Empty Trash"), deleting for good (⌥⌘⌫, "Delete Immediately…", "Delete permanently"), Don't Save and Discard, replacing a file on disk ("Replace" or "Overwrite" in a save dialog), uninstalling, closing or deleting an account, cancelling a subscription, unsubscribing. It also covers deleting in apps without a trash: a "Delete" in Reminders, Calendar or Contacts, or in an app Milo doesn't know (`risk._button`).
- **Sending, sharing, publishing, posting**, as before.
- **Buying and anything with money:** buy, order, checkout, pay, transfer, withdraw, sell (with the German words). See below.
- Scripts that reach outside the document, terminals, System Settings and unnamed clicks, as before.

Can be undone. These don't ask in `task` or `auto` mode, and still ask in "Every step":

- moving files or mail to the Trash: "Move to Trash" in an app (not on a web page, which writes its own labels), a plain "Delete" in Finder, Mail or Photos, and ⌘⌫ there while a file, a row or a message has the focus. ⌘⌫ with a button or nothing named in focus asks, because it may be the Delete of a "keep this new document?" sheet;
- deleting a note (Notes keeps it in Recently Deleted);
- closing a document whose changes are saved. ⌘W and ⌘Q don't ask; the Don't Save button behind them does.

Deleting or replacing content inside an open document (cells, rows, text; the "Delete" menu item, "Clear", "Replace All" in Excel, Numbers, Pages, Keynote, Word, PowerPoint, TextEdit) is ⌘Z work. A "Delete" *button* there asks every time: it may be the sheet that throws a new document away. This kind of work is what ADR 22's `Scope` already covers. It asks once per task in `task` mode and not at all in `auto`. ⌘⌫ in a cell or in text is undoable like the Trash, so it asks only in "Every step".

When it isn't clear, Milo asks. Only exact labels in apps known to keep a trash count as undoable. "Delete Mailbox", "Delete Sheet" and "Delete…" with a dialog behind it ask, and so do unknown apps and web pages. A bare "Replace" button asks every time: it is what the save dialog says when a file already exists, and a word list can't tell it apart from Find and Replace. "Replace All" counts as document work.

**Risk levels.** `risk.classify` returns `OK`, `UNDO` (asks only in "Every step" mode), `ASK`, `MONEY` (asks always, button only) or `NEVER`. Money words win over everything else in a label, so "Confirm purchase" is money.

**Action kinds** (`[approvals.levels]`). Screen actions follow the classifier, but a `trash` level stricter than `change` counts for them too: `ask_first` asks every time, `never` refuses.

**Action kinds** (`[approvals.levels]`): `delete` now means for good. New kinds: `trash` (`change` by default: it asks only in "Every step" mode, or once per app for a careful helper), `discard` and `overwrite_file` (`ask_first`). Old configs keep working: an unknown key still fails, and every old key still parses. `delete = "never"` without a `trash` line makes `trash` never too, so it still means Milo deletes nothing. `delete = "ask_first"`, which the old template wrote out, was the old default and leaves `trash` alone.

**Connection tools.** None of them deletes anything. `reminders_complete` can be unticked, `files_move` never replaces a file, notes are only made or added to, and calendar events are only added. All of them are `change`. `memory_forget` is a `delete` and asks every time. The MCP listing sets `destructiveHint` for `delete`, `discard` and `overwrite_file`.

**Money moved from `never` to asking.** This is the user's call: they want Milo to be able to buy something they asked for, and to stop first. Since a wrong yes costs real money, the answer is stricter than for any other question:

- `buy` and `money` are `ask_first`. config.toml may make them `never` but nothing below `ask_first`; a lower value is logged and ignored, so an old `buy = "read"` doesn't stop the brain.
- `confirm.money` marks the question. The bubble's heading says "This involves money" with a card icon instead of "Okay to go ahead?". Under the question it says "Only a click on Yes counts for this, not a spoken yes". The window and Today show the same line instead of "Or hold … and say yes or no."
- Only a click on Yes answers it. `Approvals.answer` refuses a yes that comes by voice, by typing or from the phone. A spoken yes is taken so it doesn't start a turn, and Milo says that the button has to answer. A spoken "no" still says no.
- No Allow always and no scope, so no task Allow and no auto mode covers it.
- While the owner is away (the phone relay would take the question `only`), it isn't asked at all: the answer is no, and the phone gets a note without buttons. When the owner writes from the phone but is at the Mac, the phone gets a note and the Mac asks.
- Typing into password fields, card-number and security-code fields (`risk._CARD`: card number, CVV, CVC, security code and their German names), the keychain and security settings stay `never`.

**Auto is the default.** `[approvals] ask` defaults to `auto`, in `ApprovalSettings`, `Permits` and the template config.toml. The Settings label is "Only when it matters (auto)". Step and task stay as choices. A config.toml that says `ask = "task"` keeps it: the template wrote that key between ADR 22 (2026-10-31 00:54) and this ADR, so configs made in that window keep asking once per task until the user picks auto in Settings. Nothing migrates them on its own.

In auto mode, ADR 22's rules for `user_asked` are unchanged. A task from the reply to a look starts without a question when the user's words that turn asked for work ("make it completely red"). The careful helper's "May I use Excel?" is a scoped question, so `user_asked` covers it. A look itself never asked. Routines and work after outside text still ask once per task, and a task from "can you see my screen?" alone asks first. That keeps a page Milo was only asked to look at from starting work.

**Settings copy.** Under "How often Milo asks before he acts": "He always stops for things that can't be undone, sending, buying and money. Passwords and security settings he never touches." In auto mode it starts with "Milo does what you ask without checking first."

## Consequences

- The Excel story (`tests/services/test_undo_line.py`): a helper that replaces cells, moves a file to the Trash and deletes a note asks 8 questions in "Every step", 1 in "Once per task" and 0 in auto. The same helper emptying the Trash, choosing Don't Save, buying and starting a transfer asks each time, twice over, in all three modes, with Allow always clicked on everything. "Make the whole Excel red" in the default config asks nothing and the script runs.
- Mail's Trash mailbox and Notes' Recently Deleted folder are the exceptions the word list can't see: there "Delete" deletes for good, but the label is the same, so Milo treats it as undoable. Milo doesn't see which mailbox or folder is open.
- ⌘D is Don't Save in an unsaved-changes sheet and Fill Down in Excel. It isn't treated as risky, so the Don't Save it can trigger doesn't ask. Clicking the button asks.
- The money check is a word list too. A script that mentions "order" asks as a money question and can only be answered with a click. A bank page whose button says "Confirm" asks, but not as money. The worker's instructions (`connect/tools.py`, `AGENTS.md`) tell it to stop before buying. That only reaches new workspaces: an existing `~/Milo/AGENTS.md` keeps its old line ("Never move money"), which is stricter.
- With auto as the default, the menu bar's "auto" badge (ADR 22) is gone: it would show for everyone. The menu still says auto mode is on and can turn it off.
