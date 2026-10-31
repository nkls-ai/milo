# Meeting notes that you can see: research

2026-10-31. Background for the "Taking notes" capsule, the live meeting page and the notes page ([docs/design/meetings.md](../design/meetings.md), "What the user sees"). The question: what do the meeting-note apps people already use do while a call runs and right after it, and what of that fits Milo, whose users are not technical and who works only on the Mac?

## What the others do

- **Granola** never joins the call. While it records, a small pill floats at the right edge of the screen; you can drag it away, and a click takes you back to the meeting's note. Inside the note, the same pill opens the live transcript. Recording is offered when a calendar event with a call link starts. After the call it writes the notes from the transcript and what you typed. ([Granola blog](https://www.granola.ai/blog/granola-google-meet-integration-recording-transcription), [UX reference](https://cdn.jsdelivr.net/npm/@agent-native/core@0.124.6/corpus/templates/clips/desktop/design-refs/granola-ux.md))
- **Apple Notes** (macOS 15) records into a note with a timer, a waveform, Pause and Resume, and the live transcript under it; the transcript can be searched and copied. ([Apple support](https://support.apple.com/en-jo/guide/notes/apdb5106e334), [Tom's Guide](https://tomsguide.com/computing/macos/how-to-record-audio-in-macos-sequoia-notes))
- **Otter** shows the transcript live with a name and a coloured avatar per speaker and a timestamp per paragraph, scrolls with the talk and stops following when you scroll up ("Jump to live"). Questions about the meeting go to a chat beside the transcript.
- **Fathom** and **tl;dv** put a big "Highlight" button on the call and have the summary seconds after the call, in fixed sections: summary, next steps with the owner's name, then the transcript.
- **Fireflies** and **Otter** send a bot into the call, which everyone sees. That doubles as the consent notice, and many people dislike it.
- **Zoom AI Companion** tells everyone in the call that a summary is on, offers "Catch me up" for someone who joined late, and sends a summary with next steps after the call.

## What Milo takes

1. **One small capsule near Milo, never a hidden mode** (Granola's pill, Apple Notes' timer): "Taking notes · 12:34" with a red dot, Pause and a big Stop. A click on the capsule opens the meeting's page.
2. **Milo himself shows it.** A wren with a notepad who writes a little and looks up to listen: the people who use Milo look at him, not at a menu bar icon.
3. **The transcript live, with names and colours, timestamps, and following that stops when you scroll up**, with a "Back to now" button (Otter). Milo's chunks come 30 to 60 s late, so the end of the list always says so: "Listening… the last minute shows up shortly." Nothing looks stuck.
4. **Ask about the meeting from its page** (Otter's chat, Zoom's "Catch me up"): a field that says "Ask about this meeting", with a few ready questions ("What did I miss?", "Sum up the last ten minutes").
5. **Fixed sections after the call** (Fathom): Notes (summary, decisions), To-dos with "Add to Reminders" on each, then the transcript. The notes show as text in the window; the file stays a secondary "Show in Finder".
6. **Consent without a bot** (Zoom, Fireflies): a "Copy a note for the chat" button with the line Milo suggests, so telling the others takes one paste.
7. **Ask once, remember the answer per app** (Granola asks per calendar event): "Take notes", "Not this time", "Always for Zoom", "Never for WhatsApp". The choice goes into config.toml through Settings and can be changed there.
8. **Say what happens after Stop**: "Writing your notes…" with the step it is on, then "Notes ready" with an Open button, instead of a file appearing silently.
9. **Pause, not only Stop** (Apple Notes): a paused stretch is recorded as silence, so nothing said then can reach the notes.

## What Milo leaves out

- A bot in the call, highlight buttons and clips: they need the call app's cooperation or a cloud.
- Typing your own notes into the page during the call (Granola's core): a good idea for later, but a second editor is more than the people Milo is for need now.

## Rendering the notes

notes.md is Markdown with headings, bullets, `- [ ]` to-dos and bold. SwiftUI's `AttributedString(markdown:)` handles only inline styles. [swift-markdown-ui](https://github.com/gonzalezreal/swift-markdown-ui) (MIT) renders full Markdown but is in maintenance mode, its successor Textual is new, and Milo's app has no dependencies ([ADR 4](../adr/0004-dependencies.md)). The summarizer writes a small, fixed subset, so the app has its own block renderer (`MarkdownBlocks`, about 150 lines): headings, paragraphs, bullets, numbered items and checkboxes, with inline bold, italics, code and links from `AttributedString`.
