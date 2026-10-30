# 5. A streaming chat model for talk, the agent harness for tasks

Date: 2026-10-30. Status: accepted. Narrows [ADR 2](0002-agent-clis-as-the-llm-harness.md).

## Context

Every turn went through `codex exec`. That carries about 17k fixed tokens of agent instructions and tool definitions, and a turn measured 62k to 84k input tokens once memory files were involved. Answers took several seconds, and Milo only started speaking after the whole reply and its first sentence of audio were ready. Talking to him felt like sending email.

Users also expect to cut a voice assistant off. Pressing the talk key while Milo spoke stopped the audio, but a reply still being generated came back and was spoken anyway.

## Decision

- User turns go to a `LiveModel` (`[chat] use = "claude_live"`): one persistent `claude -p` process in stream-json mode, with no tools, Sonnet at low effort. The conversation stays in that process between turns and starts fresh after `conversation_idle_reset_s` of silence. A turn costs about 600 tokens, and the first text arrives after 1 to 2 s. The process starts at boot with the system prompt, so the first turn doesn't pay for it.
- The reply is plain text with inline tags: an opening `[emotion]`, plus `<remember>`, `<reminder>` and `<task>`. They replace the JSON schema, which can't be spoken until it is complete. The brain applies remember and reminder tags itself, so memory and reminders cost no agent call.
- `<task>` hands real work to the existing agent harness (Codex by default) in the background. It keeps its sandbox, file tools and `AGENTS.md`, and its `say` is spoken when it finishes.
- Speech streams onto one open audio stream, and the next piece synthesizes while the current one plays. The first piece is a short clause; later pieces are sized to what the voice can synthesize before the queued audio runs out. Measured on the M3: each OmniVoice call costs about 1 s plus about 0.5 s per second of audio at 6 steps, so pieces under ~45 characters can't keep up and are avoided.
- The talk key interrupts everything: the model's reply, the audio and any queued chunks. A new turn does the same.
- OmniVoice speaks with one voice, designed once from `instruct` and saved as a clone reference, so every chunk of every reply sounds like the same Milo. It runs at 6 diffusion steps: Whisper transcribes 6-step speech as cleanly as 8-step speech, 5 starts dropping words and 4 garbles longer sentences.
- The heartbeat is unchanged: local rules, zero tokens by default.

## Consequences

- Small talk is fast and cheap. Anything needing files or the web takes the slow path, and Milo says so ("On it, I'll tell you when it's done.") instead of going quiet.
- Two models can disagree about what happened. The chat model learns a task's result through a note on the next user message, and the agent learns about the chat only through the task description.
- The speech bubble shows each chunk when its audio is queued, so it can run a chunk ahead of the voice.
- Users with an older `~/Milo/config.toml` keep working: a missing `[chat]` section means `claude_live`, and the retired `[harness] conversation_idle_reset_s` is ignored with a warning.
