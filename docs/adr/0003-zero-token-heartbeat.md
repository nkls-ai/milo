# 3. The heartbeat runs local rules and never calls the LLM by default

Date: 2026-10-29. Status: accepted.

## Context

Proactive assistants that run an LLM turn on a timer bill tokens around the clock. OpenClaw users report exactly this. A Codex turn here costs 19k+ input tokens, so a 30 s tick would cost millions of tokens a day.

## Decision

- A tick costs a `stat()` of `reminders.md`, some in-memory rule checks and one small state write.
- Rules are classes registered by name: reminders, morning, late_night, welcome_back, focus_break. `[heartbeat] rules` enables them, and their order sets precedence.
- Rules give fixed wording. A rule may attach an `llm_prompt` for nicer wording, which is used only while `DailyBudget` allows it. The default budget is 0 calls per day.
- Spoken voluntary nudges go through a rate limiter (min gap, per-hour cap). Nothing is spoken while a quiet app (Zoom, FaceTime, ...) is frontmost. Reminders still show silently.
- Reminders are set by the agent writing a line to `reminders.md`, so the only token cost is the conversation turn that created them.

## Consequences

`tests/proactive` simulates 24 h of ticks with the shipped config and asserts zero harness calls. Smarter proactivity (calendar, screen context) has to arrive as more local signals feeding rules, not as an LLM loop.
