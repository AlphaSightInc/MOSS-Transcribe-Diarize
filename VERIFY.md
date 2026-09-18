# WP12 accepted production verification

Lead decision: ACCEPTED after reference adjudication. Same-lane overlap mapping
with cropped acoustic fallback is already the production lane path, introduced
in c410db8f; no shadow flag or prototype import is involved. Concurrent terminal
lane jobs remain. Legacy mono finalization and identity policy values, sampling,
thresholds and QUALITY_BOUNDS are unchanged.

Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp12-stop-latency-identity`.
Branch: `mvpfix/wp12-stop-latency-identity`; continuation starts at a2ee97eb.
Only this tree may be modified. No push/merge/deploy/shared-service changes.
1165/1200 decoder calls already used. Conditional 1300 cap is authorized only if
a final confirmation is needed; these checks make no decoder calls.

Question: does the accepted lane path preserve covered identities and all terminal
words while limiting new acoustic work to uncovered same-lane segments?
Primitives: lane-owned canonical identities, settled lane spans, terminal speaker
partition, cropped probe. Invariants: lane isolation, terminal words/times retained,
unchanged one-to-one speaker mapping and acoustic policy, single publication after
both concurrent lane jobs. Reference truth overrides the old acoustic baseline's
blanket abstention. Unknown: larger-duration accuracy/capacity outside measured runs.
Falsifiers: covered single-voice regression loses identity; an uncovered probe reads
outside its segment; abstention loses words; 24/60 row equality or lane isolation
breaks; any existing suite fails. These checks require a fix before final reporting.

Regression coverage in tests/test_live_lane_decode.py:
- 180 s single-voice lane: real causal commits and terminal publication, 36 terminal
  segments keep their words and identity; zero acoustic probes.
- 3–5 s uncovered system segment: exactly 2 s of system PCM reaches preparation;
  success and injected legitimate abstention both preserve words; simultaneous mic
  evidence cannot cover the gap.
- 24/60 s: 13/28 full segment dictionaries equal accepted acoustic row geometry,
  with synthetic text and causal subdivisions. Reversed local labels collide across
  lanes. This is deterministic production-finalizer coverage, not another live run.
- Existing concurrent-terminal and lifecycle tests remain in the full suite.

Known residual: the 180 s two-voice interview leaves Lex's 149.61–153.75 and
160.68–161.40 s turns unassigned (16 words). These HAVE same-lane causal overlap;
three terminal local labels compete for two canonical speakers, leaving one local
unmapped. Zero fallback audio was used. Do not relabel this as an uncovered-tail
acoustic abstention. Cropped fallback may independently abstain for a true gap.

Run in a NEW shell process, from the worktree (no installs):

```bash
bash --noprofile --norc <<'SH'
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
WP12_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
{
  pwd
  git branch --show-current
  git rev-parse HEAD
  "$WP12_PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
} > evidence/mvpfix/wp12/accepted-shell.txt
bash prototypes/streaming-diarization/wp12-stop-identity/check-python.sh > evidence/mvpfix/wp12/accepted-full-python.txt 2>&1
bash prototypes/streaming-diarization/wp12-stop-identity/check-frontend.sh > evidence/mvpfix/wp12/accepted-full-frontend.txt 2>&1
"$WP12_PY" prototypes/streaming-diarization/wp12-stop-identity/audit.py > evidence/mvpfix/wp12/accepted-audit.json
"$WP12_PY" prototypes/streaming-diarization/wp12-stop-identity/analyze_overlap.py > evidence/mvpfix/wp12/overlap-comparison.json
"$WP12_PY" prototypes/streaming-diarization/wp12-stop-identity/analyze_fixed.py > evidence/mvpfix/wp12/overlap-timings.json
"$WP12_PY" prototypes/streaming-diarization/wp12-stop-identity/adjudicate_reference.py > evidence/mvpfix/wp12/reference-adjudication.json
"$WP12_PY" prototypes/streaming-diarization/wp12-stop-identity/analyze_180.py > evidence/mvpfix/wp12/stop-180-breakdown.json
git restore -- evidence/mvpfix/wp2/production-1280.png evidence/mvpfix/wp2/production-390.png evidence/mvpfix/wp2/production-400.png
git diff --check
if lsof -nP -iTCP:18112 -iTCP:17872 -sTCP:LISTEN; then exit 1; fi
SH
```

Expected: local package path, 1809 Python tests / 2 skips / 37 subtests;
230 frontend tests / 26 files, typecheck/build pass. Ledger 1165 calls, max two
in flight, 22 completed final/saved agreements, 14 previously invalidated calls
included. Six real-input 24/60 shadow cases: 135 exact segments, zero cross-lane
assignments. 180 s: 54 reference-correct restorations, 16 unassigned Lex words.
Timing analyzers retain previous measurements; no new GPU confirmation required
because production behavior has not changed since those runs.

Historical comparison artifacts still label the old baseline-equality criterion
FALSIFIED; this is not rejection of the now reference-adjudicated implementation.
The current verdict is in NOTES.md and VERIFY-RESULT.md. Verify no production
behavior/policy drift, no generated assets outside scope, and clean owned ports.
Record actual counts and any failures in VERIFY-RESULT.md, then commit locally.
Fresh shell is not a new /new model context; do not claim the latter.
