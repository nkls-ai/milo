# Milo architecture

Milo is two processes on one Mac:

- **The app** (`app/`, Swift). The floating character, speech bubble, push-to-talk keys, pasting dictated text into the focused app, the Milo window with the conversation, and the menu bar item. It knows nothing about models.
- **The brain** (`brain/`, Python, run with `uv`). Microphone, speech-to-text, the live chat model, the agent harness, text-to-speech, memory and the heartbeat.

They talk over a Unix socket at `~/Milo/run/brain.sock` (mode 0600) using JSON objects, one per line. Every message is listed in [`protocol/messages.json`](../protocol/messages.json) and defined in `brain/src/milo/core/events.py`. Both test suites decode that file, so the two sides can't drift apart silently.

`~/Milo/` is the workspace. It holds `config.toml`, Milo's persona for the chat model (`persona.md`), the agent's instructions (`AGENTS.md`, `CLAUDE.md`), `memory/`, `reminders.md`, `state/` and `logs/`. The harness runs with this folder as its working directory, so the agent reads and edits its own memory with ordinary file tools.

## Brain layout

```
brain/src/milo/
  core/           types, ports (Protocols), wire events, registries, clock. Depends on nothing.
  adapters/       concrete engines, each registering itself by name
    harness/      codex, claude (agent harnesses), claude_live (the streaming chat model)
    stt/          mlx_whisper
    tts/          omnivoice, say
    audio/        sounddevice (mic in, speaker out)
    text/         fillers, plain (dictation cleanup)
  memory/         Workspace paths and bootstrap, profile.md, reminders.md, usage ledger, dictation history,
                  transcript (the Milo window's conversation)
  proactive/      heartbeat engine, daily LLM budget, rules (one class per rule, registered by name)
  services/       use cases built only on ports: listening (push-to-talk, barge-in), dictation,
                  live_transcript (pause segmenter and partial passes while recording),
                  live_talk (user turns on the chat model), reply_stream (tags out of the reply stream),
                  chunker + speaker (streaming TTS), task_runner + conversation (delegated work on the
                  harness), transcript (what the Milo window shows), heartbeat_runner, plus small shared pieces: ui_state, context (latest app/idle
                  report), levels (throttled meters), quiet (wait for a turn to end), fallback_voice
  transport/      Unix socket JSONL server (an EventSink)
  brain.py        routes inbound commands to services
  config.py       reads config.toml into sections
  compose.py      composition root: the only module that names concrete classes
  server.py       main()
```

Rules that keep the parts swappable:

1. **Services depend on ports, never on adapters.** `services/` imports from `milo.core` only. A service gets every collaborator through its constructor.
2. **Adapters register themselves.** `@HARNESSES.register("codex")` sits next to the class. `milo.adapters.load_builtin()` imports the built-in modules. Adding an engine means adding a module, without editing any switch statement.
3. **Config picks by name.** Every swappable section has `use = "<name>"` and a table `[<section>.<name>]` holding that implementation's options. An adapter parses its own table with `options_from(OptionsDataclass, table, "section.name")`, which rejects unknown keys.
4. **Only `compose.py` wires concrete things.** Tests wire fakes from `tests/fakes.py` instead.
5. **Blocking work runs on dedicated single-thread executors.** STT gets one thread and TTS another, so MLX and PyTorch each stay on their own thread and the event loop never blocks.

## Cross-module interfaces

Beyond `milo.core.ports`, these entry points are fixed:

| Function / class | Owner | Contract |
|---|---|---|
| `milo.adapters.load_builtin() -> None` | adapters | Imports every built-in adapter module so it registers. Idempotent. Heavy imports (torch, mlx) stay inside methods, never at module import. |
| `milo.memory.workspace.Workspace(home)` | memory | `.ensure()` copies the template without overwriting, and creates dirs. Path properties: `config_path`, `reminders_path`, `profile_path`, `persona_path`, `state_dir`, `log_dir`, `socket_path`, `usage_path`, `dictation_history_path`, `transcript_path`, `heartbeat_state_path`. |
| `milo.memory.reminders.MarkdownReminders(path)` | memory | `ReminderBook`. Re-parses only when mtime changes. `add(due, text)` appends a line. Shared by the heartbeat and LiveTalk. |
| `milo.memory.profile.MarkdownProfile(path)` | memory | `ProfileMemory` over `memory/profile.md`. |
| `milo.memory.ledger.JsonlUsageLedger(path, clock)` | memory | `UsageLedger`. Appends one JSON line per harness call. |
| `milo.memory.history.JsonlDictationHistory(path, clock)` | memory | `DictationHistory`. |
| `milo.memory.transcript.JsonlTranscript(path)` | memory | `TranscriptStore` over `state/transcript.jsonl`. `tail(n)` reads the file backwards block by block, so its cost doesn't grow with the file. |
| `milo.proactive.build_engine(section, ctx, reminders) -> ProactiveEngine` | proactive | `section` is the whole `[heartbeat]` table including sub-tables. Ignores `enabled` (compose.py decides whether to run it). |

## A user turn

Typed and spoken turns take the same path through `LiveTalk`:

1. **Chat model.** `[chat] use = "claude_live"` keeps one `claude -p --input-format stream-json` process running with no tools. Its system prompt is `persona.md`, the reply rules, `memory/profile.md` and the open reminders. The conversation stays open between turns. After `[chat] conversation_idle_reset_s` (600 s) of silence the next turn starts a fresh one, which also reloads the persona and profile. At boot `server.py` warms it, so the first turn skips the process start.
2. **Reply stream.** Each user message is prefixed with `[weekday date time, frontmost app: X]`. The model starts its reply with an emotion tag such as `[happy]` and may add `<remember>fact</remember>`, `<reminder>YYYY-MM-DD HH:MM text</reminder>` and `<task>description</task>`. `ReplyParser` reads the text deltas as they arrive, sets the face once the emotion is known, holds back anything that could still turn into a tag, and passes the rest on as speech. When the stream ends, LiveTalk saves facts to the profile and reminders to `reminders.md`, and hands tasks to the `TaskRunner`.
3. **Speech.** `SpeechChunker` releases the first chunk at the first clause with three or more words (or after eight words), then one chunk per sentence, never more than 220 characters. A `Speaker.utterance` has one worker: it synthesizes chunks in order on the TTS thread and feeds each one to a single open `AudioOutput` stream as soon as it is ready. Feeding doesn't block, so chunk N+1 synthesizes while chunk N plays and the chunks play back to back. The bubble grows as each chunk is fed. If synthesis fails, the text still shows and silence of about the right length plays.
4. **Barge-in.** Pressing the talk key while Milo thinks or speaks calls `LiveTalk.interrupt()`: it cancels the turn, interrupts the model and the audio stream, and the mic opens straight away. A new typed turn does the same. Side effects of an interrupted reply are dropped.

## Delegated tasks

The chat model has no tools. Work that needs files, research or several steps comes out of a reply as a `<task>`. `TaskRunner` runs tasks one at a time in the background on the agent harness (`[harness]`, Codex by default) through `Conversation`, which resumes one harness session so the agent keeps context across tasks. The agent works in its `~/Milo` sandbox under `AGENTS.md`. When it finishes, Milo speaks its `say`, and the next chat message carries the result so the chat model knows about it. A result that finishes during a live turn waits up to 30 s for the turn to end, then shows silently. Heartbeat nudges wait the same way, and a silent bubble never cuts off speech.

## The Milo window

The window shows the conversation as text and lets the user type to Milo. Clicking the character or "Open conversation" in the menu bar item opens it; a second click or the close button hides it. macOS keeps its frame.

- **Transcript.** `services/transcript.py` keeps the last 50 entries in memory: user turns (`via` voice or typed), Milo's replies and tasks with their steps. LiveTalk adds the user turn and streams the reply into it (`entry`, then `reply_delta` events, then the finished `entry`). TaskRunner adds a task entry and its steps (`activity` events). Finished entries are appended to `state/transcript.jsonl`. At the first need after a start the brain reads the last 50 lines from the end of that file, never the whole file.
- **History.** The brain sends `history` with those entries when the app connects and when the window opens (`get_history`). Both read memory only and call no model.
- **Activity.** `Harness.reply` takes an optional `on_step` callback. The worker adapters read the CLI's stdout line by line while it runs: `codex exec --json` reports `item.started`/`item.completed` for `command_execution`, `file_change`, `mcp_tool_call` and `web_search` (reasoning, messages and todo lists are skipped), and `claude -p --output-format stream-json --verbose` reports `tool_use` blocks with their `tool_result`. `adapters/harness/_activity.py` turns each into a `Step` with a plain title ("Reading your Downloads folder", "Opening Microsoft Excel", "Searching the web for ...") and keeps the raw command or tool payload as `detail`, shown only when the row is expanded. Callers without a callback get the same `Reply` as before.
- **Typing.** The text field sends `text`. The window's "speak replies" toggle (off by default, kept in UserDefaults) adds `"speak": false`, and Milo then answers in the bubble and the window without audio.

## Heartbeat cost model

The heartbeat must not burn tokens. One tick does a `stat()` on `reminders.md`, runs the enabled rules in memory and writes `state/heartbeat.json`. That's zero harness calls. A rule can attach an `llm_prompt` asking for nicer wording, but the runner uses it only if `LlmBudget.allow(today)` is true. The default `llm_calls_per_day = 0` means it never is. `tests/proactive` simulates a full day of ticks and asserts zero calls.

A chat turn costs one message to the running chat model: about 600 tokens, with the first text after 1 to 2 s. A delegated task costs one harness call. Measured with `codex exec` on 2026-10-29: about 19k input tokens for a plain reply (mostly cached on resume) and about 62k when the agent edits memory files. That takes 5 to 10 s. The usage ledger labels these `chat`, `task` and `proactive`. See [ADR 5](adr/0005-live-chat.md).

## App layout

```
app/
  Sources/MiloKit/   protocols, wire types, controller, hotkey state machine, views (all testable).
                     The Milo window: TranscriptModel, Views/ConversationView + ActivityView,
                     AppKit/ConversationWindow
  Sources/Milo/      main.swift: builds concrete adapters, hands them to MiloController
  Tests/MiloKitTests Swift Testing; decodes protocol/messages.json, drives the controller with fakes.
                     MILO_RENDER_DIR=/tmp/milo-render swift test --filter ConversationRender renders the
                     window offscreen into PNGs
```
