# 6. Milo looks at the screen only when asked, and screen text is data

Date: 2026-10-30. Status: accepted.

## Context

"What do you think of this?" and "why is this cell red?" only make sense if Milo can see the window. The chat model has no tools, and the permissions to read other apps (Accessibility) and take screenshots (Screen Recording) belong to Milo.app, not to the brain. Whatever is on the screen can also contain text written to steer an assistant.

## Decision

- The chat model asks to look with a `<look/>` tag, like the other reply tags. The brain sends `look_request` to the app and keeps the eye on (`looking`) while it waits. The app reads the front window through Accessibility (app, window title, focused element, selection, visible text, capped at about 8000 characters) and takes a ScreenCaptureKit picture of that window, long side 1400 px, saved as a 0600 PNG under `~/Milo/state/screens/`. The newest 30 are kept. The brain then sends the text and the image to the chat model in a follow-up message and the model answers again.
- The capture starts while Milo says his first words ("Let me look."), so the look costs no extra waiting.
- `claude -p --input-format stream-json` takes base64 image blocks in a user message. Checked with claude 2.1.312 on 2026-10-30, both with the raw CLI and through `ClaudeLiveModel`.
- "What's this?" (`[ui] whats_this_key`, default `ctrl+option+m`, or the menu bar item) captures the selection, or the window if nothing is selected, and starts a turn with it. A selection goes without a screenshot. The shortcut uses Carbon's `RegisterEventHotKey`: it needs no permission, the key press doesn't reach the app in front, and it can't collide with the push-to-talk modifiers.
- Screen text always travels between `<screen_data>` markers with a note that it is untrusted data. A marker inside the text is defused. Facts from a turn with screen data are never remembered. While a conversation has seen screen data, every task it hands off waits for the user's yes, so text on a web page can't start work on its own.
- The brain reads an image only if its path lies inside `state/screens`.
- Password managers are never read or captured, and secure text fields are skipped.

## Consequences

- A look adds one chat turn and roughly 1500 tokens for a 1400 px screenshot.
- Without Screen Recording Milo still reads the window's text and tells the user which switch to turn on. Without Accessibility he still sends the screenshot.
- Asking before every task after a look is some friction for "look at this and fill it in". That's the price of a page not being able to give Milo orders.
