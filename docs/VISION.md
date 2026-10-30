# Milo: what he could become

Written 2026-10-30. This is the brainstorm behind [ROADMAP.md](ROADMAP.md): what is possible, what is worth it, and in which order. Nothing here is built yet.

## The shift

Today you use a computer by finding the app, the menu, the button. Milo turns that around: you say what you want and he does the clicking. Dictation is the first taste of it. You stop typing and just talk, and the text shows up where it belongs. The same move works for everything else: "put the dentist in my calendar", "send Anna the photos from Sunday", "fill in this form with my details".

For someone who doesn't use AI, Milo isn't "an AI". He's the way you use your computer now. Three things make that work:

1. **He can reach your stuff.** Calendar, mail, files, messages, the browser, the apps you use.
2. **He remembers.** Who your people are, what you're working on, how you like things done.
3. **You can see and stop what he does.** Every step is visible, the risky ones wait for a yes, and most can be undone.

## How Milo reaches your apps

Ordered from most reliable to least. Milo should always use the highest route that can do the job.

| Route | What it covers | Speed and reliability |
|---|---|---|
| Built-in Mac frameworks | Calendar and Reminders (EventKit), Contacts, Photos, Spotlight search, Music | Instant, never misclicks |
| Shortcuts | Every app that offers Shortcuts actions, plus the user's own shortcuts. `shortcuts run` from the command line | Instant. One integration opens hundreds of apps |
| AppleScript | Mail, Notes, Messages (send), Finder, Safari, Excel, Word, Numbers, Keynote | Fast, mostly reliable |
| Files directly | xlsx, docx, pdf, csv, images | Milliseconds, can't misclick |
| Connectors (MCP servers) | Gmail, Google Calendar and Drive, Outlook, Notion, Slack, WhatsApp Business, Spotify, banks with APIs | Fast. Needs a one-time "Connect Google" sign-in |
| Milo's own browser | Any website: forms, bookings, research, shopping carts | A few seconds per step. Runs out of sight |
| Accessibility tree | Any Mac app's buttons and fields, by name | Fast, works in background windows for many apps |
| Screenshots and clicks | Everything else | Slow, costs the most, sometimes wrong |

Shortcuts deserves a special mention. Apple pushes every app to expose its actions there (App Intents), so Milo gets things like "start a timer in Clock", "add to Things", "play in Spotify" without anyone writing code for each app.

Connectors should feel like connecting a phone to Wi-Fi: a list with "Connect" buttons, a plain sentence about what Milo can then do, and a switch to turn each one off. The word MCP never shows up.

## Features worth building

Grouped by who they help. Some are small, some are big; the ROADMAP section at the end picks the order.

### Dictation that edits, not just types

- **Voice editing.** Select text, hold the key, say "make this friendlier", "shorter", "translate to English", "turn this into a list". Milo rewrites the selection in place.
- **Formatting by app.** Casual in WhatsApp and Slack, proper sentences in Mail, code-friendly in a terminal.
- **Learns your words.** When you fix a word Milo got wrong, he notices the correction (by reading the field again after pasting) and spells it right next time.
- **Snippets by voice.** "Insert my address", "my IBAN", "the standard reply for job offers".

### Knowing what's on your screen

- **"Look at my screen."** Say it in a normal conversation and Milo looks: he reads the text of the window in front of you (Accessibility, no permission prompt beyond the one he has) and takes a screenshot of it (ScreenCaptureKit, needs Screen Recording once). Then "what do you think of this?", "why is this cell red?", "help me fill this in" all just work. He looks only when asked or when a task needs it, and a small eye on Milo shows when he is looking. A setting "Milo may look when it helps" lets him check the screen on his own during a task, never in the background.
- **"What's this?"** Hold a key and ask about whatever is in front of you: an error message, a letter from the tax office, a contract clause, a chart. Milo reads the selection or the window's text, and only takes a screenshot if he has to.
- **"Is this real?"** A scam check for emails, texts and websites. Big for older users: fake parcel notices, fake bank emails, "your computer has a virus" pop-ups.
- **Patient tech support.** "My printer doesn't print", "the internet is slow", "where did my file go?". Milo checks settings, explains in plain words, and fixes what he can.

### Remembering for you

- **Remember anything.** "Remember that Anna's birthday is March 3", "remember I parked on level 4". It goes into memory and comes back when relevant.
- **Find by meaning.** "Where's the PDF from the insurance about the car?" A local search index over your documents, mail and notes that understands what you mean, not just file names.
- **Follow-ups.** "Remind me if Tom hasn't answered by Friday." Milo watches the mailbox locally and only speaks up if the answer doesn't come.
- **Meeting notes.** Transcribe a call locally (with a clear "recording" indicator and consent), then summarize it, list the to-dos, and put them in reminders.
- **A morning brief.** Today's appointments, who's having a birthday, what's still open from yesterday, the weather. Built from local rules, so it costs nothing.

### Doing things

- **Routines.** "Remember how to do this, call it the Monday report." Already in the roadmap.
- **Watch and learn.** "Watch me do it once." Milo follows your clicks through the Accessibility API and writes the routine for you.
- **Noticing patterns.** "You open Mail, the calendar and the bank every morning. Want me to do that at 8?" Asked once, never pushy.
- **Undo.** Before Milo changes a file, he keeps a copy, so "Milo, undo that" puts it back. Nothing builds trust faster.

### For families

This could be what makes Milo stand out.

- **Set up Milo for your parents.** A son or daughter installs Milo on Mom's Mac, connects her mail and calendar, and sets what Milo may do on his own.
- **A helper you can check on.** Mom says "Milo, I need help with the printer". Milo tries first, and if he can't fix it he asks: "Should I tell Niklas?" Niklas gets a message saying what was tried.
- **Scam guard with a backup.** When Milo thinks something is a scam, he tells Mom plainly and can let the family know.

## Many things at once

You will want Milo to do several things in parallel: research a holiday while filling in a spreadsheet while sorting photos. The problem is that a Mac has one screen, one mouse and one keyboard focus. If Milo clicks in Excel while you type an email, you fight over the same pointer.

The answer comes in layers. Each layer is more powerful and more expensive than the last.

1. **No screen needed (most tasks).** Everything that goes through frameworks, Shortcuts, AppleScript, files, connectors or the Accessibility tree runs in the background, away from the screen. Ten helpers can run at once without touching your mouse. Each one shows up as a task in the Milo window.
2. **Milo's own invisible browsers.** Each helper that needs the web gets its own browser out of sight, with its own tabs. Research, bookings and forms run in parallel. It costs some memory, nothing else.
3. **Borrowing your screen, politely.** When a task really needs your screen, Milo waits until you're idle or asks "Can I use the screen for 30 seconds?" While he works, a soft frame around the screen says "Milo is working". If you touch the mouse or keyboard, he stops at once and gives control back.
4. **A second computer for Milo.** For long tasks with apps that need a screen, Milo gets his own desktop:
   - **A virtual machine on your Mac.** Apple's Virtualization framework runs macOS or Linux in a window. A macOS guest needs about 8 GB of memory, so on a 16 GB Mac it's one at a time at most. Fine for "Milo's desk", not for many parallel ones.
   - **A computer in the cloud.** Milo rents a cloud desktop or browser for the task (services like Browserbase for browsers or E2B for desktops do this today) and streams a small live preview into the Milo window. Many can run in parallel. It costs per minute, and files move between the cloud and your Mac.

How it looks: Milo sends out **helpers**. If Milo is the bird, they're small birds. Each one carries a task, has a progress bar in the Milo window, and comes back with the result. "I sent two helpers: one is comparing flights, one is filling in the spreadsheet." This makes parallel work easy to understand without any technical words.

Under the hood this is the sub-agent pattern: a coordinating agent (the live Claude session Milo already has) hands tasks to workers (Codex or Claude processes), each with its own tools, sandbox and budget, and collects their results.

## Every device

What should follow you around: memory, routines, reminders, conversation history, connections and settings. What stays on each device: the speech models and the voice.

**Phase one: just your Apple devices, no server.** Put `~/Milo` in iCloud Drive. Memory is plain Markdown, so syncing it is simple, and Apple handles the encryption.

**Phase two: a Milo account.** Needed anyway for the hosted product, and for anything beyond Apple. End-to-end encrypted sync of the same files and a history log.

**The phone app.** Milo in your pocket, and a remote control for your computer:

- Talk to Milo anywhere, with the same memory.
- Reminders arrive as real notifications.
- Quick capture: "remember…", "add to the shopping list".
- **Ask your Mac to do things while you're away:** "On my Mac, export the report and send it to me." The Mac does the work, the phone shows the progress. Most assistants can't do this, and it's a strong selling point.
- A dictation keyboard for iPhone, like Wispr Flow has.

**Watch:** "Remind me…" from your wrist.

**Other operating systems.** Windows is where most less technical users are. The brain (Python) and the message protocol already work anywhere. Only the app with the character is Mac-only. So: stay native on the Mac until people clearly want Milo, then write a Windows app against the same brain. Don't switch to a cross-platform framework now; the polish of a native app is part of the product.

## Trust and safety

Without these, nobody hands Milo their mail and bank tabs:

- **Permissions per connection:** what Milo may read, what he may change.
- **Three levels of action:**
  - Just do it: reading, searching, drafting.
  - Ask first: sending, deleting, buying, anything going to another person.
  - Never: passwords, banking transfers, changing security settings.
- **Undo** for file changes, **drafts instead of sends** by default.
- **Passwords never reach the model.** Milo uses the Keychain and passkeys and fills fields himself without reading them.
- **Untrusted text stays untrusted.** Web pages and emails can contain instructions aimed at Milo. Anything from outside is treated as data, never as orders. (The security review already flagged this in the current code.)
- **A spending cap** per day and per task, visible in the menu.
- **A log** the user (or family) can read: what Milo did, when, and why.

## How we'll know it works

A fixed set of about 30 real tasks, written the way a non-technical person would say them: "put my doctor's appointment on Thursday at 3 in the calendar", "find the electricity bill from last month", "make the font bigger in this email". Run them after every big change, score how many Milo finishes without help, and how long it takes. This becomes the main number for the product.

## Next steps, in order

1. **Finish the current build and live with it for a week.** Apply the live-dictation patch, rebuild, use Milo daily. Keep a note of everything you asked for that he couldn't do. That list decides the first connectors.
2. **The first connections:** "Look at my screen", Calendar and Reminders via EventKit, Mail and Notes via AppleScript, Shortcuts, and files. Plus "What's this?" and voice editing in dictation. These are the most useful per day of work.
3. **The task list and the trust layer:** the 30-task test set, the three action levels, undo, and the security fixes.
4. **Helpers in parallel:** background routes plus invisible browsers, shown as helpers in the Milo window.
5. **Borrowing the screen** with the "Milo is working" frame, then the `milo-mac` tools for real computer use.
6. **Routines and watch-and-learn.**
7. **The phone app** as a remote and capture tool, with iCloud sync.
8. **The product work:** account, hosted models, family setup, signing, onboarding, pricing.
9. **Cloud desktops and Windows**, if people want Milo.

## Open questions

- Who is the first real user besides you? Your mom is the clearest test. Ten people like her would tell us more than a hundred tech people.
- Do we lead with "Milo for your parents" (family setup, scam guard, tech support) or "Milo for me" (dictation, routines, meetings)? They share the same product but need different stories.
- How much should Milo do without asking? It might differ per user, which argues for the three action levels being settings.
