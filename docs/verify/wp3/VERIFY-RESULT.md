# WP3 fresh-context verification — FAIL

Inspected branch `mvpfix/wp3-capture-guards` at
`fb73b30e4a6b7d02ed11e5481643cca7d319edb9`; initially clean tracked and untracked
status. Fresh session read VERIFY.md, COMMON.md, WP3 brief, execution plan §§1–2,
IMPLEMENTATION.md, and prototype NOTES.md. No prior-session memory was used.

## F1 — Literal verification failed

Command (cwd = this worktree):
```sh
bash evidence/mvpfix/wp3/verify.sh > evidence/mvpfix/wp3/fresh-verification.log 2>&1
```
Exit 1. Imported package resolved inside this worktree. Python: **450 passed,
2 failed, 19 subtests passed, 1 warning, 13.04 s** (expected 452 passed).
Both failures: `tests/phase2/test_pre_stop_terminal_boundary.py::test_late_stop_has_same_refusal_for_distinct_prior_endings`,
parameters `lease_expiry` and `explicit_abort`. Both fail before lifecycle assertions:
`SqliteRuntimeError: Refusing SQLite runtime 3.50.4; exactly 3.53.4 is required.`
The shell's `set -e` prevented subsequent checks. Original failure log retained unchanged.

Diagnostic command:
```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/evidence/mvpfix/wp3/tmp" /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=evidence/mvpfix/wp3/tmp/isolated tests/phase2/test_pre_stop_terminal_boundary.py > evidence/mvpfix/wp3/fresh-isolated.log 2>&1
```
Exit 0: **2 passed, 1 warning, 1.26 s**. Failure is order-dependent; exact state
contamination cause remains unresolved. Existing phase2 conftest adapts the runtime
pin for semantic tests. That fixture, failing test file, and production phase2.py
are unchanged from base 37979e53. No SQLite assertion or lifecycle test was weakened;
no shared interpreter was modified. Isolated success does not overturn FAIL.

## F2 — Remaining checks completed separately

```sh
{ sed -n '1,8p' evidence/mvpfix/wp3/verify.sh; sed -n '11,$p' evidence/mvpfix/wp3/verify.sh; } | bash > evidence/mvpfix/wp3/fresh-remaining.log 2>&1
TMPDIR="$PWD/evidence/mvpfix/wp3/tmp" npm --prefix frontend test -- --run > evidence/mvpfix/wp3/fresh-frontend.log 2>&1
```
Both exit 0. Frontend: **25 files passed, 215 tests passed, duration 2.80 s**,
including all nine new F4 behavior cases. Typecheck exit 0. Build exit 0, **67 ms**;
bundled assets match committed assets (`git diff --exit-code`). Python/JavaScript
attended-kit syntax PASS. `git diff --check` exit 0. No separate wall-clock timing
was captured for typecheck/syntax or the complete shell command. Nonfatal warnings:
Starlette/httpx deprecation, Vite future native-loader compatibility, Node localstorage.

## F3 — Independent falsifier inspection

- Zero/silent: mixer renders `silent` frames as zeros; live adapter and terminal
  finalizer bypass model calls for exact-zero PCM. Eight new guard tests passed in
  the literal suite; zero/silent fixtures assert no words/speakers and no runner call.
  Signed one-bit nonzero inputs reach the live adapter runner. This is decode-boundary
  coverage, not proof that every tiny capture signal survives existing browser silence
  gating or mono mixer quantization; those existing policies remain unchanged.
- F4: synchronous chooser invocation is inside try. Shared graph-construction catch
  disconnects partial nodes and stops newly acquired tracks; Reset releases existing
  lanes. Source/worklet failure, replacement, chooser throw, denial/cancel recovery
  covered by nine passing frontend cases. Prior restored-defect 7/9 failures are
  retained historical evidence, not rerun in this session.
- F5: v2 sample-rate rejection precedes mutation/acceptance. HTTP test passed:
  8000 Hz -> 400 with identical before/after v2 snapshot; valid 16000 Hz -> 200.
- Telemetry: observe_capture_span returns statistics and never edits PCM;
  leak_suppression is always false. Exact-copy test still selects decode. Snapshot
  stores latest committed span only. Protocol explicitly marks physical AEC unmeasured.
- Base-to-inspected-SHA source diff preserves QUALITY_BOUNDS, readiness, identity,
  nine-key frame contract and existing lifecycle checks. Speech-stub fixture PCM
  changed to nonzero without weakening assertions. Existing lifecycle tests were run,
  but the two order-dependent failures prevent claiming full suite acceptance.

## F4 — Prototype verdict read from NOTES.md; not repeated

Question: distinguish empty audio and playback leakage without losing quiet speech?
Zero guard accepted; leakage suppression REJECTED. Experimental threshold >=99%
explained energy is not shipped as policy.

| Population | Spans | Candidate skip/suspect | False suppress | False pass |
|---|---:|---:|---:|---:|
| Digital zero | 1 | 1 | 0 | 0 |
| Noise only | 2 | 0 | 0 | n/a |
| Echo only, 60 s | 36 | 12 | n/a | 24 |
| Near speech -10/-15/-20 dB, 60 s | 108 | 0 | 0 | n/a |
| Near speech, 0.5 s | 12960 | 80 | 80 | n/a |
| Echo only, 0.5 s | 4320 | 669 | n/a | 3651 |

False suppress here means nonzero local signal, not necessarily intelligible words.
Targeted lane-alone decodes contained 1/2/1 words; mixtures already lost those words.
Thus signal separation is falsified, not additional guard-induced intelligible-word loss.
Recorded prototype: 147 full spans, 17640 half-second spans, 52 real requests total;
45 main requests took 87.369362 s. Main 27/27 mixed spans unchanged by candidate;
ordered near-reference word error rate 0.627586–1.565517. Statistic-cost artifact:
1000 x 8000 samples, mean 0.2270089 ms, p95 0.2528381 ms, max 1.2317500 ms.
These are retained measurements, not fresh reruns.

## F5 — Limits and deviations

Fresh-session deviation: after literal command failed, ran remaining checks separately
and isolated the two failed cases. No production/test/harness changes. PASS remains
blocked pending resolution of combined-suite order dependence, then literal rerun.
Earlier implementation deviations remain as recorded in IMPLEMENTATION.md: guard at
decode boundaries preserves accounting; failed leak prototype uses telemetry-only
fallback; deterministic LOGIC output instead of TUI; initial pre-pick pytest scratch
outside worktree. This session used only worktree-local scratch/output.
P4 remains open. Physical speakers/microphone/acoustic echo cancellation (AEC) require
an attended operator and actual hardware using the supplied protocol. No physical
capture, real model request, prototype rerun, tunnel, background server, service change,
other-worktree edit, push, merge, deployment, or external publication in this session.
WP1 integration must preserve silent-to-zero rendering for separate lane decoders;
other WPs, integrated runtime, deployment and full product remain unqualified here.

Raw captured logs contain pytest trailing whitespace and a frontend trailing blank
line: staged whitespace check reports these; logs intentionally preserved verbatim.

## F6 — Lead-requested follow-up (same session)

Overall verdict remains **FAIL**. Starting point for review edits: `cf866016`
(initial verification record), production base inspected `fb73b30e`. This is a
same-session follow-up, not a second `/new` verification.

All four lead requests addressed:
1. Production correlation measured before edits over 300 x 8000-sample real-speech
   chunks: process CPU median/max **440/5121 microseconds**. After edits, enabled
   **447/4581 us**, disabled **1/17 us**, each 300 chunks. Inputs cycle 120 distinct
   retained-corpus chunks, represented as mixer lists; cost includes conversion.
   Bench command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <COMMON venv-python> prototypes/streaming-diarization/capture-guards/cost.py`
   (add `--correlation` for enabled). Full state/times in correlation-cost-*.json.
   Default mixer only evaluates exact-zero decisions; no FFT, snapshot.capture_guard
   null. Constructor/registry flag or process env `MOSS_CAPTURE_CORRELATION=1` opts
   in. Standalone attended scorer explicitly enables correlation. Suppression absent.
2. HTTP regression now asserts exact 400 detail and before/after lane next_sequence,
   accepted_samples, accounted_samples, retained_samples; also runtime
   next_frame_sequence and accepted_samples. Rejected frame leaves each at zero;
   subsequent valid frames reach lane sequence 2 / accepted_samples 4. Tested with
   correlation both off and on.
3. One signed nonzero sample among 7999 zeros still reaches the runner (two cases).
   IMPLEMENTATION.md explicitly states current mixed-span guard and WP1's required
   per-lane rolling/terminal exact-zero guard. No claim of capture-level quiet-audio
   preservation through pre-existing silence marking/quantization.
4. WER audited, annotated in NOTES.md and reference-audit.json: 960000 samples /
   16000 Hz = 60 seconds for each retained clip; reference ranges 0–60 seconds.
   Source sends len(x), not 24 seconds. Quiet baselines 9/145 = 0.062069 WER;
   27 mixtures 91–227/145 = 0.627586–1.565517 against near-only reference, so playback
   words also incur errors. No source/reference duration mismatch found. Actual
   wire duration cannot be independently recovered because request WAVs were not
   retained. No new model requests; suppression experiment not repeated.

Follow-up exact checks:
```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/evidence/mvpfix/wp3/tmp" /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=evidence/mvpfix/wp3/tmp/review-targeted tests/test_live_capture_guard.py tests/phase2/test_owner_bound_live_meeting.py -k 'capture_guard or nonzero or opt_in' > evidence/mvpfix/wp3/review-targeted.log 2>&1
bash evidence/mvpfix/wp3/verify.sh > evidence/mvpfix/wp3/review-verification.log 2>&1
{ sed -n '1,8p' evidence/mvpfix/wp3/verify.sh; sed -n '10,$p' evidence/mvpfix/wp3/verify.sh; } | bash > evidence/mvpfix/wp3/review-remaining.log 2>&1
```
Targeted: **14 passed, 62 deselected, 1 warning, 1.37 s**, exit 0.
Final literal Python: **455 passed, 2 failed, 19 subtests passed, 1 warning,
13.19 s**, exit 1. Includes both touched phase2 files and all new WP3 cases.
Failures are the same two SQLite/runtime-pin failures in F1; no new failure.
Remaining checks: **25 frontend files, 215 passed, 2.59 s**; typecheck exit 0;
build exit 0 (**92 ms**); bundled assets unchanged; attended Python/JS syntax PASS;
working diff whitespace check exit 0. Raw logs retain tool-generated whitespace.
All logs force-added. No changes outside worktree, shared services, deployment,
push/merge, physical capture, or decoder requests. CPU benchmark is the only new
prototype measurement authorized in the lead follow-up. P4 and WP1 integration
boundaries remain as F5. Fixing the unresolved test-order interaction is still
required before claiming the literal combined verification passes.
