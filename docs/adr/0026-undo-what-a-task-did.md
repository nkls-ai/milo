# 26. Undo what a task did

Date: 2026-10-31. Status: accepted. Builds on [ADR 11](0011-helpers-and-the-orchestrator.md), [ADR 12](0012-background-delivery.md) and [ADR 23](0023-stop-for-what-cant-be-undone.md).

## Context

On the morning of 2026-10-31 a helper made every cell of the user's unsaved workbook "Book2" red with one AppleScript (`set color of interior object of range "A1:XFD1048576" …`). The user: "I can reverse stuff that he did, because he changed stuff in the Excel, but I can't Command-Z to return it. That should definitely be a feature."

Helpers change documents mostly through `run_applescript` and Accessibility actions. A script's changes don't land on Excel's undo stack. ADR 23 lets in-document changes go ahead without a question because they "can be undone", so they need a real undo.

## Decision

**Every task that changes something gets an Undo** that puts things back the way they were before the task. It shows on the task's card in the conversation, on the task's page, on Today's "Done today", and under the bubble that says the task's result. Saying "undo that" or "mach das rückgängig" works too: the talker writes `<undo/>` (the newest task that can be undone) or `<undo helper="2"/>`.

**An undo point before the first change** (`services/undo.py`, `Undo.before_change`, called by `HandsService` right before any Mac action that may change something):

- **Excel workbooks.** Before a task first changes a workbook, the brain has Excel copy its sheets into a new workbook, save that as `.xlsx` in Excel's own folder (`~/Library/Containers/com.microsoft.Excel/Data/tmp/milo-undo-<task>-<n>.xlsx`) and close it (`services/snapshots.py`). The user's workbook isn't saved, renamed or touched, and it may have no file at all ("Book2"). The workbook is the one the script names (`workbook "Book2"`), the target of `sheet_write`, or else the active one. Once per workbook per task.
- **Files.** The worker calls `undo_point` (a `milo` tool) with a file's path before it changes, moves or overwrites it. The brain copies it to `~/Milo/state/undo/<task>/files/`. A file that doesn't exist yet is recorded as new.
- **What can't be copied** (text in a TextEdit or Pages window, a note, an event, cells in Numbers): the worker writes down what it changes and how it was with `undo_note`. The brain also records every Mac action that changed something, and the worker's own edits from its steps.

The worker knows its task by an id at the end of its prompt ("Task id for undo_point and undo_note: …"). The tool socket can't tell helpers apart (ADR 11), so a call without a known id goes to the only helper at work, and is refused when several are.

**Undo puts it back** (`Undo.undo`):

1. Excel copies are copied back over each sheet of the same name, the whole sheet (`copy range` of `A1:XFD1048576`), values, formulas and formats. Files are copied back; a file that was new moves to the Trash.
2. What no copy covers goes to a helper, "Undo: <title>", with the record of what the task changed (as data) and the worker's notes. It runs on the screen if the task did.
3. Milo says what he restored: "Undid “Excel red”: “Book2” is back the way it was."

**Never silently over the user's later edits.** When a task ends, the brain takes each copied workbook's fingerprint (each sheet's name, used range, formulas, and the fill and font colour over the whole sheet) and each kept file's hash. Before Undo overwrites anything it compares them. If something changed since, it asks, in every mode and without Allow always: "“Book2” changed since “Excel red”. Undo anyway? Your changes since would be lost." No keeps the Undo for later. Otherwise Undo asks nothing in auto mode: it is a change in the same app as the task, and it only puts back what Milo changed.

**Undo never asks first from the talker either.** Like a stop, an `<undo>` tag runs even in a conversation with outside text in it. A page that talks the chat model into `<undo/>` can only make Milo put back his own change, and the fingerprint check still asks when the user changed it since.

**Excel must never show a dialog.** Excel is sandboxed. A path outside its own folder makes it show "Grant File Access" and wait; a copy whose formulas link to an unsaved workbook asks "Save with references to unsaved documents?". Both happened during testing on this Mac. So:

- `snapshots.inside()` refuses any path that isn't a plain file name right in Excel's folder, before a script is written. A Mac without that folder (Excel never opened) gets no copies.
- Every script turns `display alerts` off while it works and back to what it was after, turns `screen updating` off so the copy doesn't flash, has a `with timeout` and closes its copy when it fails.
- The worker's instructions (`connect/tools.py`, `AGENTS.md`, `run_applescript`'s description) say: never save, open or export to new places from a script, never save a workbook linked to unsaved ones, and if a script times out, the app is probably showing a dialog, so stop and say so.

**Where it lives, and for how long.** `~/Milo/state/undo/<task>/record.json` and `files/`, plus the Excel copies in Excel's folder. A record expires after a day, and only the last 20 finished tasks keep one; expiry deletes the record, its file copies and its Excel copies, and logs what is left on disk. It runs at start-up and after every task. Files over 200 MB, and copies that would leave under 2 GB free, are refused, and the worker is told why.

**Wire.** `undo_points` (brain to app) lists tasks that can be undone, newest first: `{id, title, state, said}`, `state` ready, undoing or undone. It is sent on connect and on every change. It is a list of its own rather than a field on stored task entries, because a conversation file only grows: rewriting a task would add a second card. `said` is the result Milo spoke; the app puts the Undo button under the bubble whose text it begins with, for the newest ready task, and keeps that bubble up 8 s longer. `undo_task {id}` (app to brain) is the button.

## Measured

On this Mac (Excel 16, macOS 26.3), on a scratch workbook, never on the user's:

- Copying a one-sheet workbook to a new workbook, saving that in Excel's folder and closing it: about 1 s, no dialog, the user's workbook unchanged.
- After making the whole sheet red, changing a value and narrowing a column, copying the saved sheet's whole range back restored values, the formula, the header's fill, the white fill elsewhere, the black font, bold and the column width, in under 1 s.
- Saving to `/tmp` showed "Grant File Access" and timed out. A two-sheet workbook whose second sheet refers to the first asked "Save 'Book6' with references to unsaved documents?" and timed out.

Not tested live: the scripts with `display alerts` and `screen updating` off, workbooks with several sheets, and the fingerprint script. All three compile against Excel's dictionary (`osacompile`), and the story tests run them against a fake Excel.

## Consequences

- **Covered by a copy:** Excel workbooks, saved or not, and files the worker kept with `undo_point`.
- **Undone by a helper from the record:** Numbers, Pages, Keynote, Word, TextEdit, Notes, Calendar, Reminders, Mail drafts, and anything else. That is only as good as what the worker noted and what the app still allows.
- **Excel's limits.** Sheets the task added stay; a sheet it deleted or renamed can't be put back (Undo says it couldn't). Restoring copies cells, not charts, pictures, names or the workbook's window. A formula that refers to another sheet may come back as a link to the workbook it was copied from (untested). The fingerprint doesn't see every format change: a colour change on a few cells inside a sheet that had several colours already, or a changed column width, isn't noticed, and Undo would overwrite it without asking.
- **Excel's own ⌘Z** still can't undo a script's change, and after Undo it can't undo the Undo either. A new task's Undo is the way back.
- **The talker's `<undo>` tag needs the chat model to see "can be undone" on the board,** which only lists helpers from the last 10 minutes. Older tasks are undone with the button.
- **Existing workspaces keep their `AGENTS.md`.** The tool descriptions and the connections server's instructions reach every worker, so `undo_point` and `undo_note` are still known.
- A copy costs about 1 s before the first change in each workbook, and some disk: a few KB for a small workbook, more for big ones.
