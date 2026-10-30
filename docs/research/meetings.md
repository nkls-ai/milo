# Meeting notes: research and choices

2026-10-30. Background for [docs/design/meetings.md](../design/meetings.md). It covers how to get the call's audio on a Mac, how to tell that a call is on, how to tell speakers apart locally, and what the open-source meeting-note apps do. Licenses had to be MIT, Apache or BSD for code, and allow commercial use for model weights. GPL and AGPL code was read for ideas, never copied.

## What Milo uses

| Part | Choice | License | Size |
|---|---|---|---|
| The call's audio | Core Audio process tap of everything except Milo and its brain (macOS 14.4+), ScreenCaptureKit audio below that | Apple SDK | 0 |
| The user's voice | AVAudioEngine on the microphone, in the app | Apple SDK | 0 |
| Noticing a call | Core Audio's process list (`kAudioProcessPropertyIsRunningInput`) every 2.5 s, plus browser window titles through Accessibility | Apple SDK | 0 |
| Words with times | mlx-whisper large-v3-turbo, already in Milo, with `word_timestamps` | MIT | 0 extra |
| Telling voices apart | sherpa-onnx `SpeakerEmbeddingExtractor` with NeMo TitaNet-small, one embedding per Whisper segment, our own online clustering | sherpa-onnx Apache-2.0, TitaNet weights CC-BY-4.0 | 2 MB wheel + 9 MB core + 40 MB model |
| Summary, decisions, to-dos | The chat model Milo already uses, a fresh session per meeting | n/a | 0 |

Nothing new is needed in the app. The brain gains one package, `sherpa-onnx` (no torch). The diarizer is behind the `Diarizer` port and the `DIARIZERS` registry, so FluidAudio or pyannote can replace it later without touching the service.

## Getting the call's audio

**Core Audio process taps** (macOS 14.2 API, but asking for the permission only works from 14.4). Apple's sample is [Capturing system audio with Core Audio taps](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps), and [AudioCap](https://github.com/insidegui/AudioCap) (BSD-2) is the smallest working Swift example. Milo follows AudioCap's steps:

1. `CATapDescription(stereoGlobalTapButExcludeProcesses:)` with Milo's and the brain's process objects, `isPrivate`, `muteBehavior = .unmuted`.
2. `AudioHardwareCreateProcessTap`, then a private aggregate device on the default output with the tap in its tap list.
3. `AudioDeviceCreateIOProcIDWithBlock` and `AudioDeviceStart`. The format comes from `kAudioTapPropertyFormat`, usually 48 kHz float stereo. Milo resamples it to 16 kHz mono with `AVAudioConverter`.
4. Teardown runs in the reverse order.

A global tap, rather than a tap per app, was the right call. Chrome, Arc, Edge, Teams and Slack play audio through a separate audio-service helper process, Safari through `com.apple.WebKit.GPU`, and FaceTime through daemons (`avconferenced`). A per-app tap has to hunt for those. [meeting-transcriber](https://github.com/pasrom/meeting-transcriber) (MIT) does the hunting in `tools/audiotap` and still has edge cases. A global tap that leaves Milo out gets all of them. It also catches music or a video playing at the same time, which is the price.

The permission ("System Audio Recording", TCC service `kTCCServiceAudioCapture`) has no public API to check or request. Without it every call returns `noErr` and the buffers are all zeros ([dev.to, "2000 buffers of nothing"](https://dev.to/nickdelv/2000-buffers-of-nothing-3i8); [Apple forum](https://developer.apple.com/forums/thread/825780)). AudioCap calls the private `TCCAccessPreflight` behind a build flag. Milo doesn't use private API. Instead, a call track that stays digitally silent for 45 s is reported to the brain as missing, with plain words about the switch in System Settings, and it counts again once sound arrives. `NSAudioCaptureUsageDescription` has to be in Info.plist by hand.

**ScreenCaptureKit** is the fallback for macOS 14.0 to 14.3, or when the tap fails. `capturesAudio`, `excludesCurrentProcessAudio`, `sampleRate = 16000` and `channelCount = 1` are all supported ([sampleRate](https://developer.apple.com/documentation/screencapturekit/scstreamconfiguration/samplerate), [WWDC22 10156](https://developer.apple.com/videos/play/wwdc2022/10156/)). It needs Screen Recording, which Milo already asks for to look at the screen. It filters by app only and misses daemon audio, so FaceTime is silent through it.

The microphone starts before the tap. Starting the aggregate device first can keep AirPods in their music profile.

## Noticing a call

Call apps use the microphone only in a call, so the mic is enough for them. Core Audio lists every process that uses audio (`kAudioHardwarePropertyProcessObjectList`), with its pid, bundle id and `kAudioProcessPropertyIsRunningInput`. On this Mac the list shows the same bundle ids the research found: `com.google.Chrome.helper`, `com.brave.Browser.helper`, `com.apple.WebKit.GPU`, `com.apple.avconferenced`.

| App | How Milo knows |
|---|---|
| Zoom (`us.zoom.xos`), Teams (`com.microsoft.teams2`), FaceTime, Webex | Uses the mic |
| Slack (`com.tinyspeck.slackmacgap`) | Uses the mic (only in a huddle) |
| Meet, Teams, Zoom, Whereby or Jitsi in a browser | The browser's helper uses the mic and a window is titled `Meet - …`, `… \| Microsoft Teams`, `Zoom Meeting`, … |

A call starts after two polls in a row (about 5 s, so a mic check in Zoom's settings isn't a call) and ends after three polls without it. The brain waits `[meetings] end_after_s` more before it stops the notes, because muting or a dropped connection isn't the end.

Others do more: [Hyprnote/anarlog](https://github.com/fastrepl/anarlog) (MIT) reads the "Leave Huddle" button and Zoom's mute state through Accessibility, and meeting-transcriber reads power assertions (`IOPMCopyAssertionsByProcess`: Teams says "call in progress"). Milo's detector only has to be good enough to ask once, so it stays at the mic plus titles. [OverSight](https://github.com/objective-see/OverSight) is GPL-3.0 and was only read. [MeetingBar](https://github.com/leits/MeetingBar) (Apache-2.0) works from the calendar, which Milo already reads through EventKit for `auto = "calendar"` and for attendee names.

## Telling speakers apart

### Candidates

| Option | License | Notes |
|---|---|---|
| [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 2.0.1 | Apache-2.0 | `uv add`, arm64 wheel, onnxruntime inside, no torch. `OfflineSpeakerDiarization` (pyannote segmentation 3.0, MIT) and `SpeakerEmbeddingExtractor` with many embedding models. |
| pyannote.audio 4 / community-1 | MIT code, CC-BY-4.0 weights, gated download | Best-known accuracy (DER 11.2 on VoxConverse), but torch and lightning, about 1 GB more. |
| [FluidAudio](https://github.com/FluidInference/FluidAudio) 0.18 | Apache-2.0, CC-BY-4.0 weights | CoreML on the Neural Engine, very fast offline ([benchmarks](https://github.com/FluidInference/FluidAudio/blob/main/Documentation/Benchmarks.md)), but Swift only, and chunked streaming DER goes up to 38%. |
| [senko](https://github.com/narcotic-sh/senko) | MIT | CoreML CAM++, whole files only, pulls in umap and hdbscan. |
| whisperX | BSD-2 | Needs torch and faster-whisper next to mlx-whisper. Skipped. |
| NeMo Sortformer v1, VoxBlink2 models, Rev's Reverb | Non-commercial | Out. |

The embedding models sherpa-onnx ships ([release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models)) are 3D-Speaker CAM++ and ERes2Net (Apache-2.0), and WeSpeaker ResNet34 and NeMo TitaNet (CC-BY-4.0, which allows commercial use with attribution).

### What I measured

German and English `say` voices (Anna, Daniel, Samantha, Fred, Moira, Rishi), cut into the same sentences, on an M3 under load. "Same" is the lowest cosine between two clips of one voice, "different" is the highest between two voices. A wider gap is better.

| Embedding | Same, lowest | Different, highest | Time per clip |
|---|---|---|---|
| NeMo TitaNet-small (40 MB) | 0.81 | 0.59 | 0.05 s |
| 3D-Speaker ERes2Net | 0.75 | 0.51 | 0.45 s |
| 3D-Speaker CAM++ zh+en | 0.75 | 0.61 | |
| WeSpeaker ResNet34 | 0.89 | 0.81 | |
| 3D-Speaker CAM++ en VoxCeleb | broken output with sherpa-onnx 2.0.1 | | |

TitaNet-small separates as well as ERes2Net and is about nine times faster, so it's the default. ERes2Net (Apache weights) is one setting away: `[meetings.sherpa_onnx] embedding = "eres2net"`.

Then the whole pipeline on a generated meeting:

| Approach | Speech given to the right speaker |
|---|---|
| sherpa `OfflineSpeakerDiarization` (pyannote segmentation + clustering) | 57.7%, at about 0.5x real time |
| Embeddings over sliding 1.5 s windows | 63% |
| One embedding per Whisper segment | 100% at the embedding level, 96.4% end to end |

Segmentation models are trained on real conversations with overlap and noise, and on clean synthetic turns they cut in the wrong places. Whisper already knows where sentences start and end. So Milo embeds the stretches between Whisper's segment boundaries, sentence ends and pauses of 0.4 s or more, and clusters those online across the meeting:

- A stretch joins the nearest known voice above 0.6 cosine, and updates it only from 2 s of speech or more.
- A stretch becomes a new voice only from 1 s of speech. Shorter ones go to the nearest known voice. Short turns are where embeddings get unreliable ([DAME](https://arxiv.org/html/2601.13999v1): ResNet34 EER goes from 1% to 4.3% with 1 s tests).
- At the end, voices closer than 0.75 merge (one person who sounded different at first).
- The voice book matches finished voices with 8 s of speech or more against voices the user named before ("that was Anna").

The online part follows [diart's incremental clustering](https://github.com/juanmc2005/diart/blob/main/src/diart/blocks/clustering.py) in spirit (MIT, read, not copied).

## Two things Whisper does in a meeting

**One language per 30 s window.** Whisper picks one language for the window. When Anna speaks German and Sam English in the same window, one of them comes out translated. Milo finds each speaker's language once from 2 s of their speech, then transcribes the stretches of speakers whose language differs from the window's again, glued together, one call per language.

**A skipped sentence.** Large-v3-turbo sometimes drops a sentence inside a segment. Milo looks for speech energy that no word covers, glues those stretches and runs Whisper once more on them, and removes words the second pass repeats.

Together the two fixes took word error on the call track from 18.9% to 3.0% on the mixed German and English script.

## What the open-source meeting apps do

| App | License | What Milo took |
|---|---|---|
| [Hyprnote / anarlog](https://github.com/fastrepl/anarlog) | MIT (outside `enterprise/`) | The WAV header written before any audio, so a crash leaves a readable file. Echo handling is skipped on headphones. |
| [Meetily](https://github.com/Zackriya-Solutions/meetily) | MIT | 30 s checkpoints that survive a crash. Meetily mixes everything into one track; Milo keeps two. |
| [meeting-transcriber](https://github.com/pasrom/meeting-transcriber) | MIT | Two 16 kHz tracks, one diarized; a watchdog for a silent tap; an echo check that drops mic lines matching the call. |
| [Recap](https://github.com/RecapAI/Recap), [audiotee](https://github.com/makeusabrew/audiotee) | MIT | Confirmation that the AudioCap tap setup works in shipping apps. |

Milo writes every chunk to disk first: `~/Milo/meetings/<id>/audio/me-0001.wav`, `them-0001.wav`, … (16 kHz mono 16-bit, folder 0700, files 0600). The header goes in at the start and gets its sizes when the chunk is full. The brain reads a chunk to its last byte, whatever the header says, so a chunk from a crashed app still counts. Passes take at most 30 s, cut at the quietest moment between 24 and 30 s, and each pass writes its lines and a progress mark to `transcript.jsonl` in one write. A restarted brain starts after the last mark: nothing is lost and nothing is said twice. A test kills the brain process with SIGKILL in the middle of a pass and checks exactly that.

## Numbers

All on the M3 with 16 GB, while other agents ran builds and models (load average 4 to 13).

| What | Result |
|---|---|
| Speakers found, generated 6-voice meeting (5 others + the user) | 5 of 5 |
| Speech given to the right speaker | 96.4% (1.2 min), 98.7% (3.6 min), 99.3% (9.7 min) |
| Word error, call track, German + English | 3.0% to 3.7% |
| Echo of the call kept on the user's track | 0 of 12 lines, 1 of 33 |
| Processing, models already loaded | 0.57x to 1.21x the meeting's length, depending on load |
| Speech to transcript, chunks arriving in real time (3.6 min call) | median 42 s, 90% 54 s, max 62 s: the 30 s chunk fills, then a 7 to 12 s pass under load |
| Memory over 1 h of call, service and store with fake models | flat, 303 MB at minute 5 and 45, 255 MB at 55 |
| Memory over a 9.7 min call with the real models (160 lines, 99.3% attributed, WER 3.4%) | 1.65 to 2.4 GB resident plus MLX, going up and down with MLX's buffer cache, no upward trend; processed in 0.60x the call |
| Models loaded | about 1 GB resident (Whisper large-v3-turbo + TitaNet-small) |

The remaining mistakes are short replies ("Yes, exactly.", under 1 s) that go to the nearest voice, and a pass cut that splits "one more / thing" across two lines.

## Not verified

- The process tap and its permission prompt. Creating a tap records what the Mac plays, and the rules for this work forbid recording real audio. The tap code builds against the macOS 15.5 SDK and follows AudioCap step by step, but it hasn't run. The first real test is a call with a test account.
- The ScreenCaptureKit fallback, for the same reason.
- Call detection with a real Zoom, Teams, Meet or FaceTime call. The classifier is tested on bundle ids and titles, and the Core Audio process list was read on this Mac (no app used the mic at the time).
- An hour with the real models in one go. The model lock allows about 15 minutes, so the hour ran with the test fakes (flat at 303 MB) and the real models ran for 9.7 minutes.
- Diarization of real voices over a real call connection. The numbers above are `say` voices, which are cleaner and more distinct than people on a bad line. The voice-match threshold (0.6) will likely need tuning on real calls.
- German speaker-embedding quality in general: no published benchmark covers it.
