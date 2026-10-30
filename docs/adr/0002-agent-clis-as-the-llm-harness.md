# 2. Use agent CLIs (Codex, Claude Code) as the LLM, behind one port

Date: 2026-10-29. Status: accepted.

## Context

The user has Codex and Claude subscriptions and wants to switch between them. Milo needs file access for memory, multi-step tasks, and structured output for the emotion tag.

## Decision

- The `Harness` port has one method: `reply(prompt, session_id) -> Reply`. Adapters run `codex exec --json --output-schema` and `claude -p --output-format json --json-schema`.
- Each harness runs with `~/Milo` as its working directory, in a sandbox that can write only that folder. The agent's instructions are `~/Milo/AGENTS.md`, which `CLAUDE.md` imports.
- Follow-up turns resume the CLI session. After 10 idle minutes Milo starts a fresh one.

## Consequences

- Memory needs no database. The agent edits Markdown files with its own tools.
- Every turn is slow and expensive. Measured on an M3: 5–10 s per turn, about 19k input tokens for a plain reply and about 62k when it edits memory. That's acceptable for tasks and too slow for small talk. A fast local model for chit-chat is on the TODO list.
- `codex exec` hangs while stdin is open, so the adapter always passes /dev/null. `exec resume` has no `--sandbox` flag, so the sandbox is set with `-c sandbox_mode=...` on every call.
