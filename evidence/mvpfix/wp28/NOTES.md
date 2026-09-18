# WP28 evidence

Base: d49fc50a (WP26 integrated); branch mvpfix/wp28-file-resolver-perf.
All writes confined to own worktree. Import custody verified before measurement.

Q1 / I1 / F1: profile file resolver; preserve every interval, vector, ordered
aggregation, ordered album update and byte of serialized identity output.
No policy/threshold, readiness, lifecycle, frame or sentinel changes authorized.

Source: WP19's retained `real-6` and `real-30` audio/decode directories, copied
read-only into ignored `.wp28runtime`. Same WP16 alternating public one-minute
Ackman/Keyu Jin clips, 3 actual voices; 3/15 windows, 150 s window / 120 s stride.
The long fixture repeats two clips. This tests cost and exact equality, not wider
speaker accuracy, deployment performance or concurrent-file capacity.

Baseline measurements in baseline-{6,30}.json; original results remain in ignored
scratch. Fixture files retain boundaries, local labels, and baseline diagnostics,
but substitute synthetic `window-N-segment-M` text for every transcript string.
Thus committed regression oracles contain no original speech text or audio.

Prototype and production accepted; measurements below. Full-suite/fresh results
are recorded separately. Failures and deviations are retained below.

Duplicate qualification: `duplicate_intervals` in initial profile means exact
same path/start/end within a window: 0 for both. Offline comparison of rounded
absolute sample boundaries in the retained fixtures finds 1/107 and 14/575 exact
repeats across overlapping windows. No caching used; overlapping observation
weight and complete evidence remain unchanged. Later probe reports both counts.
ONNX/features stage durations in parallel runs are summed worker seconds (can
exceed elapsed time). `embedding` and `resolver` are elapsed wall time.
`process_peak_rss_bytes` is the macOS process high-water mark, not current memory.

## Production verdict

Accepted: complete result byte equality 2/2 real fixtures; all input evidence and
ordered album decisions retained. Performance is wall-time reduction; acoustic
work count is unchanged. Two real fixtures are enabled in the full suite.

| Stage (seconds) | 3 windows before | 3 after | 15 before | 15 after |
| --- | ---: | ---: | ---: | ---: |
| Resolver wall | 60.177873 | 18.085652 | 313.204362 | 92.432865 |
| Embedding wall | 59.837990 | 17.724491 | 311.669349 | 90.883597 |
| ONNX worker sum | 59.470240 | 61.316699 | 310.204913 | 319.853234 |
| Features worker sum | 0.320968 | 0.434046 | 1.225561 | 2.059606 |
| Audio read | 0.040512 | 0.036199 | 0.209409 | 0.189333 |
| Asset hash | 0.301497 | 0.306585 | 1.484475 | 1.496670 |
| Session creation | 0.034622 | 0.035918 | 0.028200 | 0.028767 |
| Album / other residual wall | 0.003764 | 0.018658 | 0.022337 | 0.023831 |

The residual includes matching, admissions, sweep, Python dispatch and contract
construction; it is not a separately isolated album-only measurement. Parallel
worker sums overlap in wall time; do not add them to derive elapsed time.

| Population | 3 windows | 15 windows |
| --- | ---: | ---: |
| Embedding calls | 9 | 45 |
| Intervals / ONNX calls | 107 | 575 |
| Embedded audio seconds | 391.32 | 2059.98 |
| Sessions created | 1 | 1 |
| Same-window repeats | 0 | 0 |
| Exact absolute repeats | 1 | 14 |

6 minutes: 110 window-local segments; speedup 3.327x; wall-time reduction 69.95%.

30 minutes: 590 window-local segments; speedup 3.388x; wall-time reduction 70.49%.

Production peak RSS 1,431,027,712 bytes (cumulative process peak across both runs).
No new model session, cache, speech cap, threshold, feature flag or policy added.
The constructor scheduling argument defaults to one and is not a manifest/CLI
option. Only file album composition requests four workers.

## Failed attempts retained

Initial full-suite launcher omitted `mkdir -p runs/wp28` before providing
`--basetemp=runs/wp28/tests`. Installed pytest creates the final directory with
`parents=False`; early tmp_path fixtures therefore errored until a later socket
fixture incidentally created the parent. Stopped that run (SIGINT did not end it,
then SIGTERM to the owned pytest PID); its progress-only log is retained. A first
`-x` diagnostic used another basename after the parent existed, so no recurrence;
stopped it after it passed the affected prefix. Exact invocation rerun uses `-x`
and the original basename; it must finish the ENTIRE suite before gate acceptance.
No completed-suite counts claimed for either interrupted run.

Controlled reproduction: missing parent `runs/wp28-missing-parent/tests`, exactly
one test (`tests/phase2/test_acceptance_setup.py::test_shipped_template_declares_every_measurement_content_boundary`)
-> 1 setup error, FileNotFoundError at pathlib.mkdir. Retained traceback:
`initial/missing-parent-reproduction.txt`. This is test-launcher setup, not an
identity/product defect. Fixed launcher creates its parent before pytest. No
assertions or production behavior changed to make the suite pass.

Exact full rerun stopped at a real test-double mismatch: 1 failed / 1402 passed /
1 skipped / 6 subtests in 265.91 s. `tests/test_live_provider_bundle.py` replaces
the adapter with `_FakeWeSpeakerAdapter`; its constructor did not accept the new
`interval_workers` keyword. Real constructor now explicitly supports that
execution-only argument, defaulting to one. Updated the fake's signature AND
asserted `interval_workers == 1`, preserving/strengthening the live serial
contract. No existing semantic assertion removed. Failure log retained as
`initial/full-fake-constructor-failure.txt`. Both new real-fixture tests had passed
before this later test. Entire suite rerun required, no failure waived.

## Initial full gate — PASS

Final corrected complete invocation (`suites.sh initial`): Python 1929 passed,
2 skipped, 37 subtests, 21 dependency/deprecation warnings, 259.40 s. Skips are
existing operator-owned real-identity and real F-cert corpora, not WP28 fixtures.
Both WP28 real 6/30-minute equality regressions PASS (enabled explicitly).
Frontend: 250 passed / 28 files, 2.59 s. Focused initial 126 passed / 2 optional
real skips; constructor-focused repair 54 passed / 2 optional real skips.
Whitespace and verification-layout checks PASS. All failures above are resolved;
none waived. No frontend source/assets changed, so no asset rebuild needed.

Verification docs use `docs/verify/wp28/` per repository layout. LOGIC prototype
was a scripted reproducible CPU experiment, not an interactive TUI; full per-window
state retained in JSON. Temporary candidate implementation absorbed then deleted.
No transcript text/audio committed; no push/merge/deploy/GitHub, service restart,
shared port use, or decoder request (0/300). Reads from prior WP fixtures only.
Fresh `/new` verification is still pending and is not claimed by this initial gate.
