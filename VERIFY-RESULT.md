# WP12 — second reference voice confirmed; acceptance stopped

2026-09-18. Branch `mvpfix/wp12-stop-latency-identity`; clean start c410db8f.
User replaced baseline-equivalence adjudication with source-reference truth.
No production, test, identity-policy, sampling, threshold or QUALITY_BOUNDS changes
in this continuation. Candidate remains on the isolated branch for review only.

## F4 — source adjudication

The looped Bill Ackman reference contains TWO voices. All 54 restored assignments
agree with reference words: 50 segments / 543 words belong to Bill Ackman
(speaker-0001); 4 segments / 32 words belong to Lex Fridman (speaker-0004).
The acoustic baseline's blanket `same_span_cannot_link_conflict` abstention was
wrong to leave those 575 words unassigned. speaker-0004 is legitimate.

| System segment index (zero-based) | Meeting interval | Reference voice / row |
| ---: | --- | --- |
| 9 | 29.61–33.75 s | Lex Fridman / 2 |
| 12 | 40.68–41.40 s | Lex Fridman / 4 |
| 28 | 89.61–93.75 s | Lex Fridman / 2, second loop |
| 31 | 100.68–101.40 s | Lex Fridman / 4, second loop |

Two third-loop Lex turns still lack identity: indices 47 and 50,
149.61–153.75 and 160.68–161.40 s, 16 words. The user's second-voice condition
therefore requires reporting and stopping acceptance/tuning. The requested
single-voice acceptance/regression condition does not apply to this fixture.
No new regression test claiming a single voice was added.

`evidence/mvpfix/wp12/reference-adjudication.json` records every one of the 56
system segments, including all 54 differences, with reference labels/row numbers,
loop offsets, original sample-derived times and word counts. Reference intervals
are coarse. Manual word-to-reference-row adjudication is recorded separately
from all raw time overlaps: several Bill/Lex turns cross reference boundaries,
and Bill's short continuation after 40 s belongs to reference row 3 despite
falling inside row 4's coarse time interval. No word-level timing or new audio
listening claimed. No transcript/audio committed. Reproducer: `adjudicate_reference.py`.

Six earlier same-input 24/60 s cases remain PASS: parity, mic -10 dB, same voice
on both lanes; 135/135 segment dictionaries equal the acoustic control. At 180 s,
all words and boundaries remain equal; zero cross-lane assignments, 30/30 mic
segments equal. Historical FALSIFIED labels in comparison artifacts describe
baseline equivalence, not source correctness; current adjudication supersedes it.

## F1 / F3 — remaining Stop cost

| Measurement | Candidate lanes, 180 s | Base mono, 180 s |
| --- | ---: | ---: |
| Stop→observed final | 16.964282 s | 12.717313 s |
| Stop→terminal start | 4.794547 s | 1.282284 s |
| Drain wait itself | 4.769188 s | 1.262668 s |
| Pending causal tail job | 1.088189 s | 0.675147 s |
| Pending rolling refinement | 3.681203 s | 0.587704 s |
| Final identity sweep | 0.008471 s | 0.006496 s |
| Terminal decode, system / mono | 11.783398 s | 11.025424 s |
| Terminal decode, microphone | 9.257648 s | — |
| Terminal start→publication event | 11.791761 s | 11.031425 s |
| Publication event→client observes final | 0.377974 s | 0.403604 s |
| Terminal decoder windows / audio-seconds | 4 / 360 | 2 / 180 |
| Whole run decoder calls | 184 | 92 |

Lane terminal jobs run concurrently; their durations must not be summed into
Stop latency. Drain is actual pending causal/rolling work, not a fixed timer,
poll or lease delay. Decode stage includes WAV/window handling.

Mapping/publication precision: the retained candidate trace bounds mapping plus
all other non-decode finalizer work to **<3.45 ms system / <2.97 ms microphone**.
It does not isolate mapping calls. Last terminal return→publication event is
**2.875 ms**, including lane aggregation and publication to that event; exact
publication-method duration and persistence time were not separately measured.
Mono's new instrumentation directly measures **0.692 ms mapping** and
**2.557 ms publication-method wall time**. The event-to-client residual includes
observation/persistence work and is not assigned to any one component.

**Whole-meeting terminal decode dominates both:** the critical decoder stage is
69.5% of lane Stop→final and 86.7% of mono. Removing embeddings does not remove
that full-meeting decode. No extrapolated 30-minute guarantee. Both 180 s runs
exceed the 10 s bar. These are single observations on the shared GPU; mono mixes
the same two input clips and is a timing reference, not a transcript parity claim.

Mono used base archive **37979e53**: 86/86 Python files byte-equal to Git; loaded
package path recorded in `mono180-source-audit.json`. One run, idle admission
running=0/waiting=0, no retry. Command:
`WP12_ARM=mono180-traced bash prototypes/streaming-diarization/wp12-stop-identity/experiment.sh 180 parity`.
Timing data/reproducer: `stop-180-breakdown.json`, `analyze_180.py`.

## F2 — embedding work and retained shorter timings

| Parity duration | Candidate Stop→final | Acoustic terminal embedded audio | Candidate |
| --- | ---: | ---: | ---: |
| 24 s | 3.788534 s | 43.08 s | 0 |
| 60 s | 7.490138 s | 111.90 s | 0 |
| 180 s | 16.964282 s | 335.52 s | 0 |

Mono 24 s reference: 1.880702 s. Mono 180 s terminal embeddings: zero calls,
zero audio-seconds. Candidate terminal calls/intervals also zero at all lengths.
All measured final surfaces equal their saved text/identity. Earlier independent
24 s comparison: 13/13 saved dictionaries exact; 60 s: all 28 text/speaker pairs
exact, one start differs by 20 ms (54.96→54.94 s). Same-input shadow rows all equal.

## F5 — full verification

Executed root VERIFY.md checks in this continuation, worktree-local imports:

- `check-python.sh`: **1805 passed, 2 skipped, 21 warnings, 37 subtests passed**,
  139.91 s. Log: `evidence/mvpfix/wp12/adjudication-full-python.txt`.
- `check-frontend.sh`: **26 files / 230 tests passed**, typecheck and build pass.
  Log: `evidence/mvpfix/wp12/adjudication-full-frontend.txt`.
- `audit.py`, `analyze_overlap.py`, `analyze_fixed.py`, `adjudicate_reference.py`,
  `analyze_180.py`: pass their retained-data assertions; no decoder calls.
- Existing three overlap regressions and lane/identity/lifecycle suites included;
  historical focused gate: 191 passed. No assertions weakened.
- Generated WP2 screenshots restored, frontend assets unchanged, diff whitespace
  check passes. Owned ports 18112/17872 have no listeners.

Bench changes only: unique base-mono arm, mapping/publication timers, offline
reference and timing reports. This is current-context verification; no new /new
fresh acceptance is claimed. No second lane run was made after the reference
stop condition; its mapping/publication timing limitations are explicit above.

## F6 — accounting and boundaries

**1165/1200 calls**, peak own concurrency **2**; 1151 across 22 completed runs,
all 22 final/saved agreements, plus the previously recorded 14 invalidated calls.
Mono added exactly 92 calls. Conditional 1350 cap was unnecessary and not used.
Prior twelve busy admission refusals and invalidated overlapping-launch incident
remain recorded; this continuation has no admission refusal or failed decoder run.
One documentation patch had a context mismatch, made no changes, and was corrected.

No production acceptance, tuning, push, merge, deployment, shared-service change,
or writes outside the worktree. Earlier two-mic-ID allegation remains falsified:
that fixture also contains two voices. Stop/report condition honored; no identity
policy repair or single-voice claim made.
