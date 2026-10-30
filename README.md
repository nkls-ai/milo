<img src="assets/icon.svg" width="64" height="64" alt="">

# Milo

A small assistant that lives in the bottom-right corner of your Mac. Hold a key and talk to him, or hold another key to dictate into any app. Speech recognition, speech synthesis and memory run on your Mac. Only the LLM turn goes out, through whichever agent CLI you configure (Codex by default, Claude Code as an alternative).

- **Dictation (Wispr Flow replacement).** Hold `fn`, speak, release. Whisper large-v3-turbo transcribes on the GPU while you speak, phrase by phrase, so the text is pasted into the focused app right after you let go, however long you talked. Filler words are dropped. Your clipboard is restored afterwards. For hands-free, double-tap `fn`: a lock shows next to Milo, tap `fn` once more to paste, `esc` to throw it away. A hands-free recording stops by itself after 5 minutes (`[ui] hands_free_max_s`).
- **Live words.** While you speak, for dictation and when talking to Milo, the words appear in a small pill next to Milo. `[dictation] stream` (or menu bar › Dictation style) picks how: `"preview"` (default) shows them and pastes on release, `"type"` also types each phrase into the app at the pause after it, `"off"` shows nothing and transcribes the whole recording on release.
- **Talk to Milo.** Hold right `⌥`, speak, release. Double-tap it for hands-free, like dictation. Your words show while you speak, and Milo gets them the moment you let go. He thinks with Codex, answers in a speech bubble, and speaks with OmniVoice, sentence by sentence. Press the key while he talks and he goes quiet at once; let go without saying anything and he picks up where he stopped. If his first word is slow in coming he says a short "Hm." first (`[chat] backchannels`). To talk over him without the key, try `[chat] voice_barge_in = true` (experimental: it hasn't been tested with real speakers yet).
- **Milo by message.** Write to Milo in Telegram from your phone and he works on your Mac: finds and sends you a file (after your yes), answers from your calendar, starts helpers and tells you when they're done. Risky steps ask you in the chat. Pairing takes a code shown on the Mac, no port is opened, and only your chat counts. Off by default; see [docs/setup/messages.md](docs/setup/messages.md). iMessage works too, experimentally.
- **Pip, and friends.** Milo is a small lavender bird. He blinks, follows your cursor, leans in and nods while you talk, ruffles his tuft while thinking and sleeps tucked in at night. When he works on something on screen he flies there and points at it with a wing. In Settings he can also be a round dragon who puffs smoke while he thinks, Kit the paper fox, Glow the lantern firefly, or the purple robot (`[ui] character` = `pip`, `dragon`, `kit`, `glow`, `classic`). The bubble and the windows take on his colours.
- **Settings.** "Settings…" in the menu bar item (or the gear in the Milo window) picks his look, how often he tells you what he's doing (`[chat] updates`), how dictation shows your words, his keys and whether he speaks his answers (`[ui] voice`). Changes are saved in `~/Milo/config.toml` with your comments kept, and apply at once. The menu bar's "Dictation style" changes the same setting as the window.
- **The Milo window.** Click Milo (or "Open conversation" in the menu bar) to read the conversation, type to him, and watch what he does when he works on something for you: "Looking in your Downloads folder", "Editing notes.md". Click a step to see the exact command. The speaker button decides whether he reads typed answers aloud. The history is kept in `~/Milo/state/transcript.jsonl`.
- **Helpers.** Ask for something that takes work and Milo hands it to a helper, then keeps talking with you. Several helpers work at once (`[harness] max_helpers`, 3 by default), and work on the screen goes one at a time. A small bird next to Milo stands for each helper, with what it is doing; click it to see its steps in the Milo window, where Stop ends it. Ask "how far are you?", change a task while it runs ("make it 2000 instead"), or say "stop that one" or "stop everything". `[chat] updates` decides how much Milo tells you along the way: `"quiet"`, `"bubble"` (short notes, the default) or `"chatty"` (he says it). It applies without a restart.
- **Your apps.** Milo can look in your calendar and reminders, add to them, search and read your mail, write drafts (he never sends mail; you press Send), search, read and add to notes, run your shortcuts and find documents in your home folder, including PDFs, Word files and spreadsheets. Each one can be switched off under `[connections]` in `~/Milo/config.toml`.
- **He asks first.** Reading and drafting just happen. Anything that goes to another person, deletes, buys or runs a shortcut waits for a yes: Milo asks in the bubble and the window with Yes and No buttons, and you can also hold the talk key and say "yes" or "no". No answer within a minute means no. Passwords, money transfers and security settings he never does. Change the levels under `[approvals.levels]`.
- **Memory.** Milo remembers what happened and what he learned about you, for years, and brings the bits that fit into each conversation. It all stays in `~/Milo/memory/` as plain files. "What Milo knows…" in the menu bar lists it, with Edit and Forget; `profile.md` shows it too, and your edits there count. At night, while you're away and the Mac is plugged in, he tidies up the day in one model call.
- **Milo looks when you ask.** "Look at my screen, what do you think?" Milo reads the window in front and takes a picture of it, then answers. An eye shows next to him while he looks. He never looks on his own.
- **What's this?** Select something and press `⌃⌥M` (or pick "What's this?" in the menu bar item). Milo explains the selection, or the whole window if nothing is selected. Change the shortcut with `[ui] whats_this_key`.
- **Milo uses the Mac for you.** "Put these numbers into the Excel sheet", "find the email from Anna and file it". The worker gets tools to read windows, press buttons, type and click. He works in the background wherever he can — pressing buttons, filling in fields and scrolling without touching your mouse or keyboard — so you can keep working on the side. His own pointer, in his colours, shows you where he's working, the window he's in gets a soft outline that says "Milo is working here", and Pip perches on its corner. Press `esc` or the Stop button to stop him. When something can only be done the old way (typing into an Excel cell, clicking a web page), he asks "Can I borrow your mouse for a moment?" first, uses it, and puts your pointer back — and while he's borrowing it, any touch stops him. A new table in Excel or Numbers, or a new text document in TextEdit or Pages, is one step that needs no question. Each action shows up as a step in the Milo window. Before he sends, deletes, buys, runs a script or replaces filled cells, he asks in the bubble, in one short sentence. No answer within a minute counts as no. He never touches password fields or password apps.
- **Routines.** After Milo did something, say "remember how to do this, call it the Monday report". A helper writes the steps down as a plain recipe, with the things that change each time (the month, a file name) as questions, and shows it in the Milo window: Save, or say what to change. Then "do the Monday report", "the Monday report for October", or "every Monday at 9". He follows the recipe, checks each step, and asks when something looks different. The recipes are Markdown files in `~/Milo/routines/` you can edit. The window's Routines section has Run now, pause and delete. `[routines]` caps scheduled runs a day and sets how late a missed run may still run.
- **Meeting notes.** When Zoom, Teams, FaceTime, a Slack huddle or Google Meet in a browser uses your microphone, Milo asks once in the bubble: "Looks like a meeting. Should I take notes?" On a yes he records you and the others as two tracks, and a red dot shows on him and in the menu bar. "Take meeting notes" in the menu starts and stops it by hand. During the call, ask him "what did Sam just say about the deadline?" or "sum up the last ten minutes". Tell him "that was Anna" and he remembers her voice for next time. After the call `~/Milo/meetings/<date-title>/` has `notes.md` (summary, decisions, to-dos) and `transcript.md` with who said what. He offers your to-dos as Reminders and a follow-up mail draft. Everything is transcribed on your Mac, the audio is deleted once the notes are written (`[meetings] keep_audio`), and if the brain or the app crashes mid-call, nothing already recorded is lost. `[meetings] auto = "calendar"` takes notes without asking during meetings in your calendar; `"off"` never asks. Recording others needs their consent in many places, Germany among them: Milo shows a line you can paste into the chat.
- **Reminders and nudges cost no tokens.** Say "remind me at 9 to call the dentist" and Milo writes a line to `~/Milo/reminders.md` (a helper asks you first). The local heartbeat fires it later without calling the LLM. Morning greetings, break nudges and "welcome back" are local rules too. Cap: `llm_calls_per_day = 0`.

## Run it

Requirements: Apple Silicon Mac, macOS 14+, [uv](https://docs.astral.sh/uv/), Swift (Command Line Tools), and a logged-in Codex CLI. Milo finds the copy bundled with ChatGPT.app on his own.

```sh
cd brain && uv sync --extra omnivoice   # ~1.4 GB of Python deps
cd .. && scripts/build-app.sh --open    # builds build/Milo.app and starts it
```

The first start downloads the Whisper (1.6 GB plus 150 MB for live words) and OmniVoice models to `~/.cache/huggingface`. Then:

1. A setup window opens on the first start and walks through **Microphone**, **Accessibility** (hotkeys, pasting, reading windows, using apps) and **Screen Recording** (looking at the screen), plus Calendars, Reminders and Mail and Notes if you want them. Each button opens the right switch in System Settings with Milo already in the list; if he isn't, drag him in from the little window next to it. If Milo shows as on but doesn't get a tick (it happens after a rebuild), press Fix it. Screen Recording needs a restart, which the window offers. Open it again any time with "Check permissions…" in the menu bar item.
   For meeting notes, macOS asks the first time Milo takes notes whether he may hear the others in the call (System Audio Recording).
2. System Settings › Keyboard › "Press 🌐 key to" › **Do Nothing**, so `fn` belongs to Milo.
3. Quit Wispr Flow if it's running. It wants `fn` too.

The first time Milo uses your calendar or reminders, macOS asks whether Milo may; the first time he uses Mail or Notes, it asks whether Milo may control them. Say OK once each. You can change it later in System Settings › Privacy & Security.

Settings live in `~/Milo/config.toml`: harness, voice, keys, heartbeat rules. The Settings window changes the common ones for you; after editing the file by hand, restart the brain from the menu bar item. Milo never overwrites `~/Milo/AGENTS.md` or `~/Milo/config.toml`, so a workspace from before gets the advice for the user's apps and for using the Mac only if you copy the "The user's apps" and "Using the Mac" sections from `brain/src/milo/workspace_template/AGENTS.md`. The tools carry the most important rules themselves. The worker runs with Milo's tools only: Codex gets a home of its own in `~/Milo/.codex` (sharing only your login), and Claude Code skips your user settings, skills and MCP servers, so your own setup doesn't reach it. Helpers work in `~/Milo/work` and can't change Milo's own files: settings, persona, instructions, reminders, routines, memory and keys ([ADR 20](docs/adr/0020-helpers-never-write-milos-control-files.md)). `[hands] enabled = false` takes the Mac tools away from the worker, and `applescript = false` turns off scripts only. Jobs on the screen take a while, so give the harness more time: `[harness.codex] timeout_s = 600`. Questions before a risky step wait `[approvals] timeout_s`; an old `[hands] confirm_timeout_s` is ignored with a warning in the log.

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

The on-screen eval runs real tasks on your real Mac with a second Milo.app: a budget table in Excel and in Numbers, filing the newest PDF from a test Downloads folder, and a Mail reply draft that it deletes again. It prints a score and the time of every step, and closes what it opened without saving. Run it only while you're not using the Mac:

```sh
cd brain && uv run python -m milo.eval.screen --only excel,numbers,file
```

## Docs

- [Architecture](docs/ARCHITECTURE.md): processes, ports and adapters, how to add an engine
- [Decisions](docs/adr/)
- [Message Milo from your phone](docs/setup/messages.md), and the [research](docs/research/messaging.md) behind it
- [The 30-task eval](docs/eval/tasks.md)
- [TODO](TODO.md)
