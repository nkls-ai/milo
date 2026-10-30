# TODO

## Next
- Fast path for small talk: a local model (mlx-lm, Qwen3 1.7B or so) answers chit-chat in under a second. Codex only gets real tasks. Needs a router port.
- Calendar signal (EventKit in the app, sent as context) and a "meeting in 5 minutes" rule.
- Thumbs up/down on unprompted nudges, stored in memory, so rules learn what you care about.
- Context-aware dictation formatting by frontmost app (casual in Slack, formal in Mail), via a local model `TextCleaner`.
- A stable signing identity so macOS permissions survive rebuilds.

- Pip: measure idle CPU on screen in the real app. The offscreen probe (`MILO_PROBE_DIR=... swift test --filter OverlayProbe`) can't make its window count as visible from a non-GUI shell; one frame of Pip costs 1.3 ms against the robot's 1.7 ms on the same 15 Hz clock.
- Pip pointing near the left screen edge: the bubble hangs to his left and can be cut off. Move the bubble to his right when he perches there.
- Pip: a fold or flap animation when he takes off and lands, instead of starting mid-flap.

- Milo window: show heartbeat nudges and reminders in the transcript too (only turns and tasks are recorded now).
- Milo window: a stop button for a running task, and a confirm row for irreversible steps (Phase 2 brakes).
- Milo window: persist a task when it starts, so one cut off by a brain restart still shows (now it is lost).

## Later
- "What's this?" hotkey: screenshot or selection goes to the harness.
- Wake word ("hey Milo") with a small local model.
- Rive or sprite animations instead of SwiftUI shapes.
- Usage readout in the menu (`JsonlUsageLedger.today_totals()` exists).
- Mic pre-roll buffer. Skipped for now: a ring buffer needs the input stream running all the time, which keeps the macOS orange mic indicator on permanently. Recording already starts at key-down (before the 250 ms hold check shows anything), and a double tap records from the first tap.
- The final pass over a long hands-free recording is slow (about 1.5 s per 30 s). The live phrases come from the small preview model, so they can't simply be reused; transcribing closed phrases with the full model while the user still speaks would, at the cost of a busier GPU.
