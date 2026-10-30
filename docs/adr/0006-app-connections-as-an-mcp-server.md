# 6. App connections as one MCP server the worker loads

Date: 2026-10-30. Status: accepted.

## Context

Milo's worker (Codex or Claude Code) could already run shell commands, so it could in principle script Mail with `osascript` or read files with `cat`. That gave three problems: nothing asked the user before something risky, the activity list could only say "Controlling an app", and every task re-invented how to talk to each app. The vision ranks routes by reliability: Mac frameworks first, then Shortcuts, AppleScript and files, and screenshots last.

## Decision

- **One MCP stdio server, `python -m milo.connect`,** gives the worker 18 tools: Calendar (list, add), Reminders (list, add, tick off), Mail (search, read, draft, pass on as a draft), Notes (search, read, create, append), Shortcuts (list, run) and files (find by name, find by content, read). `compose.py` hands it to the harness as a `ToolServer`. Claude Code gets it with `--mcp-config` and `--strict-mcp-config`, plus `--allowedTools mcp__milo` because `-p` mode can't show a permission prompt. Codex gets `-c mcp_servers.milo.*` with `default_tools_approval_mode = "approve"` and a 240 s tool timeout. Both are allowed to call it without a prompt because the server asks the user itself when it matters (see [ADR 7](0007-approvals-and-action-levels.md)).
- **Written with the standard library.** The protocol part is about 100 lines of JSON-RPC over stdin and stdout. The official `mcp` package would pull in pydantic, anyio, starlette and more for the same thing. No new dependency.
- **The server runs with the brain's Python** (`sys.executable -m milo.connect`), so a task doesn't pay for `uv run` resolving the environment.
- **Calendar and Reminders run in Milo.app through EventKit,** not through AppleScript from the brain. The app is the process macOS shows in the permission prompt, EventKit is fast and doesn't open Calendar, and the permission survives across brain restarts. The MCP server asks the brain over its tool socket (`run/tools.sock`), the brain sends `app_request` to the app over the existing connection, and the app answers with `app_response`. So the app needs no new socket. The brain checks the connection switch and applies the op's action level itself for these, because the app lends its permission to whoever asks.
- **Naming next to track A.** Track A adds a 0600 "hands" socket inside the app for computer use. This design adds no socket to the app. The brain's socket is called `tools.sock` and serves approvals (`approve`, `confirm`) and app work (`app`). If the two should merge later, the `app` op can forward to the hands socket instead of the brain connection, or the hands server can call `approve` here before an action.
- **Mail and Notes use AppleScript** with every input passed as an argument (`on run argv`), never pasted into the script. Mail has no send command anywhere: drafts open in Mail and the user presses Send. Passing an email on is its own tool of kind `share`, so it asks first, naming the sender, the subject and every recipient, because the draft carries the original and its attachments. A note with pictures or files is never rewritten, because replacing its body can drop them.
- **Files** use Spotlight (`mdfind`) inside a scope (`[connections.mac] files_scope`, the home folder by default). `~/Library` and hidden folders are never found or read, whatever their case. Text comes out of pdf (PDFKit through JavaScript for Automation), docx, doc, rtf, odt and html (`textutil`), xlsx (zip and XML from the standard library) and eml (`email`).
- **Shortcuts** use the `shortcuts` command.
- **`[connections]` in config.toml** has an on/off switch per connection and `use = "mac"` or `"fake"`. The fake one keeps a made-up world in `~/Milo/fake` for tests, the eval and trying Milo out.
- **Plain step titles** come from the tool and its arguments in `milo.core.wording`: "Looking in your calendar", "Writing a draft to Anna", "Running your shortcut “Lights off”".

## Consequences

- The worker can still script apps through its own shell, around these tools and their questions. The tool descriptions, the server's instructions and `AGENTS.md` tell it not to, and the eval runs Claude Code with its shell off. Taking the shell away from Codex in normal use is a separate decision.
- The first use of each app shows one macOS prompt: Calendars and Reminders for Milo.app, and Automation for Mail and Notes. Until the user allows it, the tool answers with a plain sentence saying where to switch it on.
- Calendar and Reminders need the app. A brain started from a terminal still works, as long as Milo.app is running and connected to it.
- Any process of the same user can talk to `tools.sock` and so reach the calendar without its own permission prompt. Same-user processes can already do most things as the user; writes still go through the action levels.
