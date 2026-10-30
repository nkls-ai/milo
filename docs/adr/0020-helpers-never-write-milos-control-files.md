# 20. Helpers never write Milo's control files

Date: 2026-10-30. Status: accepted. Finding: H3 in [docs/review/2026-10-30.md](../review/2026-10-30.md).

## Context

A helper is one run of the worker harness (Codex or Claude Code). It reads mail, web pages and documents that other people wrote. Until now it ran with `~/Milo` as its working directory, and its sandbox could write the whole folder. That folder also holds what decides Milo's rules, memory and approvals: `config.toml` (action levels, `[hands]`, the harness), `persona.md`, `AGENTS.md`, `reminders.md`, `routines/`, `memory/` and `secrets/`. So one injected line in a mail could make a helper lower an action level to "never ask", plant a routine that runs every morning, add a fact to every system prompt, or rewrite the helpers' own instructions for the next task. This works whether the user is at the Mac or away. A prompt telling the helper not to do it isn't a boundary.

## Decision

Helpers can't write Milo's control files. This is enforced where the writes happen, not in the prompt.

- **The control files** are listed once, in `milo.core.control`: `config.toml`, `persona.md`, `AGENTS.md`, `CLAUDE.md`, `reminders.md`, and the folders `routines/`, `memory/`, `secrets/`, `state/`, `run/`, `.codex/` and `.claude/`. `Protected` checks a path against them. It resolves links first and ignores case, as APFS does.
- **The worker runs in `~/Milo/work/`.** It's the only folder of the workspace its sandbox may write. It holds the helper's scratch files and the routine drafts.
  - **Codex:** the `workspace-write` sandbox writes only the working directory and the temp folders. Checked with `codex sandbox`, and a test runs it: writes to `../config.toml`, `../routines`, `../memory` and `../secrets` fail, and reads work. The factory refuses `danger-full-access`. Codex gets `AGENTS.md` copied into its own home (`~/Milo/.codex`), which is outside the sandbox and rewritten before every run.
  - **Claude Code:**
    - It runs with `--restricted`. The file tools stay in the working directory, no settings file counts, and only a person may approve a write to a settings file.
    - The `--settings` it gets adds `Edit`/`Write` deny rules for every control path, and a `Read` deny for `secrets/`.
    - Its Bash runs in Claude Code's sandbox. `failIfUnavailable` and `allowUnsandboxedCommands = false` are set, so no command runs outside it, and `denyWrite` lists the control paths.
    - It finds its instructions in `~/Milo/CLAUDE.md`, one folder up.
- **Tools that run outside the sandbox check `Protected` themselves.**
  - The files tools (`files_find`, `files_search`, `files_read`, `files_list`, `files_move`) never list, read or move a control path, and never move anything into one. A link counts as the file it points to.
  - A `run_applescript` script that names a control path, by full path or by `~/` path, is refused without a question. A script that builds the path some other way still waits for the user's yes, like every script.
- **The ways to change them**:
  - The Settings window.
  - Milo's own tags in the chat (`<remember>`, `<reminder>`), which the user hears.
  - Tools that ask the user every time: `memory_remember`, `memory_forget`, and the new `milo_remind`. It goes to the brain over `run/tools.sock` (`reminder.add`), which asks with the reminder on its own marked line before it adds the line to `reminders.md`.
  - The routine flow: the helper writes a draft in `work/routine-drafts/`, and Save keeps exactly the text the user saw.
  - The user's own editor.

## Consequences

- A helper can still read the control files (not `secrets/` in Claude Code). Reading tells it nothing it can use against the user, and routines and memory are meant to be read.
- The worker can't keep notes in `memory/profile.md` or the journal any more. Without the memory tools it says it can't remember this time. The journal is written only by the night's consolidation.
- Routine drafts moved from `state/routine-drafts/` to `work/routine-drafts/`. A draft that was open during the update is gone. It was never saved, so nothing that ran is lost.
- Bash in a Claude Code helper now runs in the sandbox: no network, and writes only in `work/` and the temp folder. This matches what Codex's `workspace-write` always did. A Mac where Claude Code's sandbox can't start runs no Claude Code helper, and says why.
- A workspace from before keeps its old `AGENTS.md`, which still tells the helper to append to `reminders.md`. That write now fails in the sandbox, and the helper says it couldn't. The tool descriptions carry the new way, and copying the template's "Memory", "Reminders", "Routines" and "Limits" sections brings the instructions up to date.
- Milo's app-connections MCP server now starts for every helper, even with connections and memory off, because it carries `milo_remind`.
- Not covered: the milo-mac tools that click and type could still open `config.toml` in an editor and type into it. The user sees the outline around that window and every step, and clicking or typing in an app the user didn't clear asks first in a careful task. While the owner is away, the settings guard (ADR 0017) also puts `config.toml`, `state/messages.json` and `secrets/` back.
