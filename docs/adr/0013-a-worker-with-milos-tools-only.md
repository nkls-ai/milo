# 13. The worker runs with Milo's tools only

Date: 2026-10-30. Status: accepted. Builds on [ADR 2](0002-agent-clis-as-the-llm-harness.md) and [ADR 7](0007-computer-use-through-the-brain.md). Changed by [ADR 32](0032-helpers-get-only-what-their-task-needs.md): Codex's home holds no AGENTS.md any more; each new session gets Milo's instructions, trimmed to its task, as `developer_instructions`.

## Context

On the morning of 2026-10-30 a task to make a table in Excel went to Codex, and Codex picked its own built-in computer use (a "cua" plugin from the user's `~/.codex`) instead of the milo-mac tools. Those actions skipped Milo's checks, steps and stop key. The worker CLIs load a lot from the user's own setup: Codex reads `~/.codex/config.toml`, its plugins, skills, hooks, rules and the global `AGENTS.md`; Claude Code reads `~/.claude/settings.json`, user skills, slash commands and memory. `--ignore-user-config` alone still loads the global `AGENTS.md` and the skills (checked with codex 0.164).

## Decision

- **Codex** runs with `CODEX_HOME=<workspace>/.codex`, a home of Milo's own. Before every task `prepare_home` writes its `config.toml` (built-in computer use, browser, in-app browser, plugins, remote plugins, apps, tool suggestions, sub-agents, goals, memories and image generation off; skill instructions and bundled skills off; no update check), deletes anything else that would add instructions or tools (`AGENTS.md`, hooks, rules, skills, plugins, agents, profile configs), and links `auth.json` to the user's login. A home that is itself a symlink is refused. `codex exec` also gets `--ignore-rules`. The user's `~/.codex` is never written.
- The home sits in the workspace, which the worker may write, but Codex's sandbox keeps `.codex` inside writable roots read-only, and the config is rewritten before every task anyway.
- The login is shared through the symlink. Codex writes a refreshed login through it, so the user's own Codex stays logged in.
- **Claude Code** gets `--setting-sources project,local` (no user settings), `--settings '{"autoMemoryEnabled": false}'`, `--disable-slash-commands` (no skills), `--tools` with its own built-ins minus the ones Milo disallows, and `--strict-mcp-config` always, with `--mcp-config` only for Milo's servers.
- Both workers get it: the screen helpers' harness with the milo-mac tools and the background helpers' harness without them ([ADR 11](0011-helpers-and-the-orchestrator.md)) share the one Codex home, and both Claude Code commands carry the flags above.
- Checked with real runs of both CLIs: the tool list holds milo-mac and milo and the built-ins, and nothing from the user's plugins.

## Consequences

- A user's Codex or Claude customisations don't reach Milo's worker, good or bad. Milo's behaviour is the same on every Mac.
- A Codex update can add a new feature that is on by default. The config names every feature that reaches the screen or adds tools; a new one needs a line there.
- The Codex shell is still there for files in the workspace. Taking it away is a TODO.
