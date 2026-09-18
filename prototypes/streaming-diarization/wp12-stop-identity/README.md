# WP12 LOGIC measurement prototype

**Current verdict: FALSIFIED, candidate retained for review only.** The six
required 24/60 cases pass, but the additional 180 s same-input control changes
54/56 system segment identities (575 words). Acoustic matching abstains on
`same_span_cannot_link_conflict`; overlap labels those segments. No tuning or
further decoder runs after this finding. See `overlap-falsifier-summary.json`.

Latest continuation: same-lane terminal overlap mapping. Six paired shadow
cases (24/60 s parity, mic -10 dB, same voice on both lanes) passed 135/135 exact
segment comparisons against acoustic attribution. Production now reuses mono's
existing finalizer with a lane-filtered pre-terminal surface and speaker set.
Only terminal segments without labelled overlap use cropped acoustic probes.
Sampling/threshold values and QUALITY_BOUNDS are unchanged.

`overlap_prototype.py` is absorbed into the standing bench as a counterfactual
comparator, using the frozen acoustic implementation. Prepare its ignored source:
`mkdir -p .wp12/base-acoustic && git archive 60b3b584 moss_transcribe_diarize | tar -x -C .wp12/base-acoustic`.
Then run `WP12_ARM=overlap-shadow-<unique-name> bash prototypes/streaming-diarization/wp12-stop-identity/experiment.sh 24 parity`.
Supported cases: `parity`, `mic-minus10`, `same-voice`, `alternation`.
`analyze_overlap.py` reports segment differences without retaining transcript text.
For current production timings use `WP12_ARM=overlap-fixed` and durations
24, 60, or 180 with the same experiment command. Comparison runs retain acoustic
publication, so their Stop timings are NOT optimized-production timings.

The following sections describe the earlier latency diagnosis/history.

Question: where does per-lane Stop time go, how does it scale, and why does the
microphone gain a second identity in WP1's half-system/half-mic 48 s fixture?
Primitives: source tape; decoder window; lane-owned voice reference; publication.
Invariants: complete terminal contract, lane isolation, unchanged identity policy,
unchanged frame/lifecycle/readiness/quality contracts, at most two decoder calls.
Unknown: decoder versus queue versus embedding cost; actual acoustic continuity.
Falsifiers: lost committed words, missing/foreign voice reference, changed final
contract; measured acoustic rejection falsifies a bookkeeping-only repair.

One command from worktree root:
`WP12_ARM=lane bash prototypes/streaming-diarization/wp12-stop-identity/experiment.sh 24 parity`
Use `mono` for the `37979e53` archive inside `.wp12`, and `48 alternation` for the
WP1 identity reproduction. 180 s inputs repeat each public 60 s clip three times.
All frames are paced, heartbeat precedes every pair, Stop deadline is 30 s. State
prints each frame; text/audio/credentials stay out of retained evidence. Real API,
real decoder and pinned production encoder; SQLite version-pin bypass is inherited
from the local bench. Global request ledger refuses beyond the authorized 1200.
Each batch owns/tears down port 18112 tunnel and port 17872 server.

H1 serial whole-meeting decodes dominate; H2 pending canonical/rolling work dominates;
H3 lost lane album evidence causes births; H4 real embeddings reject the old voice.
Timestamps and per-span score/assignment/album traces distinguish these hypotheses.

After absorption, `lane`, `parallel` and `fixed` all use current production code.
`serial` loads the untouched b31683a6 archive in `.wp12/base-b316`; `mono` loads
37979e53 from `.wp12`. Recorded historical `lane` results predate the absorption.
The fresh user request raised the total cap to 1200. `mono-traced` and
`serial-traced` select those same archives; `concurrent-traced` selects current
production. The three new matched 24 s runs used 65 calls, total 339. Phase and
embedding instrumentation is measurement-only. No production change: the
inherent-cost stop condition applied (see NOTES.md F1–F3). Offline:
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> prototypes/streaming-diarization/wp12-stop-identity/audit.py`
Full local suites: `bash prototypes/streaming-diarization/wp12-stop-identity/check-python.sh`
and `bash prototypes/streaming-diarization/wp12-stop-identity/check-frontend.sh`.
The concurrency prototype was absorbed/deleted; these scripts are the standing
bench's measurement and fault-control tools, not alternate product implementations.

Matched embedding accounting (no decoder calls):
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> prototypes/streaming-diarization/wp12-stop-identity/analyze_embeddings.py`.
This reports job timestamps, embedding calls, interval/audio totals, and exact
versus partial input reuse. No speaker words or audio are retained in the report.
