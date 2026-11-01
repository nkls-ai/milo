# Milo on Windows and Linux

The shared desktop is `brain/src/milo/desktop/`, built with Qt for Python. It uses the same brain, workspace,
conversation history, protocol, approval rules and helper services as the native Mac app. OS calls live behind
the desktop accessibility/input interfaces and `milo.system`; models remain registered brain adapters.

The existing Swift Mac app remains supported. The Qt desktop also runs on macOS for development, but use the
Swift app there for Apple accessibility and app integrations. Moving the Mac interface to Qt is a separate
migration; the brain and new non-Apple integrations already share their implementation.

## Run from a checkout

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.12 (uv can supply Python).
Install Claude Code and/or Codex as on the Mac, and sign in using their own terminal/browser flows. Choose
Claude CLI, Codex CLI, or an OpenAI-compatible local or hosted endpoint as the talking provider. A Codex-only
setup can both talk and run helpers; Claude is optional. The default remains Claude until you choose another provider.
No credentials belong in this repository or in chat.

Windows, from the checkout:

```powershell
uv sync --project brain --extra desktop
uv run --project brain --extra desktop milo-desktop
```

Linux, on a desktop session:

```sh
# Debian/Ubuntu desktop runtime and build dependencies:
sudo apt-get install libportaudio2 libpulse0 libatspi2.0-0 at-spi2-core libxcb-cursor0 \
  libegl1 libopengl0 libxkbcommon0 gcc linux-libc-dev
uv sync --project brain --extra desktop
uv run --project brain --extra desktop milo-desktop
```

`scripts/start-desktop.ps1` and `sh scripts/start-desktop.sh` provide the same launch command. The app starts its
own brain, or joins a brain already running in the workspace. Restart and Quit only stop the brain it started.
Do not run the Windows and Linux brains against the same live workspace simultaneously; their OS locks are
different. Use separate `MILO_HOME` folders when testing both.

Hold **Right Control** to dictate and **Right Alt** to talk. The keys work as on the Mac: recording starts the
moment the key goes down and shows after a short hold; a quick tap does nothing; a double tap locks recording on
until you press the key again; Escape cancels a recording; any other key during a hold makes it an ordinary
shortcut. The desktop also has hold-to-talk/dictate buttons. Keys remain configurable. Windows keyboards often
use Right Alt as AltGr; choose another key in Settings when that conflicts with typing. A lone Right Alt (or
Windows key) press is masked, so letting it go doesn't open the app's menu bar or Start.

Speech stays local: faster-whisper and the existing Pocket TTS voice. Models download at the first warm-up and are
cached. With an NVIDIA GPU, install its runtime libraries (about 1 GB, into the project environment only):

```sh
uv sync --project brain --extra desktop --extra cuda
```

The default `[stt.faster_whisper] device = "auto"` then uses the GPU with `large-v3-turbo` and a `small` preview
(on an RTX 2070 the text is ready about 0.0–0.3 s after you let go). Without the GPU libraries, or if the GPU
fails to load, it uses the CPU by itself, with `small` and a `base` preview (several seconds after release on a
typical desktop CPU; setting `language` saves a detection pass). `model`, `preview_model`, `device` and
`compute_type` can each be set explicitly. The Linux dependency lock selects CPU PyTorch to avoid downloading GPU
libraries for Pocket.

Memory also stays local. Windows and Linux use quantized multilingual-e5-small
through ONNX Runtime on the CPU for semantic recall, with the same query/passage
convention as the Mac's e5 engine. Its model downloads at first warm-up and is
cached; text being embedded is not sent to the model host. The default uses two
CPU threads so memory leaves capacity for speech and the desktop.

For a small setup that does not download a memory model, explicitly set
`[memory] embedder = "hash"`. That selects word-based recall rather than semantic
embeddings. Switching engines automatically rebuilds the cached search index
from the existing memory files; those files are preserved. Model and thread
options live under `[memory.onnx_e5]` in `config.toml`.

## Desktop integration

Windows uses UI Automation, native input and clipboard APIs, and WASAPI speaker loopback for meetings. Linux
uses AT-SPI2, X11 input, Qt capture and the PulseAudio/PipeWire compatibility monitor. Meeting audio is split
into microphone and system tracks, stored as private 16 kHz chunks; pausing writes silence.

An X11 session provides the most complete Linux desktop support. On Wayland, accessibility is available where
apps export it, but global modifier hooks, synthetic input, arbitrary screenshots and overlays are controlled
by the compositor. The app reports unavailable operations instead of claiming they worked. Compositor portal
support is still required for full Wayland parity.

Dictation pastes where the keyboard focus is when the words arrive, as on the Mac, also into browsers, Electron
apps, editors and terminals that don't report a text field to accessibility. It is refused in password fields
and password managers, in Milo's own window, for line breaks into a terminal, and into an app running as
administrator while Milo isn't (Windows drops the keys without an error; the words stay on the clipboard and in
Milo's window to copy). The paste is Ctrl+V with no other modifier held, and the clipboard comes back afterwards,
kept out of Windows clipboard history. When the field can be verified, a space is added after a word and Undo
removes the insertion while that exact field still contains it. Text Milo writes for you while talking
(`text.write`) still goes only into the exact field you were in. Windows UI Automation cannot control an elevated
application from an unelevated Milo process. `~/Milo/logs/desktop.log` records each key phase and paste outcome
(never the words).

The default `desktop` connections backend provides protected, bounded file search/read/list/move. PDF, DOCX,
ODT, HTML, XLSX, EML and common text files are readable. Files are never moved into shared/synced folders or over
an existing file. Calendar/tasks, mail and notes need a configured provider: see
[desktop connections](desktop-connections.md) for Outlook and CalDAV.

Structured Office tools use live Excel/Word through COM on Windows and LibreOffice
Calc/Writer through UNO on Linux. Linux uses a separate Milo workspace profile;
it does not attach to an arbitrary LibreOffice instance already using your normal
profile. New Linux documents are saved under `~/Milo/work/created/`, and these
LibreOffice windows survive Milo's Stop or Quit. Without a live integration,
new XLSX/DOCX file creation remains available. See [desktop Office](desktop-office.md)
for installation requirements, target-change checks and actual integration tests.

Use **Connections & models…** in the window, Settings or tray menu to choose
Claude CLI, Codex CLI, an OpenAI-compatible/local API, or dictation only, and to select or disable
helper CLIs. No setting changes until you press **Save and restart brain**.
CLI sign-ins happen in your own terminal/browser. An API key goes alone in its file under `~/Milo/secrets/`:
paste it in Connections & models, which writes that file for you, or create the file yourself.

The shared Settings report also offers a talking-provider selector on Windows, Linux and the native Mac app.
Changing it requires restarting the brain. For Codex, run `codex login` in your own terminal first, then choose
**Codex CLI**. The equivalent configuration is:

```toml
[chat]
use = "codex_live"

[harness]
use = "codex"
```

The talking model inherits your Codex CLI model selection when `[chat.codex_live] model` is empty. Talking and
helpers are separate choices: either can use Claude or Codex independently. **Dictation only** sets
`[chat] use = "none"`; it does not change your helper choice. For an OpenAI-compatible endpoint, configure
its URL/model/key-file reference in **Connections & models…** or `[chat.openai_compat]` before restarting.

Apple Home, Apple Shortcuts, iMessage and FaceTime are Apple-only integrations. Home Assistant and Telegram
remain shared alternatives. Outlook requires Classic Outlook and its configured desktop profile; CalDAV
requires the user's server/account. Neither is silently enabled.

## Plug in any model

Milo can talk through any OpenAI-style chat API: a model on your own computer, or a hosted one. In
**Connections & models…**, choose **OpenAI-compatible API or local server** under **Talking**, then pick where the
model runs:

| Preset | API base URL | Key |
|---|---|---|
| Ollama | `http://localhost:11434/v1` | none |
| LM Studio | `http://localhost:1234/v1` | none |
| OpenAI | `https://api.openai.com/v1` | `openai.key` |
| OpenRouter | `https://openrouter.ai/api/v1` | `openrouter.key` |
| Groq | `https://api.groq.com/openai/v1` | `groq.key` |
| Custom | any address that ends where `/chat/completions` begins | a file name you choose, or none |

- **On this computer** (Ollama, LM Studio): Milo looks for the server by itself and says *Found Ollama on this
  computer with 4 models*, or *Ollama isn't running on this computer. Start it, then look again.* Its installed
  models appear under **Model**; click one. **Look again** checks once more.
- **Hosted** (OpenAI, OpenRouter, Groq): paste your key into **API key**. **List models** shows the provider's
  models (type to filter). The key is saved alone in `~/Milo/secrets/<file>` when you save, never in
  `config.toml`, never logged, and the field is empty again afterwards.
- **Test** asks the model for one short reply through the same code Milo talks with, and shows *Answered in
  420 ms* or what to change: a key that was turned down, a model the server doesn't know, a server that isn't
  running.
- **Save and restart brain** writes only `[chat] use` and `base_url`, `model`, `key_ref` in `[chat.openai_compat]`,
  keeping your comments.

The model you talk with doesn't do helper jobs: those still run through Claude or Codex CLI. Without either,
choose **Disabled** under **Helper jobs** and Milo only talks. If the server goes away later, Milo says so in his
bubble (*I can't reach localhost:11434…*) instead of a generic error. Servers that reject OpenAI's extra request
fields (`stream_options`, `prompt_cache_key`) are asked again without them. The preset list lives in one place,
`brain/src/milo/adapters/harness/openai_presets.py`.

## Build a standalone folder

Build on the target OS; PyInstaller is not a cross-compiler:

```sh
uv sync --project brain --extra desktop --extra build
uv run --project brain --no-sync python scripts/build-desktop.py
```

Copy the complete `dist/Milo/` folder. Windows starts `Milo.exe`; Linux starts `Milo`. The adjacent
`Milo-runtime[.exe]` and `_internal/` are part of the app, not optional files. Python is bundled; uv is not needed to run it. The
user's chat/helper CLI and speech weights are still configured/downloaded as above. The build is unsigned.

Linux binaries target the builder's glibc baseline: CI builds on Ubuntu 22.04; the local WSL build was produced
on Ubuntu 20.04. Use a build made on your distribution or an older compatible distribution. Keep executable
permissions when copying the folder (`chmod +x Milo Milo-runtime` if a ZIP download stripped them).

Both executables share one dispatcher. The runtime also starts the brain, the whitelisted MCP tool modules,
and the isolated Office actor, so these frozen helpers use the bundled Python interpreter.

## Validation

```sh
uv run --project brain --extra desktop pytest brain/tests -q
uv run --project brain --extra desktop milo-desktop --smoke-test --screenshot build/desktop-smoke.png
uv run --project brain --extra desktop milo-desktop --diagnose
uv run --project brain --extra desktop python scripts/native-desktop-e2e.py
uv run --project brain --extra desktop python scripts/meeting-loopback-e2e.py
```

The native E2E opens only its disposable test window and checks real Unicode paste, exact-field Undo,
accessibility, and screenshot capture. The loopback check plays two quiet generated tones, opens no microphone,
and saves no captured audio. The real brain-process test uses a local HTTP model fixture and a temporary
workspace; CalDAV E2E uses an isolated local Radicale server and disposable account.

`scripts/local-speech-e2e.py --model small` generates a Windows SAPI fixture and runs the actual local speech
engine. Linux can use the same WAV with `--audio`. It reports measured timing and word timestamps instead of
assuming Mac latency. `scripts/drive-milo.py` can drive a running app on every supported OS.

The packaged runtime can also exercise its real local models, without opening a microphone or playing audio:

```sh
Milo-runtime --check-models --model-check-audio path/to/speech.wav --model-check-output model-check
```

Use `Milo-runtime.exe` on Windows. The check downloads missing weights, verifies multilingual semantic recall,
transcribes the supplied PCM WAV (optional), and saves generated English/German voice samples plus a JSON report.
The same check passed inside both local standalone builds. To verify the Linux bundled Office bridge too, use
`scripts/uno-office-e2e.py --runtime /path/to/Milo-runtime` with the source test environment.

For WSLg, start accessibility tests in a session bus if there is no desktop session bus:

```sh
QT_QPA_PLATFORM=xcb dbus-run-session -- uv run --project brain --extra desktop \
  python scripts/native-desktop-e2e.py
```

Build and test environments and build outputs are best kept on the Linux filesystem, rather than under `/mnt/c`,
so Linux permissions, shared-library links and file locking are real. For example, build with
`--output /tmp/milo-dist`, then archive with `tar -czf Milo-Linux.tar.gz -C /tmp/milo-dist Milo` and copy that
archive to Windows. Extract it on Linux before launching.

The desktop UI is Qt Quick (QML through PySide6) and follows the Mac app's look and motion: one design source,
`protocol/design.json`, springs for every move, and the same voice-capsule rules (`protocol/voice_phases.json`).
For a still Milo, set `MILO_REDUCED_MOTION=1` before launching; `MILO_APPEARANCE=dark|light` overrides the system's.
To render the real window and overlays with a scripted brain, without devices, hooks or models:

```sh
uv run --project brain --extra desktop python -m milo.desktop.main --smoke-test --screenshot build/qml-shots/smoke
```

It saves one picture per scene (a turn, a dictation, helpers, a question) and fails on any QML warning.
