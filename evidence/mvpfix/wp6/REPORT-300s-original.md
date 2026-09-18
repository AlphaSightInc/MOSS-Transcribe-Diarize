> Historical report at 57907d76. Speaker-count interpretation corrected in WP12.md;
> local/deployed scope clarified in MANIFEST.md. Original numerical records retained.

# WP6 — 600-second capacity baseline not accepted

**F1 — Four sessions completed capture and saved transcripts, but all four lost the second
300 seconds of downloadable audio and could not run terminal refinement.** The supplied
local provider manifest declares `max_tape_bytes=9,600,000`: exactly 300 seconds of
16 kHz mono PCM16. Both the in-memory terminal tape and durable audio stage use it.
600 seconds requires at least 19,200,000 bytes per complete PCM tape. The runtime
correctly reports partial audio / unavailable refinement; this configured stack
cannot pass the requested 600-second retention/finalization baseline. **Eight-session
safe-overload was not run**, because the required clean 4x600 result does not exist.

**F2 — Capture capacity measurements were healthy during the uncontaminated 4x600:**
9,600/9,600 lane frames acknowledged; 0/9,600 wrong-owner probe failures; four closed
session events and four durable completed meetings. Every final canonical commit
reached 9,600,000 samples. Exact accepted/accounted API counters were not retained
by the original collector; acknowledgement-derived sample totals are labeled as such.

**F3 — No production defect or repair established.** The retention refusal is the
explicit ADR-0003 D5/D8 contract. Changing that declared retention policy to obtain a
passing baseline would change the measured configuration. The two proven collector
defects were repaired: foreign-load resume detection and failure to recognize the
terminal `unavailable` outcome. Production, identity, quality, readiness, mixer and
decoder code/policies remain unchanged. Part 0 a20595a5 remains accepted.

## Four-session measurements

All are 600 seconds of audio, in four independent browser-private workspaces.
`age p95` is visible update age; `canonical p95` is a conservative upper bound from
a timestamp before bootstrap (exact replay-start anchor was omitted by the old collector).
First text is API polling, compared descriptively with 4 seconds; canonical lag is
compared with the existing 10-second gate. Words/minute uses audio duration.

| Session / public clip | First text s | Age p95 s | Canonical p95 s | Words / reference | Words/min | Vocabulary retention | Ordered WER | Speakers / reference |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 Bill Ackman | 3.048 | 3.136 | <=2.501 | 1,890 / 1,760 | 189.0 | 94.74% | 20.45% | 3 / 2 |
| 2 Keyu Jin | 3.548 | 3.312 | <=2.494 | 1,500 / 1,390 | 150.0 | 97.59% | 10.79% | 2 / 2 |
| 3 mono_javier_intro | 1.560 | 3.419 | <=2.890 | 1,306 / 1,356 | 130.6 | 95.12% | 11.14% | 2 / 1 |
| 4 Jamie Dimon discussion | 2.057 | 3.515 | <=3.020 | 1,977 / 1,884 complete-reference words | 197.7 | 97.30% | unknown: final reference sentence cut | 5 / 3 |

Stop-to-**final** is unavailable for all four; no final refinement occurred. Recorded
`tape_unavailable` outcomes arrived within conservative upper bounds of
3.115 / 2.697 / 3.323 / 3.732 seconds after Stop. The collector incorrectly waited
90 seconds, then attempted abort against already closed meetings. Its timeout and
abort HTTP errors are retained in result.json; they are **not stuck runtime sessions**.

The saved word counts equal each session's last API-visible count. WER is recovered
from the actual persisted transcript, not reconstructed from that count. Each MP3
was independently probed: 16 kHz mono, exactly 300.000 seconds, 1,800,837 bytes, partial.
This establishes 1,200 seconds archived of 2,400 seconds acknowledged across the four.
Vocabulary retention is not accuracy. Speaker counts show fragmentation but do not
measure attribution accuracy; identity-policy changes are outside WP6. The three
available WERs exceed the 9.5074% final-WER comparator, but these looped clips are not
the fixed six-case/two-pass quality population and received no terminal refinement.

- **M1:** 1,133 jointly-ready dispatch observations; maximum skew 1 (gate <=1).
- **M2:** pre-Stop inference real-time factor 0.089592 (gate <1); refinement queue peak 1.
- **M3:** 25 resource samples; app RSS 630.406 -> peak 1,017.266 MiB, growth 386.859 MiB.
  GPU memory 14,175/16,376 MiB; GPU cache peak 0.951814%; sampled vLLM waiting peak 0.
- **M4:** 0/25 foreign-load samples, zero pauses, 1,209 decoder calls, all completed;
  maximum own requests in flight 1. No 429/backpressure occurred at four sessions.

## Full ladder, including failed attempts

| Run directory | Outcome | Decoder calls | Frames acknowledged | Wrong-owner failures / probes |
|---|---|---:|---:|---:|
| 20260917-234705-1x120 | final 1/1; foreign load detected | 61 | 480 | 0 / 480 |
| 20260917-234938-2x300 | deliberately interrupted to correct collector resume logic; saved interrupted 2/2, 39 s partial audio each | 36 | 316 | 0 / 313 |
| 20260917-235110-2x300 | final 2/2; contaminated by foreign traffic | 306 | 2,400 | 0 / 2,400 |
| 20260918-000221-4x600 | completed 4/4; final refinement unavailable 4/4; partial audio 4/4 | 1,209 | 9,600 | 0 / 9,600 |

**Total: 1,612 decoder calls / 1,612 completed calls; maximum own concurrency 2.**
Nine sessions including the interrupted attempt: seven completed, two intentionally
interrupted. No capacity qualification or eight-session overload claimed.

Smoke: first text 4.032 s, canonical p95 0.754 s, Stop->final 6.159 s, 369/352 words,
184.5 words/min, retention 95.79%, WER 15.06%, two speakers.
Completed two-session step: first text 4.040/3.542 s; Stop->final 18.964/14.135 s;
919/880 and 751/695 words; 183.8/150.2 words/min; retention 95.79%/100%;
WER 15.23%/8.06%; two speakers each. Its four pauses were
149.909/90.006/60.004/29.980 s (329.898 s total). Wall-clock canonical p95
330.457/330.974 s includes those pauses and is not uncontended latency.

## Root cause and scope

- `app/live_service_runtime.py:682` supplies the declared bound to the terminal tape;
  `app/live_tape.py:273` records exhaustion and stops retention.
- `app/phase2.py:1685` supplies that same bound to `LiveMeetingAudioStages`;
  `app/phase2_live.py:704` publishes the retained prefix as partial.
- `app/live_transcript_convergence.py:641` maps tape refusal to `unavailable`;
  `app/live_service_runtime.py:1221` publishes the truthful outcome without failing
  the captured meeting. ADR-0003 D5/D8 explicitly requires this behavior.

The files above are under `moss_transcribe_diarize/`. No bound was silently raised,
no incomplete terminal pass was called final, and no failed attempt was discarded.

## Validation and reproduction

Focused existing retention suites: **42 passed, 19 subtests passed, one existing
Starlette warning** (`retention-contract-tests.txt`). They include the real owner-bound
normal-Stop case where a stage cap produces partial audio without losing transcript.
Four Python files compile; original production diff from 37979e53 is empty.
Fresh `/new` verification is prescribed in root VERIFY.md; its separate result is
VERIFY-RESULT.md. Do not treat this implementing-context verification as fresh.

Commands: see prototypes/capacity-campaign/NOTES.md and AUTHORITY.md. Offline reductions:
`python evidence/mvpfix/wp6/summarize.py`; `python evidence/mvpfix/wp6/recover_four.py`
(using COMMON.md Python, PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=., cwd this worktree).
Recovery requires this run's retained ignored SQLite artifact; numeric output is committed.
Original result.json/actions.jsonl/decoder.jsonl remain unchanged. SUMMARY.json gives
all per-session update/resource aggregates; recovered.json and audio-files.json retain
supplementary evidence. Raw audio/text/certificates/cookies are not committed.

Limits: this is a local API campaign with the specified measurement-side two-request
ceiling and local SQLite runtime adaptation. It is not deployed G4/#22/#27 qualification.
Remote process-tree RSS, host error journals, full semantic cross-talk, fixed quality
macro, attended browser latency and speaker attribution remain unmeasured. The four-session
run incurred no full terminal decode cost. Thirty-second sampling cannot exclude all
brief foreign traffic, although this run's shared completion total matched its own calls.
Harness reporting repairs have offline/source verification; no extra live retry to green.
