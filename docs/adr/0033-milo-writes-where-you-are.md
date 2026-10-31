# 33. Milo writes where you are

Date: 2026-10-31. Status: accepted. The number may change: other ADRs written the same day may take it. Builds on [ADR 21](0021-dictation-learns-from-your-fixes.md) (the paste), [ADR 23](0023-stop-for-what-cant-be-undone.md), [ADR 28](0028-open-at-once-and-answer-in-the-users-language.md), [ADR 29](0029-quick-actions-from-the-talker.md) and [ADR 31](0031-talk-as-naturally-as-dictation.md). Changes ADR 29's rule that writing a mail means a `<draft>`.

## Context

The user wants to talk to Milo and get text where their cursor is: "write me an email to Anna that I'm ten minutes late", "answer this message politely", "write a short summary of what we discussed for Slack". It should land the way dictation does, at once and without a helper.

Until now the talker could only make a Mail draft (`<draft>`, ADR 29) or start a helper. A draft opens a new Mail window, which is wrong when the user is already in Slack, in a reply in Gmail, or in a Notes page. A helper takes 12 to 60 s.

## Decision

**A `<write>` tag.** The talker writes the text inside `<write>…</write>`, with its line breaks, and says nothing else. `ReplyParser` keeps the text as written (only the ends trimmed, `\r\n` made `\n`) and never speaks it. Attributes are allowed and ignored, so a `<write what="email">` can't leak the text into speech. The rules put `<write>` before a `<task>` or a `<draft>`; `<draft>` stays for when the user says to put it in Mail.

**The brain decides what may go, the app decides where.** `services/writing.py` (`Writer`) sends the app `app_request` `text.write {text, paste}` the moment the tag closes, while the reply still streams. The app (`Writing/WriteRequests`) answers `{pasted, app, field}` or `{pasted: false, why, app}`. Then Milo says one templated line in the user's language once it is true, like the quick actions: "It's in Mail, have a look." The window gets the text as a `written` entry with a Copy button, a `written` card shows its first words, and Undo gets a record. The brain names no app, no key and no field kind (ADR 27); `field` is an opaque id it echoes back.

**Where it lands.** When the talk key goes down, the app remembers the focused element (`AXFieldProbe`, off the main queue, 0.25 s Accessibility timeout). At paste time it reads the focus again and `PasteTarget.verdict` (pure) allows the paste only when:

- it is the same app and the same field as at the key's press. If the user moved on, nothing is pasted blind (`moved`);
- it isn't Milo's own window. A turn typed in the Milo window has its text right there to copy (`here`);
- it isn't a password field, a field in a password app, or a field labelled for a card number or security code (`secure`);
- it isn't a terminal: Terminal, iTerm, Warp, kitty, Alacritty, Ghostty, Hyper, WezTerm, Tabby, Rio, Wave, or a terminal inside another app. xterm.js labels its input "Terminal input" (VS Code, Cursor, T3 Code), VS Code's pane says "Terminal 1, zsh", JetBrains says "Terminal". A pasted line break runs a command there (`terminal`);
- it takes text: a text role, a settable value, or web content with an editable ancestor (`no_field`). Text with line breaks needs more: a settable value or editable web content. A terminal the list doesn't know shows its text area to Accessibility as read-only, so lines never reach it;
- the key press is fresh: it is used for one paste, and not after 10 minutes. A second text, or a turn long after the press, waits to be copied until the talk key goes down again.

No line break goes in at the end of the text, in the brain or in the app: in a terminal a final line break is what runs the line.

The paste itself is dictation's: `PasteboardInserter` puts the text on the clipboard, presses ⌘V and puts the user's clipboard back 0.6 s later. One inserter serves both, so a clipboard saved by one is the one the other restores. Without Accessibility the app doesn't paste at all (`blocked`), because macOS would drop the ⌘V silently.

**What doesn't land waits to be copied.** The text is in the window with Copy, and the line Milo says about it ("I don't paste into a terminal, so it's in my window to copy.") gets a Copy button under the bubble (`BubbleAction.copy`, kept while that line grows as he speaks). The card says "Ready to copy" and a click opens the conversation.

**Text after outside text.** Pasting isn't sending: the user reads the text in their own field before anything leaves, and ⌘Z takes it out. But text the model wrote after reading outside text (the screen, a task's result, another person's line in `<today>`, an untrusted memory) can carry words someone else put there. The rule:

- After outside text, the text goes in only when the user's own words in this turn asked for writing (`asks_to_write`). "Answer this email", "okay, write Anna back", "can you reply to Tom", "make it shorter", "a short summary for Slack", "schreib ihr", "fass das zusammen" count. The verb has to lead the request or follow "can you" directly, and a noun phrase needs "for", "to" or "saying". A question or a sentence that only mentions a reply never counts: "what does the reply say?", "can you tell me what the reply says?", "an email from my bank, is it legit?", "was hat er geantwortet?".
- Otherwise the brain sends `paste: false`: the app pastes nothing and offers Copy, and Milo says "This comes from something I read, so look it over first."
- Milo doesn't ask first. A yes or no question would cost a turn and a click, and the only thing it could ask is "paste this?", which the user can't judge without reading the text. Copy shows the text first and is one click.
- Invisible characters never go along: control characters other than line breaks and tabs, bidi overrides, zero-width characters and Unicode tag characters. They could hide words from the user, so what they read is all that is there.
- The target can't be steered. It is the field from the key's press, checked by the app, and terminals are refused there whatever the text says.
- At most one text per reply is pasted. A second waits in the window. A helper's spoken update writes nothing, and nothing is pasted from the phone: a reply by message carries the text instead.

So look-then-write works as one turn. "Answer this email" makes the talker write only `<look/>` (no words), Milo captures the front window, and the reply to the screen holds the `<write>`. The conversation is outside after the look, but the user's own words asked for the answer, so it goes into the field they were in when they started talking. Looking doesn't move the focus, so that field is still the target.

**Undo.** "Undo that" is `<undo/>` as for every quick action. The record's step `write.remove` goes to the app as `text.unwrite {field, text}`. The app reads the focused field: if it is the same field, nothing is selected, and the text right before the caret is exactly what Milo pasted, it selects that range and deletes it (setting the selected text, else a Delete key with Milo's event marker). Otherwise it says so in its platform's words, "The text there changed since, so I left it. Press ⌘Z in Mail to take it back.", and Undo passes that on. `Writer` adds its step to `Undo.reverse` in front of the quick actions' steps, so `undo.py` stays as it is.

**Streaming or at the end.** The paste goes at the tag's close, in one piece. Pasting while the text streams would put a dozen pastes into the user's field: each one is a separate ⌘Z in the target app, each needs the focus checked again, and the clipboard would change under the user every few hundred milliseconds. A half-written text in a field the user is looking at isn't useful either. The tag closes when the model finishes the text, and the paste lands one app round trip later: a socket message, one Accessibility read (a few ms, 0.25 s at worst) and a ⌘V. That is well inside the 1 s target. The text arrives at the model's speed (about 2 s for a 100-word mail), and Milo shows thinking meanwhile.

## Consequences

- From the end of the user's words: the talker's first token in about 0.7 to 1.8 s (ADR 29's measurements), the text at the model's speed, the paste about 0.1 s after the tag closes, and the line's first sound 0.3 to 0.5 s after that. Look-then-write adds a look (0.2 to 1 s) and a second model turn with the screenshot. These are estimates from the logged timings, not measured end to end.
- A field the app can't read through Accessibility (some Electron and canvas apps) counts as no field: the text waits to be copied. Some apps make a new Accessibility element for the same field on each read; there the check sees "moved". Both fail safe, to Copy.
- After outside text a follow-up that `asks_to_write` misses ("Tom wants 1, so say yes to that") waits in the window. That is the safe side of the heuristic. A request it wrongly matches pastes text the user then reads in their own field.
- Text the user asked for after outside text can still quote what the page said, including a line written to steer Milo. The user sees it before sending, and sending is theirs.
- A one-line text may still go into an unknown terminal's input line if it accepts typing there. Without a line break it doesn't run; the user would have to press Return.
- Undo by selection works where Accessibility shows the field's value and caret and lets Milo select. In web content and Electron apps it often doesn't; then Milo names ⌘Z. A line break the app stores as two characters (`\r\n`) also makes the match fail.
- The written text is kept in the conversation file like any reply, so it is in the recap when the user picks the conversation up.
- English and German lines only, as for the quick actions. The model writes the text itself in whatever language the user wants.
- Not run against real apps: the paste into Mail, Slack, Gmail and Notes, the terminal labels in VS Code and T3 Code, `AXEditableAncestor` in Chrome and Safari, and Undo by selection. The Swift code compiles and `PasteTarget`, `WriteRequests`, the Copy bubble and the controller hook are tested with fakes.
