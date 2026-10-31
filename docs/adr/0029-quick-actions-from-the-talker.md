# 29. Quick actions from the talker, and the day at hand

Date: 2026-10-31. Status: accepted. Builds on [ADR 28](0028-open-at-once-and-answer-in-the-users-language.md) and [ADR 9](0009-approvals-and-action-levels.md), [ADR 22](0022-one-question-per-piece-of-work.md), [ADR 23](0023-stop-for-what-cant-be-undone.md) and [ADR 26](0026-undo-what-a-task-did.md). Changes [ADR 11](0011-helpers-and-the-orchestrator.md): the user's calendar, reminders, notes, mail drafts and shortcuts no longer always go to a helper.

## Context

Talking to Milo should feel like an extension of yourself, as fast as dictation already is. It didn't, for the most everyday things. The talker's rules sent "the user's calendar, reminders, mail, notes, shortcuts or files" to a helper. In `brain.log` those helper turns took 11.8 to 60 s, with 47k to 227k input tokens each. "What's on today" took 26 s through a helper with 62k tokens. The talker itself answers in 1.1 to 2.3 s (first delta 0.7 to 1.8 s) on about 3 to 6k mostly cached tokens.

Some of it didn't work at all. "I'm done taking notes" got a reply that promised to stop, but nothing stopped: the talker had no way to stop meeting notes. A timer could only be faked with `<reminder>`, at minute resolution on the 30 s heartbeat tick, up to about 90 s late. A timed `<reminder>` goes to `reminders.md`, not Apple Reminders, so a to-do never showed on the phone. Media could only be scripted through a helper's `run_applescript`, which asks "Run a script in Music?".

The target: words to done in under 2 s, with one short spoken line ("Dentist, Thursday at 3. It's in.").

## Decision

**The talker writes one tag per action, and the brain does it in-process.** `<event>` (add, `do="move"`, `do="cancel"`), `<todo>`, `<note>`, `<timer>`, `<draft>`, `<shortcut>`, `<music>` and `<meeting>`. They are written like `<reminder>` (attributes, text inside where there is text) and collected by `ReplyParser` (`acts`). Like `<open>` (ADR 28), each starts the moment its tag closes, while the reply still streams (`LiveTalk._act_now`), so the event is usually in before the reply's last word. `QuickActions` (`services/quick_actions.py`) runs each in its own task, outside any helper. No harness turn, no MCP server. One tag per kind rather than one `<act kind=…>`: the tag reads as what it does and costs fewer tokens.

**It reuses what exists.** Calendar and Reminders go through `AppBridge.call` to EventKit in the app, as `brief.py` already did: about 100 ms and no tokens. Undo and moving need three new app ops, `calendar.event`, `calendar.update_event` and `calendar.delete_event`, and one for to-dos, `reminders.delete`. All four take the occurrence's start (`at`), so one meeting of a repeating series is moved or deleted alone. Notes, Mail and Shortcuts run on the same `Connections` the worker gets (`[connections] use`), built once more in the brain and called on a thread, after `AccessGate` (ADR 25). When the connections are the fake ones, `AppOps` sends Calendar, Reminders and the player to them too, so a quick action never writes to the real calendar while the worker works on made-up data.

**Media is an app op, not a script.** `media.state`, `media.play`, `media.pause`, `media.next` and `media.previous` (`MediaRequests` behind a `MediaPlayer` port). On the Mac, `SystemMediaPlayer` uses MediaRemote, the system's now-playing controls, so it works for whatever plays (Music, Spotify, a browser) and nothing asks. If MediaRemote can't be loaded, it presses the media keys. `media.state` answers "" after 0.5 s if the system won't say. Newer macOS keeps now-playing to Apple's own apps.

**Timers run on the brain's event loop** (`loop.call_later`) and ring within milliseconds: "Time's up: Pasta." They are kept in memory and don't survive a restart.

**`<todo>` is Apple Reminders; `<reminder>` stays Milo's own.** A to-do shows on the phone. "Remind me at 9" is still Milo saying it out loud at 9. A `<reminder>` now gets a card and an Undo too.

**Milo says what happened, after it happened.** The model writes the tag and says nothing about it. Once the action is done and the reply's own words are said, Milo says one templated line in the language of the message he answers (`quick_words.py`, English and German, the language `SpokenLanguage` heard, ADR 28): "Dentist, Thursday 5 November at 3 pm. It's in.", "Zahnarzt, morgen um 9 Uhr. Steht drin." A failure is a line too: "That didn't work: …". The model can't promise something that then doesn't happen, which is what went wrong with "I'm done taking notes". A reply by message carries the lines in its text instead of speaking them.

**Asking follows the rules that exist.**

- An act tag follows the `<reminder>` rule: in a conversation with outside text (task results, the screen), it asks first. It asks as a careful action (`approve(careful=True)`), with the question that names what it is about, in the message's language (`quick_words.QUESTIONS`). Another change will narrow what taints at-Mac turns; acts get that for free.
- The act's own kind goes through `Approvals` as it would from the worker. An event, a to-do, a note and the music are `change`, which doesn't ask. A draft is `draft`, which doesn't ask: nothing leaves the Mac. A shortcut is `shortcut`, which asks every time (ADR 9), and nothing undoes it.
- Deleting asks only when Undo couldn't bring it back (ADR 23). Deleting your own one-off event is `trash`: Undo makes it again from what the app returned. Deleting an invite or one occurrence of a series is `delete` and asks every time, because a made-again copy isn't the invitation or the series, and the others see it. Moving an invite is `share`: the others see that too.
- Stopping or pausing meeting notes never asks, like `<stop>`. Starting them from outside text asks.
- The act starts while the reply streams, but a question waits until the reply is over, so the bubble shows it.

**Every change can be undone.** Each act records its inverse with `Undo.done` (a ready record at once, `said` = the spoken line, so the Undo button sits under that bubble). "Undo that" is `<undo/>`, the newest record. The inverses: delete the event Milo made, move it back, make a deleted one again, delete the to-do, delete the note into Recently Deleted, take Milo's reminder out of `reminders.md`, stop the timer, put the music back as it was. Before deleting or moving back an event or a note the user changed since, Undo asks, in every mode (ADR 26). A mail draft has no inverse Milo can run without a dialog (Mail keeps no id he could find it by): its record goes to an "Undo:" helper, like a task's.

**A card for each.** `action_done` {kind, title, detail, when?, app?, undo?}, kind one of event, todo, reminder, note, timer, draft, shortcut, music or opened. `undo` is the id `undo_task` takes. The window's done card shows it. The app decodes it now and does nothing with it yet.

**The day at hand: `<today>`.** `Today` (`services/today.py`) fetches today's and tomorrow's events, due and overdue to-dos and whether music plays, at no token cost. It does so when a conversation starts, after an act, and when the block is older than 5 minutes; a turn waits at most 0.3 s for it. Milo's running timers are in it too. It goes into the next user message only when it changed since the conversation saw it, never into the system prompt. A changed system prompt would restart a warmed conversation (1 to 3 s) and lose the cache. Each event gets a handle (e1, e2) the model moves or cancels it by; another day's event is named by title and day. The block is about 60 to 250 tokens; the act rules add about 600 tokens to the cached system prompt.

**Invites are other people's text.** Titles are made inert like task results (no tag can open inside them, cut at 60 characters). An event with other people is marked "invite". An event or to-do on a subscribed or read-only calendar or list, or organized by someone else, is marked "shared" (the app sends `shared`). A reply to a message whose block carried either counts as a reply to screen data for every tag in it: an act, a task, a steer, a routine, a reminder, a fact and an `<open>` ask first, and a task from it runs careful. That holds for that reply, not the whole conversation: the block goes in once, and most work calendars always carry invites, so a lasting taint would make every task careful.

**Meeting notes by voice.** `<meeting do="start|stop|pause|resume"/>` calls `MeetingService.toggle` and `pause`, with a templated reply: "I've stopped taking notes. They'll be ready in a moment."

**Switches.** `[chat] quick_actions` (on) turns all of it off. The `[connections]` switches turn off single connections, now with `music`.

## Consequences

- Per action, from the end of the user's words: the talker's reply is the emotion tag and one tag, about 1.0 to 1.8 s to its end. Then the act runs: EventKit about 0.1 s, Notes and Mail through AppleScript about 0.3 to 1 s, the player under 0.1 s, a timer at once. The line's first sound comes 0.3 to 0.5 s after that, with ElevenLabs streaming. So an event or a to-do is in after about 1.1 to 1.9 s and said by about 1.5 to 2.4 s. A helper took 12 to 60 s. These are estimates from the logged talker and EventKit timings. Nothing here was measured end to end on the real calendar, on purpose: the tests use the fake connections.
- When the tag is all the reply says, it closes at the reply's end, so streaming gains nothing there. When the model says something after it ("Anything else?"), the act runs meanwhile and is done before those words end.
- The line comes about half a second later than if the model said it while streaming. That is the price of saying it only once it is true.
- English and German lines and questions only. Other languages hear English. A failure's reason ("That didn't work: …") is English inside a German line.
- A shortcut still asks every time and can't be undone. A user who wants otherwise sets `shortcut` in `[approvals.levels]`.
- Messages (iMessage) can't be drafted: the system offers no draft to script. "Write Anna a message" still goes to a helper.
- MediaRemote is a private framework. If a macOS update removes it, the media keys take over, and they only toggle play and pause. `pause` when nothing plays would then start playing.
- Making a deleted event again loses its alarms and attachments, and it gets a new id. An all-day event comes back all day.
- A calendar someone else shared with the user through iCloud, which the user may change, isn't marked "shared": EventKit doesn't say who owns it. Its events are marked only when they have attendees or another organizer.
- A reply after the one that carried an invite isn't tainted by it, though the model still remembers the title. What it could do with it is an undoable change or something that asks.
- Not run against the real apps: the four new EventKit ops, the `shared` flag, MediaRemote, `notes.delete`'s AppleScript and the in-brain Notes and Mail calls. The Swift code compiles and `MediaRequests` is tested with a fake player. EventKit has no fake in the app's tests.
