# Live transcription + speaker labels: market check (researched 2026-09-28)

Web research (two parallel research agents; vendor docs, pricing pages, independent benchmarks, Hacker News,
Google/OpenAI developer forums, GitHub issues). Reddit was not readable by the tools; Quora had nothing relevant.
Every claim below carries its source. "Not found" is stated where applicable.

## Bottom line

- Neither Google's nor OpenAI's live transcription model returns speaker labels while streaming. Both keep speaker
  labels in file/batch mode only.
- OpenAI's live transcriber (`gpt-live-transcribe`, 2026-07-28, $0.017/min) has no speaker labels, no word
  timestamps and no automatic turn detection. Its only speaker-labelling model (`gpt-4o-transcribe-diarize`, batch,
  $0.006/min) is deprecated and shuts down 2027-02-26, with no named speaker-labelling successor.
- Services with live speaker labels: Soniox stt-rt-v5 ($0.002/min incl. labels), AssemblyAI Universal-Streaming
  ($0.0045–0.0095/min, 1–10 speakers), Deepgram Nova-3 ($0.0068/min), Speechmatics real-time (price not verified).
  None is regarded as having solved live speaker labelling.
- Practitioner consensus: one channel per participant (mic = you, system audio = others) plus echo removal — what
  this design does.

## OpenAI models (as of 2026-09-28)

| Model | Live | Speaker labels | Word timestamps | Price |
|---|---|---|---|---|
| gpt-live-transcribe | Yes (realtime transcription sessions) | No | No | $0.017/min |
| gpt-realtime-whisper | Yes | Not documented | Not documented | $0.017/min |
| gpt-transcribe | Files (+ finished turns in live) | Not documented | Not documented | $0.0045/min |
| gpt-4o-transcribe / -mini | Files + live | No | No | $0.006 / $0.003 per min — deprecated |
| gpt-4o-transcribe-diarize | Files only | Yes (labels A/B/…; up to 4 known-speaker clips) | Segment only | $0.006/min — shuts down 2027-02-26 |

Sources: https://developers.openai.com/api/docs/guides/realtime-transcription ·
https://developers.openai.com/api/docs/guides/speech-to-text · https://developers.openai.com/api/docs/deprecations ·
https://developers.openai.com/api/docs/pricing ·
https://community.openai.com/t/gpt-live-transcribe-and-gpt-transcribe-two-new-transcription-models-in-the-api/1388318 ·
https://community.openai.com/t/realtime-transcription-problem-gpt-live-transcribe-no-final-events-received/1397959 ·
https://www.datacamp.com/tutorial/gpt-live-transcribe-api (first partial 0.70–2.91 s by delay setting; 60-min sessions)

Community on OpenAI diarize: dropped words, invented speakers, language mixing, no min/max speaker setting
(https://community.openai.com/t/introducing-gpt-4o-transcribe-diarize-now-available-in-the-audio-api/1362933);
labels reset per chunk (https://community.openai.com/t/best-practices-for-maintaining-speaker-identity-across-chunks-with-gpt-4o-transcribe-diarize/1364126);
not available in realtime sessions (https://community.openai.com/t/how-to-enable-gpt-4o-transcribe-diarize-for-realtime-transcription/1373561).

## Gemini (what we use) — community reports

- Live model: no diarization, no word timestamps, 10-minute sessions
  (https://ai.google.dev/gemini-api/docs/models/gemini-3.5-transcribe;
  https://dev.to/gde/ai-in-practice-gemini-35-transcribe-real-time-transcription-and-speaker-diarization-in-a-macos-152h).
- Latency: first partial 151–162 ms while speaking; final 410–484 ms after speech ends (one 5 s clip)
  (https://github.com/google-gemini/jot-gemini-transcribe-macOS/issues/11). Ours: ~0.5–0.8 s per word via interims.
- **Two simultaneous live sessions silently stop returning transcripts** (connection open, no GoAway/error; staff
  acknowledged 09-02) — https://discuss.ai.google.dev/t/gemini-3-5-transcribe-live-sessions-stay-connected-but-silently-stop-returning-transcripts/180230 → guard G1.
- **Batch model silently drops content** (>7 min missing from a 17-min file, status completed; HTTP 200 empty
  transcript) — https://github.com/machinewrapped/llm-subtrans/issues/458 ·
  https://discuss.ai.google.dev/t/gemini-3-5-transcribe-returns-empty-transcription-http-200-zero-output-tokens-on-all-documented-rest-paths/179937 → guard G2.
- One field test of batch diarization failed (67–75% vs 89% incumbent; up to 9 IDs per window; duplicated words)
  — https://github.com/srsaito/jp-lesson-distill/pull/8.
- Lost final words at Stop (live) — https://github.com/DevEmperor/DictateKeyboard/issues/372 (our saved transcript is
  owned by the batch passes + Stop drain, so this affects only the preview).
- Gemini Live API (3.x Live models) built-in input transcription unreliable: mishears, invents text on silence, not
  incremental — https://discuss.ai.google.dev/t/gemini-live-api-input-audio-transcription-returns-incorrect-text-while-model-correctly-processes-audio/128300 ·
  https://discuss.ai.google.dev/t/gemini-live-api-models-inputtranscription-hallucinations/107899 ·
  https://discuss.ai.google.dev/t/gemini-live-flash-3-1-api-inputtranscription-no-longer-streams-incrementally/136977
- HN (~2026-08-28): mixed; "beats every other model on accuracy … needs more work on latency"; "still no real time
  diarization beyond 3 people … when others do it very well, like Soniox and Deepgram" — https://news.ycombinator.com/item?id=49468818

## Benchmarks (independent where available)

- Batch WER (Artificial Analysis): Gemini 3.5 Transcribe 2.6%, ElevenLabs Scribe v2 2.2%, AssemblyAI U3 Pro 3.1%,
  GPT Transcribe 3.3%, Deepgram Nova-3 5.2% — https://artificialanalysis.ai/speech-to-text/models/openai-gpt-live-transcribe
- Streaming (Artificial Analysis 2026-06-01): Scribe v2 RT 3.64% / 0.14 s; AssemblyAI U3 RT Pro 4.46% / 0.47 s;
  Deepgram Nova-3 RT 6.69% / 0.06 s — https://artificialanalysis.ai/articles/new-streaming-speech-to-text-benchmark-aa-wer-streaming
- Coval (gpt-realtime-whisper): WER 4.5%, time to final segment 588 ms, first token 1,818 ms —
  https://benchmarks.coval.ai/models/gpt-realtime-whisper
- No independent head-to-head benchmark of LIVE speaker labelling exists (vendor claims only, e.g.
  https://www.assemblyai.com/blog/streaming-diarization-major-upgrade).

## Live speaker-label services

- Soniox $0.12/h live incl. speaker labels — https://soniox.com/pricing
- AssemblyAI streaming labels (1–10 speakers, per word, "PENDING" for < 1 s turns, mid-session corrections) —
  https://www.assemblyai.com/docs/streaming/label-speakers-and-separate-channels · https://www.assemblyai.com/pricing
- Deepgram live labels only with the older model; +$0.002/min — https://developers.deepgram.com/docs/diarization ;
  complaints: label switching, "speaker 0" for the first 20–30 s — https://github.com/orgs/deepgram/discussions/1127 ·
  https://github.com/orgs/deepgram/discussions/1144
- Speechmatics real-time diarization — https://docs.speechmatics.com/speech-to-text/realtime/realtime-diarization
- ElevenLabs Scribe v2 Realtime: no live labels ("not a priority") — https://elevenlabs.io/realtime-speech-to-text
- Architecture advice: separate stream per participant (https://www.recall.ai/blog/speaker-diarization); echo is the
  dominant mic-lane failure (477/641 "me" rows were echo in a 42-min meeting; fixed by dropping mic text ≥ 70%
  contained in system text within ±400 ms — https://github.com/humanitas-labs/quill/issues/56).

## Not verified

Max speaker count for gpt-4o-transcribe-diarize; any OpenAI DER benchmark; gpt-live-transcribe latency per delay
level and language list; Speechmatics live price; Azure live price (third-party $1/h); Gemini's speaker cap
("up to 3 reliable" in launch material vs "up to 8" in docs); any Reddit consensus.
