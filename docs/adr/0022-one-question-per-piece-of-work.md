# 22. One question per piece of work, Allow always, and auto mode

Date: 2026-10-31. Status: accepted. Changes [ADR 9](0009-approvals-and-action-levels.md) and [ADR 14](0014-scripts-milo-writes-and-short-questions.md).

## Context

"There are so many questions if you just want to work on Excel." A helper filling in a budget sheet asked six times in one task: replace the filled cells, run a script to make the header bold, run another for a chart, borrow the mouse to click a cell, borrow the keyboard to type a formula, and replace cells again for the totals row. Every question was about the same piece of work in the same app. ADR 9 warned about exactly this: asking too often teaches people to say yes without reading.

The user asked for three things. The first question in a task should cover the rest of that task in that app. "Allow always" should stop the questions for an app for good. And an auto mode should not ask at all for what they asked for, including "look at my screen" and fixing what Milo sees there.

## Decision

**A question about work in an app carries a `Scope`**: the apps it acts in (`AppRef`, by bundle id where known, else by name) and the task that asks (the helper's id). Only these questions get one:

- replacing filled cells (`sheet_write`), and clicking a button labelled replace or overwrite;
- a script that names exactly one app, by a quoted name or id, and doesn't reach outside the document in front. As far as words can tell, that means it doesn't save, open, close, read or write files, paths, links or folders, doesn't name an HFS path, and doesn't use `do shell script`, VBA or System Events;
- borrowing the mouse or keyboard in that app;
- a careful helper's first change in an app ("May I use Excel for this?"), and its `change` actions through the connection tools (Notes, Calendar, Reminders, Finder moves).

Terminals and other programs that run commands, System Settings, password managers and Finder never get a scope. Neither does a click on something the app can't name.

**Everything else asks as before, every time, in every mode**: sending or sharing with another person, deleting, buying, running a shortcut, scripts that reach outside the document, and new reminders or memories. The never-rules come first: password fields, money, security settings, and Milo's own control files ([ADR 20](0020-helpers-never-write-milos-control-files.md)). A scope is only looked at once a question would be asked, and `never` refuses before that, so no answer and no mode can reach them.

**`[approvals] ask`**, shown in Settings as "How often Milo asks before he acts":

- `step` ("Every step"): every scoped question asks, as before this ADR.
- `task` ("Once per task", the default): Allow covers the scope for the rest of that helper's run. A task ends when its helper ends (done, failed, stopped). A change made while it runs keeps the same helper and its Allow. A follow-up to a finished helper is a new helper and asks again. When a question from the tool socket can't tell which of several helpers asks, no task's Allow covers it; only Allow always does.
- `auto` ("Don't ask (auto)", off by default): a helper the user asked for (`Helper.user_asked`) does scoped work without asking. Everything else behaves like `task`.

**Allow always** is a third button on scoped questions. It adds the app to `[approvals] allowed_apps` in config.toml, and from then on no scoped question about that app asks, in any mode. Settings lists the apps, each with Remove. The window can only remove apps: `set_setting` with a list that adds one is refused, so only the button adds them.

**Where "always" is stored: config.toml**, as `allowed_apps = [{name = "Microsoft Excel", bundle = ""}]`.

- It is a setting the user can read and edit by hand, next to `[approvals.levels]`, which decides the same kind of thing.
- Helpers can't write it ([ADR 20](0020-helpers-never-write-milos-control-files.md)), and while the owner is away the settings guard puts it back ([ADR 17](0017-milo-by-message.md)).
- Settings already writes it one key at a time with the user's comments kept (`TomlConfigFile`), and lists of tables are written inline.
- A state file under `state/` would have been just as protected, but invisible: the user would have to find a JSON file to see what Milo may do.

**Answers.** Only a click on Allow always means always. A spoken or typed "yes" (ADR 9's rules unchanged) and a yes from the phone allow this time. "Yes, always" said out loud is a yes for this time. "Always" alone is no answer at all. A spoken word can be misheard or come from someone else in the room, and always is a lasting change to what Milo may do. The phone has no always either, since Milo by message is for when the user is away from the Mac.

**What counts as the user asking (auto mode).** `user_asked` is set only when the talker starts or changes a task in a conversation without outside text: no task results, no forwarded or quoted messages, no untrusted memory ([ADR 10](0010-untrusted-results-and-a-private-log.md)). It is lost:

- for a task from the reply to a look, unless the user's own words in that turn asked for work ("fix this sheet", "can you fill this in", "füll das aus"). "Can you see my screen?" or "what's this?" never does. So text on a page can't turn a look into work. Without such words the task asks first, as in the other modes (ADR 14).
- when a change comes from a conversation with outside text;
- when the helper reads outside text while it works. Every worker step counts except its own edits, opening an app by name, listing a folder and finding files by name: a web page, mail, notes, calendar, a file's contents, a grep or any other command ends it. From then on it is a `task` helper.

Routines (on a schedule or by name), meeting follow-ups and anything else Milo starts on his own are never `user_asked`: their instructions weren't said by the user just now. Looking at the screen never asked in any mode. ADR 6's `<look/>` captures at once; what asked after a look was the task from the reply to it, and that is what auto mode lets through.

**Wire.** `confirm` gets `always` (true: show Allow, Allow always, No). `confirm_answer` gets `always`. `confirm_done` may say `"always"`. The tool socket's `approve` takes an optional `app`, one of the apps the connection tools change things in (Notes, Finder); any other name gets no scope, so a caller can't borrow another app's Allow. `Decision.answer` may be `"always"`, or `"allowed"` when an earlier Allow covered it and nobody was asked.

**Seeing it.** While auto mode is on, the menu bar shows "auto" next to Milo, with "Auto mode: Milo doesn't ask first" and "Turn off auto mode" in the menu. The Settings row says in one line what auto means.

## Consequences

- The Excel story (`tests/services/test_permits.py`) asks 6 questions with `step`, 1 with `task`, 0 with `auto`, and 0 in the next task after Allow always.
- **Sending, deleting and buying still ask in auto mode**, although the user asked for a mode that "doesn't ask anything". They can't be undone, and they reach other people or money; a wrong one costs far more than one click. The user can still make the connection tools stop asking about them with `[approvals.levels]`, which is that same choice made deliberately in a file.
- The script check is a word list, like the rest of `risk.py`: a brake, not a sandbox. A script that only "formats the sheet" can still change any cell of any open workbook in that app. That is the work the user allowed. Anything that names a file, a path, a link or another app asks.
- Auto mode trusts the screen the user asked Milo to look at, in the turn they asked for work. A page shown at that moment could still bend that task: "fix this sheet" might become a different change in the same app. It can't send, delete, buy, run code, reach files or other apps without a question, and every step shows in the window with the stop key.
- A `task` Allow is kept per helper id in memory only. A restarted brain asks again, which is the safe direction.
- A Codex worker usually starts by running `cat` or `grep`, which ends auto coverage. In practice auto mode covers screen work through Milo's own Mac tools (which don't show up as worker steps) and tasks that don't read anything first. It errs towards asking.
