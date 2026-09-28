# D3 real cross-meeting voiceprint receipt

**Verdict: pass for this three-clip public-audio probe.** One Account owner and the real Gemini engine processed three meetings through the HTTPS API at 1.0× pace. The first meeting's Lex speaker was named through `PUT /api/meetings/{id}/speakers/{id}/name` while active and enrolled one voiceprint. The second meeting auto named the Lex speaker; Keyu remained unnamed. The 180 s Jamie negative control had three visible speaker IDs and no Lex name.

| Public clip | Frames | Max pacing lag | Settled coverage | Visible IDs | Lex reference overlap | Lex named | Other voice named Lex | Calls preview/rolling/terminal | Clamped/dropped words per call | Audio sent | Cost |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: |
| interview_bill_ackman_60s | 120 | 0.010 s | 60/60 s | 2 | 4.0 s | yes, manual | no | 1/6/1 | 0/8, 0/8 | 272 s | $0.015681 |
| interview_keyu_jin_60s | 120 | 0.010 s | 60/60 s | 2 | 14.6 s | yes, automatic | no | 1/6/1 | 0/8, 0/8 | 272 s | $0.015681 |
| discussion_jamie_dimon_180s | 360 | 0.010 s | 180/180 s | 3 | 0 s | no | no | 1/18/1 | 0/20, 0/20 | 872 s | $0.049705 |

No provider error or retry, no skipped window tick, and no voiceprint encoder error appeared in these final per-session counters. Total reported cost was $0.081066, including Gemini Live list-price estimates. The negative control's 180 s reference has about 179 s timed coverage; its no-Lex label result comes from the public speaker-label map, not a diarization score.

The first probe read `speaker_labels` inside `snapshot` and falsely reported unnamed speakers. The public HTTP response places it in the **outer envelope**. A read-only audit of the same three completed meeting responses corrected the receipt; it did not resend audio or change the voiceprint bank. The [JSON receipt](d3-voiceprint-http-trio.json) records that correction and the content-free per-session counters.

Reproduce with `prototypes/gemini-runtime/voiceprint_http_trio.py` against the local Gemini HTTPS stack. The script maps speaker IDs to timed public references by overlap only in the measurement client; it sends no reference speaker labels to the engine. This three-clip result shows the end-to-end D3 path works for these voices. Population false-match and miss rates remain unmeasured.
