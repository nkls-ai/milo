# 18. Meeting notes: the app records to disk, the brain transcribes in passes

Date: 2026-10-30. Status: accepted. Design: [docs/design/meetings.md](../design/meetings.md). Research and numbers: [docs/research/meetings.md](../research/meetings.md).

## Context

Milo should take notes in calls: who said what, a summary, decisions and to-dos, all on the Mac. An hour-long call has to work like a five-minute one, a crash of either process must not lose what was already said, and the user's own dictation has to stay instant during a call. Recording other people needs the user's yes every time, and their consent in many places.

## Decision

- **The app records, to disk first.** The app holds the microphone and the permission for the call's audio, so it records both: `me` through AVAudioEngine, `them` through one Core Audio process tap of everything the Mac plays except Milo and the brain (macOS 14.4+), or ScreenCaptureKit below that. Each track goes into 30 s, 16 kHz WAV chunks in `~/Milo/meetings/<id>/audio/` (folder 0700, files 0600), with the header written first. The brain hears about a chunk only after it is on disk (`meeting_chunk`). Sending audio over the socket was the other option; it would have lost whatever was in flight when the brain restarted.
- **The brain decides.** The app reports calls (`call_started`, `call_ended`) from who uses the mic and browser window titles. The brain asks once through Approvals, shown rather than spoken because the user is in a call, and starts the recording with `meeting_record`. `[meetings] auto = "calendar"` skips the question during a calendar event, and `"off"` never asks. The menu item stops a recording in the app at once, without waiting for the brain.
- **Passes on the shared STT thread, behind the user.** Whisper is one model on one thread. A pass is one track's next 30 s at most, cut at the quietest moment. Every Whisper call of a pass goes through `BackgroundStt`, which waits while the mic is on or Milo is listening, dictating or transcribing. A second Whisper thread would double the GPU memory on a 16 GB Mac.
- **Progress marks make passes safe to repeat.** A pass writes its lines and `{"track", "upto"}` to `transcript.jsonl` in one write. Lines without their mark don't count. A restarted brain starts each track after its last mark, so a crash repeats at most one pass and nothing counts twice.
- **Speakers from Whisper's segments.** The `them` track's Whisper segments, split at sentence ends and pauses, get one voice embedding each (sherpa-onnx with TitaNet-small, behind the `Diarizer` port). An online tracker keeps the meeting's voices across passes and merges near-duplicates at the end. A segmentation model (pyannote through sherpa-onnx) was tried first and gave 58% against 96% for this.
- **Meeting text is data.** During a call LiveTalk gets a `<meeting>` block with what was said, escaped, and the conversation counts as tainted. The follow-up mail goes to a careful helper with the meeting text inside a `<meeting_draft>` data block.

## Consequences

- Speech is in the transcript about 40 to 60 s after it was said, measured in real time on a loaded M3: the chunk takes 30 s to fill and the pass takes the rest. A question during the call ("what did he just say?") also transcribes the chunk still being written, so it sees the last seconds.
- Dictation during a call can wait for the one meeting Whisper call already running: one call on at most 30 s of audio, about 1.5 s on an idle M3 and 4 to 8 s when the Mac is under heavy load (measured during this work).
- The global tap also hears music or a video playing during the call.
- The tap's permission can't be checked through public API. A call track that stays digitally silent for 45 s is reported as missing, with the switch to turn on.
- Memory stays flat over a call: the service keeps only the meeting's voices and state, and reads the rest from disk.
- `on_episode` hands a memory episode stub per meeting to whoever wires it. The memory track connects it to its episode log.
