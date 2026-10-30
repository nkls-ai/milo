# Meeting notes: design

Status: proposed, 2026-10-30. Builds on the listening pipeline (committed segments) and on [memory](memory.md).

## What the user gets

- Milo notices a call (Zoom, Teams, Meet, FaceTime, Slack huddles) and asks once: "Looks like a meeting. Should I take notes?" A setting can make it automatic for meetings in the calendar.
- While he records, a red dot shows on Milo and in the menu bar. There's no hidden mode.
- During the call: "what did he just say about the deadline?", "sum up the last ten minutes".
- After the call: a summary, decisions, the user's to-dos (offered as Reminders), and a follow-up mail draft if the user wants one. The notes land in `~/Milo/meetings/` as Markdown and as an episode in memory.
- An hour-long call works the same as a five-minute one, and a crash loses at most the last few seconds.

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

## Never losing a meeting

- Audio goes to disk in 30-second chunks (`meetings/<id>/audio/0001.flac`, …) as it arrives, before anything else happens to it. A chunk that's on disk is safe.
- A queue transcribes finished chunks in order on the STT executor, at a priority below live dictation and talk, so the user's own dictation stays instant during a call. Each transcribed chunk appends lines to `meetings/<id>/transcript.jsonl` and re-renders `transcript.md`.
- On start, `MeetingStore.unfinished()` finds chunks without transcripts and queues them. A crash, a restart or a full disk loses at most the chunk being recorded.
- Raw audio is deleted after the notes are done, unless the user keeps it (setting).

## Telling speakers apart

- The user's track is always the user.
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
