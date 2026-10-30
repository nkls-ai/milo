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
- A stable signing identity so macOS permissions survive rebuilds.

- Pip's idle CPU is too high: measured 6.5% for Milo.app on screen, asleep at night (2026-10-30, 03:35), against the robot's ~0.4%. Find what keeps redrawing while he sleeps (the sleeping pose, the "z", the 15 Hz clock) and stop the clock when nothing moves. One frame of Pip costs 1.3 ms against the robot's 1.7 ms, so the clock rate is the likely cause, not the drawing.
- Pip pointing near the left screen edge: the bubble hangs to his left and can be cut off. Move the bubble to his right when he perches there.
- Pip: a fold or flap animation when he takes off and lands, instead of starting mid-flap.

- Milo window: show heartbeat nudges and reminders in the transcript too (only turns and tasks are recorded now).
- Helpers: a warm Claude worker process (like the chat model's) to save its start-up on every task. Codex can't be warmed, `codex exec` reads the whole prompt first.
- Helpers: say which helper an app-connection question comes from (the tool socket doesn't know now), so the right bird shows "needs you" with several at work.
- Helpers: try a screen helper with the real milo-mac tools next to two background helpers, and `chatty` updates with the real voice.
- Computer use: try it on real apps (Excel, Mail, Safari) and tune the tool descriptions, the risk words and the takeover slop.
- Computer use: a stop key that works while a question waits (input is ignored then, so the user can click Yes or No, or say yes on the talk key).
- Computer use: tune the tool descriptions and the risk words against more real apps (Mail, Safari, Keynote).
- Computer use: background typing into Chromium needs the borrow (Chromium ignores AXSelectedText). Worth a look at whether a per-process key route can be made reliable without private APIs.
- Computer use: give risky steps an action kind from `services/risk.py` (a click on Send is `send`) and ask through `Approvals.approve(kind, ...)`, so the log and the question say what kind it is. The classifier should still decide when to ask.
- Looking: send the screenshot only when the window text isn't enough, to save tokens on text-heavy windows.
- Milo window: persist a helper when it starts, so one cut off by a brain restart still shows (now it is lost).

## Later
- Wake word ("hey Milo") with a small local model.
- Rive or sprite animations instead of SwiftUI shapes.
- Usage readout in the menu (`JsonlUsageLedger.today_totals()` exists).
- Mic pre-roll buffer. Skipped for now: a ring buffer needs the input stream running all the time, which keeps the macOS orange mic indicator on permanently. Recording already starts at key-down (before the 250 ms hold check shows anything), and a double tap records from the first tap.
- The final pass over a long hands-free recording is slow (about 1.5 s per 30 s). The live phrases come from the small preview model, so they can't simply be reused; transcribing closed phrases with the full model while the user still speaks would, at the cost of a busier GPU.
