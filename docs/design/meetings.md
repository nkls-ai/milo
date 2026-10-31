# Meeting notes: design

Status: built, 2026-10-30. The research, measured numbers and what is still unverified are in [docs/research/meetings.md](../research/meetings.md). Where the build differs from this proposal: chunks are WAV, not FLAC (`audio/me-0001.wav`, `audio/them-0001.wav`), the diarizer embeds Whisper's segments instead of running a segmentation model (it was more accurate on every test), and the tap is global, leaving Milo out, instead of one per call app.

## What the user gets

- Milo notices a call (Zoom, Teams, Meet, FaceTime, Slack huddles) and asks once: "Looks like a meeting. Should I take notes?" A setting can make it automatic for meetings in the calendar, and "Always for Zoom" or "Never for Zoom" on the question makes it automatic or silent for that app.
- While he records, Milo holds a notepad, and a capsule next to him and the menu bar show the time. There's no hidden mode.
- During the call: "what did he just say about the deadline?", "sum up the last ten minutes".
- After the call: a summary, decisions, the user's to-dos (offered as Reminders), and a follow-up mail draft if the user wants one. The notes land in `~/Milo/meetings/` as Markdown and as an episode in memory.
- An hour-long call works the same as a five-minute one, and a crash loses at most the last few seconds.

## What the user sees

Background and what other note takers do: [docs/research/meeting-notes-ux.md](../research/meeting-notes-ux.md).

- **The question.** The bubble asks with four buttons: Take notes, Not this time, and smaller "Always for Zoom" and "Never for Zoom". The last two go into `[meetings] always` and `[meetings] never` through Settings (the brain's `Settings.change`), and the Settings window lists them, each with an × to ask again. `confirm` carries the buttons as `choices`; the answer comes back as `confirm_answer` with `choice`.
- **Milo while he records.** He holds a small notepad (the rig's `pad` and `pen` channels) and writes in short bursts, looking up every few lines as if someone said something worth noting. Talking to him, he looks at you instead. With Reduce Motion he holds the pad still. He keeps it while the notes are written, and never falls asleep during a meeting.
- **The capsule.** Over Milo: a red light, "Taking notes", the time (one tick a second), a Pause button and a filled Stop. Paused, the light turns grey and Pause becomes Go on; paused stretches are recorded as silence and left out of the notes. If one side can't be heard, the light turns into a warning and the bubble says what is missing, with a Fix it button that opens the right pane of System Settings. After Stop the capsule says "Writing your notes" with the step ("Telling who said what", "Writing the summary"). A click on it opens the meeting's page.
- **The menu bar.** The red dot and the time, and in the menu: Stop, Pause, Open the meeting, Copy a note for the chat.
- **The live page.** The meeting's conversation shows a page of its own: title, time, who was heard (each with a colour), Pause and Stop; a row with the line for the call's chat and "Copy for the chat"; the transcript with names, colours and times, following new lines until the user scrolls up ("Back to now · 3 new"); at its end "Listening… the last minute shows up shortly", since lines are 40 to 60 s late; then questions asked about the meeting and Milo's answers, ready questions ("What did I miss?") and a field that says "Ask about this meeting".
- **After Stop.** Milo says "Your notes from “Weekly sync” are ready. One to-do for you." with an Open notes button. The page shows the notes as text (the app's own Markdown renderer, `MarkdownBlocks`), with tabs for Notes (summary, decisions, follow-up mail with "Put the mail in Mail as a draft"), To-dos (each with "Add to Reminders", and "Add all of mine" when there are several) and Transcript. Copy notes and Show in Finder sit in the header. The sidebar row says how long the meeting was and its first sentence; Today lists the week's meetings.

### Wire

| Message | Way | What |
| --- | --- | --- |
| `meeting_status` | brain → app | Phase (`recording`, `paused`, `writing`, `done`, or none), title, app, start, seconds so far, the meeting's conversation, speakers heard, the writing step or the ready line, an error and its `fix` (`microphone`, `call_audio`), and the consent line. Sent on every change and on connect. |
| `meeting_lines` | brain → app | New transcript lines (`at`, `end`, `who`, `me`, `text`); `reset` when names or the cleanup changed earlier ones. |
| `meeting_notes` | brain → app | The notes page: `notes.md` as Markdown, summary, decisions, to-dos with `mine` and `added`, follow-up, people, folder, and whether Reminders and Mail are offered. |
| `meeting_pause` | app → brain | Pause (true) or go on. The recorder writes silence at once. |
| `open_meeting` | app → brain | The page opened: send its status and lines, or its notes. |
| `meeting_todo` | app → brain | Add to-do `index` to Reminders; -1 for all of the user's own. |
| `meeting_mail` | app → brain | Draft the follow-up mail. |

## Pieces and ports

```
app: CallDetector ──► brain: MeetingService ◄── app: two audio streams (mic, call audio)
                              │
                ChunkWriter ──┤── writes 30 s audio chunks to disk
              ChunkTranscriber ── a queue: Whisper on each finished chunk
                     Diarizer ── who spoke when, matched to known voices
                 MeetingStore ── transcript.jsonl + notes.md per meeting
                   Summarizer ── after the call, and on demand during it
```

```python
class CallDetector(Protocol):        # app side, reported to the brain as `call_started` / `call_ended`
    ...

class CallAudio(Protocol):
    """Two streams: the user's microphone and the call's audio, kept separate."""
    def start(self, on_chunk: Callable[[Track, Audio], None]) -> None: ...
    def stop(self) -> None: ...

class Diarizer(Protocol):
    def speakers(self, audio: Audio) -> list[Turn]:
        """Who spoke when in one chunk of the call track. Turn(start, end, voice: VoiceEmbedding)."""

class VoiceBook(Protocol):
    """Known voices, so "Speaker 2" becomes "Anna" after the user names her once."""
    def match(self, voice: VoiceEmbedding) -> str | None: ...
    def learn(self, name: str, voice: VoiceEmbedding) -> None: ...

class MeetingStore(Protocol):
    def open(self, meeting: MeetingInfo) -> str: ...
    def append(self, meeting_id: str, lines: Sequence[TranscriptLine]) -> None: ...
    def close(self, meeting_id: str, notes: MeetingNotes) -> None: ...
    def unfinished(self) -> list[str]:
        """Meetings with chunks on disk that aren't transcribed yet, for recovery after a crash."""
```

## Getting the audio

- **The user's voice** comes from the microphone, as today.
- **The other people** come from the call app's own audio output, not the speakers. macOS 14.4 and later can tap one process's audio with Core Audio process taps; ScreenCaptureKit audio capture is the fallback. Either needs the user's permission once.
- Two tracks give "you" versus "them" for free and remove echo of the others from the user's track.
- Without headphones the microphone also hears the speakers. Before Whisper reads a chunk of the user's track, `echo_muted` (services/meeting_text.py) compares its loudness, 50 ms frame by frame, with the call track at the same moment: where the mic only follows the call, a little later and at a steady ratio, it's the call's echo and is muted. Where the mic is clearly louder than that echo would be, the user is talking over the call and stays. Real echo cancellation in the app (Apple's voice processing) would be better still.

## Never losing a meeting

- Audio goes to disk in 30-second chunks (`meetings/<id>/audio/0001.flac`, …) as it arrives, before anything else happens to it. A chunk that's on disk is safe.
- A queue transcribes finished chunks in order on the STT executor, at a priority below live dictation and talk, so the user's own dictation stays instant during a call. Each transcribed chunk appends lines to `meetings/<id>/transcript.jsonl` and re-renders `transcript.md`.
- On start, `MeetingStore.unfinished()` finds chunks without transcripts and queues them. A crash, a restart or a full disk loses at most the chunk being recorded.
- Raw audio is deleted after the notes are done, unless the user keeps it (setting).

## Telling speakers apart

- The user's track is always the user.
- A speaker's language is only named when Whisper is at least 80% sure (`SURE_OF_LANGUAGE`). Music and a few words otherwise sent passes off into the wrong language.
- The whole-call regroup starts the moment the user presses Stop, on its own thread, while the last passes still run, so the notes don't wait for it after them.
- The call track gets split into turns by a small local speaker-embedding model (candidates: pyannote's segmentation and embedding models, or sherpa-onnx's speaker models; measure size, speed and accuracy on the M3).
- Names come from the calendar invite's attendees, the call app's window (who is speaking, when it shows it), and the user naming a voice once ("that was Anna"). `VoiceBook` remembers voices locally.

## Consent and law

Recording other people needs their consent in many places (Germany among them). Milo should:

- never start recording without the user's yes (or their explicit "always for calendar meetings" setting),
- offer a one-line message for the chat ("Milo is taking notes for me"),
- keep everything local unless the user shares it.

## Tests

- Feed recorded multi-speaker clips (generated with `say` voices for CI, real recordings on demand) through the pipeline and check transcript order, speaker labels and recovery after a killed brain.
- A one-hour soak test with a synthetic call to check memory use stays flat.
