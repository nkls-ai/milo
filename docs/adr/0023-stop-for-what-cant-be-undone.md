# 23. Stop for what can't be undone, and auto by default

Date: 2026-10-31. Status: accepted. Changes [ADR 9](0009-approvals-and-action-levels.md) and [ADR 22](0022-one-question-per-piece-of-work.md). Changed by [ADR 31](0031-talk-as-naturally-as-dictation.md): no answer no longer means no by default; the question stays open and a parked helper goes on after a yes. Money still only counts a click.

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

## Update, 2026-10-31: the user's own words are the yes

The morning after, auto mode still asked three times in one conversation: "Start “Excel-Zugriff prüfen”?", "Start “Excel-Tabelle rot färben”?" and "Run a script in Microsoft Excel?". The conversation counted as having read outside text (recalled memory, then the first task's result), and that made every task ask to start and run careful. In auto mode, at the Mac (voice or typed), a task now never asks to start:

- When the user's own words ask for work ("mach die Mappe rot", "fix this sheet"), that request is the yes for the whole task. It runs as theirs, not careful, even after Milo read the screen or a task result.
- Otherwise ("what's on my calendar?", "thanks" after a task result, "can you see my screen?") the task still starts, since reading never asks, but runs careful: before it changes anything in an app it asks.
- Everything this ADR always asks about still asks: what can't be undone, sending, sharing, buying and money.
- Routines still ask to start from such a conversation, and messages from the phone keep the old rules.

What this gives up: a task the model starts after reading outside text, in a turn where the user didn't ask for work, no longer waits for a yes before it reads. A page could talk Milo into reading something and then into a step that sends it; that step asks. A web search or fetch by the worker doesn't ask, so a read could leak through one. The user chose fewer questions ("like the auto mode from Claude").


**Update, later the same day.** After a look alone (no task result, no untrusted memory), such a task ran careful but still counted as `user_asked`, and in auto mode `Permits.covers` let that skip the careful helper's questions. Now a careful helper is never `user_asked` (`TagPolicy.user_asked` is `not careful`, ADR 34), so "before it changes anything in an app it asks" holds after a look too.

**Update, 2026-10-31: installing a program the user asked for.** "Install the Codex CLI" failed twice. A helper's shell has no network and writes only in `work/` (ADR 20), so `brew install` couldn't write `/opt/homebrew` and the curl installer couldn't resolve its host. And "install" wasn't a word for work in `tag_policy`, so after the shared calendar made the conversation outside the helper ran careful. Now:

- `install`, `reinstall`, `upgrade` and `installier…` count as work, and a request with them sets `TagPolicy.installs`.
- Helpers whose task is about installing (`task_scope` kind `install`) get `install_package(manager, package)`. The brain runs it outside the sandbox (`services/installs.py`): `brew install`, `brew install --cask`, `npm install --global` or `uv tool install`, as an argv list with only a checked package name (`core/packages.py`: no URL, path, flag, git source, archive or second command). It runs as the user, in an empty folder, with no terminal and stdin closed, so nothing can ask for a sudo password. The sandbox itself stays as it was.
- `install` is a new action kind (`change`). In auto mode an install needs no question only when the user's own words for that task asked for it (`Helper.install_words`, `packages.named_by`): the object of their install verb is either a program `packages.KNOWN` maps to exactly that manager and package ("the codex cli" is npm's `@openai/codex` or Homebrew's `codex` cask, "the github cli" is Homebrew's `gh`), or, for a program the map doesn't know, the package's exact name, with its scope for a scoped npm package (`@evil/codex` isn't "codex"). A manager the user named must be the one used. Everything else asks, naming the manager and the full package: a version, tag or tap, a request that points at someone else's text ("install what this page mentions", which sets no install words at all), a careful helper's install, an install while several helpers work and one of them wasn't asked, and every install in the other modes.
- Not covered: installers that only come as a script (`curl … | sh`). The worker is told not to run them; it says so instead. Uninstalling isn't a tool; it would be a `delete`.
