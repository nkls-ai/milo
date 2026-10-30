<img src="assets/icon.svg" width="64" height="64" alt="">

# Milo

A small assistant that lives in the bottom-right corner of your Mac. Hold a key and talk to him, or hold another key to dictate into any app. Speech recognition, speech synthesis and memory run on your Mac. Only the LLM turn goes out, through whichever agent CLI you configure (Codex by default, Claude Code as an alternative).

- **Dictation (Wispr Flow replacement).** Hold `fn`, speak, release. Whisper large-v3-turbo transcribes on the GPU in about 1.2 s, filler words are dropped, and the text is pasted into the focused app. Your clipboard is restored afterwards. For hands-free, double-tap `fn`: a lock shows next to Milo, tap `fn` once more to paste, `esc` to throw it away. A hands-free recording stops by itself after 5 minutes (`[ui] hands_free_max_s`).
- **Live words.** While you speak, the words appear in a small pill next to Milo. `[dictation] stream` picks how: `"preview"` (default) shows them (from the small whisper-base model, several updates a second) and pastes one final pass over the whole recording on release, `"type"` pastes each phrase into the app at the pause after it, `"off"` transcribes only on release.
- **Talk to Milo.** Hold right `⌥`, speak, release. Double-tap it for hands-free, like dictation. Milo thinks with Codex, answers in a speech bubble, and speaks with OmniVoice, sentence by sentence.
- **The Milo window.** Click Milo (or "Open conversation" in the menu bar) to read the conversation, type to him, and watch what he does when he works on something for you: "Looking in your Downloads folder", "Editing notes.md". Click a step to see the exact command. The speaker button decides whether he reads typed answers aloud. The history is kept in `~/Milo/state/transcript.jsonl`.
- **Memory.** `~/Milo/memory/` is plain Markdown that Milo reads and edits himself. Open it and fix anything he got wrong.
- **Reminders and nudges cost no tokens.** Say "remind me at 9 to call the dentist" and Milo writes a line to `~/Milo/reminders.md`. The local heartbeat fires it later without calling the LLM. Morning greetings, break nudges and "welcome back" are local rules too. Cap: `llm_calls_per_day = 0`.

## Run it

Requirements: Apple Silicon Mac, macOS 14+, [uv](https://docs.astral.sh/uv/), Swift (Command Line Tools), and a logged-in Codex CLI. Milo finds the copy bundled with ChatGPT.app on his own.

```sh
cd brain && uv sync --extra omnivoice   # ~1.4 GB of Python deps
cd .. && scripts/build-app.sh --open    # builds build/Milo.app and starts it
```

The first start downloads the Whisper (1.6 GB plus 150 MB for live words) and OmniVoice models to `~/.cache/huggingface`. Then:

1. Grant **Accessibility** (for the hotkeys and pasting) and **Microphone** when macOS asks. Ad-hoc signed builds may ask again after a rebuild.
2. System Settings › Keyboard › "Press 🌐 key to" › **Do Nothing**, so `fn` belongs to Milo.
3. Quit Wispr Flow if it's running. It wants `fn` too.

Settings live in `~/Milo/config.toml`: harness, voice, keys, heartbeat rules. Restart the brain from the menu bar item after editing.

For brain development, run it in a terminal (the app connects to it instead of starting its own):

```sh
cd brain && uv run --extra omnivoice milo
```

## Tests

```sh
cd brain && uv run pytest -q
cd app && swift test
```

## Docs

- [Architecture](docs/ARCHITECTURE.md): processes, ports and adapters, how to add an engine
- [Decisions](docs/adr/)
- [TODO](TODO.md)
