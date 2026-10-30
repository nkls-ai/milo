# 7. Computer use: a milo-mac MCP server, checked in the brain, run in the app

Date: 2026-10-30. Status: accepted. Builds on [ADR 2](0002-agent-clis-as-the-llm-harness.md). The tools and the questions changed in [ADR 14](0014-scripts-milo-writes-and-short-questions.md): `sheet_write`, `sheet_read`, `write_document` and `ax_find` come first, and making something new never asks.

## Context

The worker CLIs (Codex, Claude Code) need tools to use the Mac: read a window, press a button, type, click. The permissions belong to Milo.app. The brain owns the parts that need judgement: which task is running, the activity list, asking before risky actions, and telling the character where to fly.

The first plan had the app listen on the hands socket itself. That would have put the safety checks, the steps and the fly target in Swift, away from the task they belong to, and the brain would never see the actions.

## Decision

- `milo.mcp_server` is a small MCP stdio server written with the standard library: initialize, ping, tools/list, tools/call. The worker CLI starts it with the brain's own Python (`sys.executable -m milo.mcp_server --socket ~/Milo/run/hands.sock`). Claude Code gets it through `--mcp-config`, `--strict-mcp-config` and `--allowedTools mcp__milo-mac`, in the same config as the app connections ([ADR 8](0008-app-connections-as-an-mcp-server.md)). Codex gets it through `-c mcp_servers.milo-mac.*` with `default_tools_approval_mode="approve"`, because `codex exec` can't ask and would otherwise refuse every call (checked with codex 0.164).
- The brain listens on `~/Milo/run/hands.sock` (0600 in a 0700 directory, peers of another user refused). One JSON line per request and per answer, see `milo/core/hands.py`.
- `HandsService` checks each call against the tool's schema, asks the app to `describe` what the action would touch (the element under a click, the focused field before typing), classifies it, asks through the `Confirmer` port if needed, logs the action as a step of the running task, starts the session (`hands_session`, the "Milo is working" frame) and sends `fly_to` with the point, then has the app run it through `hands_request` and `hands_result` on the brain socket.
- The tools only work while `TaskRunner` runs a task. Between tasks the socket answers with an error, so nothing else on the Mac can drive it then.
- Tools, in the order their descriptions recommend: `list_apps`, `open_app`, `window_text`, `ax_tree` (element ids), `ax_press`, `ax_set_value`, `run_applescript`, `screenshot`, `click`, `type`, `key`, `scroll`. Clicks and scrolls take pixels of the last screenshot; the app maps them to screen points.
- Asking first (`services/risk.py`): clicks and presses on elements titled send, delete, buy, pay, submit, order, transfer, remove, empty trash and similar words in English and German; shortcuts like cmd+delete and cmd+return; every AppleScript; typing into terminals; any change in System Settings; and a click the app can't name. A word list can't tell what an AppleScript does, so scripts always ask; the question shows short scripts line by line and the step shows the whole script before the user answers.
- Never: typing into or setting password fields, Keychain Access and password managers, security and privacy settings, scripts that mention passwords or the keychain.
- `Confirmer` is a port with one method, `confirm(summary) -> bool`. It is `Approvals` ([ADR 9](0009-approvals-and-action-levels.md)): Yes and No in Milo's bubble and the Milo window (`confirm`, `confirm_answer`, `confirm_done`), or a spoken or typed yes or no. No answer within `[approvals] timeout_s` (60 s) is a no. A first version had its own `ConfirmGate` port and bubble messages; they were folded into Approvals so Milo asks one way.
- Stopping: while the session runs, the app watches global mouse and keyboard input. Milo's own events carry `PasteboardInserter.eventMarker`. `TakeoverDetector` stops on any real key, click or scroll, on esc, and on pointer moves beyond 6 points outside a 0.3 s grace after Milo's own actions. The app sends `hands_stop`, cancels a running AppleScript and refuses further actions. The brain fails the waiting call and every later one in that task with a message telling the worker to stop and report. Input doesn't count while a question waits for its answer.
- `_activity.py` skips milo-mac calls from the CLI's stream, since HandsService logs them with what they touched ("Clicking 'Save' in Microsoft Excel").

## Consequences

- One extra local hop per action (MCP server, brain, app), well under a millisecond, next to seconds per model step.
- Any process of the same user could connect to the hands socket during a task. That's the same trust boundary as the brain socket, and every action still goes through the checks, the step log and the stop key.
- A determined agent can phrase its way around a word list. The brakes are the visible steps, the frame, the questions and the stop on touch, not the list alone.
- `[hands] enabled = false` gives the worker no Mac tools at all; `applescript = false` turns that tool off.
