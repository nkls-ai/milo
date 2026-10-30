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
                  may say), routines (the recipe format and plain-word schedules). Depends on nothing.
  adapters/       concrete engines, each registering itself by name
    harness/      codex, claude (agent harnesses), claude_live (the streaming chat model)
    stt/          mlx_whisper
    diarize/      sherpa_onnx (voice embeddings for meeting notes, TitaNet-small by default)
    tts/          omnivoice, say
    audio/        sounddevice (mic in, speaker out), wav (a real-time virtual sound card that writes WAV files,
                  and a WAV file as the mic, for timing tests and voice comparisons without the speakers)
    text/         fillers, plain (dictation cleanup)
    connect/      mac (Calendar and Reminders through the app, Mail and Notes through AppleScript,
                  Shortcuts, Spotlight files), fake (a made-up world in ~/Milo/fake)
    channel/      telegram (Bot API long polling), imessage (experimental: chat.db and Messages AppleScript)
    headless/     none: no microphone, no voice, no speaker, for tests and the eval
    embed/        mlx_e5 (multilingual-e5-small in MLX), hash (hashed words, no model; tests and CI)
  connect/        the MCP tool server the worker loads (python -m milo.connect)
  eval/           the 30-task eval (python -m milo.eval) and the on-screen eval (python -m milo.eval.screen)
  memory/         Workspace paths and bootstrap, profile.md, reminders.md, usage ledger, dictation history,
                  transcript (the old single-file log), conversations (one file per conversation and the
                  index, the migration from transcript.jsonl), routines (the recipe folder and its state),
                  remote (state/messages.json: the paired phone), and
                  long-term memory: episodes and facts (append-only JSONL), fact_profile (profile.md as a view of
                  the facts), index (FTS5 and vectors in state/memory.sqlite), recall, when (time phrases),
                  consolidate (the night), recall_eval, meetings (FileMeetingStore,
                  JsonVoiceBook)
  proactive/      heartbeat engine, daily LLM budget, rules (one class per rule, registered by name)
  services/       use cases built only on ports: listening (push-to-talk, barge-in), dictation,
                  live_transcript (pause segmenter, phrases committed while recording, live words),
                  live_talk (user turns on the chat model), reply_stream (tags out of the reply stream),
                  chunker + speaker + speech_audio (streaming TTS), echo + barge_in (talking over Milo),
                  backchannel ("Hm." when a reply is late), orchestrator + helpers + task_runner (helpers doing
                  delegated work on the harness, see ADR 11), updates (milestones and `[chat] updates`),
                  conversation (one resumed harness session, for the heartbeat), transcript (the conversation going on and where it splits), conversations (the
                  list, opening, renaming and search for the Milo window), heartbeat_runner, approvals
                  (action levels and yes-or-no questions), app_bridge (requests to the app and their answers:
                  AppEyes, AppHands, Calendar and Reminders work), tool_requests (what the tool socket may do),
                  screen (screen data for the chat model), hands + risk (checking and logging the worker's Mac
                  actions), sheets + documents (the AppleScript behind sheet_write and write_document), memory (recall for each turn, search, forget, edit), episode_stubs (episodes
                  of turns, tasks, routine runs, looks and dictations), memory_requests (the worker's memory tools), sleep
                  (when the night's consolidation runs), routines (writing, running and scheduling recipes, see ADR 16),
                  messages + pairing + sharing + brief + settings_guard (Milo by message, ADR 17),
                  meetings + meeting_text + meeting_speakers + background_stt (meeting notes, see below),
                  plus small shared pieces: ui_state, context (latest app/idle report), levels
                  (throttled meters), quiet (wait for a turn to end), fallback_voice
  transport/      Unix socket JSONL servers: brain.sock (an EventSink), hands.sock, and the tool socket and its
                  client
  mcp_server.py   the milo-mac MCP stdio server the worker CLI starts; forwards calls to hands.sock
  brain.py        routes inbound commands to services
  config.py       reads config.toml into sections
  config_file.py  changes one key of config.toml and keeps the user's comments (the Settings window and the
                  menu's dictation style)
  settings.py     the settings the Settings window may change, their choices, and how a change lands
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
| `milo.memory.workspace.Workspace(home)` | memory | `.ensure()` copies the template without overwriting, and creates dirs. Path properties: `config_path`, `reminders_path`, `profile_path`, `persona_path`, `state_dir`, `log_dir`, `socket_path`, `lock_path`, `usage_path`, `dictation_history_path`, `transcript_path`, `heartbeat_state_path`, `hands_socket_path`, `screens_dir`, `tools_socket_path`, for memory `episodes_dir`, `facts_path`, `journal_dir`, `memory_index_path`, `profile_snapshot_path`, `sleep_state_path`, and for routines `routines_dir`, `routine_runs_path`, `routine_state_path`, `routine_drafts_dir`. |
| `milo.memory.routines.MarkdownRoutineBook(folder, runs, drafts)` | memory | `RoutineBook` over `routines/*.md`. Re-parses a file only when its mtime or size changes. `update(slug, fields)` rewrites front matter lines in place; `delete` moves the file to `routines/deleted/`. |
| `milo.memory.reminders.MarkdownReminders(path)` | memory | `ReminderBook`. Re-parses only when mtime changes. `add(due, text)` appends a line. Shared by the heartbeat and LiveTalk. |
| `milo.memory.profile.MarkdownProfile(path)` | memory | `ProfileMemory` over `memory/profile.md`. Used only with `[memory] enabled = false`. |
| `milo.memory.fact_profile.FactProfile(facts, path, snapshot, clock)` | memory | `ProfileMemory` as a view of the `FactStore`: `read()` renders facts, `remember()` adds one, the user's edits to `profile.md` become fact changes. `migrate()` turns an old `profile.md` into facts once. |
| `milo.memory.index.SqliteMemoryIndex(path, embedder, facts, episodes)` | memory | `MemoryIndex` over `state/memory.sqlite`, a cache of the logs. `refresh(limit)` catches up with lines written since. |
| `milo.memory.recall.HybridRecaller(index, facts, tuning)` | memory | `Recaller`. `render(recall, now)` makes the `<memory>` block. |
| `milo.services.memory.Memory` / `TurnMemory` | services | The brain's memory: recall on the memory thread with a 300 ms limit, search, forget, edit, the `facts` event. `TurnMemory.before_turn()` is the live chat's hook. |
| `milo.memory.ledger.JsonlUsageLedger(path, clock)` | memory | `UsageLedger`. Appends one JSON line per harness call. |
| `milo.memory.history.JsonlDictationHistory(path, clock)` | memory | `DictationHistory`. |
| `milo.memory.transcript.JsonlTranscript(path)` | memory | `TranscriptStore` over `state/transcript.jsonl`. `tail(n)` reads the file backwards block by block, so its cost doesn't grow with the file. Only the migration reads it now. |
| `milo.memory.conversations.JsonlConversationStore(root)` | memory | `ConversationStore` over `state/conversations/YYYY-MM/<id>.jsonl`, one file per conversation, and `index.jsonl`, a cache of their headers that it rebuilds when files and index disagree. `migrate(transcript, kept, store, rules)` splits an old `transcript.jsonl` into conversations once, keeping every line, then renames it to `transcript.before-conversations.jsonl`. |
| `milo.services.conversations.ConversationBrowser(transcript, store, sink, clock, memory=, reminders=)` | services | What the window asks about conversations: `list_event(before)`, `open(id)`, `rename(id, title)`, `search(query)` (titles, then memory hits mapped to their conversation, then the files' words), `reminders_event()`. `changed()` sends the list again, coalesced to one per 0.3 s. |
| `milo.services.approvals.Approvals` | services | `approve(kind, summary) -> Decision` applies the action level and asks if needed. `confirm(summary) -> bool` always asks (the `Confirmer` port). |
| `milo.transport.tool_client.BrainClient(path)` | transport | `request(body) -> dict` on `run/tools.sock`; `approve(kind, summary) -> Decision`. Used by the MCP server, and by any helper process that needs a yes. |
| `milo.services.messages.MessageService` | services | Milo by message. `run()` polls the `Channel` until cancelled, `tick()` runs on the heartbeat. A `QuestionRelay` for `Approvals` (`asked`, `closed`), an `Orchestrator` watcher (`helper_changed`), and the `Phone` behind the tool socket's `send_to_phone` (`check`, `question`, `send_file`). `pause(on)`, `forget()`, `status() -> Remote`. |
| `milo.proactive.build_engine(section, ctx, reminders) -> ProactiveEngine` | proactive | `section` is the whole `[heartbeat]` table including sub-tables. Ignores `enabled` (compose.py decides whether to run it). |

## Listening

Both keys listen the same way (`services/listening.py`, `services/live_transcript.py`). Only what happens to the text differs: dictation pastes it, talk hands it to `LiveTalk`.

1. **Phrases.** While the key is held, `LiveTranscript` reads the new audio every 0.1 s and `PauseSegmenter` cuts it into phrases at pauses: 0.7 s of quiet, or 0.3 s once a phrase has run 6 s, or the quietest frame once it reaches 12 s. Speech is anything 2.5 times above the room's floor, but at least 0.004 RMS, so a microphone far away still makes phrases and live words.
2. **Commits.** Each closed phrase that no guess holds (step 3) is transcribed by the full model (large-v3-turbo, full 30 s window) while the user goes on talking. That text is final. `stream = "type"` pastes it at once. The text before a phrase only keeps its language (a short "okay" can't be detected reliably); it is not put in Whisper's prompt, which made more errors on test dictations because Whisper copies the prompt's style.
3. **Guess.** When the open phrase has been quiet for 0.25 s, the full model transcribes it as it stands, in a quick pass (below). If the user speaks again, the guess is dropped. If they let go first, the guess is the end and the release costs no pass at all. If the pause goes on and closes the phrase, the guess is its commit too, as long as nothing voiced lies outside it: the same model has heard the same audio, and a second pass with the full window would keep the STT thread busy for 3 s per phrase on a loaded Mac, holding up live words and the release.
4. **Preview.** Otherwise the small model (whisper-base) re-reads the open phrase for the live words above Milo (`partial`). Commits and guesses always go first, so at most one preview pass (about 0.05 s) runs ahead of the full model.
5. **Release.** `finish()` interrupts a commit or preview in flight (`Transcriber.interrupt()`: the Whisper encoder runs four layers at a time and checks between them). A guess in flight is let finish if nothing was said after it. Then everything not yet committed, closed phrases and the open one, goes in one quick pass, unless a guess holds all of it.

**No word is lost.** The speech threshold is made for finding pauses, and a soft voice can stay under it: trailing off, a quiet microphone. Until 30 October such words were dropped: after a guess (its end never moved), in a tail after a commit, and in a soft phrase between pauses. `PauseSegmenter.voiced()` is a lenient second check, a little above the room's floor, and it decides what holds words: each phrase runs from the end of the one before, trimmed only up to the first voiced frame; a guess only stands if nothing voiced lies outside it; a pause is only cut where it is truly quiet, never through soft words; a quick pass that hears nothing in voiced audio is done again at full accuracy. Last, a safety net: text with fewer than 1.5 words per second of speech (test dictations had 3.5 to 7) gets one full pass over the whole recording, and that text wins if it has more words.

**The next key press doesn't wait.** The brain reads the app's commands one at a time. `release()` stops the mic, hands the recording to a task and returns, so a key pressed right after a release opens the mic at once and approval clicks aren't held up. Each recording's results (typed phrases, the paste, the talk turn) go out only after those of the recording before it (`_InOrder`), and only the newest release puts Milo back to rest. The app shows the recording 80 ms after key-down (`PushToTalk.showAfter`); a press shorter than 250 ms is still a tap, so a double tap locks hands-free.

The key going down first queues `Transcriber.wake()`: a short pass over a second of silence on each loaded model. On a 16 GB Mac with a browser and a few agents open, macOS pages an idle brain's 5 GB of model memory out, and the first pass after that took 3.8 s for 2 s of speech. Waking at key-down pages the models back in while the user is still talking. A wake that takes over half a second is logged.

All passes run one at a time on the STT thread. A quick pass encodes the audio plus 1 s of silence, but at least 10 s, instead of a padded 30 s window, so it costs roughly its own length (0.3 s for a short phrase on an idle M3 against 1.1 s). With less than 10 s the decoder loses track of where speech ends and repeats itself; a quick decode that loops, runs past 8 tokens a second or that Whisper itself doubts goes through the full window instead. Quick passes on single phrases missed a few more words than full windows (on 48 test phrases 2.7% against 1.7%), but on whole test dictations, phrase by phrase, they made fewer errors than one full pass over the recording (0.4% against 1.6%). `stream = "off"` runs no live passes and transcribes the whole recording on release with full windows.

**Measured** with `scripts/e2e-dictation.sh` (macOS voices replayed in real time into a real brain, on an M3 with 16 GB while a browser and several agents ran: load average 20 to 25, the models paged out between dictations). Release to paste, `preview` against `off`: 2 s dictations 0.41 to 1.41 s (2.8 to 4.7 s), 15 s 0.25 to 0.75 s (3.1 to 4.7 s), 60 s 0.86 and 1.29 s (14.5 to 15.9 s). The first live words came 0.4 to 1.6 s after speech began, the listening state 80 ms after key-down. Not one word of 488 was lost (word error 0.4%); `off` lost 6 (1.6%). What is left of the release is one quick pass, 0.4 s for a short phrase on a quiet Mac and up to 1.4 s on this loaded one. Before these changes (main at 5a5b284) the same run pasted after 0.80 to 2.31 s.

The menu bar item's "Dictation style" changes `[dictation] stream` the way the Settings window does (`set_setting`, see Settings below): the brain saves it and uses it from the next recording. The menu ticks the value from the brain's last `settings`, which the brain also sends on connect.

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
- **During the day.** `EpisodeTranscript` (around the transcript store) makes an episode of each user turn with Milo's answer and of each task; `RoutineEpisodes` (on `Routines.on_episode`) makes the episode of a routine run instead, a task episode named after the routine with its inputs and apps; `EpisodeEyes` of each look; `EpisodeDictations` of dictations if `[memory] dictations` is on. `<remember>` and the worker's `memory_remember` add facts. The index catches up on the memory thread in batches.
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
- **The app.** The `helpers` event lists every active helper and, for 8 s, the ones that just ended (step changes coalesced to every 0.25 s). The overlay shows a small bird per helper next to Milo; a click opens its task page in the Milo window. Today lists the helpers at work with Stop, and each task is a card in its conversation.

Task results reach the chat model as `<task_result>` blocks with `<` and `>` escaped, and the reply rules say they are data. Once a result is in the conversation, LiveTalk asks before it acts on any later tag in it, until the conversation resets. See [ADR 10](adr/0010-untrusted-results-and-a-private-log.md).

## Routines

A routine is a recipe in words that a helper follows again: `~/Milo/routines/<slug>.md`, Markdown with front matter (`name`, `description`, `inputs`, `schedule`, `apps`, `paused`, `last_run`, `version`) and a body with Goal, Steps with `Check:` lines, and Ask first. `services/routines.py` owns them. See [ADR 16](adr/0016-routines.md).

- **Tags.** The talker writes `<routine do="create|save|change|run|schedule|rename|pause|resume|delete" name="...">`. The system prompt lists the routines by name and schedule, with names inert like task results. Create never asks (the draft is looked at before it counts); the others follow the task rule of a tainted conversation.
- **Create.** A careful helper writes a draft to `state/routine-drafts/` from the last finished helper's task, steps and result. The brain normalizes it and sends it in the `routines` event; the window's draft card shows the steps, inputs and apps, or the whole file, with Save and Change it (`routine_draft_answer`).
- **Run.** A helper gets the recipe and the inputs (`month: October`, a bare value for a single input, or the defaults). A recipe changed since it was saved, or a schedule set outside Milo, asks before it runs. `last_run` and `state/routine-runs.jsonl` record each run.
- **Schedules.** `HeartbeatRunner.on_tick` calls `Routines.tick`, which costs no model call. Missed runs coalesce into one, run at wake within `[routines] grace_hours` and are reported after it. `[routines] max_runs_per_day` caps scheduled runs.
- **Tasks that repeat.** `Orchestrator.on_done` calls `Routines.seen`, which keeps the shape of each finished task (`core/task_patterns.py`) for 45 days and offers, once per kind, to keep the third one alike as a routine.
- **The window.** A Routines section above the conversation lists them with their schedule, next and last run, Run now and a menu for pause, resume and delete (`routine`).

## Looking and computer use

See [ADR 6](adr/0006-looking-at-the-screen.md) and [ADR 7](adr/0007-computer-use-through-the-brain.md).

- **Looking.** The chat model writes `<look/>` when it needs to see the screen. LiveTalk asks through the `ScreenEyes` port (`AppEyes` sends `look_request`), the app answers `look_result` with the front window's text and a screenshot path, and LiveTalk sends both to the model as a second message with an image block. `looking` turns the eye badge next to Milo on and off. "What's this?" (the shortcut or the menu item) sends `whats_this` with a capture, and the brain starts a turn with it. Screen text sits between `<screen_data>` markers (`services/screen.py`), and a task from a conversation that has seen it runs careful (see Delegated tasks).
- **Computer use.** Workers get the milo-mac tools (`core/hands.py`) through `AdapterContext.mac_tools`, which compose.py fills when `[hands] enabled`. Codex and Claude start `python -m milo.mcp_server`, next to the app connections server, and it sends each call to `~/Milo/run/hands.sock`. `HandsService` validates it, asks the app to describe the target, classifies it with `services/risk.py`, asks through the `Confirmer` port (`Approvals`, see below) when needed, logs a step, and then has the app run it (`hands_request`, `hands_result`). It only answers while a screen helper runs, and only one does at a time.
- **Background delivery.** `MacHands` works on apps without the real cursor or keyboard where macOS allows it, deciding the route per app family with the pure planner `Screen/Delivery`: `AXPress` for buttons, `AXFocused` plus a caret for a click into a field, `AXSelectedText` (read back) for typing, `AXShowMenu` for a right-click, the scroll bar's value for scrolling. What can't be done that way (a plain keystroke, a double-click, web content, Office documents) returns `HandsFailure(borrow:)`; `HandsService` asks "Can I borrow your mouse for a moment?" through the `Confirmer`, and on a yes sends `hands_borrow`. The app lends that one device on a 15 s sliding clock and warps the real pointer back afterwards. See [ADR 12](adr/0012-background-delivery.md).
- **Scripts Milo writes.** `sheet_write`, `sheet_read` (Excel, Numbers), `write_document` (TextEdit, Pages) and `ax_find` are composed in the brain: `services/sheets.py` and `services/documents.py` turn plain arguments into AppleScript with every value as an escaped literal, and run it through the app's `run_applescript` action, which works in the background. They need no question unless `sheet_write` would replace filled cells. The tool descriptions put them first, then `run_applescript` (always asks), then the accessibility tree, then screenshots. See [ADR 14](adr/0014-scripts-milo-writes-and-short-questions.md).
- **On screen.** Milo's own cursor in his theme's colours (`AppKit/CursorOverlay`, a click-through overlay, never the system cursor) glides to each spot before the action, ripples on a click and shows a caret while typing. The window he works in gets a soft outline with a "Milo is working here" tag and a Stop button (`AppKit/WorkingOutline`, `MiloModel.workingWindow`), followed by `Adapters/MacWindowWatcher`. Milo flies to its corner and perches there (`FlightDriver`). The whole-screen frame (`AppKit/WorkingFrame`) shows only while the real mouse or keyboard are borrowed. `describe` returns the target's `window` and `pid` for the outline.
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

## Milo by message

The owner reaches Milo from their phone through a chat app (`[messages]`, off by default). See [ADR 17](adr/0017-milo-by-message.md) and the [setup guide](setup/messages.md).

```
phone ──Telegram──▶ api.telegram.org ◀──HTTPS long poll── brain: TelegramChannel ──▶ MessageService
                                                                                       │
             pairing code ◀── bubble and window on the Mac ◀────────────────────────────┤
             LiveTalk.message (text turn, same conversation) ◀──────────────────────────┤
             Approvals questions while away ──▶ Yes/No buttons in the chat ─────────────┤
             helpers started from the phone ──▶ milestones and results in the chat ─────┤
             worker's send_to_phone ──tools.sock──▶ check, ask "share", send the bytes ─┘
```

- **Channels** (`CHANNELS` registry, `core/ports.Channel`) only move messages. Telegram uses the Bot API over HTTPS with the standard library, so nothing on the Mac listens for the network. The token comes from `~/Milo/secrets/telegram-token` (0600, never logged). iMessage reads chat.db read-only (Full Disk Access) and sends with AppleScript to the owner's own handle only.
- **Pairing** (`services/pairing.py`): the first message from an unknown private chat makes a 6-digit code that shows on the Mac only; sending it back makes that chat the owner (`state/messages.json`, 0600). Codes are tied to their chat, last 10 minutes and 5 tries. After pairing everything but the owner's private chat is dropped and logged without its text.
- **Turns.** `LiveTalk.message` runs a text turn on the live model: same persona, memory and helpers, no speech, no looking. Forwarded, quoted and long (pasted) text goes in as escaped `<forwarded>`, `<quoted>`, `<pasted>` data and makes later tags ask first.
- **Questions.** `Approvals.relays` holds the MessageService. While the Mac has been idle for `away_after_min`, a question goes to the chat and only the chat may answer (`Relayed.only`); while the owner writes from the phone and the Mac is in use, both may.
- **Files.** The connections server lists `send_to_phone` when messages are on. `ToolRequests` asks `services/sharing.py` whether the file may go (no private folders, case-insensitive, links resolved, at most `max_file_mb`), asks `share`, then sends the bytes read through one descriptor opened without following links, if it is still the same file.
- **Safety while away.** `services/settings_guard.py` puts `config.toml`, `state/messages.json` and `secrets/` back if they change while the owner is away (Milo's own saves excepted). `/pause` works from the phone; resuming, pairing and disconnecting only at the Mac (the menu sends `remote_pause` and `remote_forget`).
- **Morning brief** (`services/brief.py`, `brief_at`): today's events and Apple Reminders through the app, `reminders.md`, helpers at work. Templates only, zero tokens, on the heartbeat's tick (`HeartbeatRunner.on_tick`).

## Logs

`logs/brain.log` rotates at `[logging] max_mb` and keeps `keep` old files. It holds sizes and timings, never what the user said, Milo's replies or file contents: services log `milo.core.logtext.private(text)`, which is `<42 chars>` unless `[logging] content = true`. `logs/connect.log` is the MCP server's.

## The Milo window

The window has the conversations down its left side and a page beside them: Today, a conversation, or a task. Clicking the character or "Open conversation" in the menu bar item opens it; a second click or the close button hides it. macOS keeps its frame. The design is in [design/conversations.md](design/conversations.md) and [ADR 19](adr/0019-conversations-that-split-on-their-own.md).

- **Conversations.** `services/transcript.py` holds the conversation going on and asks `core.conversations.split()` at every user turn whether it starts a new one: after `[chat] conversation_idle_reset_s` of quiet, when the user asks for one (⌘N), after a 2-minute pause with no word in common with the last two turns, or when a turn comes from another channel. It never splits on an answer or while Milo waits for one. Each conversation is a JSONL file under `state/conversations/`; its id is `c-` and its first entry's id. Routine runs and meeting notes get conversations of their own.
- **Titles.** The first user turn gives a title from its words at once (`title_from`). On the reply to the first turn LiveTalk appends `[name this conversation]`, and Milo's `<title>` tag, taken out of the reply stream, replaces it. A name the user gives (double-click the title) wins over both.
- **Picking up.** Typing in an older conversation sends `text` with its `conversation`. The brain makes it the current one again and gives the chat model an `<earlier_conversation>` recap of its last lines within `[chat] recap_tokens` (600). The recap is untrusted when that conversation saw outside text or a task's result (LiveTalk's `carries_outside`, memory on or off), and always for meeting notes and routine runs.
- **Events.** On connect and when the window opens the brain sends `conversations` (the headers, the current id, whether older ones exist), `history` (the current conversation's entries) and `reminders` (open ones due before the end of tomorrow). `entry`, `reply_delta` and `activity` stream as before, each entry with its `conversation`. `open_conversation` answers with `conversation` (the header and its entries), `search_conversations` with `search_results`. None of them call a model.
- **Activity.** `Harness.reply` takes an optional `on_step` callback. The worker adapters read the CLI's stdout line by line while it runs: `codex exec --json` reports `item.started`/`item.completed` for `command_execution`, `file_change`, `mcp_tool_call` and `web_search` (reasoning, messages and todo lists are skipped), and `claude -p --output-format stream-json --verbose` reports `tool_use` blocks with their `tool_result`. `adapters/harness/_activity.py` turns each into a `Step` with a plain title ("Reading your Downloads folder", "Opening Microsoft Excel", "Searching the web for ...") and keeps the raw command or tool payload as `detail`, shown only when the row is expanded. Callers without a callback get the same `Reply` as before.
- **Tasks.** In a conversation a task is one card: its title, its state and its current step. The card opens the task's page with the result, the files it names that exist (`files`, checked when it finishes) and every step.
- **Today.** What waits for the user (Milo's question, a recipe draft), what Milo is working on, today's reminders, what got done today and the last conversation to pick up.
- **Questions.** While Milo waits for a yes or no, the bubble shows the question with Yes and No buttons and stays up, and a bar above the text field and the Today page show it too.
- **Typing.** The text field sends `text`. The window's "speak replies" toggle (off by default, kept in UserDefaults) adds `"speak": false`, and Milo then answers in the bubble and the window without audio.
- **Keys.** ⌘1 Today, ⌘N a new conversation, ⌘F search, ⌘[ back, ⌥⌘↑ and ⌥⌘↓ the conversation above or below, ⌘L the text field, ⌘0 the sidebar in a window narrower than 600 pt, Esc clears the search or leaves a task.

## Settings

The Settings window changes a few keys of `~/Milo/config.toml` through the brain; the app stores nothing.

- **Protocol.** The app sends `get_settings` when the window opens and `set_setting {section, key, value}` for each change, from the window or the menu's "Dictation style". The brain sends `settings` on connect and answers both with `settings {settings, restart, error}`: one row per setting with `value`, its `options` and their plain `labels` (both empty for a switch), and `live`. `restart` is true while a saved change waits for one; `error` says in plain words why the last change wasn't saved.
- **What can change.** `settings.SETTINGS` lists them: `[ui] character`, `[chat] updates`, `[dictation] stream`, `[ui] dictate_key`, `talk_key`, `whats_this_key` and `[ui] voice`. Anything else is refused.
- **Saving.** `config_file.TomlConfigFile`, the brain's only writer of config.toml, edits the file with tomlkit, so comments, order and blank lines stay, and a comment at the end of the changed line keeps its column. It loads the edited text with `Config` first and writes nothing if it fails (a clash of keys, a wrong type, an already broken file); the write goes to a temporary file that replaces config.toml.
- **Applying.** `compose.py` hands `Settings` one function per key that can change live: the look and the keys re-send `ui_config` (and later connects send the new one), `voice` sets `Speaker.silent` (replies still show piece by piece at speaking pace, without audio), `stream` sets `Listening.live_mode` for the next recording, `[chat] updates` goes to `LiveSettings` at once (the helpers' updates; it would otherwise notice the changed file within 2 s). Every setting in the window applies live today; a key without a function would wait for a restart, and the window would then show a Restart Milo button, which restarts the brain.

## The setup window

`SetupWindow` opens by itself at launch when the microphone, Accessibility or Screen Recording is missing, and from the menu bar as "Check permissions…". Calendars, Reminders and Mail and Notes (Automation, checked against Mail) are optional rows.

- **Checks.** `SetupModel` reads every permission through the `PermissionSource` port (`SystemPermissions` in the app, `FakePermissions` in tests) once a second, only while the window is open, so a tick appears as soon as the switch flips.
- **Granting.** The row's button first puts Milo in that permission's list (`register`: `AXIsProcessTrustedWithOptions` with the prompt, `CGRequestScreenCaptureAccess`, `AVCaptureDevice.requestAccess`, EventKit's request, an Apple Event question to Mail). Where macOS hasn't asked yet and asks in a dialog, that's all; otherwise it then opens the exact page (`x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_…`). For Accessibility and Screen Recording a small floating panel shows Milo as a tile to drag into the list.
- **Stale entries.** After a rebuild macOS can show Milo switched on while the check says no. A permission that was granted before (remembered in UserDefaults) or is still off 8 s after its page opened gets a Fix it button: `tccutil reset Accessibility|ScreenCapture <Milo's bundle id>` for Milo's own entry only, then register and open the page again.
- **Screen Recording** only counts after a restart, so once its page was opened the row offers Restart Milo, which relaunches the app.
- **Scenes.** Each row plays a short loop of what Milo does with the permission, drawn with Milo himself (`Views/SetupScenes.swift`), only while the window is open; with Reduce Motion each shows its last step still.

## The overlay, moment to moment

The overlay reacts to the keys before the brain does. `MiloController` shows each push-to-talk output on the model in the same call that sends it (`MiloModel.press`, `hold`, `release`, `cancelPress`), so the view commits within about 2 ms of the key (`ResponseLatencyTests`), a round trip and the 80 ms `showAfter` ahead of the brain's own state. One capsule over Milo (`Views/VoiceCapsule`, its look picked by `VoicePhase.of`) changes shape from step to step: a small light at key down (only a light, since it may still be a tap or a right-Option shortcut), the level meter and the words so far once the key has been down 80 ms, "Got it" for 0.6 s at key up, dots while the words are worked out and while he thinks ("Still on it" after 6 s), and "Pasted" for 1.4 s after dictation lands. It springs in with the theme's motion and leaves in 0.12 s.

The bubble (`Views/BubbleView`) holds his answer, a question with Yes and No, or a note with a button that fixes what it is about (`BubbleAction`, "Fix it" opens the permissions window). It hugs short text. While he speaks, `SpeechReveal` lays out each piece the brain sends, hidden, and shows its words at the speed he talks, learned from how long each piece took, so lines never reflow. The mic and voice level live in their own `MiloModel.live`, which only the figure and the meter watch.

Shared sizes (radii, text width, edge, shadow) are in `Views/Surface.swift`. Increase Contrast makes the paper opaque and the edges real lines; Reduce Motion turns scales into fades and stops the dots and the outline from moving. `OverlayRenderTests` renders every moment in light and dark.

## Themes

Milo has one theme, and every surface around him uses it: the bubble, the live words, the Milo window, the Settings and setup windows, the menu bar sign. Other overlays (the cursor, the working outline, helpers) should use it too.

```swift
let theme = Theme.for(.milo)        // or model.theme, from MiloModel.character
theme.primary  theme.tint  theme.accent  theme.ink  theme.glow   // SwiftUI Colors, light and dark built in
theme.onPrimary  theme.card  theme.rule                          // text on primary, cards on tint, hairlines
theme.appKit.primary                                             // the same colours as NSColor, for AppKit
theme.motion.spring  theme.motion.gentle                         // his springs; never linear tweens
theme.motion.animation(reduced: reduceMotion)                    // a short fade under Reduce Motion
theme.motion.bob                                                 // how far decorative things float

someView.themed(by: model)                     // puts model.theme in the environment
@Environment(\.miloTheme) private var theme    // inside any view below it
```

`primary` is his lavender (buttons, selection, the thread of a task), `tint` a soft wash of it (window paper), `accent` the marigold of his scarf, `ink` text on `tint`, `glow` halos and highlights. The API lives in `app/Sources/MiloKit/Theme.swift`; add a colour there rather than in a view. Windows use `.themed(by:)`; the always-there overlay panels (the cursor, the working outline, the borrowed-mouse frame) subscribe to `model.$character` instead and pass the theme into their view, so they redraw only when it changes. Task status colours (running, done, failed, needs you) are their own. The theme mechanism stays so a future look can bring its own; `[ui] character` accepts only `milo` today, and the retired names (`pip`, `classic`, `dragon`, `kit`, `glow`) fall back to him.

## Meeting notes

See [docs/design/meetings.md](design/meetings.md) and [docs/research/meetings.md](research/meetings.md).

- **The app records, the brain decides.** `Meetings/MeetingController` polls `CallSignals` (`Adapters/MacCallSignals`: who uses the mic, from Core Audio's process list, and browser window titles) and turns them into `call_started` and `call_ended` through the pure `CallDetector`. The brain's `MeetingService` asks once through `Approvals` ("Looks like a meeting. Should I take notes?", shown, not spoken) or starts on its own for `[meetings] auto = "calendar"` when the calendar has an event now. It sends `meeting_record` with the folder. The app's `MeetingRecorder` (`Adapters/MacMeetingRecorder`) writes two tracks, `me` (the mic) and `them` (a Core Audio process tap of everything but Milo and the brain, or ScreenCaptureKit), as 30 s WAV chunks through `Meetings/ChunkWriter`, and sends `meeting_chunk` for each one on disk. `meeting_recording` says which tracks are recorded, on every connect too, so a restarted brain goes on with the meeting the app is still recording. A red dot shows on Milo and in the menu bar, whose "Take meeting notes" item sends `meeting_toggle`.
- **Passes.** `MeetingService` transcribes the track furthest behind in passes of up to 30 s, cut at the quietest moment, with `TimedTranscriber.words` (Whisper word times) through `BackgroundStt`, which waits while the user dictates or talks. When a dictate or talk key goes down, `Listening.start` calls `BackgroundStt.yield_now` before it queues `wake()`: a meeting call running on the STT thread ends with `Transcriber.interrupt()`, and one still waiting there never starts. The service rolls the speaker tracker back and runs that same pass again first, once the user is done, so the user's passes never wait on a meeting. Each pass appends its lines and a progress mark to `meetings/<id>/transcript.jsonl` in one write (`MeetingStore`), and re-renders `transcript.md`. A crash repeats at most the pass it was in, and its lines count once.
- **Speakers.** The `them` track's Whisper segments go to the `Diarizer` (`DIARIZERS` registry, `[meetings] diarizer`), one voice embedding each. `SpeakerTracker` keeps the meeting's voices across passes. Names come from `VoiceBook` (voices the user named before), the calendar (one attendee and one voice), and the user ("that was Anna", "Speaker 2 is Tom").
- **During the call.** LiveTalk asks `MeetingService.before_turn(text)` for a `<meeting>` block with what was said, newest last and escaped, and treats it like screen data: untrusted, and the conversation counts as tainted.
- **After.** A fresh chat-model session writes the summary, decisions, to-dos and a follow-up draft as JSON (`meeting_text.SUMMARY_RULES`). The brain writes `notes.md`, deletes the audio unless `[meetings] keep_audio`, offers the user's to-dos as Reminders and the mail draft through `Approvals` (the draft goes to a careful helper with the meeting text as data), and records a `meeting` episode in memory (`Memory.record` through `on_episode`): the title and summary, the people named, the app, `source` `meeting:<id>`, untrusted because it's other people's words.


## Heartbeat cost model

The heartbeat must not burn tokens. One tick does a `stat()` on `reminders.md`, runs the enabled rules in memory and writes `state/heartbeat.json`. That's zero harness calls. A rule can attach an `llm_prompt` asking for nicer wording, but the runner uses it only if `LlmBudget.allow(today)` is true. The default `llm_calls_per_day = 0` means it never is. `tests/proactive` simulates a full day of ticks and asserts zero calls.

A chat turn costs one message to the running chat model: about 600 tokens, with the first text after 1 to 2 s. A delegated task costs one harness call. Measured with `codex exec` on 2026-10-29: about 19k input tokens for a plain reply (mostly cached on resume) and about 62k when the agent edits memory files. That takes 5 to 10 s. The usage ledger labels these `chat`, `task` and `proactive`. See [ADR 5](adr/0005-live-chat.md).

## App layout

```
app/
  Sources/MiloKit/   protocols, wire types (Wire/RemoteStatus: Milo by message for the menu), controller, hotkey
                     state machine, views (all testable).
                     The Milo window: TranscriptModel (the conversations, the current one's entries, opened
                     ones, search results, reminders), Wire/Conversation, Views/WindowRoute (the page and the
                     way back), Views/ConversationView (sidebar + page, the keys), ConversationsSidebar,
                     TodayView, ConversationPage, TaskPage (the task card and page), ActivityView,
                     Views/HelperViews (the birds next to Milo and a helper's row on Today, Wire/Helper),
                     Views/RoutineViews (the Routines section and the recipe draft card, Wire/Routine),
                     AppKit/ConversationWindow. Screen/: ScreenController and TakeoverDetector.
                     Hotkeys/KeyCombo. Adapters/: Accessibility, SystemScreenReader, ScreenShots,
                     MacHands (delivery through Accessibility, borrow the real pointer otherwise),
                     MacWindowWatcher, NSEventInputMonitor, CarbonHotkey, EventKitConnections (answers
                     app_request for Calendar and Reminders), SystemPermissions (the setup window's checks).
                     Milo's cursor and the window outline: AppKit/CursorOverlay + Views/CursorView,
                     AppKit/WorkingOutline + Views/WorkingOutlineView, Screen/Delivery + Screen/CursorGlide.
                     The character, a lavender wren (docs/CHARACTER.md): Views/CharacterFigure.swift is
                     CharacterFigure(input:, size:, live:), the one way to draw Milo at any size. Views/Wren/:
                     WrenPose (every number the rig reads, one spring each), WrenRig (builds the parts from
                     a pose), WrenMotion (springs, clips, blinks, flaps, follow-through), WrenDirector (the
                     pose and the moves for each state), WrenView (a CALayer per part, redrawn only when
                     its shape changes, stepped by a display link that stops when he is still), WrenIcon
                     (menu bar and app icon, drawn from the rig). CharacterLife picks his idle habits.
                     Theme.swift: his colours and springs; every window and overlay (the bubble, the
                     Milo window, the helper birds, the cursor, the working outline and frame, What Milo
                     knows) takes them from MiloModel.theme.
                     SettingsModel + Views/SettingsView + AppKit/SettingsWindow; SetupModel + Views/SetupView
                     + SetupScenes + AppKit/SetupWindow. Flight.swift + AppKit/FlightDriver fly the overlay
                     panel to MiloModel.flyTarget (AppKit global screen coordinates) and back. Meetings/: MeetingController,
                     CallDetector, ChunkWriter; Adapters/MacMeetingRecorder + CoreAudioProcesses
  Sources/Milo/      main.swift: builds concrete adapters, hands them to MiloController
  Tests/MiloKitTests Swift Testing; decodes protocol/messages.json, drives the controller with fakes.
                     MILO_RENDER_DIR=/tmp/milo-render swift test --filter ConversationRender renders the
                     narrow window offscreen into PNGs, --filter WindowRender the whole window: Today, a
                     conversation, an older one, task pages, search, empty states, light and dark.
                     MILO_RENDER_DIR=... --filter WrenState renders Milo in every state (and the icons),
                     --filter WrenFilm records his scenes as GIFs and strips, --filter OverlayRender the
                     bubble and the voice capsule in every moment, --filter SettingsRender the Settings and
                     setup windows, --filter HelperRender the birds and their task cards;
                     MILO_COMPARE_DIR=... --filter CompareRender a few states for design comparisons;
                     MILO_PROBE_DIR=... --filter OverlayProbe puts the overlay on screen, measures its CPU
                     and what a pose change costs, and flies him to a point and back
```
