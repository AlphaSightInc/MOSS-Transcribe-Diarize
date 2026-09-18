# WP6 — local tape truncation resolved; capacity baseline not accepted

**F1 — The 300-second cap belongs to the LOCAL August measurement manifest.**
Round 16 recorded four deployed 600-second finals; its exact deployed/staged tape
bound is **not recorded** here. Staging preserves a declared byte cap; the finalizer
validates frame alignment and a minimum equal to rolling retention, not a derived
session duration. See MANIFEST.md. Shared manifest remains byte-for-byte unchanged.

**F2 — One authorized rerun used an isolated 57,600,000-byte (30-minute) copy.**
Rolling retention stayed 960,000 samples. All four MP3s independently probe at
**600.000 s**, 16 kHz mono, 3,600,765 bytes each: 2,400/2,400 seconds archived.
Two sessions finalized; two were interrupted by helper-lease expiry after Stop.
The cap correction fixes the observed truncation, not the whole capacity result.
**Eight-session overload skipped**: contaminated run, two interrupted meetings.

| Session / clip | Stop→final s | Saved outcome / audio status | Saved WER | Births / named speakers |
|---|---:|---|---:|---|
| 1 Bill Ackman | 39.687 | completed / available | 15.28% final | 2 / 2 |
| 2 Keyu Jin | 29.489 | completed / available | 8.85% final | 2 / 2 |
| 3 Javier intro | unavailable | interrupted / partial | 11.14% non-final | unknown / 1 |
| 4 Jamie Dimon | unavailable | interrupted / partial | unknown: cut reference sentence | unknown / 3 |

**F3 — Stop failure mechanism remains unresolved; no production repair claimed.**
Logs confirm helper-lease expiry for 3/4. Collector omitted HTTP status/body and
final snapshots on their errors, so exact terminal-refinement status, Stop→outcome,
API sample counters and births are not retained. All 9,600 lane frames acknowledged;
0/9,600 wrong-owner probe failures. Sessions 1/2 accepted=accounted=9,600,000 samples.
For 3/4, 9,600,000 samples follows from acknowledgments only. Saved transcript ends
599.99/599.97 s do not establish exact accounted-sample obligations. See STOP-ASSESSMENT.md
inside 20260918-002944-4x600. No failure is silently reclassified as final.

**F4 — WP12 handoff corrects apparent fragmentation.** Original totals 3/2, 5/3,
2/1 included the unassigned bucket. Named/reference counts were Bill 2/2, Jamie 4/3,
Javier 1/1. Jamie's extra named identity is a finding; the other count excesses are
unassigned speech. Original births unmeasured; rerun births 2/2/unknown/unknown.
WP12.md records per-session counts and limitations. No identity policy changed.

- **M1:** 12/32 foreign-load samples; pauses 179.985/60.003/29.999 s (269.987 s total).
  Canonical p95 272.804/272.819/273.313/273.368 s includes pauses; not clean latency.
- **M2:** app RSS 627.547→peak 1,093.813 MiB, growth **466.266 MiB**. GPU memory
  14,175/16,376 MiB; cache peak 9.340%; sampled waiting peak 0. Remote RSS unmeasured.
- **M3:** fairness skew 1 over 1,299 observations; refinement queue peak 1. Inference
  RTF unknown: failed collectors left incomplete rolling admitted/completed events.
- **M4:** first text 3.070/4.065/1.559/2.058 s; words 1,841/1,513/1,303/1,938 versus
  reference 1,760/1,390/1,356/1,884 (last reference incomplete). No 429 observed.
- **M5:** rerun 1,275 starts/finishes, own concurrency max2; all five attempts total
  **2,887 starts/finishes**, 13 sessions: 9 completed, 4 interrupted (2 intentional).

Verification: Python 1,701 passed/1 known WP4 failure/2 skipped/37 subtests;
frontend 206 passed; retention 42 passed/19 subtests. See VERIFY-RESULT.md.
Changes are harness/evidence only; production diff from 37979e53 remains empty.
Historical attempts preserved in REPORT-300s-original.md and their raw records.
SUMMARY.json recomputes counts; recover_run.py verifies saved content/audio offline.
Reproduction and isolated-manifest command: prototypes/capacity-campaign/NOTES.md.
Limits: local two-request limiter, SQLite harness adaptation, foreign load, incomplete
error observations, looped clips (not the fixed quality population), no attribution
accuracy, deployed qualification, remote journals/RSS, push, merge, or deployment.
