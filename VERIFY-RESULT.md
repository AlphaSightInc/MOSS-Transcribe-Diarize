# WP12 overlap candidate — FALSIFIED; software gates PASS

Date: 2026-09-18. Branch `mvpfix/wp12-stop-latency-identity`, starting clean at
accepted diagnosis `60b3b584`. Candidate implementation and tests are retained on
this isolated branch for review only. **Not accepted, not deployed.** No tuning
or additional decoder runs followed the attribution falsifier.

## F4 — exact attribution stop condition triggered at 180 seconds

The six requested same-input comparisons pass: 24/60 s parity, mic -10 dB, and
same voice on both lanes. **135/135 segment dictionaries equal**, zero cross-lane
assignments, zero fallback audio. Acoustic output remained the saved control.

An additional 180 s control supplied the before-embedding denominator and tested
the two unassigned system segments observed in the candidate's long run. It used
identical decoder output and settled session state for both mapping methods:

| Lane | Segments | Attribution changes | Word/boundary changes |
| --- | ---: | ---: | ---: |
| System | 56 | 54 | 0 |
| Microphone | 30 | 0 | 0 |

Acoustic system preparation abstains for the whole lane with
`same_span_cannot_link_conflict`: decoder labels S01/S02/S03 compete for two
known system speakers. Overlap mapping instead changes:

- 50 segments / 543 words: unassigned → `speaker-0001`.
- 4 segments / 32 words: unassigned → `speaker-0004`.
- Two segments / 16 words remain unassigned; all 30 mic segments match.

Zero cross-lane assignments. This is a strict attribution-equivalence failure;
it does not establish which output is source-correct. No policy values, sampling
values, thresholds, QUALITY_BOUNDS, conflict rule, or mapping were tuned afterward.
All row diffs: `evidence/mvpfix/wp12/overlap-comparison.json`.
Concise verdict: `evidence/mvpfix/wp12/overlap-falsifier-summary.json`.

## F3 — measured candidate Stop latency

| Parity input | Stop→final | Stop→terminal | Terminal→publication | Decoder calls |
| --- | ---: | ---: | ---: | ---: |
| 24 s | 3.788534 s | 2.578691 s | 1.100589 s | 26 |
| 60 s | 7.490138 s | 4.867833 s | 2.446688 s | 62 |
| 180 s | 16.964282 s | 4.794547 s | 11.791761 s | 184 |

Mono 24 s reference: **1.880702 s**. Stop→final is the API client’s observed completion;
publication is timestamped separately. 60 s exceeds 4 s; 180 s exceeds both 4 s and 10 s.
These are single observations on the shared GPU, not a capacity qualification or
30-minute extrapolation. All three candidate final surfaces equal saved text/identity.

## F2 — terminal embedding work removed on these inputs

| Parity input | Acoustic control audio-seconds embedded | Candidate |
| --- | ---: | ---: |
| 24 s | 43.08 | 0 |
| 60 s | 111.90 | 0 |
| 180 s | 335.52 | 0 |

Candidate terminal embedding calls and encoder intervals are also zero for all
three lengths. Causal and rolling embeddings remain unchanged. The candidate
passes each lane's settled surface/canonical set to the existing mono finalizer;
only terminal segments without labelled same-lane overlap use cropped acoustic
probes. Regression coverage exercises an uncovered 3–5 s system segment while
simultaneous microphone evidence cannot cover it.

Separate saved-output comparison: 24 s **13/13 exact dictionaries**. At 60 s,
**all 28 rows have exact text and speaker IDs**; one microphone row starts at
54.94 rather than 54.96 s, same end/text/speaker. The same-input 60 s shadow
comparison is 28/28 exact; independent decoder calls produced the 20 ms difference.
Native saved schema lacks source_lane; lane ownership was checked on live segments.
Results: `overlap-timings.json`, `overlap-independent-output-comparison.json`,
and the read-only saved-document assertions in `overlap-audit.json`.

## F5 — software verification and source scope

Production change: `moss_transcribe_diarize/app/live_lane_decode.py` only.
Tests: `tests/test_live_lane_decode.py` adds three production-seam checks;
all three fail on the previous acoustic implementation, then pass on the candidate.
No existing assertion was weakened. Bench, evidence and design/verification docs
record the candidate and stop condition.

Commands (specified venv, PYTHONDONTWRITEBYTECODE=1, worktree-local imports):

- Focused lane/identity/session/coordinator/runtime/lifecycle pytest set:
  **191 passed**, 1 warning, 4.55 s (`overlap-focused.txt`).
- `bash prototypes/streaming-diarization/wp12-stop-identity/check-python.sh`:
  **1805 passed, 2 skipped, 21 warnings, 37 subtests passed**, 143.19 s.
- `bash prototypes/streaming-diarization/wp12-stop-identity/check-frontend.sh`:
  **26 files / 230 tests passed; typecheck and build passed**.
- `audit.py`, `analyze_overlap.py`, `analyze_fixed.py`: retained content-free
  accounting, row diffs, and timing results. Their commands are in VERIFY.md.

Logs: `evidence/mvpfix/wp12/overlap-full-python.txt` and
`overlap-full-frontend.txt`. Suites ran while waiting for the shared GPU; no
production/test edits followed. Generated WP2 PNGs restored; frontend assets
unchanged; `git diff --check` passes. This is implementation-context verification,
not a claimed new /new acceptance pass. Prior fresh verification is retained in
commit 60b3b584. Passing software tests do not override F4.

## Operational accounting and deviations

**1073/1200 dispatched calls; peak own concurrency 2.** 1059 calls across 21
completed runs, 21 final/saved agreements, plus 14 accounted calls from one
invalidated control launch. Twelve idle-only admission refusals sent no calls.
An idle retry became admitted while its parent was being stopped; an overlapping
launch failed startup and reached HTTP 409. No results from that attempt were
used. All owned processes stopped before the clean run; bench port/PID checks
now prevent reusing a listener from an overlapping launch.

The additional 180 s control used `WP12_SINGLE_FLIGHT=1`, allowing one own request
with waiting=0/running<=1 at admission. Its Stop timing is not a performance
baseline. Its source is the frozen 60b3b584 acoustic archive; production timing
runs used the candidate and normal two-request cap, with idle admission. All
attempts remain in the ledger; no silent exclusion from budget or concurrency.

No owned listeners remain on 18112/17872. No push, merge, deployment, shared-service
changes, or writes outside this worktree. No audio, transcripts, credentials, or
private databases committed. The earlier two-mic-ID claim remains falsified by
the two-voice fixture; no identity-policy repair. Work stopped on F4, with the
candidate retained for review and no further tuning or qualification claim.
