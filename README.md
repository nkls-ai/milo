<img src="assets/icon.svg" width="64" height="64" alt="">

# Milo

A small assistant that lives in the bottom-right corner of your Mac. Hold a key and talk to him, or hold another key to dictate into any app. Speech recognition, speech synthesis and memory run on your Mac. Only the LLM turn goes out, through whichever agent CLI you configure (Codex by default, Claude Code as an alternative).

- **Dictation (Wispr Flow replacement).** Hold `fn`, speak, release. Whisper large-v3-turbo transcribes on the GPU in about 1.2 s, filler words are dropped, and the text is pasted into the focused app. Your clipboard is restored afterwards. For hands-free, double-tap `fn`: a lock shows next to Milo, tap `fn` once more to paste, `esc` to throw it away. A hands-free recording stops by itself after 5 minutes (`[ui] hands_free_max_s`).
- **Live words.** While you speak, the words appear in a small pill next to Milo. `[dictation] stream` picks how: `"preview"` (default) shows them (from the small whisper-base model, several updates a second) and pastes one final pass over the whole recording on release, `"type"` pastes each phrase into the app at the pause after it, `"off"` transcribes only on release.
- **Talk to Milo.** Hold right `⌥`, speak, release. Double-tap it for hands-free, like dictation. Milo thinks with Codex, answers in a speech bubble, and speaks with OmniVoice, sentence by sentence.
- **Pip.** Milo is a small lavender bird. He blinks, follows your cursor, cocks his head to listen, ruffles his tuft while thinking and sleeps tucked in at night. When he works on something on screen he flies there and points at it with a wing. `[ui] character = "classic"` brings back the purple robot.
- **The Milo window.** Click Milo (or "Open conversation" in the menu bar) to read the conversation, type to him, and watch what he does when he works on something for you: "Looking in your Downloads folder", "Editing notes.md". Click a step to see the exact command. The speaker button decides whether he reads typed answers aloud. The history is kept in `~/Milo/state/transcript.jsonl`.
- **Helpers.** Ask for something that takes work and Milo hands it to a helper, then keeps talking with you. Several helpers work at once (`[harness] max_helpers`, 3 by default), and work on the screen goes one at a time. A small bird next to Milo stands for each helper, with what it is doing; click it to see its steps in the Milo window, where Stop ends it. Ask "how far are you?", change a task while it runs ("make it 2000 instead"), or say "stop that one" or "stop everything". `[chat] updates` decides how much Milo tells you along the way: `"quiet"`, `"bubble"` (short notes, the default) or `"chatty"` (he says it). It applies without a restart.
- **Your apps.** Milo can look in your calendar and reminders, add to them, search and read your mail, write drafts (he never sends mail; you press Send), search, read and add to notes, run your shortcuts and find documents in your home folder, including PDFs, Word files and spreadsheets. Each one can be switched off under `[connections]` in `~/Milo/config.toml`.
- **He asks first.** Reading and drafting just happen. Anything that goes to another person, deletes, buys or runs a shortcut waits for a yes: Milo asks in the bubble and the window with Yes and No buttons, and you can also hold the talk key and say "yes" or "no". No answer within a minute means no. Passwords, money transfers and security settings he never does. Change the levels under `[approvals.levels]`.
- **Memory.** `~/Milo/memory/` is plain Markdown that Milo reads and edits himself. Open it and fix anything he got wrong.
- **Milo looks when you ask.** "Look at my screen, what do you think?" Milo reads the window in front and takes a picture of it, then answers. An eye shows next to him while he looks. He never looks on his own.
- **What's this?** Select something and press `⌃⌥M` (or pick "What's this?" in the menu bar item). Milo explains the selection, or the whole window if nothing is selected. Change the shortcut with `[ui] whats_this_key`.
- **Milo uses the Mac for you.** "Put these numbers into the Excel sheet", "find the email from Anna and file it". The worker gets tools to read windows, press buttons, type and click. A frame around the screen shows while he works, and each action shows up as a step in the Milo window. Press `esc` or move the mouse to take over; he stops and tells you how far he got. Before he sends, deletes, buys or runs a script, he asks in the bubble. No answer within a minute counts as no. He never touches password fields or password apps.
- **Reminders and nudges cost no tokens.** Say "remind me at 9 to call the dentist" and Milo writes a line to `~/Milo/reminders.md`. The local heartbeat fires it later without calling the LLM. Morning greetings, break nudges and "welcome back" are local rules too. Cap: `llm_calls_per_day = 0`.

## Run it

Requirements: Apple Silicon Mac, macOS 14+, [uv](https://docs.astral.sh/uv/), Swift (Command Line Tools), and a logged-in Codex CLI. Milo finds the copy bundled with ChatGPT.app on his own.

```sh
cd brain && uv sync --extra omnivoice   # ~1.4 GB of Python deps
cd .. && scripts/build-app.sh --open    # builds build/Milo.app and starts it
```

The first start downloads the Whisper (1.6 GB plus 150 MB for live words) and OmniVoice models to `~/.cache/huggingface`. Then:

1. Grant **Accessibility** (for the hotkeys, pasting, reading windows and using apps) and **Microphone** when macOS asks. Ad-hoc signed builds may ask again after a rebuild.
   For looking at the screen, also turn on **Screen & System Audio Recording** for Milo in System Settings › Privacy & Security, then quit and reopen Milo. Without it he reads window text only and tells you which switch is missing. The first script he runs in an app makes macOS ask whether Milo may control it (Automation).
2. System Settings › Keyboard › "Press 🌐 key to" › **Do Nothing**, so `fn` belongs to Milo.
3. Quit Wispr Flow if it's running. It wants `fn` too.

The first time Milo uses your calendar or reminders, macOS asks whether Milo may; the first time he uses Mail or Notes, it asks whether Milo may control them. Say OK once each. You can change it later in System Settings › Privacy & Security.

Settings live in `~/Milo/config.toml`: harness, voice, keys, heartbeat rules. Restart the brain from the menu bar item after editing. Milo never overwrites `~/Milo/AGENTS.md` or `~/Milo/config.toml`, so a workspace from before gets the advice for the user's apps and for using the Mac only if you copy the "The user's apps" and "Using the Mac" sections from `brain/src/milo/workspace_template/AGENTS.md`. The tools carry the most important rules themselves. `[hands] enabled = false` takes the Mac tools away from the worker, and `applescript = false` turns off scripts only. Jobs on the screen take a while, so give the harness more time: `[harness.codex] timeout_s = 600`. Questions before a risky step wait `[approvals] timeout_s`; an old `[hands] confirm_timeout_s` is ignored with a warning in the log.

For brain development, run it in a terminal (the app connects to it instead of starting its own):

```sh
cd brain && uv run --extra omnivoice milo
```

## Tests

```sh
cd brain && uv run pytest -q
cd app && swift test
```

The 30-task eval runs Milo on a made-up calendar, inbox, notes and files with a real chat model and worker, and prints a score. It never touches your own data. See [docs/eval/tasks.md](docs/eval/tasks.md):

```sh
cd brain && uv run python -m milo.eval
```

## Docs

- [Architecture](docs/ARCHITECTURE.md): processes, ports and adapters, how to add an engine
- [Decisions](docs/adr/)
- [The 30-task eval](docs/eval/tasks.md)
- [TODO](TODO.md)
