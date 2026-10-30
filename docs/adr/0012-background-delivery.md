# 12. Milo works in the background, and borrows the mouse only when he must

Date: 2026-10-30. Status: accepted. Builds on [ADR 7](0007-computer-use-through-the-brain.md).

## Context

A Mac has one mouse, one keyboard focus and one screen. When Milo used the Mac he moved the real cursor and
typed real keys, so the user had to stop and watch, and any touch stopped him. The point of "many things at
once" (VISION, "Many things at once") is that Milo works on the side while the user keeps working. So the
question is: how much can Milo do to an app without taking the user's pointer or keyboard?

## Decision

Milo delivers each action by the least intrusive route that works, deciding per app family. `Screen/Delivery`
is a pure planner; `MacHands` runs the steps and reads the app back to check each one.

1. **Accessibility first (no pointer, no focus).** A button is pressed with `AXPress` (walking up to two
   ancestors, so a click on a button's label still presses it). A click into a field sets `AXFocused` and puts
   the caret with `AXRangeForPosition`. Typing sets `AXSelectedText` and reads the value back, because some
   apps answer "yes" and change nothing. A right-click uses `AXShowMenu`. Scrolling sets the scroll bar's
   `AXValue`. None of these moves the user's cursor or touches their keyboard focus.
2. **Borrow the real mouse or keyboard, with a yes.** What Accessibility can't do (a double-click, a plain
   keystroke, a click on a canvas or web content, Office document edits) falls back to the real pointer or
   keyboard — but only after the user agrees. `MacHands` returns `HandsFailure(borrow: "mouse" | "keyboard")`;
   `HandsService` asks through the usual `Confirmer` ("Can I borrow your mouse for a moment, to click in
   Microsoft Excel?") and, on a yes, sends `hands_borrow`. Each device is lent on its own 15-second sliding
   clock (every action that uses it restarts the clock) and handed back by itself; a yes for the mouse never
   lets Milo type. While a device is lent, the old rules hold: the whole-screen frame shows and any real touch
   stops him. A borrowed click warps the real pointer back to where the user left it afterwards.
3. **Stopping.** In the background the user's own typing and clicking must *not* stop Milo — that is the
   point — so `TakeoverDetector` has a `background` mode in which only `esc` (or the Stop button on the window
   outline) stops him. In `borrowed` mode it keeps today's stop-on-any-touch.
4. **On screen.** Milo's own lavender cursor (an overlay, never the system cursor) glides to each spot before
   the action, so the user sees where it will land; the window he works in gets a soft outline that follows it,
   and Pip perches on its corner. The brain tells the app the window through `describe` (it now also returns
   `window` and `pid`).

### Why not post events to the app's process in the background

A tempting middle route is to post synthesized mouse and key events to the target process so nothing on
screen moves. We tried it and rejected it for Milo:

- It only works at all with private WindowServer calls (a per-process event post, a window-local coordinate
  stamp, and a "make key without raising" record sequence). Public `postToPid` alone is dropped by AppKit
  (no window-local point) and by Chromium (untrusted at the renderer). The private symbols are undocumented
  and change between macOS releases — a poor base for a local-first app meant to keep working.
- Measured on macOS 26.3: even with the private calls, Microsoft Office documents ignore posted events
  entirely (only their ribbon, which is Accessible, responds), and posted clicks reorder window z-order.
- The honest, stable version of "don't take the user's mouse" is: do everything Accessibility allows in the
  background, and for the rest ask to borrow the real mouse for a moment. That is what we shipped.

## What works per app family (measured macOS 26.3)

| | Cocoa / AppKit (TextEdit, Numbers, Mail, Finder) | Chromium / Electron (Chrome, Slack, VS Code) | Microsoft Office (Excel, Word) |
|---|---|---|---|
| Press a button / checkbox / menu | Background (`AXPress`) | Background (`AXPress`) | Background (ribbon only) |
| Focus a field, place the caret | Background (`AXFocused` + caret) | Background | Document: borrow |
| Type into a field | Background (`AXSelectedText`), read back | Borrow — Chromium ignores `AXSelectedText` | Document: borrow |
| Right-click menu | Background (`AXShowMenu`) where offered | Left-only posted, so `AXShowMenu` or borrow | Borrow |
| Scroll | Background (scroll bar) where settable | Often borrow | Borrow |
| Plain keystroke, double-click | Borrow | Borrow | Borrow |

Verified on real apps while holding the screen lock: every background action left `NSEvent.mouseLocation`
unchanged (`mouse still`) and the frontmost app unchanged. TextEdit (plain and rich), Numbers, Chrome (its own
temp profile) and a throwaway Electron app took background AX typing, pressing and focusing; Excel and Word
documents took only the ribbon and needed the borrow. Milo's cursor overlay measured 0.01% CPU at rest (no
work when idle) and ~3% while gliding at 60 fps.

## Consequences

- Most app work now runs with the user's mouse and keyboard free. Milo's cursor and the window outline show
  what he's doing without stealing anything.
- Typing and some clicks in Office, and anything on a web page, still ask to borrow the mouse. That's a real
  interruption, but a rare and clearly-consented one, and the user keeps the pointer the rest of the time.
- No private WindowServer APIs: one less thing to break on a macOS update.
- `MacHands` reads each background action back (value changed, caret moved, scroll bar moved). A route that
  silently did nothing fails cleanly to the next one, or to the borrow, rather than reporting a false success.
