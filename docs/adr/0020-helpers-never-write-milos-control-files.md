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
    - Its Bash runs in Claude Code's sandbox. `failIfUnavailable` and `allowUnsandboxedCommands = false` are set, so no command runs outside it. `denyWrite` lists the control paths and `denyRead` the keys.
    - It finds its instructions in `~/Milo/CLAUDE.md`, one folder up.
- **The worker's own folder steers nothing.** `work/` is the helper's to write, so a helper could leave instructions there for the next one: `AGENTS.md`, `CLAUDE.md`, `.codex/`, `.claude/`, `.mcp.json`. They are removed before every run (`clear_steering`), and Claude Code's deny rules keep it from writing them at all. If one can't be removed, no helper runs.
- **The brain reads from `work/` without following links and never writes there.** A routine draft is read through a handle on the drafts folder opened without following a link, as a plain file of at most 64 KB. The checked text stays in Milo's state; Save keeps that text.
- **Tools that run outside the sandbox check `Protected` themselves.**
  - The files tools (`files_find`, `files_search`, `files_read`, `files_list`, `files_move`) never list, read or move a control path, and never move anything into one. A link counts as the file it points to. A move renames through handles on both folders, checked again through the handles, so a link swapped in after the check can't redirect it.
  - A `run_applescript` script that names a control path, by full path or by `~/` path, is refused without a question. A script that builds the path some other way still waits for the user's yes, like every script.
- **The ways to change them**:
  - The Settings window.
  - Milo's own tags in the chat (`<remember>`, `<reminder>`), which the user hears.
  - Tools that ask the user every time: `memory_remember`, `memory_forget`, and the new `milo_remind`. It goes to the brain over `run/tools.sock` (`reminder.add`), which asks with the reminder on its own marked line before it adds the line to `reminders.md`.
  - The routine flow: the helper writes a draft in `work/routine-drafts/`, and Save keeps exactly the text the user saw.
  - The user's own editor.

## Consequences

- A helper can still read the control files. Routines and memory are meant to be read. The keys in `secrets/` are hidden from Claude Code (file tools and Bash), but Codex's `workspace-write` sandbox can't hide a folder from reads. A Codex helper can read the keys. Its commands have no network, but it could still quote a key in its reply or in a mail draft. Keeping them from Codex needs the keys outside the readable disk (the Keychain), which is a separate change.
- Helpers that run at the same time share `work/`. One could leave an `AGENTS.md` there just after another run's cleanup, in the moment before that run's CLI reads it. The window is short, the file is gone before the next run, and Claude Code can't write it at all.
- The worker can't keep notes in `memory/profile.md` or the journal any more. Without the memory tools it says it can't remember this time. The journal is written only by the night's consolidation.
- Routine drafts moved from `state/routine-drafts/` to `work/routine-drafts/`. A draft that was open during the update is gone. It was never saved, so nothing that ran is lost.
- Bash in a Claude Code helper now runs in the sandbox: no network, and writes only in `work/` and the temp folder. This matches what Codex's `workspace-write` always did. A Mac where Claude Code's sandbox can't start runs no Claude Code helper, and says why.
- A workspace from before keeps its old `AGENTS.md`, which still tells the helper to append to `reminders.md`. That write now fails in the sandbox, and the helper says it couldn't. The tool descriptions carry the new way, and copying the template's "Memory", "Reminders", "Routines" and "Limits" sections brings the instructions up to date.
- Milo's app-connections MCP server now starts for every helper, even with connections and memory off, because it carries `milo_remind`.
- Not covered: the milo-mac tools that click and type could still open `config.toml` in an editor and type into it. The user sees the outline around that window and every step, and clicking or typing in an app the user didn't clear asks first in a careful task. While the owner is away, the settings guard (ADR 0017) also puts `config.toml`, `state/messages.json` and `secrets/` back.
