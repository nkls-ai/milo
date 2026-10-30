# Voice: ElevenLabs streaming speech, cloud listening, faster replies

Track 11, measured 2026-10-30 on the user's 16 GB M3 (heavily loaded, swap in use), from Germany. The sources and
the wider research are in the second half of this file.

## What Milo does now

- **Speaking.** `[tts] use = "elevenlabs"`, `eleven_v4_turbo` with the voice Callum (since 2026-10-31, see
  "Eleven v4 Turbo" below): one WebSocket to ElevenLabs' `text-to-dialogue/stream-input`, kept warm while Milo
  talks. A reply is one turn: each whole sentence goes in, flushed, as soon as the chat model has written it, and
  the audio plays as it arrives (PCM 24 kHz). A cut-off reply drops the socket and a fresh one opens. The v2.5
  models (`eleven_flash_v2_5`) still work over `multi-stream-input`, one context per reply.
  Pauses longer than 0.5 s inside the audio are shortened. Hold, barge-in and backchannels work as before.
- **Fallback.** If ElevenLabs can't be reached, the rest of the reply is spoken by `[tts] fallback` (default "say")
  for two minutes, and Milo says once, plainly, that he is using his own voice for a while. The fallback is not
  built or loaded until the first failure, so OmniVoice's GBs stay out of memory.
- **Listening (optional).** `[stt] talk = "elevenlabs"` streams talk-key recordings to Scribe v2 Realtime while
  the key is held. The text is there about 0.2 s after release, its guesses fill the live words, and Whisper isn't
  woken at all for those recordings. Dictation stays on the Mac unless `[stt] cloud_dictation = true`. On a
  failure the recording is transcribed locally, and Milo says so once.
- **Chat.** `[chat.claude_live] model` defaults to Haiku 5.5.

## Measurements

### Text to speech

| strategy (flash v2.5, one context) | first audio | phrase pitch spread (F0 sd) |
|---|---|---|
| auto_mode, whole sentences (chosen) | 0.19–0.24 s from the first sentence on a warm connection; ~0.5 s cold | 0.5–1.4 semitones, same as one whole-text render |
| default schedule, word deltas | 0.62–0.66 s | |
| clause pieces | | 2.4–3.4 st: audible jumps |
| word pairs with auto_mode | | choppy, 15 pauses in 3 lines |
| first clause cut early (tried, rejected) | 0.1–0.23 s sooner | largest jump between pieces 2.1–4.3 st (vs 0.7–2.9) |

ElevenLabs output arrives at about −20 dBFS with at most 50 ms of lead silence, so no level matching is needed.
Its own pauses can reach 1.1 s; they are capped at 0.5 s.

### Speech to text (Scribe v2 Realtime, manual commit)

From the commit to the text: 0.18–0.27 s. A 1.3 s utterance works; silence answers "" in 0.2 s; German and
English mixed in one sentence came back word for word with `secondary_languages=de,en`.

### Chat first token (claude CLI, stream-json, real 2.6k-token system prompt, ~85% cached)

| model | first delta | first sentence (median) |
|---|---|---|
| Haiku 5.5 | ~1.0 s | ~1.3 s |
| Sonnet 5.5, effort low | 1.15–3.6 s | ~2.1 s |

`--bare` would skip some start-up but needs an API key, which this setup doesn't use.

### End to end

Old path, from the user's own brain.log on 2026-10-30 (Whisper + Sonnet + OmniVoice): the final transcription took
2–15 s after release, the first chat delta 1.1–4.2 s, the first sound came 2.68 s after the first text, and the
gaps between spoken pieces were 0.2–7.2 s.

New path, test brain (Scribe, Haiku, ElevenLabs Will; recorded question as the mic, output to WAV):

| step | time |
|---|---|
| text ready after key release | 0.17–0.19 s |
| first chat delta | 0.92–1.01 s |
| first word heard, after release | 1.59–1.86 s |
| first word heard, after speech ended | 1.84–2.11 s |
| gaps between pieces | none (no "speech gap" logged) |

The 1.0 s target is not reached: the CLI's first token alone is about 0.95 s. A direct API connection with an
API key would be the next step.

## Voices

The free plan can't use library voices through the API (402 `paid_plan_required`) or Voice Design (403
`feature_not_available`), so the candidates are the account's premade voices, all on flash v2.5. Each said one
German, one English and one mixed line plus "Hm." through the streaming path, and Scribe transcribed it back:

| rank | voice | voice_id | word errors | first sound | notes |
|---|---|---|---|---|---|
| 1 | Will | `bIHbv24MWmeRgasZH58o` | 3% | 0.18–0.27 s | young, relaxed, conversational; clean German |
| 2 | Chris | `iP95p4xoKVk53GoZ742B` | 3% | 0.18–0.27 s | down-to-earth, a touch drier |
| 3 | River | `SAz9YHcvj6GT2YYXdXww` | 0% | 0.18–0.27 s | calm and neutral, less character |
| 4 | Roger | `CwhRBWXzGAHq8TQ4Fs17` | 3% | 0.18–0.27 s | laid-back, a bit older |
| – | Eric | | 12% | | smooth but older; added an "Okay" |
| – | Liam | | 6% | | too hyped |
| – | Brian | | 3% | | too deep, announcer |
| – | George | | 3% | 0.33–0.49 s | narrator, slower |

## Eleven v4 Turbo and a higher voice (2026-10-31)

Eleven v4 and v4 Turbo came out in late September 2026, on every plan at the same credit price. They are refused
by `multi-stream-input` (HTTP 400) and spoken over the dialogue socket (`/v1/text-to-dialogue/stream-input`):
first message `{"voices": [id], "voice_settings": {"stability": ...}}`, then `{"inputs": [{"text", "voice_id",
"new_turn"}], "flush": true}` per sentence. Every flush is answered with `is_final_audio_for_turn`, so a reply
can stream sentence by sentence; without a flush the server waits for about 40 characters. `alignment` uses
snake_case keys and matched the sent text character for character ("3,50 €", "12.11.", "10%", "Dr."). The
socket closes after 20 s without a message, so an idle one gets `{"keep_alive": true}` every 10 s.

| model (voice Will, then Callum) | first audio, warm |
|---|---|
| eleven_flash_v2_5, HTTP stream | 0.36 s (one run) |
| eleven_v4_turbo, HTTP stream | 0.23 s (one run) |
| eleven_v4_turbo, dialogue socket, through the adapter | 0.10 to 0.13 s |
| eleven_v4, dialogue socket | 0.75 s |

A cut-off reply, then the next one: 0.11 s to first audio, nothing of the old reply in it. After 25 s idle: 0.12 s
on the same connection. Pitch: three sentences sent as three flushed pieces showed no larger jumps than the same
text sent whole (largest gap between thirds 4.1 to 6.0 vs 6.2 to 8.0 semitones, a rough autocorrelation measure;
the spread is Callum's own intonation).

The user asked for a higher voice than Will. Premade voices on v4 Turbo, median pitch of one mixed
German/English line: Will 157 Hz, Callum 169 (+1.3 st), Liam 170, Chris 174, Charlie 188 (+3.2), Harry 208
(+4.9), River 246, Jessica 242. The user picked Callum (`N2lVS1w4EtoT3dr4eOWO`). Voice Design and library voices
would give more choice but need a paid plan.

## Licences

Only `websockets` (BSD-3-Clause) was added. Nothing from Pipecat or LiveKit was copied; their protocol use was
read for reference.

## Research notes

Researched 2026-10-30. Primary sources only. Where a number is vendor-reported, it says so.
Source snapshots (git HEAD on 2026-10-30):

- pipecat `6f777a0ef3bb98163d10d708525a0db21cda5fbf`
- livekit/agents `11c8ad8d74c272cf046e65d83cfe7be46abaec64`
- elevenlabs-python `ce12cc97d3aeabeb1a8c49073e127512c79d1e6b`
- elevenlabs-js `857eb262272ba408495e3c8c8a983a208ebc9950`
- parakeet-mlx `a47079fb1bdc324d1228af6455f1eef8e97e6fae` (v0.5.3)
- smart-turn `4786657e242dfe77dd138699ac564ee074a2a543`

Abbreviations: TTF = time to final transcript after end of speech. AA = Artificial Analysis.

---

### 0. TL;DR

- **Scribe v2 Realtime** is a sound primary. AA measures TTF at 0.135 to 0.159 s with a forced endpoint, which is a manual commit. Its English streaming WER index is 3.6%, the best among services that finalize in under 200 ms, tied with AssemblyAI U3.6 at about 0.19 s. It costs $0.39/h. German is in ElevenLabs' "Excellent (≤5% WER)" bucket. Intra-utterance code-switching is **not documented**, so test it.
- **Soniox stt-rt-v5** is the backup and the first A/B candidate for mixed de/en. It costs $0.12/h, AA TTF is about 0.055 s, it claims mid-utterance language switching, and it takes `language_hints`.
- **parakeet-mlx + parakeet-tdt-0.6b-v3** is a credible local upgrade over Whisper for German. Accuracy is roughly at parity (de: 4.90 vs 4.97 avg WER on the Open ASR multilingual track) and it is much faster on Apple silicon. The weights are CC-BY-4.0, which is commercial OK with attribution. Use it in batch mode on end of turn, not its streaming API.
- **Pipecat's default stack:** Silero VAD `stop_secs=0.2` plus Smart Turn v3 (BSD-2, 8 MB, German supported at 96.1% test accuracy). It sends the ElevenLabs `multi-stream-input` WS one context per LLM turn, ends with `flush` then `close_context`, interrupts with `close_context`, and sends a keepalive `{"text": ""}` every 10 s.

---

### 1. ElevenLabs Scribe v2 Realtime: exact protocol

Sources: [API ref](https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime) ([.md](https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime.md)), [commit strategies guide](https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/transcripts-and-commit-strategies.md), [event reference](https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/event-reference.md), SDKs: [python scribe.py](https://github.com/elevenlabs/elevenlabs-python/blob/ce12cc97d3aeabeb1a8c49073e127512c79d1e6b/src/elevenlabs/realtime/scribe.py), [python connection.py](https://github.com/elevenlabs/elevenlabs-python/blob/ce12cc97d3aeabeb1a8c49073e127512c79d1e6b/src/elevenlabs/realtime/connection.py), [js scribe.ts](https://github.com/elevenlabs/elevenlabs-js/blob/857eb262272ba408495e3c8c8a983a208ebc9950/src/wrapper/realtime/scribe.ts), [js connection.ts](https://github.com/elevenlabs/elevenlabs-js/blob/857eb262272ba408495e3c8c8a983a208ebc9950/src/wrapper/realtime/connection.ts).

#### Endpoint and auth
- `wss://api.elevenlabs.io/v1/speech-to-text/realtime`
- Regional hosts: `wss://api.us.elevenlabs.io`, **`wss://api.eu.residency.elevenlabs.io`** (EU residency; probably the lowest RTT from Germany), plus `in.residency` and `sg.residency`.
- Auth: header `xi-api-key: <key>`, or query `token=<single-use token>`. Both SDKs omit the header when a token is given.

#### Query parameters (all on the URL; there is no config message)
| param | type / range | default | notes |
|---|---|---|---|
| `model_id` | `scribe_v2_realtime` | `scribe_v2_realtime` | only enum value |
| `audio_format` | `pcm_8000`, `pcm_16000`, `pcm_22050`, `pcm_24000`, `pcm_44100`, `pcm_48000`, `ulaw_8000` | `pcm_16000` | 16-bit LE mono PCM; mono only |
| `commit_strategy` | `manual`, `vad`, `turn_prediction` | `manual` (SDKs and guide) | `turn_prediction` is "only for models that predict turns, where it is the default". `session_started.config` schema lists only manual and vad. |
| `vad_silence_threshold_secs` | 0.192 to 3.0 (server); JS/React SDK 0.3 to 3.0 | not documented | VideoSDK wrapper uses 0.8, which is not official. Guide examples use 1.5. |
| `vad_threshold` | 0.1 to 0.9 | not documented | 0.15 when `filter_background_audio=true` and unset |
| `min_speech_duration_ms` | 50 to 2000 | not documented | guide example 100 |
| `min_silence_duration_ms` | 50 to 2000 | not documented | guide example 100 |
| `language_code` | ISO-639-1 or -3 | none, meaning auto-detect | |
| `secondary_languages` | repeated param | none | "Providing them makes language identification more reliable by only focusing on a certain set of languages" (JS SDK doc) |
| `include_timestamps` | bool | false | adds `committed_transcript_with_timestamps` |
| `include_language_detection` | bool | false | detected `language_code` arrives in the with-timestamps message |
| `keyterms` | repeated, max 50, each ≤20 chars (SDK doc) | none | +$0.08/h surcharge |
| `no_verbatim` | bool | false | strips fillers and false starts |
| `entity_detection` | `all`, a category, or a type, repeated | none | |
| `transcript_edit` | string ≤2000 chars | none | +30% cost; cannot combine with entity_detection |
| `filter_background_audio` | bool | false | **cannot combine with `include_timestamps`** (sends `invalid_request` and closes) |
| `keepalive_interval_ms` | int 500 to 10000 | disabled | see below |
| `enable_logging` | bool | true | false means zero retention (enterprise only) |
| `token` | string | none | single-use token |

Example: `wss://api.elevenlabs.io/v1/speech-to-text/realtime?model_id=scribe_v2_realtime&audio_format=pcm_16000&commit_strategy=manual&secondary_languages=de&secondary_languages=en&include_language_detection=true`

#### Client to server: one message type
```json
{"message_type":"input_audio_chunk","audio_base_64":"<b64 pcm>","commit":false,"sample_rate":16000}
```
- All four fields are required (`message_type`, `audio_base_64`, `commit`, `sample_rate`).
- `previous_text` (optional) is allowed **only on the first chunk**; on a later chunk the server returns an error. It "works best when it's under 50 characters". Use cases: the agent's last utterance, or context after a reconnect.
- **Manual commit.** This is exactly what both SDKs and Pipecat send:
  `{"message_type":"input_audio_chunk","audio_base_64":"","commit":true,"sample_rate":16000}`
- Chunk size: "Send audio chunks of 0.1 - 1 second". The server-side example uses 32000 B (1 s at 16 kHz). Oversized chunks trigger the `chunk_size_exceeded` error, but no limit is documented.

#### Server to client (`message_type` field)
- `session_started`: `{session_id, config:{sample_rate, audio_format, language_code, commit_strategy, vad_silence_threshold_secs, vad_threshold, min_speech_duration_ms, min_silence_duration_ms, model_id, enable_logging, include_timestamps, include_language_detection, keyterms, no_verbatim, keepalive_interval_ms}}`
- `partial_transcript`: `{text}`. Interim; later partials replace earlier ones. An empty `text` means "no speech in current segment". Repeated identical partials during a pause are keepalives.
- `committed_transcript`: `{text}`. Final for the segment and will not change.
- `committed_transcript_with_timestamps`: `{text, language_code|null, words:[{text,start,end,type:"word"|"spacing",speaker_id,logprob,characters}]|null}`. Sent *after* `committed_transcript`, and only when `include_timestamps` or `include_language_detection` is set. Pipecat skips the plain committed message when either flag is on, to avoid double-emitting ([stt.py L940-L1010](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/services/elevenlabs/stt.py#L940)).
- `committed_transcript_entities`, `edited_transcript`, `warning {warning}`.
- Errors `{error}` with these types: `error`, `auth_error`, `quota_exceeded`, `commit_throttled`, `unaccepted_terms`, `rate_limited`, `queue_overflow`, `resource_exhausted`, `session_time_limit_exceeded`, `input_error`, `invalid_request`, `chunk_size_exceeded`, `insufficient_audio_activity`, `transcriber_error`. An error message is sent before the socket closes.
- The event reference says: "The public API does not emit a separate `final_transcript` event." The SDKs still handle `final_transcript` and `final_transcript_with_timestamps`, so tolerate unknown types.

#### Behaviour that matters for latency
- "Transcript processing starts after the first 2 seconds of audio are sent." "Audio is processed in roughly 1-second chunks." So expect partials at about 1 s cadence; they are not useful for early LLM starts. Commit is the fast path.
- Manual mode auto-commits after about 36 s of accumulated audio. ElevenLabs recommends committing during silence, "or another logical point like a turn model". Warning: "Committing manually several times in a short sequence can degrade model performance" (`commit_throttled` exists).
- **Idle close:** "the server closes the connection after 15 seconds without any client messages. This server limit is not configurable." `keepalive_interval_ms` only makes the server emit keepalive partials while you **keep streaming audio** (silence is fine).
- **Billing:** "metered on every second of audio you send, including pauses and silent stretches". So keeping the socket warm with silence costs money: 24 h × $0.39 = $9.36/day.
- Published latency: about 150 ms median "time to committed transcript", server-side, from production metrics, last updated 2026-10-29 ([methodology](https://elevenlabs.io/docs/eleven-api/concepts/latency-methodology.md)). This excludes network time.

#### Price and accuracy
- $0.39/h on every plan (Free gets 2.5 h; Creator 56 h; Pro 254 h). Keyterms add $0.08/h ([pricing](https://elevenlabs.io/pricing/api), fetched 2026-10-30). Batch Scribe v2 costs $0.22/h.
- German: listed in "Excellent (≤ 5% WER)" for Scribe v2 ([capabilities](https://elevenlabs.io/docs/overview/capabilities/speech-to-text.md)). Vendor-reported; no per-language number is published.
- Small independent German test (Famulor, 2026-10-13; **8 FLEURS clips per language, 161 German words**): Scribe v2 RT 0.62% de / 3.23% en. Next were Gemini 3.5 Transcribe Live (1.24% de), AssemblyAI U3.x (1.86%), Speechmatics Linden-1 (2.48%), Soniox v5 (3.73%), Deepgram Nova-3 (4.35%), Flux multi (6.21%). The sample is too small to rank on ([article](https://www.famulor.io/fr/blog/voice-ai-german-vs-english-benchmark-2026)).
- Older data point: Scribe **v1** averaged 10.8% de WER on the Open ASR multilingual track ([arXiv 2510.06961 Table 4](https://arxiv.org/html/2510.06961v3)). This is v1, not v2 RT.
- **Code-switching:** nothing in the ElevenLabs docs. Only `secondary_languages` exists. Test mixed de/en utterances yourself, with and without `language_code`.

#### Pipecat's Scribe integration ([stt.py](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/services/elevenlabs/stt.py))
- Defaults: `commit_strategy=MANUAL`, `model="scribe_v2_realtime"`, `include_timestamps=False`.
- Commits on every `VADUserStoppedSpeakingFrame` (Silero, after `stop_secs` = 0.2 s), **not** on smart-turn end-of-turn (L675-689). One user turn can therefore produce several committed segments, and the aggregator joins them.
- Keepalive: sends silent PCM as `input_audio_chunk` when no audio has been sent for 10 s, checking every 5 s (`keepalive_timeout=10, keepalive_interval=5`, L600-601; silence sender L741).
- P99 TTFS budget constant: `ELEVENLABS_REALTIME_TTFS_P99 = 0.41` s ([stt_latency.py L49](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/services/stt_latency.py#L49)). Compare Deepgram 0.35, Soniox 0.35, AssemblyAI 0.42, batch ElevenLabs 2.01.

---

### 2. Streaming STT comparison

#### Independent latency and WER: AA streaming STT (English data; no German breakdown)
Source: [artificialanalysis.ai/speech-to-text/streaming](https://artificialanalysis.ai/speech-to-text/streaming), data embedded in the page, fetched 2026-10-30.
- WER index = 50% AgentTalk + 25% VoxPopuli + 25% Earnings22.
- TTF is timed from the Silero end of speech. For services that support forced endpointing (for example a Scribe manual commit or Soniox finalize), AA sends the endpoint at that moment.

| model | WER idx | TTF s (AgentTalk / VoxPop / Earn22) | $/h |
|---|---|---|---|
| ElevenLabs Scribe v2 Realtime | 3.6% | 0.135 / 0.159 / 0.137 | 0.39 |
| Soniox v5 Real-Time | 4.5% | 0.054 / 0.051 / 0.057 | 0.12 |
| Deepgram Nova-3 Realtime | 6.6% | 0.061 / 0.057 / 0.086 | 0.29 (AA) |
| Deepgram Flux | 7.4% | 0.023 / 0.015 / 0.025 | 0.39 (AA) |
| AssemblyAI U3.6 Pro RT (min latency) | 3.6% | 0.190 / 0.193 / 0.195 | 0.45 |
| Speechmatics Agent STT Linden 1 | 4.4% | 0.150 / 0.163 / 0.164 | 0.30 |
| Cartesia Ink-2 (external endpoints) | 4.0% | 0.069 / 0.065 / 0.064 | 0.24 |
| OpenAI GPT Live Transcribe | 3.9% | 0.686 / 0.719 / 1.158 | 1.02 |
| OpenAI GPT Realtime Whisper | 4.9% | 0.680 / 0.648 / 0.743 | 1.02 |
| Voxtral Mini Transcribe RT 3 (480 ms) | 3.6% | 0.825 / 0.597 / 0.771 | 0.48 |
| MAI-Transcribe-2-Streaming (Microsoft) | 2.5% | 0.132 / 0.116 / 0.130 | 0.54 |

$/h = AA's $/1000 min × 0.06. MAI's German support was not checked.

#### Pipecat open STT benchmark ([pipecat-ai/stt-benchmark](https://github.com/pipecat-ai/stt-benchmark))
- 1000 samples from `smart-turn-data-v3.1-train`, scored by LLM-judged semantic WER.
- TTFS is measured from speech end, and therefore **includes the VAD `stop_secs` wait** before the commit is sent.

| service | pooled WER | TTFS p50 / p95 / p99 |
|---|---|---|
| scribe_v2_realtime | 3.13% | 281 / 348 / 407 ms |
| soniox stt-rt-v5 | 1.09% | 260 / 305 / 313 ms |
| deepgram nova-3-general | 1.37% | 247 / 298 / 326 ms |
| assemblyai universal-3-6-pro | 0.80% | 307 / 401 / 498 ms |
| speechmatics linden-1 | 0.96% | 369 / 438 / 690 ms |
| openai gpt-4o-transcribe | 2.95% | 637 / 965 / 1655 ms |
| voxtral-mini-transcribe-realtime-2602 | 5.11% | 525 / 973 / 1913 ms |

Scribe RT has the worst WER of the fast group here. AA ranks it best. The datasets differ, so weigh this against AA.

#### Per-vendor notes
- **Deepgram Nova-3** ([langs](https://developers.deepgram.com/docs/models-languages-overview), [code-switching](https://developers.deepgram.com/docs/multilingual-code-switching), [pricing](https://deepgram.com/pricing))
  - `language=multi&model=nova-3`: 55 languages, de included.
  - `language_hint` biases detection but does not restrict it.
  - Recommended `endpointing=100` for code-switching.
  - Pay-as-you-go streaming: mono $0.0077/min ($0.46/h); multi $0.0092/min ($0.55/h).
- **Deepgram Flux** ([quickstart](https://developers.deepgram.com/docs/flux/quickstart))
  - Endpoint `wss://api.deepgram.com/v2/listen` (v2 only).
  - `flux-general-multi` covers en, es, fr, **de**, hi, ru, pt, ja, it, nl; `flux-general-en` is English only.
  - Params:
    - `eot_threshold`: 0.5 to 1.0, default 0.7.
    - `eager_eot_threshold`: 0.3 to 0.9; enables `EagerEndOfTurn`.
    - `eot_timeout_ms`: default 5000.
  - Send 80 ms chunks (2560 B at 16 kHz).
  - `TurnInfo` events: `EagerEndOfTurn`, `TurnResumed`, `EndOfTurn`.
  - About 260 ms end-of-turn detection (vendor). EagerEOT adds 50 to 70% more LLM calls.
  - Price: $0.0078/min multi ($0.47/h).
  - Accuracy is the weakest of this set (AA 7.4%; Famulor de 6.21%).
- **Soniox** ([RT guide](https://docs.soniox.com/stt/rt/real-time-transcription), [WS API](https://docs.soniox.com/api-reference/stt/websocket-api))
  - Endpoint `wss://stt-rt.soniox.com/transcribe-websocket`.
  - The first frame is a JSON config, for example `{"model":"stt-rt-v5","audio_format":"pcm_s16le","sample_rate":16000,"num_channels":1,"language_hints":["de","en"],"enable_language_identification":true,"enable_endpoint_detection":true,"max_endpoint_delay_ms":2000,"context":{...}}`.
  - Binary audio follows. Control messages are `{"type":"finalize"}` and `{"type":"keepalive"}` (at least every 40 s). Send an empty frame to end.
  - Tokens arrive as `{text,start_ms,end_ms,confidence,is_final,speaker,language}`.
  - Code-switching (vendor): "auto-detects and supports mid-conversation language shifts".
  - Price: about $0.12/h streaming (vendor; AA $2/1k min).
  - Vendor German WER: 1.25% vs OpenAI 3.24%, on a "real-world YouTube" set ([compare page](https://soniox.com/compare/soniox-vs-openai/german)).
- **OpenAI** ([realtime transcription](https://developers.openai.com/api/docs/guides/realtime-transcription))
  - Endpoint `wss://api.openai.com/v1/realtime?intent=transcription`.
  - Models: `gpt-live-transcribe` (recommended) and `gpt-transcribe`. The gpt-4o-transcribe names are no longer on this page.
  - `server_vad` and `semantic_vad` are **not supported** for these models; commit with `input_audio_buffer.commit`.
  - Session fields: `languages` (plural), `delay` (`minimal` to `xhigh`).
  - Too slow for this budget: AA TTF 0.69 to 1.16 s, $1.02/h.
- **AssemblyAI** ([language FAQ](https://assemblyai.com/docs/faq/language-support-for-real-time-transcription))
  - `speech_model=universal-3-6-pro` is the default.
  - Native mid-sentence code-switching including de (32 languages on 3.6 per its model page; other doc pages say 18 or 19).
  - The legacy `universal-streaming-multilingual` switches per turn only.
  - AA TTF about 0.19 s, WER 3.6%, $0.45/h. A strong alternative.
- **Speechmatics:** no de_en bilingual pack found (bilingual packs exist for e.g. `cmn_en`). Soniox's comparison says Speechmatics needs one language per session. Linden-1: AA 4.4%, 0.15 s, $0.30/h.
- **Voxtral Mini 4B Realtime 2602** ([HF](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602))
  - Open weights, Apache-2.0, 13 languages including de.
  - Configurable delay from 80 ms to 2.4 s; recommended 480 ms.
  - FLEURS de WER: 6.19% at 480 ms, 4.87% at 960 ms, 9.50% at 160 ms.
  - 4B in BF16 is about 8 GB, which is too heavy next to an LLM on a 16 GB M3.
- **Kyutai STT** ([repo](https://github.com/kyutai-labs/delayed-streams-modeling)): `stt-1b-en_fr` (en/fr, 0.5 s delay, semantic VAD) and `stt-2.6b-en`. **No German.**

---

### 3. Local STT: parakeet-mlx vs Whisper

#### parakeet-tdt-0.6b-v3 ([model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3), [tech report arXiv 2509.14128](https://arxiv.org/abs/2509.14128))
- 600M parameters, FastConformer-TDT, 25 EU languages incl. de and en.
- "automatically detects the language … without requiring additional prompting". There is no language-forcing or prompt input.
- Automatic punctuation and capitalization; word timestamps.
- License: **CC-BY-4.0**, "ready for commercial/non-commercial use".
- Model card German WER (greedy, punctuation and case stripped): **FLEURS de 5.04%, CoVoST de 4.84%**. English: FLEURS 4.85%, CoVoST 6.80%.
- Same paper per-language FLEURS de: whisper-large-v3 ~4.30%, canary-1b-v2 ~4.40%, parakeet v3 5.04%. These are as reported in search snippets of the PDF table; not re-verified line by line.
- Open ASR multilingual track, de average over FLEURS + CoVoST-2 ([arXiv 2510.06961 Table 4](https://arxiv.org/html/2510.06961v3)):

| model | de avg WER |
|---|---|
| Phi-4-MM | 4.50 |
| **parakeet-tdt-0.6b-v3** | **4.90** |
| canary-1b-v2 | 4.96 |
| whisper-large-v3 | 4.97 |
| Voxtral Mini 3B | 5.36 |
| Scribe v1 | 10.8 |

- English Open ASR RTFx (A100): parakeet v3 3332.74 vs whisper-large-v3 145.51.
- AA (non-streaming, English): Parakeet TDT 0.6B v3 4.5% vs Whisper Large v3 4.1 to 4.5% ([AA STT](https://artificialanalysis.ai/speech-to-text)).

#### whisper-large-v3-turbo, German
- Common Voice 19 de: turbo 3.849% vs large-v3 3.484%. Tuda-De: 8.300 vs 7.884. MLS de: 3.203 vs 2.832. Source: [primeline turbo-german card](https://huggingface.co/primeline/whisper-large-v3-turbo-german), the fine-tuner's own evaluation.
- Turbo is therefore about 0.4 points worse than large-v3 on German, and parakeet v3 is about on par with large-v3 on FLEURS + CoVoST.

#### parakeet-mlx ([repo](https://github.com/senstella/parakeet-mlx))
- Code: Apache-2.0. `uv add parakeet-mlx`. Depends on mlx≥0.22.1, librosa, numpy, dacite, typer, huggingface-hub. The CLI needs ffmpeg.
- Default model `mlx-community/parakeet-tdt-0.6b-v3`: `model.safetensors` is 2.51 GB (fp32), license tag cc-by-4.0.
- Streaming API ([README](https://github.com/senstella/parakeet-mlx/blob/a47079fb1bdc324d1228af6455f1eef8e97e6fae/README.md), [parakeet.py L927+](https://github.com/senstella/parakeet-mlx/blob/a47079fb1bdc324d1228af6455f1eef8e97e6fae/parakeet_mlx/parakeet.py#L927)):
  ```py
  with model.transcribe_stream(context_size=(256, 256), depth=1) as t:
      t.add_audio(chunk_1d_mx_array)   # any length
      t.result.text; t.finalized_tokens; t.draft_tokens
  ```
  - It switches the encoder to `rel_pos_local_attn` and uses a rotating KV cache.
  - `drop_size = right_context * depth` frames stay "draft". One encoder frame is 80 ms (10 ms hop × 8× subsampling), so (256, 256) means about 20 s of right context. **For short voice-assistant turns almost everything stays draft.**
  - Practical choice: run a one-shot transcribe on the buffered utterance at end of turn.
- Apple-silicon speed (third-party, not same-clip comparisons):
  - M3 Max: parakeet v3 about 73× RT at fp32, about 95× int8, about 98× int4; "int8 no WER loss" ([sonic-speech](https://huggingface.co/spaces/sonic-speech/README/blob/main/README.md)).
  - M1 Max: parakeet v3 about 52.7× vs whisper-large-v3-turbo about 14.3× ([vllm-mlx](https://vllm-mlx.is-a.dev/zh/benchmarks/audio/)).
  - At about 50× RT, a 5 s utterance takes about 100 ms on a plain M3. That is an extrapolation; measure it.

---

### 4. Streaming TTS alternatives (brief)

| engine | German | streaming / continuity | TTFA / latency (source) | license / price |
|---|---|---|---|---|
| ElevenLabs Flash v2.5 / v4 Turbo | yes | WS `stream-input` / `multi-stream-input` with `context_id` | ~100 ms **server-side** median, excluding network ([methodology](https://elevenlabs.io/docs/eleven-api/concepts/latency-methodology.md)); v3 Conversational ~165 ms | – |
| Cartesia Sonic 3.6 | yes (44 langs, `de`) ([models](https://docs.cartesia.ai/build-with-cartesia/tts-models)) | WS continuations: same `context_id` + `"continue": true`; `max_buffer_delay_ms` default 3000 (0 to 5000); end with `continue:false` and terminal punctuation ([continuations](https://docs.cartesia.ai/build-with-cartesia/capability-guides/stream-inputs-using-continuations)) | not stated on the models page | AA price $49/1M chars |
| Deepgram Aura-2 | yes: `aura-2-{elara,aurelia,lara,julius,fabian,kara,viktoria}-de` ([tts-models](https://developers.deepgram.com/docs/tts-models)) | WS available (not documented on that page) | – | $0.030/1k chars |
| OpenAI gpt-4o-mini-tts | yes ("Voices are currently optimized for English") | chunked HTTP only; PCM 24 kHz | – | **deprecated, shutdown 2027-01-06**; successor is the Realtime API ([TTS guide](https://developers.openai.com/api/docs/guides/text-to-speech)) |
| Kyutai TTS 1.6B | **no** (en, fr) | delayed-streams text-in streaming | – | CC-BY-4.0 weights ([card](https://huggingface.co/kyutai/tts-1.6b-en_fr)) |
| Kokoro 82M (local) | **no** lang code for German (a, b, e, f, h, i, j, p, z) ([README](https://github.com/hexgrad/kokoro)) | sentence-level | – | Apache-2.0 |

AA's TTS page shows no latency data, only quality ELO: Eleven v4 Turbo 1336, Sonic 3.6 1296, v3 Conversational 1215, Kokoro 1062 ([AA TTS](https://artificialanalysis.ai/text-to-speech)).

---

### 5. Pipecat: pipeline structure (exact defaults)

#### LLM tokens to TTS
- `TextAggregationMode.SENTENCE` (default) vs `TOKEN` ([tts_service.py L85-96](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/services/tts_service.py#L85)). Docstring: SENTENCE "adds latency (~200-300ms per sentence)".
- The sentence aggregator works character by character. It waits for one non-whitespace lookahead character after `.?!`, then confirms the boundary with `sentencex` ([simple_text_aggregator.py](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/utils/text/simple_text_aggregator.py)).
- `reuse_context_id_within_turn=True` (default): one TTS context for the whole LLM turn, so sentences go into the same ElevenLabs context. **This is what keeps prosody continuous across sentences.**

#### ElevenLabsTTSService ([tts.py](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/services/elevenlabs/tts.py), [tts_base.py](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/services/elevenlabs/tts_base.py))
- URL ([L524](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/services/elevenlabs/tts.py#L524)):
  `{url}/v1/text-to-speech/{voice_id}/multi-stream-input?model_id={model}&output_format={fmt}&auto_mode={true|false}`
  - Optional additions: `&enable_ssml_parsing=`, `&enable_logging=`, `&apply_text_normalization=`, `&language_code=`.
  - `url` default `wss://api.elevenlabs.io`. Default model `eleven_flash_v2_5`. The output format is derived from the sample rate (`pcm_*`).
- **auto_mode:** if unset, `auto_mode = (text_aggregation_mode != TOKEN)`. So it is on with sentence aggregation and off with token streaming (L450-455). Reason given: "token streaming relies on the server-side chunk scheduler to accumulate enough text".
- **chunk_length_schedule:** Pipecat never sets it (no occurrence in the repo).
- **Context open** ([L673](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/services/elevenlabs/tts.py#L673)): `{"text":" ","context_id":id,"voice_settings":{...},"pronunciation_dictionary_locators":[...]}`. Then each aggregated sentence is sent as `{"text":..., "context_id":id}`.
- **End of LLM turn:**
  - `LLMFullResponseEndFrame` → flush the aggregator → `on_turn_context_completed()`.
  - That sends `{"context_id":id,"flush":true}` ([tts_service.py L902-923](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/services/tts_service.py#L902)).
  - Then `{"context_id":id,"close_context":true}`. Comment: "so isFinal arrives immediately after the last audio byte" ([tts.py L570-577](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/services/elevenlabs/tts.py#L570)).
- **Interruption:** `on_audio_context_interrupted` → `close_context` for that id, reset the word clock, drop local audio for that context ([tts_base.py L782](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/services/elevenlabs/tts_base.py#L782)). No reconnect; the socket stays open. The next turn gets a new uuid4 context.
- **Receive side:**
  - `isFinal: true` ends the context and pushes `TTSStoppedFrame`.
  - `audio` (b64) becomes a `TTSAudioRawFrame` routed by `contextId`.
  - Alignment uses `alignment` (or `normalizedAlignment` when pronunciation dictionaries are used), with `chars`, `charStartTimesMs`, `charDurationsMs`.
  - Word times = per-message offsets plus a cumulative clock: "Alignment times restart at zero in every message", so it adds each chunk's `last start + last duration`. Pipecat uses these timings to emit spoken-text frames in sync with playout; only actually spoken words enter the LLM context on interrupt.
- **Keepalive:** every **10 s** (`_create_keepalive_task(interval=10)`, [tts_base.py L699](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/services/elevenlabs/tts_base.py#L699)).
  - Message: `{"text":"","context_id":id}` if that context's init was already sent, otherwise `{"text":""}`.
  - Gotcha (L649-671): a keepalive sent *before* the context-init would become the context's first message without `voice_settings`, and "ElevenLabs would reject the later context-init with a 1008 policy violation".
- **Disconnect:** send `{"close_socket": true}`, wait up to 2.0 s for the server close, then close locally. This avoids 1006 closes (L746).
- Websocket `max_size=16 MiB`. Header `xi-api-key`.

#### LiveKit Agents ElevenLabs plugin ([tts.py](https://github.com/livekit/agents/blob/11c8ad8d74c272cf046e65d83cfe7be46abaec64/livekit-plugins/livekit-plugins-elevenlabs/livekit/plugins/elevenlabs/tts.py)), for contrast
- Also uses `multi-stream-input`. Its URL adds `inactivity_timeout=180` (constant `WS_INACTIVITY_TIMEOUT = 180`; the docstring says 300, which is inconsistent), plus `sync_alignment=true` and `apply_text_normalization`.
- `auto_mode` defaults to True unless `chunk_length_schedule` is given.
  - With auto_mode: blingfire `SentenceTokenizer`, and **`flush: true` on every sentence**.
  - Without: basic `WordTokenizer`, plus `generation_config.chunk_length_schedule` in the context-init packet. Documented server defaults are `[120, 160, 250, 290]`, range 50 to 500.
- Every text chunk is sent as `f"{text} "`, with the comment "must always end with a space".
- End of input: `{"text":"","context_id":id,"flush":true}`, then `{"context_id":id,"close_context":true}`.
- `{"context_id":..,"keep_alive":true}` every 10 s is used only for the text-to-dialogue endpoint, which "finalizes a context idle for 20s".

#### Turn detection
- **Silero VAD in Pipecat** ([vad_analyzer.py L25-28](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/audio/vad/vad_analyzer.py#L25)):
  - `confidence=0.7, start_secs=0.2, stop_secs=0.2, min_volume=0.6`.
  - ONNX, CPU-forced; 512-sample windows at 16 kHz (32 ms); bundled `silero_vad.onnx`.
- **Default user-turn strategies** ([user_turn_strategies.py L403-427](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/turns/user_turn_strategies.py#L403)):
  - Start: `[VADUserTurnStartStrategy, TranscriptionUserTurnStartStrategy]`.
  - Stop: `[TurnAnalyzerUserTurnStopStrategy(LocalSmartTurnAnalyzerV3)]`.
  - Alternative: `SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.6)`.
  - `MinWordsUserTurnStartStrategy(min_words=N, use_interim=True)` exists for barge-in gating.
- **Smart Turn v3** ([repo](https://github.com/pipecat-ai/smart-turn), [HF](https://huggingface.co/pipecat-ai/smart-turn-v3), [blog](https://www.daily.co/blog/announcing-smart-turn-v3-with-cpu-inference-in-just-12ms/)):
  - Code and weights: **BSD-2-Clause**.
  - Whisper-Tiny encoder plus a linear head, about 8M params. CPU int8 ONNX is 8 MB; the GPU fp32 version is 32 MB.
  - Pipecat bundles `smart-turn-v3.2-cpu.onnx` (8.7 MB) and runs it with onnxruntime at `cpu_count=1`. It decides `probability > 0.5`.
  - SmartTurnParams: `stop_secs=3` (fallback max silence), `pre_speech_ms=500`, `max_duration_secs=8` ([base_smart_turn.py L27-29](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/audio/turn/smart_turn/base_smart_turn.py#L27)).
  - 23 languages incl. **German: 96.14% accuracy (FP 2.50%, FN 1.36%, n=1322)**; English 94.31% (n=2846) (blog, v3.0).
  - CPU latency: 12.6 ms (c7a.2xlarge) to 94.8 ms (t3.medium); about 65 ms on a Pipecat Cloud 1x instance. No Apple numbers published, but an M3 should be at the low end.
  - Input: 16 kHz mono, up to 8 s, left-padded with zeros. Run it on the whole current turn when VAD goes silent; re-run if speech resumes.
  - A CoreML variant exists (`LocalCoreMLSmartTurnAnalyzer`, needs a `.mlpackage` path).
- **LiveKit endpointing defaults** ([turn.py L135-147](https://github.com/livekit/agents/blob/11c8ad8d74c272cf046e65d83cfe7be46abaec64/livekit-agents/livekit/agents/voice/turn.py#L135)):
  - `min_delay=0.5, max_delay=3.0`; with streaming STT, `0.3 / 2.5`.
  - Interruption: `min_duration=0.5, min_words=0, resume_false_interruption=True, false_interruption_timeout=2.0`.
  - Silero plugin: `min_speech_duration=0.05, min_silence_duration=0.55, prefix_padding_duration=0.5, activation_threshold=0.5`.
  - LiveKit's own turn-detector model is under the **"LiveKit Model License"**, not OSI. Avoid it.

#### Jitter and playout
- Pipecat output transport `audio_out_10ms_chunks=4`, i.e. writes 40 ms frames ([base_transport.py L117](https://github.com/pipecat-ai/pipecat/blob/6f777a0ef3bb98163d10d708525a0db21cda5fbf/src/pipecat/transports/base_transport.py#L117)). No explicit jitter buffer for local playout; audio contexts are queued per context id and played in order.

---

### 6. Licenses (commercial compatibility)

| component | license | OK commercially? |
|---|---|---|
| parakeet-tdt-0.6b-v3 weights (NVIDIA, and the mlx-community copy) | CC-BY-4.0 | yes, **attribution required** (credit NVIDIA, link the license, note changes) |
| parakeet-mlx code | Apache-2.0 | yes |
| smart-turn v3 code + weights | BSD-2-Clause | yes |
| silero-vad | MIT ([LICENSE](https://github.com/snakers4/silero-vad/blob/master/LICENSE)) | yes |
| websockets (python) | BSD-3-Clause ([LICENSE](https://github.com/python-websockets/websockets/blob/main/LICENSE)) | yes |
| pipecat | BSD-2-Clause | yes |
| livekit/agents code | Apache-2.0 | yes; the turn-detector **model** is the LiveKit Model License, so avoid it |
| Voxtral Mini 4B Realtime | Apache-2.0 | yes |
| Kyutai STT/TTS weights | CC-BY-4.0; code MIT/Apache | yes, with attribution (but no German) |
| Kokoro | Apache-2.0 | yes (no German) |

---

### 7. ElevenLabs TTS WS tips found incidentally (Pipecat and LiveKit source)
1. Use `multi-stream-input` with one `context_id` per assistant turn. Send each sentence into the same context for continuous prosody.
2. Open the context with `{"text":" ","context_id",..,"voice_settings":..}` first. Never let a keepalive be the first message for a context (1008).
3. Keepalive on multi-stream: `{"text":""}` or `{"text":"","context_id":id}` every 10 s (Pipecat). Alternatively, raise `inactivity_timeout` (LiveKit uses 180).
4. End of LLM turn: `{"context_id":id,"flush":true}` then `{"context_id":id,"close_context":true}`, then wait for `isFinal`.
5. Barge-in: `{"context_id":id,"close_context":true}`, discard any audio still arriving for that id, and keep the socket open.
6. Sentence chunks with `auto_mode=true` (and LiveKit adds `flush:true` per sentence). Token streaming needs `auto_mode=false` plus the server chunk schedule (default `[120,160,250,290]`).
7. Text chunks should end with a space (LiveKit).
8. Shutdown: `{"close_socket":true}`, wait up to 2 s for the server close.

---

### 8. Recommendation

#### Best streaming STT for de+en with ≤300 ms finalization
1. **ElevenLabs Scribe v2 Realtime, manual commit.** Implement this first. It fits the budget:
   - AA TTF is about 0.14 to 0.16 s after the commit.
   - Pipecat's p50 TTFS of 281 ms *includes* the 200 ms VAD wait.
   - Its streaming WER is at the top for fast services, and German is in ElevenLabs' best accuracy bucket.
   - Same vendor and key as the TTS; there is an EU host.

   Suggested setup:
   - Open the WS when local Silero starts speech (or on talk-key press) and send a ~300 to 500 ms pre-roll. Connecting while the user talks hides the handshake. This avoids paying for idle silence and the 15 s idle close.
   - Use `audio_format=pcm_16000`, 100 to 250 ms chunks, `secondary_languages=de&secondary_languages=en`, and optionally `include_language_detection=true`.
   - Send the commit on local end of turn, i.e. Silero `stop_secs≈0.2` confirmed by Smart Turn. Do not commit on every short pause, given the throttling warning.
   - Seed `previous_text` (<50 chars) with Milo's last line on the first chunk.

   Must test: intra-sentence de/en switching (undocumented) and commit latency for utterances shorter than 2 s ("processing starts after the first 2 seconds").
2. **Fallback / A-B: Soniox stt-rt-v5.** About 55 ms TTF on AA, $0.12/h, explicit `language_hints` plus claimed mid-utterance switching, and `{"type":"finalize"}` for manual endpointing. Use it if Scribe mangles mixed sentences. AssemblyAI U3.6 Pro (about 0.19 s, native de code-switching) is the third option.
3. Skip for this target:
   - OpenAI realtime transcription: 0.7 to 1.2 s TTF.
   - Deepgram Flux / Nova-3 multi: fast but the weakest WER here.
   - Voxtral RT: slower to finalize, and 8 GB locally.

#### Is parakeet-mlx a credible local upgrade over Whisper for German?
**Yes, for speed at equal accuracy. It is not a clear accuracy win.**
- German WER is about the same as whisper-large-v3: 4.90 vs 4.97 on the Open ASR multilingual de average. FLEURS-only shows Whisper slightly ahead (about 4.3 vs 5.04).
- It is better than whisper-large-v3-turbo on German by the same rough margin turbo loses to large-v3 (about 0.4 points).
- It is roughly 4 to 7× faster on Apple silicon (about 50 to 100× RT vs about 14 to 55× for turbo), with built-in punctuation and timestamps. CC-BY-4.0 needs an attribution line.
- Caveats:
  - No language or prompt conditioning, so Whisper's `initial_prompt` vocabulary trick is lost.
  - Mixed de/en inside one utterance is unverified.
  - fp32 weights are 2.5 GB.
  - Its streaming mode is not useful for short turns; transcribe the buffered utterance once at end of turn.
- Before switching the fallback, A/B it against the current Whisper on 30 to 50 of the user's own mixed de/en clips.
