# WP28 commands / failure decisions

Working directory is always MOSS-Transcribe-Diarize-wt-wp28-file-resolver-perf.
Python executable: ../MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python.
Environment: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR=$PWD/.wp28runtime/tmp.
No new decoder calls, tunnel or shared service operation.

- `python -c 'import moss_transcribe_diarize as m; print(m.__file__)'`:
  wrong editable import stops all measurement; observed own worktree.
- `python prototypes/streaming-diarization/wp28-file-resolver-perf/probe.py`:
  baseline counts / stage costs / duplicate intervals, on retained WP19 3/15 windows.
  Select only the dominant removable cost; full results remain in ignored scratch.
- `WP28_WORKERS=2 python prototypes/streaming-diarization/wp28-file-resolver-perf/parallel_prototype.py --arm parallel-2 --minutes 6`;
  repeat with 4 workers for 6 and 30 minutes. Any full serialized output mismatch
  rejects candidate. Sequential runs, no overlapping benchmark load from this WP.
- Full Python / frontend commands and fresh pass are recorded in verify.sh once
  prototype and production gates pass. A regression blocks commit/verification.

Initial read attempted speaker_identity.py at package root; actual path is app/.
No runtime failure inferred. Existing node_modules symlink created inside own
worktree; use Vite runner config loader to avoid writes to shared dependencies.

Production:
- `python prototypes/streaming-diarization/wp28-file-resolver-perf/probe.py --arm production`:
  measures default file composition against baseline raw bytes; changed output
  rejects production even if the earlier monkeypatched prototype passed.
- `python -m pytest -q -p no:cacheprovider tests/test_file_resolver_performance.py tests/test_speaker_identity_provider.py tests/test_file_identity_album.py tests/test_live_identity_album.py tests/test_live_identity_sweep.py`:
  focused fake/failure/order/provider/album coverage; first run 126 passed, 2 real
  fixtures skipped (enabled in the full gate).
- `bash prototypes/streaming-diarization/wp28-file-resolver-perf/suites.sh initial`:
  ENTIRE Python suite with real WP28 tests enabled, entire frontend suite, diff and
  verification-layout checks. Test-only scratch plugin redirects existing fixed
  /tmp/socket paths to own tree; no production/test assertion monkeypatches.
  Failures block handoff; keep exact failing output before repair.

Full gate recovery (after missing parent diagnosis):
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. WP28_REAL_FIXTURES=$PWD/.wp28runtime TMPDIR=$PWD/.wp28runtime/tmp <python> -m pytest -q -x -ra -p no:cacheprovider -p evidence.mvpfix.wp28.local_scratch --basetemp=runs/wp28/tests tests`.
`-x` was diagnostic: the accepted run must complete all tests with no failure.
The frontend command is independent and ran after the performance benchmarks.
