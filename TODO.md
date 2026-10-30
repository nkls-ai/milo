# TODO

## Next
- Fast path for small talk: a local model (mlx-lm, Qwen3 1.7B or so) answers chit-chat in under a second. Codex only gets real tasks. Needs a router port.
- Calendar signal (EventKit in the app, sent as context) and a "meeting in 5 minutes" rule.
- Thumbs up/down on unprompted nudges, stored in memory, so rules learn what you care about.
- Context-aware dictation formatting by frontmost app (casual in Slack, formal in Mail), via a local model `TextCleaner`.
- A stable signing identity so macOS permissions survive rebuilds.

- Milo window: show heartbeat nudges and reminders in the transcript too (only turns and tasks are recorded now).
- Milo window: a stop button for a running task, and a confirm row for irreversible steps (Phase 2 brakes).
- Milo window: persist a task when it starts, so one cut off by a brain restart still shows (now it is lost).

## Later
- "What's this?" hotkey: screenshot or selection goes to the harness.
- Wake word ("hey Milo") with a small local model.
- Rive or sprite animations instead of SwiftUI shapes.
- Usage readout in the menu (`JsonlUsageLedger.today_totals()` exists).
- Mic pre-roll buffer. Skipped for now: a ring buffer needs the input stream running all the time, which keeps the macOS orange mic indicator on permanently. Recording already starts at key-down (before the 250 ms hold check shows anything), and a double tap records from the first tap.
- Cheaper partial passes. Each Whisper pass costs about 1.1 s on an M3 regardless of length, because the encoder always sees a padded 30 s window. Truncating the encoder input makes Whisper repeat itself. A small model for partials (whisper-base, about 150 MB) would make live words update several times a second.
- The final pass over a long hands-free recording is slow (about 1.5 s per 30 s). In `preview` mode the phrases already transcribed could be reused for recordings over a minute or so.
