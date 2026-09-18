# WP22 fresh verification — Parts A/B only

First cd `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp22-memory-longrun`.
Modify nothing outside it. Branch must be `mvpfix/wp22-memory-longrun`.
Read this file literally after `/new`; no parent conversation needed. Do not merge,
push, deploy, call GitHub, open tunnels, or use GPU. Part C awaits the user's explicit
WP12 confirmation AND WP12 present in this branch. Prepared runner is not a real run.

## Environment and source

Use `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`
as `python` below (a shell variable is fine). Export `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONPATH=.`, `TMPDIR="$PWD/.wp22/t"`, `NPM_CONFIG_CACHE="$PWD/.wp22/npm-cache"`.
The prescribed frontend/node_modules symlink exists. Do not install packages.

1. Record current session ID, branch, HEAD and status. Verify import source:
   `python -c 'import moss_transcribe_diarize as m; print(m.__file__)'`.
   It must resolve here. Read `evidence/mvpfix/wp22/SCOPE.md`,
   `prototypes/streaming-diarization/memory-longrun/NOTES.md`, and the production diff
   `git diff 8938cb2c HEAD -- moss_transcribe_diarize`.
   Expected production change: only disable ONNX speaker encoder memory patterns.
   CPU provider, threading, model, features, thresholds and retention values unchanged.

## Execute, retain exact output

2. `python -m pytest -q -p no:cacheprovider --basetemp=.wp22/pytest-fresh tests`
   → `evidence/mvpfix/wp22/fresh-python.txt`.
   Expected 1,890 passed, 2 skipped, 37 subtests. Read every failure. A prior 30 ms
   helper-lease fixture expired during its setup under concurrent load; it uses stub
   Identity and never reaches the edited encoder. Baseline and final rerun passed.
   Do not silently tolerate a fresh failure or modify lifecycle policy to pass it.
3. `npm --prefix frontend test -- --run` → `fresh-frontend.txt` in the same directory.
   Expected 244 tests / 27 files. Then `npm --prefix frontend run typecheck` and
   `npm --prefix frontend run build` → `fresh-typecheck.txt`, `fresh-build.txt`.
   Expected exit 0; generated assets unchanged.
4. `python prototypes/streaming-diarization/memory-longrun/summarize.py`
   → `evidence/mvpfix/wp22/fresh-profile-summary.txt`.
   This independently reads all three 30-minute profiles, requires 5/15/30-minute
   checkpoints and post-terminal release, checks all 28,800,000 samples committed,
   all tapes/pending PCM empty after Stop, and EXACT before/after per-lane content.
   It also checks the supplemental HTTP/SQLite meeting completed with an empty queue.
   Missing checkpoints, changed transcript, or retained PCM falsifies acceptance.
5. `python prototypes/streaming-diarization/memory-longrun/onnx_memory.py --arena production --varying --output evidence/mvpfix/wp22/fresh-production-varying.json`
   → `evidence/mvpfix/wp22/fresh-production-varying.txt`.
   This uses the production ONNX constructor, not an options override. Compare
   `.wp22/vectors-production-varying.npy` against `.wp22/vectors-on-varying.npy`
   using `numpy.array_equal` and max absolute difference. Require 80/80 exact and
   max difference 0; retain comparison and current RSS/elapsed figures in
   `evidence/mvpfix/wp22/fresh-vector-comparison.json`. Do not use a universal RSS
   threshold; machine residency varies. Report actual evidence and limitations.
6. Read the original `arena-comparison.json`: the long-segment stress case and the
   varying-length case both preserve vectors; disabling arena/shrinking did not help.
   Read `regression-red.txt`, `focused-final.txt`, `python-before.txt`,
   `python-after.txt`, `python-final.txt`, and `part-c-prepared.txt`.
   The 30-minute profiles use the existing five-minute tape bound: terminal refinement
   is expected to report unavailable/failed after capacity exhaustion, while canonical coverage
   remains complete and tapes release. R1 is a pre-existing missing `gaps` argument on exhausted lane tapes; read
   `tape-refusal-defect.txt`. It is not fixed by WP22. This is NOT 30-minute real-decoder durability.
   The benchmark keeps the closed runtime reachable; exit is not its release proof.

## Finish

7. Stop any process started by this verification; leave no listener/tunnel/probe.
   Full suites can regenerate evidence/mvpfix/wp2/production-1280.png; restore only
   that generated file from HEAD if changed. Normalize trailing spaces/blank EOF in
   newly captured text logs. `git diff --check`; inspect status and changed assets.
8. Write `docs/verify/wp22/VERIFY-RESULT.md`: fresh session ID/source SHA, pass/fail,
   exact counts, findings and limitations. Do not call it fresh if `/new` did not occur.
   Update `evidence/mvpfix/wp22/REPORT.md` (<=60 lines), commit verification/results
   locally, then final answer in this pane (<=60 lines): branch + final SHA, prototype
   question/verdict, changed files, exact tests, measurements, remaining Part C and
   deviations. No message to any other pane is authorized.
