# Plan: the Mac on the shared QML app

Not started. Today the Mac runs the SwiftUI app in `app/`; Windows and Linux run the QML app in
`milo/desktop/`. The goal is one UI everywhere: the Mac gets a `mac.py` next to `windows.py` and `linux.py`,
and `app/` is retired once the QML app feels as good there.

Nothing above the platform boundary changes: the QML screens, the view models, `native.py`'s focus and paste
policy, `protocol/design.json` and the brain stay as they are. The Mac only has to implement the Protocols in
`ports.py`, through PyObjC (`pyobjc-framework-Quartz`, `-ApplicationServices`, `-EventKit`,
`-ScreenCaptureKit`, `-AVFoundation`), added as a `sys_platform == 'darwin'` dependency with `uv add`.

## What to build

Each row is a Swift file that already does the job; port its behaviour, not its structure.

| Port (`ports.py`) | Mac implementation | Swift reference |
|---|---|---|
| `HotkeySource` | CGEventTap on `kCGEventFlagsChanged`/`keyDown`: fn alone, right ⌥ held, double taps, Esc; drop events Milo injected (`kCGEventSourceUserData` marker, like Windows' `dwExtraInfo`) | `Hotkeys/PushToTalk.swift`, `Adapters/NSEventKeySource.swift`, `CarbonHotkey.swift` |
| `KeyPlatform` (`keys()`) | `paste_keys` as ⌘V via `CGEventPost`; `type_text` via `CGEventKeyboardSetUnicodeString`; `idle_s` from `CGEventSourceSecondsSinceLastEventType`; `blocked` always "" | `Adapters/PasteboardInserter.swift` |
| `Accessibility` backend (`native.py`) | AX API: focused element, role, `AXSecureTextField` → secure, value/selection range, set focus back, app name from `NSRunningApplication` | `Adapters/AXFocusedText.swift`, `AXFieldProbe.swift`, `Accessibility.swift` |
| clipboard | `NSPasteboard` with the snapshot/restore and the "transient/concealed" types so clipboard managers skip it | `Adapters/PasteboardInserter.swift` |
| `ScreenCapture` | ScreenCaptureKit (macOS 14+): window under the pointer or whole screen | `Adapters/ScreenShots.swift` |
| `DesktopHands` | Clicks, scrolls and shortcuts via CGEvent; window list via `CGWindowListCopyWindowInfo`; open apps/items via `NSWorkspace` | `Adapters/MacHands.swift`, `MacItemOpener.swift`, `MacWindowWatcher.swift`, `Screen/*` |
| `MeetingAudio` | Process tap on CoreAudio (macOS 14.2+) for the other side of a call; mic through the existing recorder | `Adapters/MacMeetingRecorder.swift`, `CoreAudioProcesses.swift`, `Meetings/CallDetector.swift` |
| connections | Calendars/Reminders via EventKit, Contacts, Mail/Notes via AppleScript; check what `milo/adapters/connect/mac.py` already covers first | `Adapters/EventKitConnections.swift`, `SystemContactBook.swift`, `MacAppAccess.swift` |
| permissions (setup page) | Microphone (`AVCaptureDevice`), Accessibility (`AXIsProcessTrustedWithOptions`), Screen Recording (`CGPreflightScreenCaptureAccess`/`CGRequestScreenCaptureAccess`), Automation per app; deep links into System Settings | `Adapters/SystemPermissions.swift`, `SystemAccessibilityPermission.swift`, `Access/*` |

## The overlay window

Qt gives the frameless, transparent, always-on-top window; a few NSWindow settings (via `winId()` → `NSView`
→ `window`) make it behave like `AppKit/OverlayPanel.swift`:

- non-activating (`NSWindowStyleMaskNonactivatingPanel`, Qt `Tool` already creates an NSPanel), so Milo never
  takes the focus from the field you dictate into;
- `collectionBehavior`: `canJoinAllSpaces | fullScreenAuxiliary | stationary`, so he shows over full-screen apps
  and on every Space;
- level `NSStatusWindowLevel`; `hasShadow = false` (QML draws the shadows);
- click-through outside his surfaces: `setMask` as on Windows, or `ignoresMouseEvents` toggled by the tracker.

`overlay.py` places the window with `screenAt(QCursor.pos())`; on the Mac `availableGeometry` already excludes the
menu bar and Dock, so `corner()` works unchanged. The cursor overlay and working outline
(`CursorOverlay.swift`, `WorkingOutline.swift`) need the same treatment.

## Feel

- Vibrancy: Swift uses `NSVisualEffectView` behind the bubble and capsule. Either keep QML's own blur (already
  used on Windows) or put a visual effect view behind the window; compare side by side first.
- Fonts: `Theme.qml` already falls back to "SF Pro Text"/"SF Pro Rounded"; check they resolve (`Qt.fontFamilies()`
  may list ".AppleSystemUIFont" instead).
- Key labels: `key_label`/`combo_label` already say "Right Option" and "Control-Option-M" on a Mac.
- Menu bar item: `QSystemTrayIcon` gives an NSStatusItem; use a template (monochrome) icon.
- Reduced motion and dark mode: `design.py` reads them through Qt; check they follow System Settings live.

## Packaging

- PyInstaller `.app` (`BUNDLE`) with `LSUIElement` (no Dock icon), `NSMicrophoneUsageDescription`,
  `NSAppleEventsUsageDescription` and the other usage strings from `app/` 's Info.plist.
- Sign with the existing "Milo Dev" identity (`scripts/make-signing-identity.sh`) so permissions survive
  rebuilds; hardened runtime plus the entitlements the Swift app has.
- `scripts/build-app.sh` and `install.sh` switch from `swift build` to this build; Apple silicon only, as now.
- The brain is started by the desktop shell as on Windows (replaces `UVBrainLauncher.swift`).

## Order of work

1. `keys()`, the Accessibility backend and the clipboard: dictation works end to end.
2. `HotkeySource`: fn and right ⌥.
3. Overlay window flags; check over a full-screen app and across Spaces.
4. Permissions page, then screen capture and hands.
5. Connections and meeting audio.
6. Packaging and signing; `install.sh`.
7. Side by side with the Swift app for a few days; fix what feels off; then remove `app/` and its tests,
   and update `AGENTS.md`, `docs/ARCHITECTURE.md` and the README.

## Testing

- Unit tests with fakes, as `tests/desktop/test_native.py` does, run anywhere.
- Everything that touches the OS needs a real Mac: hotkeys, paste into Notes/Safari/Terminal/Claude Code,
  password fields refused, overlay over full-screen apps, permissions after a rebuild, `scripts/drive-milo.py "hi"`.
