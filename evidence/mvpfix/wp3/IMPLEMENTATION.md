# WP3 implementation and evidence

Branch `mvpfix/wp3-capture-guards`, base `37979e539f04d4ea740a1a94d021cd3bb894a0e2`.
F5 cherry-pick `3d831f36` -> `b7695017`; no conflict. Pre-pick qualification suite 198/198.
Prototype verdict: `../../../prototypes/streaming-diarization/capture-guards/NOTES.md`.

## Change
- Exact-zero model bypass in bounded live adapter and terminal finalizer. Mixer already
  zeroes fully `silent` frames; retain timeline/accounting instead of dropping ingress.
- Aligned per-span playback explained energy, delay and gain in mixer diagnostics and
  `/snapshot.capture_guard` (latest committed span). Decisions are decode/skip-zero only.
  Failed prototype means no leak classifier/suppression. Correlation telemetry is now
  explicitly opt-in via MOSS_CAPTURE_CORRELATION=1 (default off). No readiness changes.
- Chooser invocation stays synchronous, now inside try. Shared graph construction owns
  acquired tracks; source/worklet failures release partial nodes and stop acquired media.
  Reset releases existing lanes. Active replacement failure preserves prior capture.
- Attended kit + protocol; physical recording NOT run. Kit syntax checked only.

## Validation
Commands are in `verify.sh`; run from this worktree, PYTHONPATH=., no bytecode/cache.
- `python-test.log`: 361 passed + 19 subtests, 11.51 s.
- `runtime-test.log`: 91 passed, 4.52 s. Total 452 tests + 19 subtests.
- `frontend-test.log`: 25 files, 215 tests passed; includes 9 adapted F4 behaviours.
- `typecheck.log`, `build.log`: exit 0; bundled assets rebuilt.
- `frontend-restored-defects.log`: original F4 restored -> 7 failed/2 passed, one unhandled
  synchronous-error report. Fixed source restored in finally; proves regression sensitivity.
- `statistic-cost.json`: 1000 x 8000 samples; mean 0.2270 ms, p95 0.2528 ms, max 1.2318 ms.
- Prototype: 147 full spans + 17640 half-second spans; 52 real requests total, serial.
  45 main successful requests took 87.369362 s; six targeted calls plus one initial call
  whose scoring failed. No private transcripts, credentials, or audio retained in git.

## Failed attempts and adjudication
`decoder-attempt1.log`: after one real request, scoring incorrectly expected parser.segments.
Parser returns a list; corrected before 45-call run. No provider retry.
`python-attempt1.log`: 13 failed/348 passed. Three errors in new tests (keyword-only
constructor and wrapped exception type) fixed. Six existing adapter cases and four
owner/terminal cases used exact-zero PCM while requiring a stub to speak. The new exact-zero
contract makes those inputs invalid for their runner/lifecycle purpose. Changed only those
runner test calls and the owner-suite speech-frame helper to nonzero PCM; assertions unchanged.
New explicit-zero and silent tests enforce 0 words, 0 speakers, no model call. Low-bit
positive/negative tests prove quiet nonzero audio still reaches the runner.
`guard-attempt2.log`: eight new guard tests passed.

## Limits / deviations
- Implementation guard lives at shared decode boundaries, not by dropping transport frames:
  ingress dropping would break sequence/timeline accounting. Terminal path must also bypass.
  WP1 must keep silent-to-zero semantics when decoding retained lane PCM separately.
  RunnerBoundedWavInference currently guards the MIXED span. WP1 must apply the same
  exact-zero guard independently to each lane, in rolling and terminal decode; the
  guard must never trigger on nonzero PCM. Tests cover one nonzero signed sample
  among 7999 zeros as well as uniform low-bit PCM. Existing mixer quantization and
  browser silent marking are separate from this decode-boundary guarantee.
- COMMON's failed-prototype stop is applied to leak suppression; WP3 explicitly directs
  telemetry-only fallback and independent zero/F4/F5 work. No physical echo claim.
- LOGIC prototype uses deterministic full-state corpus output instead of interactive TUI.
  Scripts absorbed into standing bench; threshold never imported into production.
- Snapshot retains latest span only, disappears on teardown; attended kit retains all blocks.
- Initial 198-test pre-pick run used pytest's default OS temporary directory (deviation from
  literal only-worktree writes). Later tests use this tree's ignored tmp directory.
  No other worktree source edits, shared-service changes, pushes/merges/deploy/GitHub writes.
- Only own 18103 tunnel started, now stopped. No attended server/browser recording started.

Fresh `/new` verification is still required; see root VERIFY.md. Do not call this qualified
for physical microphones, deployment, or the integrated WP1 per-lane runtime.


## Lead review follow-up

- Correlation flag flows through mixer registry; process env MOSS_CAPTURE_CORRELATION=1
  opts in at route attachment. Default path only computes exact-zero decisions and
  keeps snapshot.capture_guard null. Enabled telemetry never changes PCM or suppresses.
- 300 real-speech chunks x 8000 samples: before CPU median/max 440/5121 us; enabled
  447/4581 us; disabled 1/17 us. See correlation-cost-*.json and bench NOTES.md.
- HTTP regression asserts exact 400 detail, unchanged lane sequence/accepted/accounted/
  retained counters and runtime sequence/accepted samples, then valid-frame advancement.
- WER audit: both corpus clips/reference ranges cover 60 seconds, not 24. Quiet baselines
  9/145 edits (0.062069); 27 mixtures 91–227/145 (0.627586–1.565517) against near-only
  text, including errors caused by playback words. Request duration is source-derived;
  request WAVs were not retained. reference-audit.json records exact denominators.
- Initial fresh verification failed 2/452 cases in combined execution; same two pass
  standalone. Unresolved existing SQLite fixture/order interaction; not repaired by
  bypassing runtime enforcement. VERIFY-RESULT.md retains initial and follow-up counts.
