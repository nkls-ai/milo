# 30. Cards for what Milo did

Date: 2026-10-31. Status: accepted. Builds on [ADR 26](0026-undo-what-a-task-did.md) and [ADR 27](0027-a-platform-boundary.md).

## Context

The live model now does small things itself: an event, a to-do, a reminder, a note, a timer, a draft, a shortcut, music, a page opened. Milo says "Done", and the user has to go and check. A personal assistant working beside you shows what it did, where you can see it, and lets you take it back.

While a helper works in a window, the outline says "Milo is working here" but not what he is doing.

## Decision

**`action_done` (brain to app)**: `{kind, title, detail, when, app, undo, lang}`. `kind` is `event`, `todo`, `reminder`, `note`, `timer`, `draft`, `shortcut`, `music` or `opened`. `detail` is one plain line or "". `when` is an ISO time ("2026-11-05T15:00", with or without a zone) or "". `app` names the app the item lives in, or "" for Milo's own reminders. `undo` is the id of the task whose Undo takes it back, or "". `lang` is the language Milo said it in ("en", "de"), the one the title is in, or "". The fields are plain words and opaque ids (ADR 27). An unknown kind shows a plain card. `LiveTalk._remind` sends it for the `<reminder>` tag, `Opener` for what an `<open>` opened. The instant actions send it for the rest.

**A card comes out of Milo** (`DoneCards`, `Views/DoneCardViews`). It springs from his side into the corner left of him, and a check draws itself in. It stays 4 s, and as long as the pointer is on the cards. Then it shrinks back into him. The picture on the left says what it is: a calendar page with the day for an event (the line under the title gives only the time), a checkbox row for a to-do, a ring that runs down for a timer, a note sheet, an envelope, the app's icon. Up to three cards lie as a deck, newest in front, and fan out under the pointer. A fourth pushes out the oldest. With Reduce Motion they fade, and the check is simply there. Milo doesn't leave the screen while a card shows.

**A click opens the item where it lives** (`DonePlace`, pure; `Adapters/MacItemOpener`). An event opens in Calendar through `ical://ekevent/<id>` and a to-do in Reminders through `x-apple-reminderkit://REMCDReminder/<id>`, when Milo already has Calendar or Reminders access and finds the item by title. Otherwise the app opens as it is. A click never brings up a permission dialog. Milo's own reminders open Today in the Milo window, notes open Notes, drafts Mail, and a page opens in the browser.

**Undo** on a card sends `undo_task` for its task, the same as every other Undo (ADR 26). A task the brain hasn't listed in `undo_points` yet still goes, since the brain knows its own tasks. A task listed as undoing or undone doesn't go a second time. The button then shows a spinner, and after that a dimmed arrow.

**Clicks.** The cards sit in Milo's panel, left of the square the panel keeps for dragging him. They report where they are (`DoneCards.area`), and `DraggableHostingView.isControl` hands a press there to the card, also where a card or its check reaches into his square, as for Stop. A panel that isn't key doesn't always hear hovers, so while cards show the panel checks the pointer every 0.2 s (`DoneCards.pointing`).

**The step under the outline.** `MiloModel.workingStep` is what Milo's hands are doing now, in plain words: the newest running `activity` step whose id starts with `hands_` (the steps `HandsService` logs: "Typing “youtube.com” in Safari", "Filling in cells in “Budget”"). The worker's own steps don't count. It clears when the hands stop. `WorkingOutline` shows it as a small paper pill on the window's bottom edge, half outside, or just inside when the window reaches the screen's edge. Clicks still go through. A clearer step event from the brain only needs to set this one property.

## Consequences

- The user sees each small thing Milo did, can open it with one click and take it back with another.
- Opening a specific event or reminder relies on Calendar's and Reminders' URL schemes, which Apple doesn't document. If they stop working, the app still opens.
- The caption depends on the `hands_` step id. That convention now lives in the protocol's docs and in `MiloModel.handsStep`.
- Cards and the helper birds share the corner left of Milo. Three cards fanned out with a long bubble above can reach the top of the 380 pt panel.

## Changed after review (2026-10-31)

- **The card's own words follow Milo's language.** The brain writes the title and the detail in the language of the message (ADR 28), but the card's own words ("Today", "Tomorrow", "In your calendar", "Draft, not sent", "Rings at", the tooltip and VoiceOver's lines) were English. They now follow `lang`, and the day and month names with them; when `lang` is "", they follow the system's language. English and German, like Milo's lines; other languages get English. Why the brain's language and not only the system's: the card shows the line Milo just spoke, so a German line on an English Mac must not get an English card. Why not only the brain's: an older brain sends no `lang`.
- **Opened pages have cards.** `Opener` sends `opened` with the site's host, the file's name or the app as title, the address as detail, and the app that opened it.
- **Only an address opens as a page.** `DonePlace` took an `opened` card's title for a page when its detail had none, so a file named "evil.com" opened in Finder would have opened https://evil.com on a click. Only the detail can be a page now.
- **What the line says.** An event's and a reminder's detail is only a place, never the spoken day and time the card already writes from `when`. Milo's own reminders have `app` "" as this ADR says (they went out as "Milo", so a click looked in an app of that name). A music card with no detail says the player's name, else "Music", never "Playing" for a pause.
