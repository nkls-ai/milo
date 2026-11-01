# Windows and Linux validation

Local validation on 2026-11-01 used Windows 11 and Ubuntu 20.04 in WSL2/WSLg (glibc 2.31).
The standalone builds contain Python and their desktop/model libraries; Python and uv are not required to run
them. Model weights are cached separately. Chat/helper providers still require their normal account setup.

The final full runs passed **2,917 tests on Windows** (136 skipped) and **2,930 on Linux** (123 skipped).
Both standalone builds then passed UI rendering, native capability diagnostics, local model inference and a
real brain subprocess conversation with persisted history. Linux's packaged Office actor also passed the
eight-check LibreOffice integration run.

## Reproducible checks

| Boundary | Check and evidence |
| --- | --- |
| Brain and services | Full suites: `.tools/complete-suite-windows.log`, `.tools/complete-suite-linux.log` |
| Packaged UI | `Milo-runtime[.exe] --smoke-test --screenshot …` renders the real window and floating overlay |
| QML shell | `milo.desktop.main --smoke-test`: scripted scenes in `build/qml-shots/smoke/`; `tests/desktop/test_qml_window.py` renders every page to `build/qml-shots/window/` and fails on any QML warning |
| Native desktop | `scripts/native-desktop-e2e.py`: nine checks on both OSes, including real Unicode paste, accessibility, capture, correction learning, middle insertion Undo and selection replacement Undo; `build/native-e2e-{windows,linux}/native-e2e.json` |
| Meeting loopback | `scripts/meeting-loopback-e2e.py`: actual Windows WASAPI and Linux Pulse monitor capture of generated tones; `build/meeting-loopback-e2e-{windows,linux}.json` |
| Packaged models | `Milo-runtime[.exe] --check-models`: real multilingual semantic recall, Whisper transcription with word times, and generated English/German Pocket speech; `build/model-check-{windows,linux}-frozen/results.json` |
| Windows Office | `scripts/office-e2e.py`: installed Excel/Word, dedicated disposable instances, real arrays/formulas/styles, existing-target verification and Unicode documents; `build/office-e2e-windows.json` |
| Linux Office | `scripts/uno-office-e2e.py --runtime /path/to/Milo-runtime`: eight checks against installed LibreOffice 6.4.7.2, including the frozen actor and bundled bridge; `build/uno-office-frozen-e2e/results.json` |
| Calendar/tasks | `brain/tests/adapters/test_caldav_e2e.py`: isolated local Radicale server, including one-occurrence recurrence edits |
| Packaged brain | `MILO_E2E_EXECUTABLE=/path/to/Milo-runtime … pytest brain/tests/eval/test_portable_brain_e2e.py`: real subprocess, authenticated/native IPC, HTTP streaming, history and `scripts/drive-milo.py` |

The brain E2E replaces the remote model with a local HTTP fixture. Model checks use actual local weights and
generated speech, without a microphone or playback. Native desktop tests manipulate only their disposable
fixture window. Office checks use disposable documents and close only their own instances/profiles. Calendar
checks use disposable accounts. No personal provider credentials or documents are needed.

## Scope and limits

The subsequent Codex/desktop fixes add an independently selectable Codex CLI talking provider, with actual
streamed multi-turn brain checks on Windows and Linux. Reports: `build/codex-brain-{windows,linux}.json`.
`scripts/codex-chat-e2e.py` repeats this check using an existing CLI login; the implementation uses the
[official Codex app-server protocol](https://learn.chatgpt.com/docs/app-server).

The complete dictation pipeline was also checked using real global modifier hooks, a virtual WAV microphone,
Whisper small, brain IPC, native paste into an owned external window, and Undo. Reports are in
`build/dictation-desktop-{windows,linux}/report.json`. Linux uses an isolated X11 desktop under Xvfb to avoid
WSLg host focus competing with the user's Windows applications. No personal microphone audio is recorded.

Desktop single-instance ownership prevents duplicate windows/hooks. Restart regression checks cover repeated
Save/restart and reclaiming stale endpoint files; the Windows bundle explicitly includes `win32timezone`,
which pywin32 loads dynamically when opening an existing endpoint. The light/dark theme, text selection,
streamed chat row preservation, and Talk/Dictate controls have Qt rendering/interaction tests.

The brain, protocol, service logic, memory and approval rules are shared with macOS. Windows/Linux share the
Qt interface and vector animation rig. Native accessibility/input, file security, IPC and Office APIs stay
behind adapters; the existing Mac Swift frontend and Apple integrations remain available.

Full Linux automation currently targets X11. Wayland compositor portals are still needed for full global
input/capture parity. Windows elevation boundaries and password fields remain protected. Apple Home,
Shortcuts, iMessage and FaceTime need Apple services; supported alternatives are described in the setup docs.
Outlook account behavior has contract tests, but a personal Outlook profile was not used in this validation.
Live Office Undo uses the recorded helper flow; Mac Excel workbook-copy restore has not been ported to COM/UNO.
The Mac Swift suite cannot be executed on this Windows/WSL host. These are explicit limits, rather than a
claim that every native Mac service exists on every OS.

Builds are unsigned. Linux distributions must meet the build's glibc baseline. Preserve executable modes and
shared-library links by distributing the Linux folder in a tar archive. See [Windows/Linux setup](windows-linux.md)
for dependencies, provider setup, keyboard configuration, build and verification commands.
