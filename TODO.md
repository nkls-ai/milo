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
- Helpers: say which helper an app-connection question comes from (the tool socket doesn't know now), so the right bird shows "needs you" with several at work, and a careful helper's "ask before changes" applies to it alone (now any careful helper at work makes the others' changes ask too).
- Helpers: try a screen helper with the real milo-mac tools next to two background helpers, and `chatty` updates with the real voice.
- Computer use: the on-screen eval's Mail case is unchecked. The eval starts the brain from the terminal, which has no Automation permission for Mail; let Milo.app start it (`MILO_BRAIN_DIR`) or allow the terminal, then run `--only mail`. Run the eval again now that helpers run in parallel and Milo works in the background.
- Computer use: log which input stopped a session (key, click, scroll or pointer, and where), so a stop the user didn't mean can be told from a real one. The "stopped by user" cases seen in the on-screen eval came before background delivery, where only `esc` or the Stop button stops Milo; borrowed mode still stops on any touch.
- Computer use: templates like `sheet_write` for Keynote and Safari, and `sheet_write` into a table other than the first.
- Computer use: a stop key that works while a question waits (input is ignored then, so the user can click Yes or No, or say yes on the talk key).
- Computer use: tune the tool descriptions and the risk words against more real apps (Mail, Safari, Keynote).
- Computer use: background typing into Chromium needs the borrow (Chromium ignores AXSelectedText). Worth a look at whether a per-process key route can be made reliable without private APIs.
- Computer use: give risky steps an action kind from `services/risk.py` (a click on Send is `send`) and ask through `Approvals.approve(kind, ...)`, so the log and the question say what kind it is. The classifier should still decide when to ask.
- Looking: send the screenshot only when the window text isn't enough, to save tokens on text-heavy windows.
- Milo window: persist a helper when it starts, so one cut off by a brain restart still shows (now it is lost).

- Memory: knowledge sources (folders, Notes, Mail, meeting notes) behind the `KnowledgeSource` port, off until the user turns each on.
- Memory: "forget everything about X" as one step (now one fact at a time, or by the worker after a search).
- Memory: Forget on a fact leaves the conversation where the user said it, and that episode can still be recalled ("Was trinke ich abends?" still found "ich trinke abends nur Kräutertee" in a smoke test). Forget the episode a fact came from too (needs the remember tag to record its episode as the fact's source), and start a fresh chat conversation after a Forget so the model drops it as well.
- Memory: run the recall eval again on a quiet Mac, and try a larger embedder for German-English matches once memory allows (e5-small misses "Zahnarzttermin" for an English dentist episode).
- Memory: try the nightly consolidation on a real day with Codex and with Claude, and read the journal it writes.
- Memory: expire raw transcripts after a while (the design suggests 90 days) once episode summaries hold up.

- Voice barge-in (`[chat] voice_barge_in`): try it with the MacBook speakers in a real room, then with headphones, and tune `TalkDetector` on what it gets wrong. Turn it on by default once a few days of use show no false stops. It only listens while Milo speaks; talking while he thinks still needs the key.
- First sound is about 1.5 to 2.5 s after the user's words, and most of it is OmniVoice's first piece (each diffusion step costs 200 to 500 ms even for a short piece, and the audio decoder another 0.3 s). Idea not yet measured: a per-call cache of the voice reference's encoder pass. Starting the chat turn on the committed words before the key comes up is possible now (the live transcript commits phrases while the user speaks, and the words are ready about 0.5 s after release), but a message sent to the running model can't be taken back if the user goes on talking, so it would need a throwaway conversation per guess.
- OmniVoice garbled one 6-step render out of about 40 in a Whisper check ("Goodnight..."). If it happens in use, 8 steps when the GPU is free.

## Later
- Wake word ("hey Milo") with a small local model.
- Rive or sprite animations instead of SwiftUI shapes.
- Usage readout in the menu (`JsonlUsageLedger.today_totals()` exists).
- Mic pre-roll buffer. Skipped for now: a ring buffer needs the input stream running all the time, which keeps the macOS orange mic indicator on permanently. Recording already starts at key-down (before the 250 ms hold check shows anything), and a double tap records from the first tap.
- Dev: a rebuilt app joins whatever brain holds the lock, even one running older code. build-app.sh now stops this checkout's brain; better would be the brain reporting its build and the app restarting a brain from another build.
