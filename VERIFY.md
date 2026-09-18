# WP12 same-lane terminal overlap verification

**STOP / FALSIFIED:** the additional 180 s same-input control changes attribution
on 54/56 system segments. Acoustic `same_span_cannot_link_conflict` abstains for
the whole lane; overlap labels 54 segments. This candidate is retained for review,
NOT accepted. Do not tune or run more decoder experiments without new direction.
Required six 24/60 cases passed; that does not override the 180 s falsifier.

Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp12-stop-latency-identity`.
Branch: `mvpfix/wp12-stop-latency-identity`; implementation starts from accepted
latency diagnosis `60b3b584`. All writes stay in this tree. No push, merge, deploy,
shared-service changes, or messages to other agents. User-authorized total decoder
budget: 1200, max two in flight, own tunnel 18112, check waiting before each batch.
The commands below make no decoder calls. See VERIFY-RESULT.md for actual counts.

Question: can mono's existing terminal overlap assignment replace full-tape lane
probes while preserving attribution? Primitives: lane-filtered settled surface,
terminal speaker partition, overlap assignment, cropped uncovered-segment probe.
Invariants: same words/attribution on the requested comparison matrix, zero
cross-lane assignments, unchanged policy values/thresholds/QUALITY_BOUNDS, complete
final publication. Any attribution difference falsifies the change: stop, report,
never tune to the cases. Unknown outside the measured inputs remains unmeasured.

Implementation: `moss_transcribe_diarize/app/live_lane_decode.py` passes each lane's
surface/candidates to the existing mono finalizer. Only terminal segments lacking
labelled overlap use the existing acoustic preparer, on cropped PCM. Regression
coverage: `tests/test_live_lane_decode.py`; three new tests fail on the old code.
The six shadow comparisons use identical decoder output/session state and retain
acoustic publication: 24/60 parity, mic -10 dB, same voice in both lanes. They are
comparison evidence, not optimized Stop timings. Production timing arms are named
`overlap-fixed`. Frozen comparator source is 60b3b584 under `.wp12/base-acoustic`.

Run from this worktree, without installs:

```bash
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
WP12_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
git status --short
git branch --show-current
git rev-parse HEAD
"$WP12_PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
bash prototypes/streaming-diarization/wp12-stop-identity/check-python.sh > evidence/mvpfix/wp12/overlap-full-python.txt 2>&1
bash prototypes/streaming-diarization/wp12-stop-identity/check-frontend.sh > evidence/mvpfix/wp12/overlap-full-frontend.txt 2>&1
"$WP12_PY" prototypes/streaming-diarization/wp12-stop-identity/audit.py > evidence/mvpfix/wp12/overlap-audit.json
"$WP12_PY" prototypes/streaming-diarization/wp12-stop-identity/analyze_overlap.py > evidence/mvpfix/wp12/overlap-comparison.json
"$WP12_PY" prototypes/streaming-diarization/wp12-stop-identity/analyze_fixed.py > evidence/mvpfix/wp12/overlap-timings.json
```

Expected: package resolves inside this tree; full Python 1805 passed / 2 skipped /
37 subtests; frontend 230 tests / 26 files; typecheck/build succeed. Comparison:
6/6 PASS, 135/135 exact segment dictionaries, zero cross-lane assignments.
Supplementary 180 s: FALSIFIED, 54 changed system segments / 575 words,
30/30 mic segments equal, no word/boundary or cross-lane differences. Ledger:
1073/1200 calls = 1059 across 21 completed runs + 14 invalidated control calls.
This diagnostic outcome must remain visible even though all software tests pass.
The timing
report must contain all 24/60/180 s production runs with final/saved agreement.
Audit: no more than 1200 calls, peak at most two, all completed requests accounted.
Existing historical equivalence assertions remain; do not weaken assertions.
Private scratch SQLite is read ONLY; never commit it, transcripts, or audio.

The full suite rewrites WP2 screenshots. Restore only these generated files:
`git restore -- evidence/mvpfix/wp2/production-1280.png evidence/mvpfix/wp2/production-390.png evidence/mvpfix/wp2/production-400.png`.
Check `git diff --check`. Check owned listeners are gone:
`lsof -nP -iTCP:18112 -iTCP:17872 -sTCP:LISTEN` (empty/exit 1 expected).
Update VERIFY-RESULT.md with exact counts, timings, compared source and context,
limitations, and deviations. Do not call same-context verification a fresh /new.
Commit locally, report in <=60 lines. Preserve the falsified two-mic-ID finding:
the fixture contains two voices; no identity continuity or threshold repair.
