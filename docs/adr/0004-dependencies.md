# 4. Dependencies

Date: 2026-10-29. Status: accepted.

The standard library handles everything else: transport (asyncio Unix sockets), config (tomllib), WAV I/O (wave) and the Swift side (Foundation, AppKit, SwiftUI). We take a dependency only where writing it ourselves would be unreasonable:

| Package | Why | License |
|---|---|---|
| numpy | Audio buffers. Every audio and ML package needs it anyway. | BSD |
| sounddevice | Mic capture and playback through PortAudio, with callbacks for level metering. | MIT |
| mlx-whisper (Apple ml-explore) | Whisper on the Apple GPU without a server. Transcribes faster than real time on an M3. | MIT |
| omnivoice (k2-fsa), optional extra | Local neural TTS with voice design and 3–10 s voice cloning. Pulls in torch, about 1 GB. Measured on an M3 with MPS: 0.65x real time at 16 steps. | Apache-2.0 |

All were released within the last year. OmniVoice is an optional extra, so Milo also runs with macOS `say`. `[tts] fallback = "say"` takes over automatically if OmniVoice fails to load.

The milo-mac MCP server is standard library too. MCP over stdio needs four JSON-RPC methods, which is about 100 lines, and the official SDK would pull in pydantic, anyio and an HTTP stack for a process the worker CLI starts on every task. The Swift side uses ScreenCaptureKit, ApplicationServices and Carbon from the SDK.

Dev only: pytest.

2026-10-30, app connections ([ADR 8](0008-app-connections-as-an-mcp-server.md)): no new package. The MCP server is JSON-RPC from the standard library instead of the `mcp` SDK, which would bring pydantic, anyio and an HTTP stack. Text comes out of documents through macOS itself: PDFKit via `osascript -l JavaScript`, `textutil` for Word, RTF and HTML, and `zipfile` plus `xml.etree` for xlsx. Calendar and Reminders use EventKit, which ships with macOS.
