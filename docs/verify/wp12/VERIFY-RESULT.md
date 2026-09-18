# WP12 — ACCEPTED; production lane mapping verified

2026-09-18. Branch `mvpfix/wp12-stop-latency-identity`; continuation starts clean
at a2ee97eb. Lead explicitly accepted the source-adjudicated implementation.
No deployment, push or merge. This report supersedes the earlier acceptance stop.

## F1 — production behavior and regression coverage

`LiveServiceRuntime` already routes lane sessions to `finalize_lanes`; c410db8f
implemented the accepted behavior in production, not merely in the shadow bench.
Each lane passes only its own settled surface/canonical identities to the existing
mono overlap mapper. Only segments without labelled same-lane overlap use a fresh
acoustic probe cropped to that segment. Both terminal lane jobs remain concurrent;
results are assembled before one publication. Legacy mono behavior is untouched.
No policy values, sampling, thresholds, QUALITY_BOUNDS or decoder windows changed.

Productionization therefore adds regression coverage and acceptance records; the
only production-source edits in this continuation clarify two docstrings.

- Long covered single-voice lane: 180 s of real causal commits, 36 terminal segments;
  exact words/times/identity survive publication, zero acoustic probes.
- Uncovered system 3–5 s segment: exactly 64000 bytes / 2 s of system PCM reaches
  preparation. Both successful mapping and an injected legitimate preparer
  abstention preserve words. Concurrent microphone evidence cannot fill the gap.
- 24/60 s: all 13/28 segment dictionaries equal accepted acoustic row geometry,
  including times, text, speaker, lane and authority. Fixture retains real timings
  and identities; words and causal subdivisions are synthetic. Reversed local
  labels deliberately collide across lanes. This deterministic production-seam
  test complements, rather than replaces, the measured real-input comparison.
- Existing concurrency test still requires peak two lane jobs and publication
  only after both; all existing identity/lifecycle tests are included below.

Files: `tests/test_live_lane_decode.py`, `tests/fixtures/wp12_terminal_parity.json`,
production docstrings in `moss_transcribe_diarize/app/live_lane_decode.py`, bench
adjudication verdict, NOTES/design/verification docs and retained evidence.

## F4 — reference acceptance and known limitation

All 54 restored system assignments match the reference: **50 Bill Ackman segments /
543 words → speaker-0001; 4 Lex Fridman segments / 32 words → speaker-0004**.
The old acoustic path's blanket `same_span_cannot_link_conflict` abstention was
wrong for those 575 words. No attribution tuning was involved. All 56 system rows,
reference labels, loop offsets and reviewed word-to-reference associations are in
`evidence/mvpfix/wp12/reference-adjudication.json`; no transcripts/audio committed.

**Known residual:** Lex's **149.61–153.75 s and 160.68–161.40 s** turns remain
unassigned, **16 words**. These segments HAVE causal overlap: the unchanged
one-to-one speaker assignment leaves a third terminal local label unmatched
against two canonical voices. Zero fallback samples/terminal embeddings occurred.
This is not evidence of cropped-fallback abstention. A truly uncovered segment can
independently receive a cropped acoustic probe and abstain, now regression-tested.
Both paths preserve words. No promise that every decoder-created local partition
will fit the known canonical set is made.

The six measured 24/60 s cases (parity, mic -10 dB, same voice both lanes) retain
**135/135 exact segment dictionaries**, zero cross-lane assignments. At 180 s,
all words/boundaries remain equal; 30/30 mic segments equal. Historical comparison
artifacts retain FALSIFIED for baseline equality; lead's reference adjudication
supersedes that acceptance criterion. The current reference report says ACCEPTED.

## F2 / F3 — retained Stop timing and embedding work

All values below are already measured; no new GPU run was needed because runtime
behavior has not changed since the accepted measurements.

| Parity input | Lane before: acoustic control | Lane after: overlap | Mono reference | Terminal embedded audio before → after |
| --- | ---: | ---: | ---: | ---: |
| 24 s | 7.479681 s | 3.788534 s | 1.880702 s | 43.08 s → 0 |
| 60 s | 16.457955 s | 7.490138 s | — | 111.90 s → 0 |
| 180 s | 44.972440 s * | 16.964282 s | 12.717313 s | 335.52 s → 0 |

Before rows use the frozen 60b3b584 acoustic shadow controls p24/p60/p180-clean;
acoustic output was published. The after rows use the production overlap path.
*The 180 s acoustic control used one request slot with another workload present;
the after run used the normal two-slot cap and idle admission. Its observed
44.972440 s is NOT a matched throughput baseline or a causal speedup estimate.
No two-slot 180 s acoustic baseline was measured. No invented substitute.
Earlier pure concurrent-acoustic observations: 6.839325 s at 24 s and 16.174951 s
at 60 s; original serial-lane observations: 11.803096 / 26.635716 s respectively.

Candidate terminal embeddings: zero calls/intervals/audio-seconds at all three
lengths. Mono terminal embeddings: zero at both reference lengths. The mono-180
run used verified base archive 37979e53 (86/86 Python files byte-equal to Git),
exactly one run / 92 calls. Mono mixes the same two input clips; it is a timing
reference, not a transcript parity claim. All measured final surfaces equal their
saved text/identity. Independent after-vs-control saved comparison: 24 s 13/13
exact rows; 60 s all 28 text/speaker pairs exact, one start differs by 20 ms.

180 s after breakdown: **4.794547 s** before terminal (causal tail 1.088189 s,
rolling refinement 3.681203 s, final identity sweep 0.008471 s plus handoff), then
concurrent terminal decoder stages **11.783398 s system / 9.257648 s mic**.
Mapping plus other non-decode finalizer work is bounded by **<3.45 / <2.97 ms**;
old trace did not isolate mapping calls. Last terminal return→publication event
**2.875 ms**, including lane aggregation/publication; event→client final **0.378 s**.
Mono: **1.282284 s** before terminal, **11.025424 s** decode, directly measured
**0.692 ms** mapping and **2.557 ms** publication-method wall time.

Whole-meeting decode dominates remaining Stop: **69.5% lane / 86.7% mono** at
180 s. Lane decodes four windows / 360 audio-seconds; mono two / 180. Decode-stage
wall time includes WAV/window handling. Both 180 s runs exceed the 10 s bar;
these single observations do not qualify 30-minute capacity. Full breakdown:
`stop-180-breakdown.json`. No fixed Stop sleep or lease wait was identified.

## F5 — fresh-shell verification

Executed root VERIFY.md literally in a new `bash --noprofile --norc` process,
with worktree-local imports; shell/branch/base SHA recorded in `accepted-shell.txt`.
This is fresh-shell execution, not a new /new model context.

- Focused lane suite: **28 passed**, 1 warning, 3.25 s (`accepted-lane-tests.txt`).
- Full Python: **1809 passed, 2 skipped, 21 warnings, 37 subtests passed**, 142.12 s
  (`accepted-full-python.txt`).
- Full frontend: **26 files / 230 tests passed**, typecheck/build pass
  (`accepted-full-frontend.txt`).
- `audit.py`, `analyze_overlap.py`, `analyze_fixed.py`, `adjudicate_reference.py`,
  `analyze_180.py`: retained-data assertions pass; no provider calls.
- Generated WP2 screenshots restored, frontend assets unchanged; diff whitespace
  check passes; no owned listeners on 18112/17872. No existing assertion weakened.

No production behavior or test edits followed the full-suite run. One documentation
patch had an invalid context, made no changes, then was corrected. No test failures.

## F6 — accounting and boundaries

**1165/1200 decoder calls**, unchanged this continuation; conditional 1300 cap
unused. Peak own concurrency **2**; 1151 calls across 22 completed runs, all 22
final/saved agreements, plus the previously recorded 14 invalidated control calls.
Prior twelve admission refusals and invalidated-launch incident remain recorded;
no new decoder experiment, admission, tunnel or measurement server was started here.

No push, merge, deployment, shared-service change or writes outside the worktree.
Earlier two-mic-ID allegation remains falsified: that fixture contains two voices.
The accepted production optimization removes redundant terminal embedding work;
remaining decode cost and 16 unassigned Lex words are explicit limitations.
