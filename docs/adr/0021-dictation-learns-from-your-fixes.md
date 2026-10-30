# 21. Dictation learns from your fixes

Date: 2026-10-31. Status: accepted. Builds on [ADR 1](0001-two-processes-over-a-unix-socket.md), [ADR 10](0010-untrusted-results-and-a-private-log.md) and [ADR 20](0020-helpers-never-write-milos-control-files.md).

## Context

Whisper misspells the names the user says most: "Cloud Code" for Claude Code, "Nicholas" for Niklas. The user then fixes the word by hand in the app Milo pasted into. Wispr Flow notices such fixes and gets the word right from then on, without being told. The user wants the same: "when it pastes something in, but when you change some of the words it saves it automatically that these were corrected".

Milo already had two ways to steer spelling, both set by hand in config.toml: `[stt.mlx_whisper] vocabulary` (names in Whisper's prompt) and `[stt.elevenlabs] keyterms`.

## Decision

**The app watches the pasted words for a while.** Only Milo.app holds the Accessibility permission, so it does the watching (`PasteWatcher`, `app/Sources/MiloKit/Dictation/`).

- 0.3 s after a paste, it reads the focused text field's value and caret (`FocusedTextReader`, real adapter `AXFocusedText`). The pasted text has to sit right before the caret, or it gives up on this paste. It keeps up to 24 characters on each side of the span as anchors.
- It reads the field again every 0.5 s and finds the span between the anchors (`PastedSpan`). An edit right next to the span breaks an anchor, and then nothing is learned from that paste.
- The watch ends after 45 s, when the focus moves to another field or app, when the span can't be found any more (the message was sent and the field cleared, or the paste was undone), or when Milo pastes somewhere else. When it ends, it compares the last span it found with what was pasted. A paste right at the end of the span being watched (the "type" dictation style pastes phrase by phrase) joins the watch instead of ending it.
- Fields it never reads: password fields, fields in password apps (`AX.secretApps`), Milo's own windows, and fields over 100,000 characters. In an app whose field has no readable value (some Electron and web views), it doesn't watch.
- Reads run on a background queue with a 0.25 s Accessibility timeout, so a hung app never stalls Milo. Nothing is read while `[dictation] learn` is off.

**Only small fixes count** (`CorrectionDiff`, Swift). The pasted words and the span's words are aligned (Swift's `difference(from:)`, ignoring punctuation at word edges).

- If over half the pasted words changed (and more than 3), it's a rewrite: nothing is learned.
- Inserted words (text typed after the span, a new sentence) and deleted words (a sentence removed) are ignored.
- A substitution of 1 to 3 words by 1 to 3 words counts only if the two are spelled alike: letters and digits only, lower case, at most half of the longer one differs (edit distance, a swap of two neighbouring letters counting once). "big" to "huge" is a rewrite; "Cloud" to "Claude" is a mishearing. At the span's end a fix followed by typed words ("Nicholas" to "Niklas, see you") still counts.
- Spelled alike isn't enough for a change of mind. A lowercase fix whose heard words are all real words in the Mac's spell checker ("their" to "there", "cat" to "car") fits only that sentence, so it isn't learned; "teh" to "the" is. Two calendar words ("Monday" to "Sunday", "today" to "tomorrow", English and German) and two numbers ("15" to "16") are never learned.
- A change of only the first letter's case at a sentence start ("the" to "The" when the user splits a sentence) and a change of only punctuation are ignored. Other case changes ("github" to "GitHub", "milo" to "Milo" mid-sentence) and joined or split words ("Mac Book" to "MacBook") count.
- A single replaced word that the user capitalized takes its capitalized neighbours along, at most 3 words, so "Cloud Code" to "Claude Code" is learned as the name, not as "Cloud" to "Claude", which would also change "the cloud".
- At most 8 fixes per paste go to the brain. Only these word pairs leave the app, over the local socket: never the field's value, the span, or the app's name.

**The brain keeps them in `~/Milo/dictionary.md`**, a plain file next to `reminders.md` (`MarkdownDictionary`, `brain/src/milo/memory/dictionary.py`).

```markdown
## Words
- Milo

## Fixes
- Cloud Code -> Claude Code (seen 1)
- teh -> the (seen 2)
```

- `## Words`: names the user adds by hand. `## Fixes`: `heard -> meant`. A fix Milo learned carries `(seen N)`; a fix the user writes without it counts as certain. The user edits or deletes lines in any editor; the brain re-reads the file when its mtime changes (one `stat` per key press).
- Learning a fix seen before adds one to its count. A fix that contradicts one Milo learned ("Claude Code" back to "Cloud Code": the user undid Milo's replacement) deletes the learned one and learns nothing; one the user wrote stays. A new fix for the same heard words replaces the old one at count 1. The file holds at most 300 fixes; past that nothing new is learned and the log says so.
- It's a control file (ADR 20): helpers can't write it. A replacement changes what the user's dictation says, so a planted line could change a pasted text.

**When a fix applies.** Every fix's meant words go into Whisper's prompt and Scribe's keyterms at once: that only biases spelling, and a wrong guess costs little. Replacing text before the paste needs more:

- A fix the user wrote: always.
- Seen twice or more: yes.
- Seen once: only if it looks like a name, so a single fix is confident: the meant words have a capital letter, and the heard words aren't one all-lowercase word (which is likely an ordinary word that means something else elsewhere: "cloud"). "Cloud Code" to "Claude Code" applies after one fix; "cloud" to "Claude" and "teh" to "the" after two.

Replacements (`DictationFixes`, a `TextCleaner` around the configured one) match whole words, in the heard form's case or with its first letter capitalized (a sentence start), longest first. They run after filler removal, before the paste, for every phrase of "type" dictation too. A dozen precompiled regexes over a sentence: well under a millisecond, no model call.

**Vocabulary.** The words reach the transcribers through an optional port, `Vocabulary.use_vocabulary(words)`: `MlxWhisper` puts them after `[stt.mlx_whisper] vocabulary` in its prompt (at most 400 characters of learned words, about 100 tokens, the Words section and the most seen first); `ScribeRealtime` adds up to 50 to `keyterms` for the next session. The brain pushes the words at start, after each learned fix, and when a key goes down if the file changed.

**Telling the user.** The first time a fix is learned, the bubble shows "Learned: Claude Code" without speaking, unless Milo is busy (talking, listening, a question waiting); the file has it either way. The Settings window's Dictation card has a switch, "Learn from your fixes" (`[dictation] learn`, on by default, applies at once), and a "Show the words" button that opens `dictionary.md`. The menu bar's "Dictation words…" opens it too.

**Privacy.** The field's text stays in the app's memory, only for the watch. The brain logs fixes as `private(...)` (ADR 10): their length, not their words. Learned words go to ElevenLabs as keyterms only when the user already lets talking (`[stt] talk`) go there; they are words the user says to it anyway.

## What one paste costs

One AX read 0.3 s after the paste, then one every 0.5 s for at most 45 s: at most 91 reads of a field of at most 100,000 characters, each on a background queue. One word alignment of at most 200 pasted words at the end (a longer paste isn't watched). At most one socket message, and one rewrite of `dictionary.md` per learned fix. No model call. The paste itself waits for nothing new: the watch starts after it.

## Consequences

- Corrections the user makes more than 45 s after the paste, or after clicking elsewhere, aren't learned. Fixes made in the last half second before sending a message are missed.
- Apps whose text fields don't expose their value (some Electron and web editors, terminals with huge scrollback) teach Milo nothing. The paste works there as before.
- A user who edits the text right next to the span (inside the 24-character anchor) loses that paste's learning. Shorter anchors find more spans but match the wrong place more often.
- Whisper copies the prompt's style (ARCHITECTURE: Commits). A long list of learned words in the prompt could make it drop punctuation the way the previous text did. The cap of 400 characters keeps the list short; the user can delete lines.
- The Scribe keyterms cost a little more per session at ElevenLabs once there are learned words. Turning `[dictation] learn` off stops the learning, but words already in the file still go along; deleting them from the file stops that.
- Not covered: Milo's own hands typing into a watched field during a watch would count as the user's fix. The worker rarely types into the field the user just dictated into, and the similarity rule filters most of what it would type.
