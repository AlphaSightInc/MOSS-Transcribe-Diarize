# WP22 fresh verification — A/B and completed Part C

First cd `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp22-memory-longrun`.
Modify nothing outside it. Branch `mvpfix/wp22-memory-longrun`. Execute this file after
an actual `/new` in own pane MOSS:3.3 (%21); do not use a subshell as a fresh session.
Parent thread was `01a0b339-0f54-7d82-9cc9-f119bc04f5c3`; record a different session ID.
No further merge, push, deploy, GitHub, tunnel, or GPU call. No other-pane messaging.
The authorized real run is COMPLETE, not a prepared runner: 1080/2600 requests used.

## Environment/source

Use `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`
as `python` below. Export `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=.`,
`TMPDIR="$PWD/.wp22/t"`, `NPM_CONFIG_CACHE="$PWD/.wp22/npm-cache"`. No package installs.
Keep scratch/vector/audio/SQLite under the existing ignored `.wp22/`; no audio in git.

1. Record session ID, branch, HEAD, status and import source:
   `python -c 'import moss_transcribe_diarize as m; print(m.__file__)'` must resolve here.
   Read `evidence/mvpfix/wp22/SCOPE.md`, memory-longrun `NOTES.md`, draft `REPORT.md`.
   `git merge-base --is-ancestor 1745b96f HEAD` must succeed: WP12 was merged before C.
   `git diff 1745b96f HEAD -- moss_transcribe_diarize` must contain only WP22's four
   ONNX constructor lines (memory patterns disabled). CPU provider, threads, model,
   features, thresholds and retention values unchanged. Source for C: a28eecd9.

## Execute and retain exact output

2. `python -m pytest -q -p no:cacheprovider --basetemp=.wp22/pytest-fresh tests`
   → `evidence/mvpfix/wp22/fresh-python.txt`; expected 1911 passed, 2 skipped,
   37 subtests. No unresolved failure is acceptable. A prior 30 ms helper-lease
   fixture expired during setup under load (uses stub Identity, not edited encoder);
   baseline and both merged full suites passed unchanged. Preserve failed attempts.
3. `npm --prefix frontend test -- --run` → `fresh-frontend.txt` in that directory;
   expected 249 tests / 28 files. Then `npm --prefix frontend run typecheck` and
   `npm --prefix frontend run build` → `fresh-typecheck.txt`, `fresh-build.txt`.
   Expected exit 0, unchanged generated assets. Frontend may run alongside Python;
   wait for full Python to finish before the CPU-heavy ONNX experiment below.
4. `python prototypes/streaming-diarization/memory-longrun/summarize.py`
   → `evidence/mvpfix/wp22/fresh-profile-summary.txt`. Requires all three 30-minute
   profiles' checkpoints, all 28,800,000 samples committed and all tapes/PCM empty
   after Stop; requires EXACT 1440-segment before/after content and completed HTTP
   supplement. Missing data, changed words or retained PCM falsifies these claims.
5. `python prototypes/streaming-diarization/memory-longrun/audit_real.py evidence/mvpfix/wp22/real-1789715856876413000`
   → `evidence/mvpfix/wp22/fresh-real-audit.json`. Compare parsed JSON exactly with
   the run's committed `audit.json`. This reopens retained SQLite, compares exact
   words with terminal snapshot, probes MP3, checks 7200 frames / 28,800,000 samples,
   1080 requests / peak two, no pauses, and all three complete tapes released.
   Expect final/completed, 6269 words, MP3 1800 s, Stop→final 101.697916 s,
   tapes 172800000→0 bytes, contention 36/65 samples. No new real session.
6. `python prototypes/streaming-diarization/memory-longrun/onnx_memory.py --arena production --varying --output evidence/mvpfix/wp22/fresh-production-varying.json`
   → `evidence/mvpfix/wp22/fresh-production-varying.txt`. Actual production constructor,
   no options override. Compare `.wp22/vectors-production-varying.npy` with
   `.wp22/vectors-on-varying.npy` using numpy.array_equal and max absolute difference.
   Require 80/80 exact and max difference 0; retain comparison/current RSS/timing in
   `fresh-vector-comparison.json`. No universal RSS threshold: report actual values.
7. Read `arena-comparison.json`, `regression-red.txt`, `focused-final.txt`,
   `python-before.txt`, `python-after.txt`, `python-final.txt`, merged/post-real suite
   logs. Post-real full gates: 1911/2/37 (158.29 s), frontend 249/28, typecheck/build 0.
   Main GPU-free profiles used the existing five-minute tape cap; R1 is the existing
   missing keyword-only `gaps` on exhausted lane tapes (generic failed finalization).
   Canonical content survives and tapes release. The real run's larger tape did not
   exhaust. R1 remains open; do not call the stub profiles successful refinement.
   R2: late real capture approximately flat (932/981/973 MiB near 5/15/30 minutes),
   but post-final RSS 1149 MiB vs 616 at startup / 902 after 30 s. Full return near
   startup and repeated/four-session safety are NOT demonstrated. Native retention
   reduction and one-session durability pass their measured claims, not every memory
   aspiration. 56 system segments unattributed; mic's last segment ends 299.88 s.
   Saved equality is not human word/speaker accuracy. No identity-policy tuning.

## Finish

8. Leave no processes started by verification. Confirm no listener on 18122/17882;
   parent already stopped both. Full tests may rewrite WP2 production-1280.png;
   restore only that generated file from HEAD if changed. Normalize new text logs'
   trailing whitespace. `git diff --check`, inspect status and generated assets.
9. Write `docs/verify/wp22/VERIFY-RESULT.md`: actual new session ID, inspected SHA,
   exact results, scoped pass/fail, R1/R2 and limitations. Update draft
   `evidence/mvpfix/wp22/REPORT.md` (<=60 lines), commit locally. Report in this pane
   (<=60 lines): branch/final SHA, prototype verdict, files, counts, measurements,
   limits/deviations. No other-pane message. Do not rerun `/new` again on completion.
