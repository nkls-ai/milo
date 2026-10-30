# Milo architecture

Milo is two processes on one Mac:

- **The app** (`app/`, Swift). The floating character, speech bubble, push-to-talk keys, pasting dictated text into the focused app, the Milo window with the conversation, and the menu bar item. It holds the Accessibility and Screen Recording permissions, so it also reads windows, takes screenshots and runs the worker's actions on the Mac. It knows nothing about models.
- **The brain** (`brain/`, Python, run with `uv`). Microphone, speech-to-text, the live chat model, the agent harness, text-to-speech, memory and the heartbeat.

They talk over a Unix socket at `~/Milo/run/brain.sock` (mode 0600) using JSON objects, one per line. Every message is listed in [`protocol/messages.json`](../protocol/messages.json) and defined in `brain/src/milo/core/events.py`. Both test suites decode that file, so the two sides can't drift apart silently.

Only one brain runs per workspace. It takes an `flock` on `~/Milo/run/brain.lock` before it loads anything and holds it until the process ends, and a second brain exits at once. The app starts a brain only while nobody holds that lock: after a restart it waits for the old brain to let go, and it leaves a brain started by hand alone. It stops its brain with SIGTERM, since `uv run` passes that on and swallows SIGINT. Two brains would each load Whisper and OmniVoice, which on 16 GB fills swap and makes every Whisper pass several times slower.

`~/Milo/` is the workspace. It holds `config.toml`, Milo's persona for the chat model (`persona.md`), the agent's instructions (`AGENTS.md`, `CLAUDE.md`), `memory/`, `reminders.md`, `state/` and `logs/`. The harness runs with this folder as its working directory, so the agent reads and edits its own memory with ordinary file tools.

## Brain layout

```
brain/src/milo/
  core/           types, ports (Protocols), wire events, registries, clock, hands (the milo-mac tools and
                  their schemas), wording (plain titles and questions for app actions), logtext (what the log
                  may say). Depends on nothing.
  adapters/       concrete engines, each registering itself by name
    harness/      codex, claude (agent harnesses), claude_live (the streaming chat model)
    stt/          mlx_whisper
    tts/          omnivoice, say
    audio/        sounddevice (mic in, speaker out), wav (a real-time virtual sound card that writes WAV files,
                  and a WAV file as the mic, for timing tests and voice comparisons without the speakers)
    text/         fillers, plain (dictation cleanup)
    connect/      mac (Calendar and Reminders through the app, Mail and Notes through AppleScript,
                  Shortcuts, Spotlight files), fake (a made-up world in ~/Milo/fake)
    headless/     none: no microphone, no voice, no speaker, for tests and the eval
    embed/        mlx_e5 (multilingual-e5-small in MLX), hash (hashed words, no model; tests and CI)
  connect/        the MCP tool server the worker loads (python -m milo.connect)
  eval/           the 30-task eval (python -m milo.eval) and the on-screen eval (python -m milo.eval.screen)
  memory/         Workspace paths and bootstrap, profile.md, reminders.md, usage ledger, dictation history,
                  transcript (the Milo window's conversation), and long-term memory: episodes and facts
                  (append-only JSONL), fact_profile (profile.md as a view of the facts), index (FTS5 and
                  vectors in state/memory.sqlite), recall, when (time phrases), consolidate (the night),
                  recall_eval
  proactive/      heartbeat engine, daily LLM budget, rules (one class per rule, registered by name)
  services/       use cases built only on ports: listening (push-to-talk, barge-in), dictation,
                  live_transcript (pause segmenter, phrases committed while recording, live words),
                  live_talk (user turns on the chat model), reply_stream (tags out of the reply stream),
                  chunker + speaker + speech_audio (streaming TTS), echo + barge_in (talking over Milo),
                  backchannel ("Hm." when a reply is late), orchestrator + helpers + task_runner (helpers doing
                  delegated work on the harness, see ADR 11), updates (milestones and `[chat] updates`),
                  conversation (one resumed harness session, for the heartbeat), transcript (what the Milo window shows), heartbeat_runner, approvals
                  (action levels and yes-or-no questions), app_bridge (requests to the app and their answers:
                  AppEyes, AppHands, Calendar and Reminders work), tool_requests (what the tool socket may do),
                  screen (screen data for the chat model), hands + risk (checking and logging the worker's Mac
                  actions), sheets + documents (the AppleScript behind sheet_write and write_document), memory (recall for each turn, search, forget, edit), episode_stubs (episodes
                  of turns, tasks, looks and dictations), memory_requests (the worker's memory tools), sleep
                  (when the night's consolidation runs), plus small shared pieces: ui_state, context (latest app/idle report), levels
                  (throttled meters), quiet (wait for a turn to end), fallback_voice
  transport/      Unix socket JSONL servers: brain.sock (an EventSink), hands.sock, and the tool socket and its
                  client
  mcp_server.py   the milo-mac MCP stdio server the worker CLI starts; forwards calls to hands.sock
  brain.py        routes inbound commands to services
  config.py       reads config.toml into sections
  config_edit.py  changes one setting in config.toml in place (the menu's dictation style)
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
| `milo.memory.workspace.Workspace(home)` | memory | `.ensure()` copies the template without overwriting, and creates dirs. Path properties: `config_path`, `reminders_path`, `profile_path`, `persona_path`, `state_dir`, `log_dir`, `socket_path`, `lock_path`, `usage_path`, `dictation_history_path`, `transcript_path`, `heartbeat_state_path`, `hands_socket_path`, `screens_dir`, `tools_socket_path`, and for memory `episodes_dir`, `facts_path`, `journal_dir`, `memory_index_path`, `profile_snapshot_path`, `sleep_state_path`. |
| `milo.memory.reminders.MarkdownReminders(path)` | memory | `ReminderBook`. Re-parses only when mtime changes. `add(due, text)` appends a line. Shared by the heartbeat and LiveTalk. |
| `milo.memory.profile.MarkdownProfile(path)` | memory | `ProfileMemory` over `memory/profile.md`. Used only with `[memory] enabled = false`. |
| `milo.memory.fact_profile.FactProfile(facts, path, snapshot, clock)` | memory | `ProfileMemory` as a view of the `FactStore`: `read()` renders facts, `remember()` adds one, the user's edits to `profile.md` become fact changes. `migrate()` turns an old `profile.md` into facts once. |
| `milo.memory.index.SqliteMemoryIndex(path, embedder, facts, episodes)` | memory | `MemoryIndex` over `state/memory.sqlite`, a cache of the logs. `refresh(limit)` catches up with lines written since. |
| `milo.memory.recall.HybridRecaller(index, facts, tuning)` | memory | `Recaller`. `render(recall, now)` makes the `<memory>` block. |
| `milo.services.memory.Memory` / `TurnMemory` | services | The brain's memory: recall on the memory thread with a 300 ms limit, search, forget, edit, the `facts` event. `TurnMemory.before_turn()` is the live chat's hook. |
| `milo.memory.ledger.JsonlUsageLedger(path, clock)` | memory | `UsageLedger`. Appends one JSON line per harness call. |
| `milo.memory.history.JsonlDictationHistory(path, clock)` | memory | `DictationHistory`. |
| `milo.memory.transcript.JsonlTranscript(path)` | memory | `TranscriptStore` over `state/transcript.jsonl`. `tail(n)` reads the file backwards block by block, so its cost doesn't grow with the file. |
| `milo.services.approvals.Approvals` | services | `approve(kind, summary) -> Decision` applies the action level and asks if needed. `confirm(summary) -> bool` always asks (the `Confirmer` port). |
| `milo.transport.tool_client.BrainClient(path)` | transport | `request(body) -> dict` on `run/tools.sock`; `approve(kind, summary) -> Decision`. Used by the MCP server, and by any helper process that needs a yes. |
| `milo.proactive.build_engine(section, ctx, reminders) -> ProactiveEngine` | proactive | `section` is the whole `[heartbeat]` table including sub-tables. Ignores `enabled` (compose.py decides whether to run it). |

## Listening

Both keys listen the same way (`services/listening.py`, `services/live_transcript.py`). Only what happens to the text differs: dictation pastes it, talk hands it to `LiveTalk`.

1. **Phrases.** While the key is held, `LiveTranscript` reads the new audio every 0.1 s and `PauseSegmenter` cuts it into phrases at pauses: 0.7 s of quiet, or 0.3 s once a phrase has run 6 s, or the quietest frame once it reaches 12 s.
2. **Commits.** Each closed phrase is transcribed by the full model (large-v3-turbo, full 30 s window) while the user goes on talking. That text is final. `stream = "type"` pastes it at once. The text before a phrase only keeps its language (a short "okay" can't be detected reliably); it is not put in Whisper's prompt, which made more errors on test dictations because Whisper copies the prompt's style.
3. **Guess.** When the open phrase has been quiet for 0.25 s, the full model transcribes it as it stands, in a quick pass (below). If the user speaks again, the guess is dropped. If they let go first, the guess is the last phrase and the release costs no pass at all. A pause that closes the phrase still gets its full commit.
4. **Preview.** Otherwise the small model (whisper-base) re-reads the open phrase for the live words above Milo (`partial`). Commits and guesses always go first, so at most one preview pass (about 0.05 s) runs ahead of the full model.
5. **Release.** `finish()` interrupts a commit or preview in flight (`Transcriber.interrupt()`: the Whisper encoder runs four layers at a time and checks between them), lets a guess finish, then does whatever is left in quick passes: phrases still waiting and the open phrase unless a guess covers it.

All passes run one at a time on the STT thread. A quick pass encodes the audio plus 1 s of silence, but at least 10 s, instead of a padded 30 s window, so it costs roughly its own length (0.3 s for a short phrase on an idle M3 against 1.1 s). With less than 10 s the decoder loses track of where speech ends and repeats itself; a quick decode that loops, runs past 8 tokens a second or that Whisper itself doubts goes through the full window instead. Quick passes miss a few more words (on 48 test phrases 2.7% against 1.7%), which is why only the last phrase of a recording normally gets one. `stream = "off"` runs no live passes and transcribes the whole recording on release with full windows.

The menu bar item's "Dictation style" sends `set_dictation_stream`; the brain uses it from the next recording, writes `[dictation] stream` into `config.toml` in place (`config_edit.py`, comments kept) and answers `dictation_stream`, which it also sends on connect.

## A user turn

Typed and spoken turns take the same path through `LiveTalk`:

1. **Chat model.** `[chat] use = "claude_live"` keeps one `claude -p --input-format stream-json` process running with no tools. Its system prompt is `persona.md`, the reply rules, the memory rules, the always-on facts (the basics and pinned ones) and the open reminders. Each turn then carries a `<memory>` block in front of the user's words: what `TurnMemory.before_turn()` recalled for it (see Memory below). The conversation stays open between turns. After `[chat] conversation_idle_reset_s` (600 s) of silence the next turn starts a fresh one, which also reloads the persona and profile. At boot `server.py` warms it, so the first turn skips the process start. A fresh process also gets one throwaway priming turn in the background, because the first real turn on a new process takes 2 to 3 s to its first word and the second about 0.5 to 1 s. And the talk key going down starts a due fresh conversation (`LiveTalk.prepare()`), so the start hides behind the user's own words.
2. **Reply stream.** Each user message is prefixed with `[weekday date time, frontmost app: X]`. The model starts its reply with an emotion tag such as `[happy]` and may add `<remember>fact</remember>`, `<reminder>YYYY-MM-DD HH:MM text</reminder>`, `<task title="..." screen="yes|no">description</task>`, `<steer helper="2">change</steer>` and `<stop helper="2"/>`. `ReplyParser` reads the text deltas as they arrive, sets the face once the emotion is known, holds back anything that could still turn into a tag, and passes the rest on as speech. When the stream ends, LiveTalk saves facts to the profile and reminders to `reminders.md`, and hands tasks, steers and stops to the `Orchestrator`.
3. **Speech.** A `Speaker.utterance` has one worker. It asks `SpeechChunker` for the next piece, synthesizes it on the TTS thread and feeds it to a single open `AudioOutput` stream. Feeding doesn't block, so the next piece synthesizes while this one plays. The first piece ends at the first clause or sentence end with five or more words (or after twelve words), so Milo starts talking early but leaves the next piece time to get ready. Every later piece gets a budget: the characters the voice can synthesize while the queued audio plays, from `SynthesisPace`, a least-squares fit of a fixed cost per call plus a cost per character over the last pieces. The piece ends at the furthest sentence or clause boundary within the budget (a boundary up to 40% past it beats a cut mid-clause), never under 45 characters, because OmniVoice re-reads its 2 s voice reference on every call and shorter pieces synthesize slower than they play. With no boundary in reach it waits for the next one, up to 220 characters, rather than cut a clause in two. Each piece is trimmed to its speech and levelled to the same loudness (`speech_audio.py`): OmniVoice pads every call with about 200 ms of silence at each end and its loudness wanders by 8 dB. The pause before the next piece then follows the punctuation: 300 ms after a full stop, 160 ms after a comma, 40 ms mid-clause, and time spent waiting for a late piece counts towards it. A gap beyond the intended pause is logged as `speech gap`, and each reply's first sound as `first sound`. After the last piece a quarter second of silence and the device's own output latency play out before the stream closes, so a Bluetooth headset doesn't lose the last syllable. On Apple GPUs OmniVoice decodes its audio tokens on the GPU in 40-frame windows with 12 frames of context; one long call gives wrong audio there past 65,536 samples, and the windows match the CPU to -110 dB at twice the speed. The decoder checks itself against the CPU at warm-up and stays on the CPU if they differ. The bubble grows as each piece is fed. If synthesis fails, the text still shows and silence of about the right length plays. Barge-in calls `Voice.cancel()`, which OmniVoice honours between diffusion steps, so the TTS thread is free for the next reply within a fraction of a second.
4. **Barge-in.** Pressing the talk key while Milo thinks or speaks calls `LiveTalk.hold()`: the audio stops at once and the mic opens, but the reply keeps its place and the model keeps writing. If the user says something, `LiveTalk.interrupt()` cancels the turn and the model, and their words start the next one; side effects of the dropped reply are dropped too. If they say nothing (or the key was cancelled, as when right ⌥ types @ on a German keyboard), `resume()` goes on from the start of the sentence or clause that was cut off. A hold ends by itself after 330 s. A new typed turn interrupts at once.
   With `[chat] voice_barge_in = true` the user can also just talk over Milo. While he speaks, `BargeIn` opens the mic and lines each 16 ms block up with what the speakers played at that moment: the output says what it played and when (`PlaybackTap`) and the mic says when it heard. `EchoCanceller` (a frequency-domain NLMS filter, 128 ms long) takes Milo's echo out, and `TalkDetector` calls it the user once what is left is speech, above the room's noise floor and above the echo the canceller usually leaves, for 144 ms. Until the canceller has learned the room, the user has to be louder than Milo in the mic. Then the turn holds, the mic records until a pause, and Whisper transcribes the echo-free audio. Real words start a turn; nothing, or a transcript of Milo's own words, resumes him. The talk key always takes over. It is off by default because it hasn't been tried with real speakers and a real room yet: on Milo's real renders through simulated rooms it hears the user 114 to 136 ms after they start (274 ms for a short "Stop.") and false-triggers up to 3 times in 72 s at the loudest echo.
5. **Backchannels.** If no sound has gone out 2 s into a reply and its first piece isn't about to be ready, Milo says "Hm.", "Mm.", "Hmm." or "One sec." on the reply's own stream, ahead of the answer. The clips are rendered once at warm-up in his voice. One per reply, none within 30 s of the last, never the same twice in a row, never while held. `[chat] backchannels = false` turns them off.

## Memory

Milo remembers episodes (what happened) and facts (what is true about the user) for years. See the [design](design/memory.md) and [ADR 15](adr/0015-memory-files-and-a-rebuildable-index.md).

- **Files.** `memory/episodes/YYYY-MM.jsonl` and `memory/facts.jsonl` are append-only logs and the only truth. `memory/profile.md` is written from the facts; the user may edit it. `state/memory.sqlite` is a search index that rebuilds itself from the logs.
- **During the day.** `EpisodeTranscript` (around the transcript store) makes an episode of each user turn with Milo's answer and of each task; `EpisodeEyes` of each look; `EpisodeDictations` of dictations if `[memory] dictations` is on. `<remember>` and the worker's `memory_remember` add facts. The index catches up on the memory thread in batches.
- **Each turn.** The recall runs hybrid search (FTS5 words, with German and English words for each other, and e5 vectors, merged by reciprocal rank fusion), boosts recent episodes, the current app and named people, adds the episodes of a time phrase ("yesterday", "letzte Woche"), and fits the result into `[memory] recall_tokens` (800). Outside episodes come marked as data and taint the conversation (ADR 10). No model call.
- **At night.** `SleepRunner` consolidates each finished day with one worker call: better summaries, new, changed and retired facts, and a journal section. Every change is a log line; `python -m milo.memory.consolidate --undo <run>` takes a night back.
- **The user's view.** "What Milo knows…" in the menu bar lists the facts by topic with Edit and Forget. The worker has `memory_search`, `memory_remember` and `memory_forget` in the `milo` MCP server; the latter two ask the user first.

## Helpers

The chat model, the talker, has no tools and never waits for work. Work that needs files, research, the user's apps or the screen comes out of a reply as a `<task>`, and `services/orchestrator.py` hands it to a helper: one run of the agent harness (`[harness]`, Codex by default) in its own process and its own session, working in the `~/Milo` sandbox under `AGENTS.md`. See [ADR 11](adr/0011-helpers-and-the-orchestrator.md).

- **At once and in turn.** Up to `[harness] max_helpers` (3) helpers work at the same time; more wait as queued. Helpers with `screen="yes"` take turns on the screen harness (with the milo-mac tools). The rest run on a second harness instance without them. A background helper that answers `NEEDS_SCREEN` is queued again for the screen.
- **Milo's tools only.** Both harness instances run without the user's own setup: Codex in a home of Milo's own (`~/Milo/.codex`, rewritten before every turn, the login linked from the user's), Claude Code without user settings, skills and other MCP servers. See [ADR 13](adr/0013-a-worker-with-milos-tools-only.md).
- **The board.** Before every user message the talker gets a `<helpers>` block from `services/helpers.py`: status, time, step count and the last steps in plain kind words and installed app names, never file names, commands or page text. So it can answer "how far are you?" without the conversation counting as tainted.
- **Steer and stop.** `<steer>` stops the helper's turn and resumes its session with the change; without a session the task starts over with the change written in. `<stop>`, or `stop_helper` from the Stop button in the Milo window, kills the worker's whole process tree. A steer asks first once the conversation is tainted, a stop never does.
- **Careful helpers.** A task the user asks for in a conversation that has seen the screen starts at once, but its helper runs careful (`Helper.careful`): Approvals asks before its `change` actions too, and HandsService asks once per app before the first change there. The flag is per helper: `TaskRunner` passes it to `hands.begin`, and `HelperQuestions` passes it to `Approvals.approve` for the connection tools (any careful helper at work counts when the tool socket can't tell which one asks). A task or steer the chat model starts on its own in reply to screen data or after reading untrusted text asks first, in one sentence of at most 80 characters (`live_talk.task_question`); the whole task shows under it in the Milo window. See [ADR 14](adr/0014-scripts-milo-writes-and-short-questions.md).
- **Updates.** `services/updates.py` finds milestones with rules over step kinds and titles and tells the user as `[chat] updates` says: `quiet`, `bubble` (a short note) or `chatty` (the talker says it, at most every 45 s). `LiveSettings` re-reads `config.toml` when it changed, at most every 2 s, so `updates` and `max_helpers` apply without a restart.
- **Results.** When a helper finishes, Milo speaks its `say` and the next chat message carries the result. A result that finishes during a live turn waits up to 30 s for the turn to end, then shows silently. Heartbeat nudges wait the same way, and a silent bubble never cuts off speech.
- **The app.** The `helpers` event lists every active helper and, for 8 s, the ones that just ended (step changes coalesced to every 0.25 s). The overlay shows a small bird per helper next to Milo, the Milo window a list with steps and Stop.

Task results reach the chat model as `<task_result>` blocks with `<` and `>` escaped, and the reply rules say they are data. Once a result is in the conversation, LiveTalk asks before it acts on any later tag in it, until the conversation resets. See [ADR 10](adr/0010-untrusted-results-and-a-private-log.md).

## Looking and computer use

See [ADR 6](adr/0006-looking-at-the-screen.md) and [ADR 7](adr/0007-computer-use-through-the-brain.md).

- **Looking.** The chat model writes `<look/>` when it needs to see the screen. LiveTalk asks through the `ScreenEyes` port (`AppEyes` sends `look_request`), the app answers `look_result` with the front window's text and a screenshot path, and LiveTalk sends both to the model as a second message with an image block. `looking` turns the eye badge next to Milo on and off. "What's this?" (the shortcut or the menu item) sends `whats_this` with a capture, and the brain starts a turn with it. Screen text sits between `<screen_data>` markers (`services/screen.py`), and a task from a conversation that has seen it runs careful (see Delegated tasks).
- **Computer use.** Workers get the milo-mac tools (`core/hands.py`) through `AdapterContext.mac_tools`, which compose.py fills when `[hands] enabled`. Codex and Claude start `python -m milo.mcp_server`, next to the app connections server, and it sends each call to `~/Milo/run/hands.sock`. `HandsService` validates it, asks the app to describe the target, classifies it with `services/risk.py`, asks through the `Confirmer` port (`Approvals`, see below) when needed, logs a step, and then has the app run it (`hands_request`, `hands_result`). It only answers while a screen helper runs, and only one does at a time.
- **Background delivery.** `MacHands` works on apps without the real cursor or keyboard where macOS allows it, deciding the route per app family with the pure planner `Screen/Delivery`: `AXPress` for buttons, `AXFocused` plus a caret for a click into a field, `AXSelectedText` (read back) for typing, `AXShowMenu` for a right-click, the scroll bar's value for scrolling. What can't be done that way (a plain keystroke, a double-click, web content, Office documents) returns `HandsFailure(borrow:)`; `HandsService` asks "Can I borrow your mouse for a moment?" through the `Confirmer`, and on a yes sends `hands_borrow`. The app lends that one device on a 15 s sliding clock and warps the real pointer back afterwards. See [ADR 12](adr/0012-background-delivery.md).
- **Scripts Milo writes.** `sheet_write`, `sheet_read` (Excel, Numbers), `write_document` (TextEdit, Pages) and `ax_find` are composed in the brain: `services/sheets.py` and `services/documents.py` turn plain arguments into AppleScript with every value as an escaped literal, and run it through the app's `run_applescript` action, which works in the background. They need no question unless `sheet_write` would replace filled cells. The tool descriptions put them first, then `run_applescript` (always asks), then the accessibility tree, then screenshots. See [ADR 14](adr/0014-scripts-milo-writes-and-short-questions.md).
- **On screen.** Milo's own lavender cursor (`AppKit/CursorOverlay`, a click-through overlay, never the system cursor) glides to each spot before the action, ripples on a click and shows a caret while typing. The window he works in gets a soft outline with a "Milo is working here" tag and a Stop button (`AppKit/WorkingOutline`, `MiloModel.workingWindow`), followed by `Adapters/MacWindowWatcher`. Pip perches on its corner (`FlightDriver`). The whole-screen frame (`AppKit/WorkingFrame`) shows only while the real mouse or keyboard are borrowed. `describe` returns the target's `window` and `pid` for the outline.
- **Stopping.** `Screen/ScreenController` watches real input during a session through `UserInputSource`. `TakeoverDetector` is pure and has two modes: in `background` the user's own mouse and keyboard never stop Milo (that's the point), only `esc` or the Stop button does; while a device is `borrowed` any real touch stops him, as before. Input doesn't count while a question waits (`confirm` until `confirm_done`). On a stop the app sends `hands_stop` and the brain fails every later call in that task.

## App connections

The worker reaches the user's apps through one MCP stdio server, `python -m milo.connect`, which `compose.py` passes to the harness as a `ToolServer`: Claude Code gets `--mcp-config state/mcp-servers.json --strict-mcp-config --allowedTools mcp__milo-mac mcp__milo` (milo-mac only when `[hands] enabled`), Codex gets `-c mcp_servers.milo.*` and `-c mcp_servers.milo-mac.*`. The server's 20 tools sit on the connection ports in `milo.core.ports` (`Calendar`, `Reminders`, `Mail`, `Notes`, `Shortcuts`, `Files`). `[connections] use` picks the adapter set (`CONNECTIONS` registry): `mac` or `fake`. Each connection has its own switch.

```
worker CLI ──stdio──▶ milo.connect ──run/tools.sock──▶ brain ──brain.sock──▶ Milo.app (EventKit)
                         │                               │
                         ├─ AppleScript (Mail, Notes)    └─ Approvals: bubble, window, voice
                         ├─ shortcuts CLI
                         └─ mdfind, textutil, PDFKit
```

- **Before any change** the server asks the brain over `run/tools.sock` (0600, peer UID checked, one JSON object per line, `id` echoed): `{"op": "approve", "kind": "send", "summary": "Write a draft to Anna?"}` returns `{"ok": true, "result": {"allowed": true, "level": "ask_first", "answer": "yes"}}`. `{"op": "confirm", "summary": ...}` returns `{"result": {"yes": bool}}`. If the brain can't be reached, reads go ahead and everything else is refused.
- **Calendar and Reminders** run in the app: `{"op": "app", "name": "calendar.add_event", "args": {...}}` on the tool socket. The brain checks the connection switch, asks if the level says so, then sends `app_request` to the app and waits up to 90 s for `app_response`. Ops: `calendar.events` (start, end, query), `calendar.add_event` (title, start, end, location, notes, calendar), `reminders.list` (query, include_done), `reminders.add` (title, due, notes, list), `reminders.complete` (id). Times are local, `2026-11-05T15:00`.
- **Kinds.** Reading is `read`, a mail draft is `draft`, passing an email on is `share`, a new event, reminder or note is `change`, running a shortcut is `shortcut`. See [ADR 8](adr/0008-app-connections-as-an-mcp-server.md) and [ADR 9](adr/0009-approvals-and-action-levels.md).
- **Unknown arguments** are refused, and a tool whose question needs facts (whose email is being passed on) looks them up with a read before asking.
- **Step titles** for the window come from `milo.core.wording.title(tool, args)`, so a task shows "Looking in your calendar" and not `mcp__milo__calendar_events`.

## Approvals

`Approvals` owns the one open question. `approve(kind, summary)` looks up the level in `[approvals.levels]`: `read` and `change` go ahead, `never` is refused, `ask_first` asks. Asking sends `confirm` (the bubble and the window show Yes and No), speaks the question unless a turn is running, and waits for `confirm_answer`, a short spoken or typed yes or no while the bubble still shows the question, or `[approvals] timeout_s`, which counts as no. `confirm_done` tells the app it is over. Computer use asks through the same flow with `confirm(summary)`; its own classifier decides when, so the levels don't loosen it. `approve(kind, summary, careful=True)`, for a careful helper (see Delegated tasks), asks before `change` actions as well.

## Logs

`logs/brain.log` rotates at `[logging] max_mb` and keeps `keep` old files. It holds sizes and timings, never what the user said, Milo's replies or file contents: services log `milo.core.logtext.private(text)`, which is `<42 chars>` unless `[logging] content = true`. `logs/connect.log` is the MCP server's.

## The Milo window

The window shows the conversation as text and lets the user type to Milo. Clicking the character or "Open conversation" in the menu bar item opens it; a second click or the close button hides it. macOS keeps its frame.

- **Transcript.** `services/transcript.py` keeps the last 50 entries in memory: user turns (`via` voice or typed), Milo's replies and tasks with their steps. LiveTalk adds the user turn and streams the reply into it (`entry`, then `reply_delta` events, then the finished `entry`). The orchestrator adds an entry per helper and its steps (`activity` events). Finished entries are appended to `state/transcript.jsonl`. At the first need after a start the brain reads the last 50 lines from the end of that file, never the whole file.
- **History.** The brain sends `history` with those entries when the app connects and when the window opens (`get_history`). Both read memory only and call no model.
- **Activity.** `Harness.reply` takes an optional `on_step` callback. The worker adapters read the CLI's stdout line by line while it runs: `codex exec --json` reports `item.started`/`item.completed` for `command_execution`, `file_change`, `mcp_tool_call` and `web_search` (reasoning, messages and todo lists are skipped), and `claude -p --output-format stream-json --verbose` reports `tool_use` blocks with their `tool_result`. `adapters/harness/_activity.py` turns each into a `Step` with a plain title ("Reading your Downloads folder", "Opening Microsoft Excel", "Searching the web for ...") and keeps the raw command or tool payload as `detail`, shown only when the row is expanded. Callers without a callback get the same `Reply` as before.
- **Questions.** While Milo waits for a yes or no, the bubble shows the question with Yes and No buttons and stays up, and a bar above the text field shows it too.
- **Typing.** The text field sends `text`. The window's "speak replies" toggle (off by default, kept in UserDefaults) adds `"speak": false`, and Milo then answers in the bubble and the window without audio.

## Heartbeat cost model

The heartbeat must not burn tokens. One tick does a `stat()` on `reminders.md`, runs the enabled rules in memory and writes `state/heartbeat.json`. That's zero harness calls. A rule can attach an `llm_prompt` asking for nicer wording, but the runner uses it only if `LlmBudget.allow(today)` is true. The default `llm_calls_per_day = 0` means it never is. `tests/proactive` simulates a full day of ticks and asserts zero calls.

A chat turn costs one message to the running chat model: about 600 tokens, with the first text after 1 to 2 s. A delegated task costs one harness call. Measured with `codex exec` on 2026-10-29: about 19k input tokens for a plain reply (mostly cached on resume) and about 62k when the agent edits memory files. That takes 5 to 10 s. The usage ledger labels these `chat`, `task` and `proactive`. See [ADR 5](adr/0005-live-chat.md).

## App layout

```
app/
  Sources/MiloKit/   protocols, wire types, controller, hotkey state machine, views (all testable).
                     The Milo window: TranscriptModel, Views/ConversationView + ActivityView,
                     Views/HelperViews (the birds next to Milo and the helpers list, Wire/Helper),
                     AppKit/ConversationWindow. Screen/: ScreenController and TakeoverDetector.
                     Hotkeys/KeyCombo. Adapters/: Accessibility, SystemScreenReader, ScreenShots,
                     MacHands (delivery through Accessibility, borrow the real pointer otherwise),
                     MacWindowWatcher, NSEventInputMonitor, CarbonHotkey, EventKitConnections (answers
                     app_request for Calendar and Reminders). Milo's cursor and the window outline:
                     AppKit/CursorOverlay + Views/CursorView, AppKit/WorkingOutline + Views/WorkingOutlineView,
                     Screen/Delivery + Screen/CursorGlide. The character: Views/PipFigure (the bird, default) or
                     Views/CharacterView's CharacterFigure (the robot, [ui] character = "classic"), both
                     posed by CharacterLife. Flight.swift + AppKit/FlightDriver fly the overlay panel to
                     MiloModel.flyTarget (AppKit global screen coordinates) and back
  Sources/Milo/      main.swift: builds concrete adapters, hands them to MiloController
  Tests/MiloKitTests Swift Testing; decodes protocol/messages.json, drives the controller with fakes.
                     MILO_RENDER_DIR=/tmp/milo-render swift test --filter ConversationRender renders the
                     window offscreen into PNGs. MILO_RENDER_DIR=... --filter PipRender renders Pip's key
                     frames; MILO_RENDER_DIR=... --filter HelperRender renders the birds and the helpers list;
                     MILO_PROBE_DIR=... --filter OverlayProbe puts the overlay on screen, measures
                     its CPU and flies Pip to a point and back
```
