# WP33 evidence

Question: can the existing lane-result, capture-error callback, transcript key,
and required-row verdict boundaries preserve facts without changing finalization?
Hypothesis: OR warnings, sum counts, retain lane-labelled diagnostics; use existing
pre-session cleanup; retain no-lane keys; distinguish required skips.
Invariants: finalization/lifecycle, protected policy values, nine frame keys unchanged.
Unknown: physical capture and real decoder behavior; neither needed for these defects.
Falsifier: any lane warning lost, Reset absent, legacy byte mismatch, required SKIP accepted.
Tools: WP32 actual native-finalizer/component/export probes establish before behavior;
focused regressions and whole suites determine whether implementation can ship locally.

Prototype: `python .wp33/prototype.py --all` (interactive without --all).
Throwaway in-memory state model prints all state per action; retained prototype.jsonl.
Baseline real-path witnesses: before-truncation.json = 2/3 flags, 3/3 final;
before-reset.txt = 1/1 stuck configuring; before-legacy.jsonl = 4/5 parity, JSON 523/497.
Model supports the smallest design on all 5 actions; no new threshold or framework.
The executable prototype is deleted after absorption into regressions.

## Findings and diagnostic audit

F1: `live_lane_decode.py` ORs truncation across all results, sums seam losses and
existing counters even if every lane refuses, combines window diagnostics with
`source_lane`, and keeps window failures keyed by lane. Original 2/3 flags -> 3/3;
3/3 proposals still applied/final. Asymmetric and refusal regressions added.
Every accounting field audited:
- Outcome/reason: assembled proposal authority retained; partial-lane failure reason
  retained. No successful lane => original refusal selection unchanged.
- Epoch/end sample/rolling through/rolling status: shared input plan, template correct.
- Window/stride seconds: same finalizer and runner across lanes, template correct.
- Tape samples/gaps: all tapes, retained existing totals.
- Window/completed/audio/token/prompt/local-speaker counts and decode seconds:
  summed across results; time is cumulative decoder time, not wall duration.
- Truncation: OR; seam merged/dropped/displaced: sum.
- Window diagnostics: lane-labelled concatenation; window failures: lane-keyed map
  (mono dictionary unchanged). Prevents loss when only the second lane fails.
- Segments/mapped speakers/unattributed: assembled surface recount, unchanged.
No model/configuration/threshold/lifecycle changes. Real native decoder unmeasured.

F2: `captureClient.ts` routes ended tracks before session creation through the
existing `failBeforeSession` -> `onPreSessionFailure` -> ControlPanel error path.
No ControlPanel production edit needed. Both lane meters become Not connected,
tracks stop, worklets detach, context closes, Reset offered, fresh setup succeeds.
Baseline 1/1 stuck configuring; four fixed cases: both lanes x configuring/ready.
WP27's 23 existing component cases remain in the same suite.

F3: `transcriptKeys.ts` returns legacy timing/text key when source_lane absent;
existing lane/speaker suffix preserved for tagged rows. Same WP32 synthetic input:
4/5 -> 5/5 format parity. JSON 523 -> 497 bytes (base 497); md 72, txt 69, srt 91,
vtt 99 bytes unchanged. Unit regressions cover speaker-bearing legacy/tagged rows.

F4: `verify_workspace.py`, `tools/qualify/run.py`, README and shell exit-code comment.
Required SKIP retained distinctly; harness 2 and bundle INCOMPLETE/qualified false.
FAIL takes precedence; 1. PASS only all required measured; 0. Unrequested long
measurements explicitly optional. Real baseline cleanup/exit-expression comparison:
13 PASS + 1 SKIP /14 previously exit0/qualified true; now exit2/false/INCOMPLETE.
Tests exercise real summary-check SKIP, bundle workspace classification, cleanup,
required/optional rules, and shell propagation. No live GPU/relay bundle dispatched.

F5: historical mutation log prefaced, WP12 NOTES qualified: 3 valid + 2 invalid.
`fault_controls.py --terminal-only` repairs required `gaps=()` and reruns only those
controls. 2/2 now fail assertions (0 HTTP requests; failed vs final), 0 TypeErrors.
Historical malformed run remains intact after the explicit qualification prefix.

## Failed attempts and scope

`red-python.txt`: restored old production -> 4 failed, 2 passed, 38 deselected.
`red-frontend.txt`: restored old production -> 3 failed, 26 filtered. Restored
candidate source in finally. Focused attempt1 Python: 2 fixture-import failures,
89 passed/19 subtests; including existing phase2 test file exposes its fixture path,
no test weakening. Focused attempt1 frontend: 2 failed/27 passed because an assertion
matched lowercase 'connected' inside 'Not connected'; fixed exact two-label assertion.
Initial guessed vitest.config.ts was absent; chained probe write did not run; missing
probe invocation failed, then script created and run successfully. No product defect.
A nonexistent fixture_mutations.py read corrected to the retained fault_controls.py.

Prototype model executable absorbed into regressions and removed. `.wp33` scratch
is never committed. Python bytecode disabled; TMPDIR and local-scratch plugin keep
fixtures inside this worktree. Frontend uses shared dependency symlink and local
Vite cache, --configLoader runner. No installs, GPU, external service starts, push,
merge, GitHub or deployment. Verification docs use docs/verify/wp33 per repository
layout rule. Fresh /new verification is a separate thread, not claimed by this draft.

## Draft verification results (before /new)

- Full Python: 1962 passed, 4 skipped, 21 warnings, 37 subtests; 170.76 s, exit0.
- Full frontend: 271 passed /28 files; 2.47 s, exit0.
- Focused Python: 108 passed, 4 warnings, 19 subtests; 8.37 s.
- Focused frontend: 31 passed /2 files; 684 ms.
- Typecheck exit0; build exit0, 108 ms; committed rebuilt app.js/app.js.map.
- Existing four full-suite skips: 2 optional WP28 real WAV cases, 1 operator identity
  corpus, 1 real F-cert corpus. All are unmeasured, not coverage passes.

Commands from this worktree, with PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. and
TMPDIR=$PWD/.wp33/tmp; Python = COMMON's wt-auto-mvp-0911/.venv/bin/python:
`python -m pytest -q -rs -p no:cacheprovider -p evidence.mvpfix.wp16.local_scratch tests`;
`npm --prefix frontend test -- --run --configLoader runner`;
`npm --prefix frontend run typecheck`;
`npm --prefix frontend run build -- --configLoader runner`.
Focused paths: test_live_lane_decode.py, test_live_terminal_finalizer.py,
test_qualification_verdict.py, tools/qualify/test_bundle.py,
tests/phase2/test_runner_composition.py; frontend ControlPanel.captureFailure and
transcriptKeys. Existing WP16 scratch plugin only relocates paths, not assertions.
