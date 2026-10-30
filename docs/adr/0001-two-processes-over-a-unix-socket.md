# 1. A Swift app and a Python brain, talking JSON lines over a Unix socket

Date: 2026-10-29. Status: accepted.

## Context

The overlay, global hotkeys and pasting into other apps need AppKit: a transparent always-on-top panel, NSEvent monitors and CGEvent posting. The models we want (MLX Whisper, OmniVoice on PyTorch) are Python packages.

## Decision

- Run two processes. The app spawns the brain with `uv run`, unless a brain already answers on the socket (development).
- Transport: newline-delimited JSON over `~/Milo/run/brain.sock`. The socket is 0600 inside a 0700 directory, and the brain refuses peers with a different UID.
- Both sides use their standard library only, with no WebSocket or HTTP framework.
- `protocol/messages.json` lists every message, and both test suites decode it.

## Consequences

- Each side can be rebuilt and restarted alone.
- A localhost TCP port would let any local process drive the mic and the LLM. The Unix socket limits that to the user.
- The mic permission belongs to Milo.app, because the brain is its child process. Running the brain from a terminal gives that terminal the mic permission instead.
