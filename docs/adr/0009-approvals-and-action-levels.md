# 9. Approvals: four action levels and one confirm flow

Date: 2026-10-30. Status: accepted. How often a question about work in an app asks, Allow always and auto mode: [ADR 22](0022-one-question-per-piece-of-work.md). The line between asking and not asking is now whether it can be undone, and money asks instead of being refused: [ADR 23](0023-stop-for-what-cant-be-undone.md).

## Context

Once Milo can reach mail, shortcuts and soon the screen, he needs brakes. The vision names three levels (just do it, ask first, never) and the character sheet says how he asks: one plain yes-or-no question that names the thing and the consequence, and nothing for things that can be undone. Computer use (track A) needs the same gate.

## Decision

- **Levels** (`ActionLevel`): `read` (just do it), `change` (do it, it shows in the window and can be undone), `ask_first` and `never`.
- **Kinds of action** map to levels in `[approvals.levels]`. Defaults: read and draft are `read`; change is `change`; send, share (anything going to another person), delete, buy and shortcut are `ask_first`; password, money and security are `never`, and config.toml can't change those three. An unknown kind is `ask_first`.
- **One service, `Approvals`,** in the brain. `approve(kind, summary)` applies the level and asks if needed; `confirm(summary)` always asks and is the `Confirmer` port any service or tool can take. One question at a time; later ones wait.
- **Asking** shows the question in the bubble and in a bar above the Milo window's text field, each with Yes and No (`confirm`), speaks it unless the user is mid-turn, and adds it to the transcript. A click (`confirm_answer`), or a short spoken or typed "yes"/"no" while the question is still what the bubble shows, answers it. After `[approvals] timeout_s` (60 s) it is a no. The app hears the end with `confirm_done`.
- **Other processes** ask over the brain's tool socket (`run/tools.sock`, 0600, same user only), one JSON object per line: `{"id": 1, "op": "approve", "kind": "send", "summary": "..."}` returns `{"id": 1, "ok": true, "result": {"allowed": false, "level": "ask_first", "answer": "no"}}`, and `{"op": "confirm", "summary": "..."}` returns `{"result": {"yes": true}}`.

## Consequences

- Computer use ([ADR 7](0007-computer-use-through-the-brain.md)) asks through this flow too: `HandsService` takes `Approvals` as its `Confirmer` and calls `confirm(summary)` when its own classifier (`services/risk.py`) says to ask. That classifier keeps deciding for screen actions, so `[approvals.levels]` can't loosen them, and its never-rules (password fields, security settings) stay. The stand-in it used before, `BubbleConfirm` with its own `confirm_request`, `confirm_result` and `confirm_end` messages, is gone.
- A spoken "yes" only counts while the question is the last thing Milo showed. If a reply, a task result or a nudge came in between, only the buttons answer it, so a "yes" meant for something else can't approve an action.
- Asking too often teaches people to say yes without reading. The defaults ask only for things that leave the Mac or can't be undone.
