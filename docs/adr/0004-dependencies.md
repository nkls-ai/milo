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

Dev only: pytest.
