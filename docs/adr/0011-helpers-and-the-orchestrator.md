# 11. The talker and its helpers

Date: 2026-10-30. Status: accepted. Builds on [ADR 5](0005-live-chat.md), which handed `<task>` work to the harness one task at a time. Changed by [ADR 28](0028-open-at-once-and-answer-in-the-users-language.md): the talker opens apps, pages and files itself (`<open>`), without a helper.

## Context

Milo ran one delegated task at a time, on one harness session. While a task ran, a second request waited behind it, the user couldn't change the task without waiting for it to end, and there was no way to stop it short of quitting the brain. Asking "how far are you?" got a guess, because the chat model never saw what the worker was doing.

## Decision

There are two kinds of Milo. The **talker** is the live chat model (`LiveTalk`). It answers at once and never waits for work. **Helpers** do the work: each is one run of the worker CLI (Codex or Claude) with its own id, short title, status, steps and result. `services/orchestrator.py` owns them.

**Starting work.** The talker writes `<task title="Budget table" screen="yes">...</task>`. `Orchestrator.submit` returns at once. Up to `[harness] max_helpers` (3, at most 8) work at the same time and the rest wait as `queued`. Helpers with `screen="yes"` take turns, because there is one mouse; the others run alongside. Background helpers run on a second harness instance without the milo-mac tools (and with its own state folder, so the two don't share Claude's MCP config file). If one finds it needs the screen after all, it answers `NEEDS_SCREEN` and goes back in the queue as a screen helper. Since only one screen helper runs at a time, `HandsService` keeps a single task id and needs no change.

**Seeing the work.** Before every user message the talker gets a `<helpers>` block: per helper, how long it has worked, how many steps, the last two steps and how far through its plan it is. The steps are rewritten by `helpers.plain_step` into kind words ("reading", "running a command") plus the names of apps installed in /Applications. File names, commands, web pages and window text never go in. That is why the board doesn't taint the conversation under [ADR 10](0010-untrusted-results-and-a-private-log.md): there is nothing outside in it to carry an instruction. Results still go in as `<task_result>` data and taint it as before.

**Steering.** `<steer helper="2">make it 2000 instead</steer>`. Milo runs workers as `codex exec` and `claude -p` with one prompt, and neither takes new input in the middle of such a turn, so steering stops the running turn and continues the same session with the change (`codex exec resume <id>`, `claude --resume <id>`). The worker keeps what it already did and read. A helper without a session yet starts over with the change written into its task. Steering a finished helper starts a new helper that continues the old one's session. Steering a queued one just edits its task. Both CLIs did this reliably in live runs: Codex took 17.5 s from steer to done on a small file task, Claude 34.5 s. Once outside text is in the conversation, a steer asks for a yes like any other tag.

**Stopping.** `<stop helper="2"/>` or `<stop helper="all"/>` from the talker, or the Stop button in the Milo window (`stop_helper`). It never asks: stopping is always safe. Codex starts shell commands and its tool helpers in process groups of their own, so `_process.stop` signals the whole process tree (SIGTERM, then SIGKILL after 2 s), not only the worker's group.

**Telling the user.** `[chat] updates` decides what happens at a milestone, and changes to it apply within 2 s, without a restart:

- `quiet`: nothing is said or shown. The birds and the window show progress.
- `bubble` (default): a short note such as "Budget table: Opening Microsoft Excel", at most every 6 s, never spoken.
- `chatty`: the talker says it in one sentence of its own, at most every 45 s, from the plain words only. Tags in that turn are ignored. Otherwise it falls back to a note.

Milestones are rules over step kinds and titles in `services/updates.py`: the first app opened, the first file change, the first web step, halfway through a plan of three or more. They come no sooner than 5 s after the start and no more often than every 20 s per helper. Nothing shows while Milo talks, the user records, or a question waits. Results and questions that need a yes always come through. The heartbeat is untouched and still costs no tokens.

**The app.** The `helpers` event lists each helper with id, title, status (`queued`, `working`, `needs_you`, `done`, `failed`, `stopped`), current step and progress. Step changes are sent at most every 0.25 s, status changes at once, and a finished helper stays in the list for 8 s. Next to Milo a small bird stands for each helper, drawn by the same `CharacterView` with its own `MiloModel`, so the `[ui] character` skin applies. It is a still figure with no animation clock. Clicking one opens the Milo window at that helper, where a list shows every helper with its steps and a Stop button.

## Speed

From "do X" to the helper's first real step, measured with Codex on 2026-10-30 over a dozen tasks: the talker's first words come 1.4 to 3.8 s after the request (once 5.3 s), and the helper's first step 5.2 to 5.7 s after the helper starts (once 19 s). Small file tasks were done 7 to 9 s after the helper started.

The worker adapters now return as soon as the CLI prints its final line (`turn.completed` for Codex, the `result` line for Claude) instead of waiting for the process to exit. Codex spends 4 to 6 s shutting down after that line, so every task, and every result the user waits for, is that much faster.

Starting a Codex process ahead of time doesn't help: `codex exec` reads the whole prompt from stdin before it does anything. Keeping a warm Claude worker process (like the chat model's) would save its start-up second or so. It is not done yet.

## Consequences

- Each new task gets a fresh session, so helpers no longer share context across unrelated tasks. A steer, or a follow-up to a finished helper, continues the right session.
- Several helpers at once cost several workers' tokens at once. `max_helpers` caps it.
- A question from the app connections can't say which helper asked. It marks a helper `needs_you` only when exactly one is working. Questions from the screen always belong to the screen helper.
- A stopped worker loses the turn it was in. Work already written to disk stays.
