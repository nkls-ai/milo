# 27. A platform boundary

Date: 2026-10-31. Status: accepted. The number may change: other ADRs written the same day may take 0025 to 0027.

## Context

The user: "We have to think about, when we want to port this from Mac to other computers, how I will do it, so that it's kind of flexible programming-wise. Just make sure that we have that in mind."

[VISION](../VISION.md) says the brain and the protocol "already work anywhere" and only the app is Mac-only. An audit on 2026-10-31 shows that is mostly true of the structure but not of the details. The brain's layers are right: services see ports, engines are adapters picked by name, and only `compose.py` wires concrete things. But macOS leaks into the core in 31 modules. It shows up as AppleScript, bundle ids, the ⌘ key vocabulary, System Settings, `/Applications` and `~/Library`, Mac app names, "on your Mac" in what Milo says, and POSIX-only sockets and locks.

The app is split well too. Every OS call sits behind a port in `app/Sources/MiloKit/Ports.swift`, and only `Sources/Milo/main.swift` names the adapters. About 5,700 lines of `MiloKit` import only Foundation or Combine. Those are the wire types, controllers, `Presence`, `TakeoverDetector`, `ScreenController`, the `Delivery` planner, `KeyCombo`, meetings logic and dictation. The macOS adapters (`Adapters/`, `AppKit/`) are about 3,800 lines. The views are about 10,000.

### The ten hardest couplings, hardest first

1. **Computer use in the app.** `MacHands` (628 lines), `Accessibility`, `MacWindowWatcher` and the `Delivery` planner. They do background delivery per app family (AXPress, AXSelectedText, AXShowMenu), borrow the real pointer with CGEvent, and follow windows with CGWindowList. UI Automation can do the same jobs, but which app takes what in the background has to be found out again, app by app, and this is the part where a mistake does damage.
2. **The character and the overlay.** The wren is CALayers stepped by a display link (`WrenView`) and CGPath drawing (`WrenRig`, `WrenRender`) in an NSPanel that floats, flies (`FlightDriver`) and lets clicks through. About 10,000 lines of views sit on top. None of it runs outside Apple's frameworks, and it is the product's face.
3. **Meeting audio.** `MacMeetingRecorder` taps other apps' audio with a CoreAudio process tap and ScreenCaptureKit. `CoreAudioProcesses` sees which apps use the microphone. Windows has WASAPI process loopback (Windows 10 2004 and later); Linux has PipeWire. Each is its own project.
4. **AppleScript as the worker's scripting language.** `run_applescript` (in `core/hands.py`, run by `MacHands` through `/usr/bin/osascript`), the script builders `services/sheets.py` and `services/documents.py`, the script words in `services/risk.py`, the `tell application` parsing in `services/hands.py`, and Mail, Notes and PDF text in `adapters/connect`.
5. **Risk rules and app identity.** `risk.py` names apps by bundle id (`com.apple.finder`), writes shortcuts in ⌘ terms (`cmd+delete` is the Trash) and treats System Settings as the settings app. `core/types._BUNDLES` and `services/tool_requests` define apps by bundle id. These rules guard money and deletes, so a port needs new data and its own tests, not just new names.
6. **Dictation's keys and paste.** Push-to-talk on a bare modifier (`fn`, `right_option`) through NSEvent monitors, and paste as a synthetic ⌘V (`PasteboardInserter`). Reading the field back after a paste (`AXFocusedText`) feeds ADR 21. A Windows low-level keyboard hook can do all three. Wayland mostly can't.
7. **The local models.** `mlx-whisper` is a hard dependency in `pyproject.toml`, the `mlx_e5` embedder is the default, and OmniVoice defaults to `device = "mps"`. Replacements exist (faster-whisper or whisper.cpp, an ONNX e5, CUDA or CPU), but the quick-pass timing in ARCHITECTURE was tuned on MLX and needs measuring again.
8. **Transport and processes.** Three AF_UNIX sockets (`transport/unix_socket.py`, `tool_client.py`, `mcp_server.py`), the darwin `LOCAL_PEERCRED` peer check, `fcntl.flock` for the one-brain lock (in the brain and in `UVBrainLauncher`), process groups (`start_new_session`, `killpg`) in `adapters/harness/_process.py`, and `os.getuid` checks in `core/secrets.py`. Linux gets all of it free. On Windows, CPython's `socket` has no AF_UNIX and asyncio's Unix servers are Unix-only, so it needs named pipes, ACLs and Job Objects.
9. **Connections and channels.** EventKit runs in the app. Mail and Notes go through AppleScript, plus the `shortcuts` CLI, Spotlight's `mdfind`, `textutil` and PDFKit. The iMessage channel reads `chat.db`. These are adapters already, and each connection has its own switch, so a platform can ship without one.
10. **Words and defaults.** "Mac" in 14 core modules' strings, System Settings paths in errors (`services/hands.py`, `adapters/connect/_osascript.py`, and the app's permission messages), the key names in `config.py` and `settings.py`, `AppleLocale` read by `defaults` in `compose.py`, `pmset` in `adapters/power.py`, and Mac defaults in `config.toml`: `connections = "mac"`, `stt = "mlx_whisper"`, the `say` fallback voice. All mechanical.

### The protocol

Most of `protocol/messages.json` is neutral already: states, bubbles, conversations, confirm, helpers, memory, routines, meetings. Screen points are global with the origin top-left (`fly_to`), and the app converts. `describe` sends control roles as plain words (`button`, `text field`, `menu item`), mapped from `AXButton` and the rest in `Accessibility.swift`. Element ids (`e12`) say nothing about where they came from. What assumes macOS:

- the tool name `run_applescript` in `hands_request`, and its `script` argument;
- `key` combos in `cmd`/`option`, and the same grammar in `ui_config` (`ctrl+option+m`), with push-to-talk names `fn`, `right_option`, `right_command`, `right_control`;
- `bundle` as app identity in `describe` targets, `show_app` and `call_started`;
- `window` (the window server's number) and `pid` in `describe` targets. The brain only passes them back, which is fine as long as it never reads them;
- the `sheet_write`, `sheet_read` and `write_document` app enums (`Numbers`, `TextEdit`, `Pages`);
- no handshake. The brain can't know which platform or which tools the app on the other end has.

## Decision

### The rule

**The brain core and the protocol are platform-neutral. Platform specifics live in brain adapters, picked by platform, and in each native app's adapters.**

- Core means `core/`, `services/`, `memory/`, `proactive/`, `connect/`, `transport/` and the top-level modules. `tests/test_portability.py` enforces it (below).
- A platform is a set of brain adapters. They register by name like every other adapter (`stt.mlx_whisper`, `connect.mac`, `channel.imessage`). Platform data that services need (app names, risk words, key glyphs, how to say "your Mac") comes as one `Platform` value through constructors, built by an adapter such as `adapters/platform/mac.py`.
- `compose.py` is the one place that asks which OS it runs on. It picks the `Platform` and the default adapter names from it. `config.toml` still overrides any of them by name.
- On the wire, everything is plain words or opaque ids. Native enums (AX roles, NSEvent key codes, HRESULTs) never cross the socket. An id the brain can't interpret, such as `pid` or `window`, is only ever echoed back to the app.
- An app says what it is when it connects (`app_hello` below), and the brain offers the worker only the tools that app can run.

### The worker tools

The tools describe intent, not an API. Most already do. The changes:

- **`run_script {language, script}`** replaces `run_applescript`. `language` is one the app announced: `applescript` on the Mac, `powershell` on Windows (which reaches COM, so Excel, Word and Outlook), maybe `bash` on Linux. The tool description lists only those. Every free-form script still asks every time (ADR 14). `[hands] applescript` becomes `[hands] scripts`, keeping the old key as an alias.
- **The script builders become a port.** `sheets.py` and `documents.py` keep their pure parts (cell ranges, number formats, `parse`) in core. The code that writes the script moves behind a `ScriptDialect` port. The AppleScript version is today's code. A Windows version writes PowerShell that drives Excel through COM. The rule from ADR 14 carries over: values go in as data (arguments or JSON on stdin), never pasted into the code.
- **Office JS is not the route.** It runs only inside an Office add-in's task pane, so Milo couldn't create a document or work in the background. COM is the counterpart of AppleScript: it is scriptable, it works in the background, and it is what Excel on Windows exposes. Office JS is only worth it for Excel on the web.
- **Keys use `mod`.** The `key` tool and the config combos accept `mod`, `ctrl`, `alt`, `shift` and `super`. `mod` is ⌘ on the Mac and Ctrl elsewhere. `cmd`, `command` and `option` stay as aliases on the Mac, so old routines and configs keep working. `normalize_combo` moves to core with this vocabulary. The app maps names to its own key codes, as `KeyCombo` does today.
- **Push-to-talk keys** become platform-named choices that the app reports: `fn` and `right_option` on the Mac, `right_ctrl` and `right_alt` on Windows. The brain stores the name and doesn't check it against a Mac list.
- **App identity.** `AppRef(name, bundle)` becomes `AppRef(name, id)`. `id` is the platform's stable id: the bundle id on the Mac, the executable name or AppUserModelID on Windows (`excel.exe`), the desktop file id on Linux. The platform's `AppCatalog` maps ids to canonical keys (`excel`, `word`, `numbers`, `files`, `browser`, `terminal`, `settings`, `passwords`, `notes`, `mail`). Risk, permits and wording compare keys, never raw ids. On the wire `bundle` becomes `app_id`, and the brain reads `bundle` until every app sends the new name.
- **`ax_*` keep their names.** `ax` reads as "accessibility". UI Automation and AT-SPI give the same tree, press, set-value and text, so the names fit every platform. The descriptions stop saying "Mac".
- **`sheet_write` and `write_document`** take their app enums from the catalog: Excel and Numbers on the Mac, Excel on Windows, LibreOffice Calc on Linux if it's ever done.

A new message, **`app_hello`** (app to brain, first line on connect): `{platform: "macos" | "windows" | "linux", version, tools: [...], script_languages: [...], keys: [...]}`. The brain builds the worker's tool list and the `Platform` checks from it. A brain talking to an app that sends no hello assumes today's Mac app.

### A Windows or Linux app

Each OS gets a native shell that speaks the same protocol and has the same ports as `Ports.swift`. The brain runs unchanged next to it with `uv run`. `protocol/messages.json` and the Swift tests over `MiloKit`'s logic are the spec. A new shell ports `MiloController`, `MiloModel`, `Presence`, `TakeoverDetector`, `ScreenController` and `Delivery` by translation and runs the same fixture.

| Port (today) | macOS | Windows | Linux |
|---|---|---|---|
| Overlay panel, flight | NSPanel, CALayer | layered topmost no-activate window (WPF, or WinUI 3 with Win32 interop), Composition/Win2D | X11 override-redirect; Wayland needs layer-shell and may not allow it |
| Hotkeys, push-to-talk | Carbon, NSEvent | `RegisterHotKey`, low-level keyboard hook | X11 `XGrabKey`; Wayland GlobalShortcuts portal (no bare modifiers) |
| Paste | NSPasteboard, CGEvent ⌘V | clipboard, `SendInput` Ctrl+V | wl-clipboard or X11 selection, XTest or the RemoteDesktop portal |
| Read windows, ax tools | AX | UI Automation (Invoke, Value, Text, Scroll patterns) | AT-SPI2 |
| Borrowed mouse and keys | CGEvent | `SendInput` | XTest, libei |
| Screenshots | ScreenCaptureKit | Windows.Graphics.Capture | PipeWire ScreenCast portal |
| Window outline | CGWindowList, AXObserver | `SetWinEventHook`, DWM bounds | X11 only |
| Scripts | `osascript` | PowerShell plus COM | bash (rarely useful) |
| Calendar, Reminders | EventKit | Outlook COM or Microsoft Graph | Evolution Data Server or CalDAV |
| Meeting audio | CoreAudio process tap | WASAPI process loopback | PipeWire monitor streams |
| Permissions | TCC | microphone privacy only; UIA needs no permission but can't reach elevated windows | portals ask per use |
| Brain launcher | `uv run`, `flock` | `uv run`, a named mutex, a Job Object for the process tree | as on the Mac |

**Windows: C# on .NET, with WPF or WinUI 3.** UI Automation, `SendInput`, Graphics.Capture, WASAPI (through NAudio) and COM are all first-class in .NET, and those are the hard rows above. WPF does per-pixel transparent, click-through windows more simply than WinUI 3. The wren gets drawn again in Composition or Win2D from the numbers in `WrenPose` and `WrenRig`.

The other options, briefly:

- **Tauri** (Rust and a web view) could cover Windows and Linux with one UI, at a fraction of Electron's memory. But the overlay becomes HTML in a transparent web view, and every system call is a Rust crate (`windows-rs`), so the hard rows cost the same.
- **Electron** is the easiest UI and the heaviest process: roughly 150 MB more memory, next to a brain that already holds Whisper. That goes against Milo being cheap to keep running, and VISION already chose a native app for polish.
- **Swift on Windows** could reuse `MiloKit`'s Foundation-only logic as it is (Arc for Windows is written that way), but there is no SwiftUI and the WinRT bindings are young. Worth checking again when the port starts. Until then, keeping the logic Foundation-only keeps the option open.

**Linux** comes last. It is the smallest market, and on Wayland global hotkeys on a bare modifier, input injection and a floating overlay depend on portals and the compositor. X11 works. Its brain is nearly free: everything POSIX already runs there.

**Models and voices on other platforms.** Speech to text: a `stt.faster_whisper` or `stt.whisper_cpp` adapter (CPU, CUDA, Vulkan), and the existing ElevenLabs Scribe adapter as is. Windows' own speech recognition is weaker for dictation than Whisper. Embeddings: an ONNX e5 adapter, or `hash`. TTS: ElevenLabs as is, OmniVoice on `cuda` or `cpu`, and Piper as the offline fallback in place of `say`. `sounddevice` (PortAudio) already runs everywhere. `mlx-whisper` gets a `sys_platform == 'darwin'` marker in `pyproject.toml`: MLX has no Windows wheels, so today the brain doesn't install there at all.

### Approvals and risk

`Approvals`, `Permits`, `Scope` and the question flow (describe, classify, ask, act) are neutral and stay. The brain never injects input itself. It always asks the app to act, so the same checks run on every platform. What changes:

- **`risk.py` splits into rules and data.** The rules stay in core: the order of checks, `Verdict`, money words that only a click may answer, for-good words, password and card fields, unnamed clicks. The data moves to `Platform.risk` and is written in canonical app keys: which apps keep a trash, document apps, browsers, password managers, the settings app, terminals and file managers, which shortcuts send or delete, the trash's labels, and per script language the words that run other programs and reach outside the document (AppleScript's `do shell script`; PowerShell's `Start-Process`, `Invoke-Expression`, `Remove-Item`, `WScript.Shell`).
- **Meaning differs, not just names.** On Windows, Delete in Explorer goes to the Recycle Bin (it can be undone), Shift+Delete deletes for good, and Ctrl+Enter or Alt+S sends in Outlook. So each platform's combo table says what a shortcut does there. Nobody translates the Mac table.
- **Platform data can only add.** It can make more things ask or be refused. It can't remove a core never-rule.
- **Tests.** Today's `tests/services/test_risk.py` cases become the Mac data's tests. A shared set in canonical terms ("emptying the trash in the file manager asks every time", "a script that starts another program asks") runs against every platform's data.
- Questions and errors that name a settings path come from the platform ("System Settings › Privacy & Security › Automation" on the Mac), or from the app, which already writes its own permission errors.

### Port order

1. **Now:** this ADR, the guard and the checklist below. No code moves.
2. **The brain on Linux CI.** Mark the Apple-only dependencies, add a Whisper adapter that runs on CPU, run `uv run pytest` on Linux. It's cheap, and it proves the core runs off the Mac.
3. **Empty the allowlist, cheapest first.** `Platform` with the wording and key glyphs. The `AppCatalog` and `AppRef.id`. `mod` keys. `app_hello` and `run_script`. The risk data split. `ScriptDialect` for sheets and documents. Locale and power adapters.
4. **Brain on Windows.** A named-pipe transport adapter, the instance lock, Job Objects in `adapters/harness/_process.py`, Windows CI. Check the Codex and Claude CLIs on Windows at that point.
5. **Windows shell, first version:** the character, the bubble, push-to-talk, dictation and paste, the Milo window, settings and setup. No screen work. That is already most of Milo: talking, dictating, memory, routines and helpers that don't touch the screen.
6. **Windows screen work:** the ax tools on UI Automation, screenshots, borrowing, takeover, Milo's cursor and the window outline. Then Excel through COM.
7. **Windows connections:** Outlook for mail and calendar, Windows Search for files. Then meeting notes on WASAPI.
8. **Linux shell**, X11 first, if people ask for it.

### What to keep doing now

Every new feature passes this list. It is also in [ARCHITECTURE](../ARCHITECTURE.md#portability).

- An OS call in the brain goes into an adapter behind a port. Services get the port.
- Words the user or the model reads in core don't say "Mac", "⌘" or "System Settings". Use neutral words ("your computer", "the settings app"), or take them from the platform once it exists, or let the app write the platform's text, as it does for permission errors today.
- An app the brain must know about goes in the app catalog under a canonical key. Not a bundle id in a service.
- A worker tool is named for what it does (press, fill cells, write a document), never for the API behind it. A tool that only one platform has is announced by that app.
- A protocol field carries plain words, opaque ids or top-left global points. Never a native enum or code.
- Key combos and risk words: new entries say what they mean on that platform. They are data, not rules.
- In the app, logic goes in `MiloKit` files that import only Foundation or Combine. AppKit, AX, CGEvent and ScreenCaptureKit go in `Adapters/` or `AppKit/` behind a port. Don't add AppKit to views or models: `Theme.swift` and seven views already import it.
- An Apple-only Python package gets a `sys_platform == 'darwin'` marker and is imported only inside its adapter's methods.
- `uv run pytest tests/test_portability.py` fails on a new coupling in core. Move it. Add an `ALLOWED` line only with a reason a reviewer would accept.

### The guard

`brain/tests/test_portability.py` parses every core module and checks imports, attribute uses, argv lists and string values. It skips comments and docstrings, so they may still explain macOS. Its rules: `applescript`, `bundle-id`, `mac-path`, `mac-command` (`osascript`, `defaults`, `pmset`, `mdfind` and others as the first word of an argv), `mac-keys`, `mac-settings`, `mac-framework` (MLX, `mps`, AppKit, Spotlight, TCC, `AX…` names), `mac-app` (Finder, Safari, TextEdit, Numbers, Pages, Keynote, iMessage and a few more), `mac-word` ("Mac", "macOS"), `mac-import`, `posix` (`fcntl`, `os.getuid`, `AF_UNIX`, `killpg` and the like) and `platform-branch` (`sys.platform`).

`ALLOWED` started with 62 file-and-rule pairs in 31 files, each with a one-line reason. It is the to-do list. A coupling that moves out has to have its line deleted too, since a line that matches nothing fails the test.

That alone didn't keep it short: by the end of the same day it had grown to 68 lines in 34 files, while this ADR and ARCHITECTURE still said 62 and "only shorter". A stale-line check stops lines from staying behind; nothing stopped new ones. So now `CEILING` holds the count and may only go down, a line added past it needs a `GROWN` entry saying why the coupling can't move yet, and a test checks that ARCHITECTURE states the real count. After the first port work below it is 57 lines in 29 files.

## Update, 2026-10-31: the first port work

Port step 2 and parts of 3 and 4 are done in the brain, with macOS unchanged:

- `mlx` and `mlx-whisper` carry `sys_platform == 'darwin'`. The lock resolves for Linux and Windows without MLX or torch, and the brain imports and its tests pass with the Apple-only packages missing. `.github/workflows/brain.yml` runs the tests on Ubuntu.
- **The `Platform` value** is plain data in `core/platform.py`: the default `use` for `[stt]`, `[tts]`, `[connections]` and `[chat]`, the fallback voice and the embedder. `adapters/platform.py` holds one per OS and is the one place that asks which OS this is (it moved out of compose so compose has no `sys.platform` either). Compose, the connections server and the consolidator load `config.toml` with it. macOS gets today's engines; Linux and Windows get ElevenLabs for hearing (a new whole-recording Scribe transcriber for `[stt] use`) and voice, the hash embedder, no fallback voice and the new `none` connections. The template names none of the Mac engines any more; configs that name them stay valid. The wording, risk data and app catalog this ADR puts in `Platform` are still to come.
- **`milo.system`** holds the POSIX calls the core made itself: secret-file ownership and modes, the instance lock, the harness CLI's process group and kill, the process table, and the local sockets (bind, connect, peer check). `windows.py` has the same functions, each raising NotImplementedError with what Windows would use, and a test keeps the two in step. Port step 4 is filling in that one file.
- **Dates** come from `core/dates.py` in English words (now `core/words/dates.py`, ADR 0034); the guard's new `posix-strftime` rule catches `%-d` and `%#d`, which Windows' strftime rejects.
- **The chat model** can be any OpenAI-style API (`openai_compat`: OpenAI, OpenRouter, Ollama, LM Studio), so a port isn't tied to the Claude CLI for talking.
- The region for money formats moved from compose into `adapters/region.py`.

## Consequences

- Porting stops being a rewrite of the brain. It becomes three pieces of work: a native shell per OS, a set of brain adapters per OS, and the platform data for risk and the app catalog.
- New core code can't quietly add a macOS dependency. The cost is an allowlist line and a reason, and the reviewer sees both.
- The guard reads words, so it can't tell "Mac" the computer from a Mac-only behaviour. It errs on the side of flagging. A false hit costs one line in `ALLOWED`.
- The ADR changes nothing yet. `run_script`, `mod`, `AppRef.id` and `app_hello` are protocol changes that need both sides and an alias period, and they come in step 3, after the work going on now in `hands.py`, approvals and the overlay has landed.
- `eval/` (developer tools that drive the real Mac app) and `adapters/` are outside the guard on purpose.
