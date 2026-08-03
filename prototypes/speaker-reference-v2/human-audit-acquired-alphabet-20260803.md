# Acquired Alphabet speaker-reference v2 human audit

Status: **ACCEPTED 2026-08-03**. Machine-readable frozen record:
`tests/fixtures/live_identity_real_corpus/speaker-reference-v2-human-audit-20260803.json`.

Corpus audio: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/audio.wav`

- audio SHA256: `333b1e50b05d5dc888a6bdb4dc82f1c429e0e9c5a0b1df0cf115c2215eb394fb`
- v1 SHA256: `27c9b96e86cce3be86a3ce06dd64c1710e2c94e72a01c30339e953db94b8ebbe`
- rejected candidate v2 SHA256: `7c3020b89326a933dd011cbbd8c8b398b6a5e0aea51a42458d716cd2867565f8`
- transcript-independent ASR evidence SHA256: `367b474cf8c6f9da3f8dd28dbd47961f9c34f2d9060497e9cdd7051205531896`
- existence rule: local token F1 `>=0.65`, `+/-1.5s`; up to four reference-token deletions allowed

## R1 — 11.565–14.587

- candidate v2 row 4, David, 11.565–14.587: “Well, I thought because of the war between Android and…”
- v1 row 4, David, 13.040–15.135: same text
- independent ASR: **ACCEPT**, score 0.909; “well i thought because of the you know war between android and”
- listen: `/opt/homebrew/bin/ffplay -nodisp -autoexit -ss 11.565 -t 3.022 '/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/audio.wav'`

## R2 — 101.404–104.484

- candidate v2 row 12, Ben, 101.404–104.484: “Just unreal. Can't wait to tell all of these stories today.”
- v1 row 12, Ben, 103.759–104.950: same text
- independent ASR: **ACCEPT**, score 1.000; exact normalized text
- listen: `/opt/homebrew/bin/ffplay -nodisp -autoexit -ss 101.404 -t 3.080 '/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/audio.wav'`

## R3 — 121.546–124.326

- candidate v2 row 15, David, 121.546–123.046: “Oh man, I forgot about the hot air balloons.”
- candidate v2 row 16, Ben, 123.286–124.326: “Google Glass.”
- v1 row 15, David, 122.719–123.429: first text
- v1 row 16, Ben, 124.914–126.389: “Google Glass.” (starts 0.588 s after this requested range)
- independent ASR: **ACCEPT**, scores 1.000/1.000; exact normalized texts
- listen: `/opt/homebrew/bin/ffplay -nodisp -autoexit -ss 121.546 -t 2.780 '/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/audio.wav'`

## R4 — 161.971–163.411

- candidate v2 row 23, David, 161.971–163.411: “Woo hoo hoo. Oh, you're giving away the end.”
- v1 row 22, David, 159.449–162.390: “We'll end this episode story right at the dawn of the AI era.”
- v1 row 23, David, 163.419–163.689: the candidate text (starts 0.008 s after this requested range)
- independent ASR: score 0.714; ASR only says “you're giving away the end” and omits “Woo hoo hoo. Oh”
- operator disposition: **EDIT**. A direct human listen at 162.0–163.4 confirms the audible lexical text is exactly “Oh, you're giving away the end.” and that there is no “Woo hoo hoo.” This direct confirmation is primary; captions, independent MOSS ASR, Whisper base/small, and waveform evidence are corroborating only. Preserve David speaker activity at 161.8–163.411; represent 161.8–162.4 as an uncertain nonlexical vocalization, not confirmed words.
- listen: `/opt/homebrew/bin/ffplay -nodisp -autoexit -ss 161.971 -t 1.440 '/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/audio.wav'`

## R5 — 237.637–248.877

- candidate v2 row 33, David, 237.637–242.157: “I want to start with a quote from Russ Hanneman.”
- candidate v2 row 34, Ben, 242.737–243.557: “The fictional character?”
- candidate v2 row 35, David, 243.577–248.877: “From Silicon Valley, HBO show. Oh yeah, from the TV show.”
- v1 row 32, David, 236.388–238.453: “I have a very, very fun beginning for you, Ben.”
- v1 rows 33–35, 240.558–249.110: the same three candidate texts
- independent ASR: **ACCEPT**, scores 0.947/1.000/0.960; “Russ Hanneman” is decoded only as “Russ”
- listen: `/opt/homebrew/bin/ffplay -nodisp -autoexit -ss 237.637 -t 11.240 '/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/audio.wav'`

## R6 — 287.279–296.480

- candidate v2 row 45, David, 287.279–296.480: “But what was the problem in 2004, 2005, 2006 was being viewed as, in Russ's terms, pure play.”
- v1 row 45, David, 291.280–295.063: same text
- independent ASR: **ACCEPT**, score 1.000; exact normalized text
- listen: `/opt/homebrew/bin/ffplay -nodisp -autoexit -ss 287.279 -t 9.201 '/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/audio.wav'`

## Frozen disposition

R1, R2, R3, R5, and R6 are `PRESENT`. R4 is the `EDIT` above. No candidate row is removed; one lexical claim is removed while its speaker-activity interval remains.
