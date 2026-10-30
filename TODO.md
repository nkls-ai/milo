# TODO

## Next
- Fast path for small talk: a local model (mlx-lm, Qwen3 1.7B or so) answers chit-chat in under a second. Codex only gets real tasks. Needs a router port.
- Calendar signal (EventKit is in the app now, for the worker's tools; send upcoming events as context too) and a "meeting in 5 minutes" rule.
- Take the shell away from the Codex worker, or route its `osascript` through the approvals, so it can't script Mail around Milo's tools and their questions.
- Live-test the Mail and Notes AppleScript on a real account: saving a draft, reply quoting, a new note without a folder.
- Mail: delete and move with `ask_first`; Reminders: change a due date; Calendar: move and delete an event.
- Let the brain ask the app whether a question still shows, instead of trusting its own record of the bubble, so a spoken yes can't land on a question already gone.
- Run the eval on Codex as the worker too, and on a few German phrasings.
- Thumbs up/down on unprompted nudges, stored in memory, so rules learn what you care about.
- Context-aware dictation formatting by frontmost app (casual in Slack, formal in Mail), via a local model `TextCleaner`.

- Idle CPU awake is still above 1%: about 1.8 to 3% for a release build with nobody touching the Mac (2026-10-30, on a busy machine; asleep 0.04%, before the skin system 7.2%). Repeating motion is in Core Animation now; what's left is each pose change (blinks, glances, the eyes following the cursor) redrawing the whole figure and every looping part's own hosting view, plus the springs' frames. Next: draw the eyes in their own small layer so a blink or a glance redraws only them.
- Settings: `[chat] updates` needs a brain restart to apply; make it live once the task runner reads it.
- Setup window: Automation is checked against Mail only, and macOS can only say while Mail is open. Check Notes too.
- Pip pointing near the left screen edge: the bubble hangs to his left and can be cut off. Move the bubble to his right when he perches there.
- Pip: a fold or flap animation when he takes off and lands, instead of starting mid-flap.

- Milo window: show heartbeat nudges and reminders in the transcript too (only turns and tasks are recorded now).
- Milo window: a stop button for a running task.
- Computer use: the character flies to `MiloModel.flyTarget` instead of the ring from `FlyFallback`.
- Computer use: try it on real apps (Excel, Mail, Safari) and tune the tool descriptions, the risk words and the takeover slop.
- Computer use: a stop key that works while a question waits (input is ignored then, so the user can click Yes or No, or say yes on the talk key).
- Computer use: give risky steps an action kind from `services/risk.py` (a click on Send is `send`) and ask through `Approvals.approve(kind, ...)`, so the log and the question say what kind it is. The classifier should still decide when to ask.
- Looking: send the screenshot only when the window text isn't enough, to save tokens on text-heavy windows.
- Milo window: persist a task when it starts, so one cut off by a brain restart still shows (now it is lost).

## Later
- Wake word ("hey Milo") with a small local model.
- Rive or sprite animations instead of SwiftUI shapes.
- Usage readout in the menu (`JsonlUsageLedger.today_totals()` exists).
- Mic pre-roll buffer. Skipped for now: a ring buffer needs the input stream running all the time, which keeps the macOS orange mic indicator on permanently. Recording already starts at key-down (before the 250 ms hold check shows anything), and a double tap records from the first tap.
- The final pass over a long hands-free recording is slow (about 1.5 s per 30 s). The live phrases come from the small preview model, so they can't simply be reused; transcribing closed phrases with the full model while the user still speaks would, at the cost of a busier GPU.
