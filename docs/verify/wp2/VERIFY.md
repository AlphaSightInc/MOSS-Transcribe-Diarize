# WP2 fresh-context verification (after /new)

User explicitly requires a fresh session in pane MOSS:3.2. This is the remaining execution assignment, not a new research/design task. Read this file in a new context and execute literally; do not rely on the previous agent's results. Modify nothing outside this worktree. No pushes, merges, GitHub, deployment, shared services, decoder calls or extra agents.

Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp2-lane-consumers`
Expected branch: `mvpfix/wp2-lane-consumers`; base `37979e53`.
Question: do published overlapping lane segments survive persistence, history, UI/search/rename, all exports, and summary input while legacy remains usable?
Contract: order committed before provisional → start → system before microphone → end; preserve each speaker/lane, no cross-lane merging; no shifted subtitle times. Two speakers per lane can share a person's display name/voiceprint across lanes. No SQLite migration needed: schema v2 stores arbitrary JSON exactly.

## Execute
Always cwd = this worktree. Python must resolve this checkout; otherwise STOP verification and report the import mismatch.

```sh
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp2-lane-consumers
git branch --show-current
git rev-parse HEAD
git status --short
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -c 'import moss_transcribe_diarize as m; print(m.__file__)'
```

Read `docs/design-lane-consumers.md`, `frontend/src/lib/laneConsumers.test.ts`, and `tests/phase2/test_lane_consumer_store.py` to inspect what is actually checked. Run these commands separately and retain exit status and timings. They detect respectively consumer regressions; type/interface mismatch; unbuildable/stale shipped assets; persistence/lifecycle/geometry/sentinel regressions; corpus-field loss through the actual data paths. On failure, record it; fix only a proven WP2 defect and rerun affected checks. Do not weaken requirements or sentinels.

```sh
npm --prefix frontend test -- --run --configLoader native --cache=false > evidence/mvpfix/wp2/fresh-frontend.log 2>&1
npm --prefix frontend run typecheck > evidence/mvpfix/wp2/fresh-typecheck.log 2>&1
npm --prefix frontend run build -- --configLoader native > evidence/mvpfix/wp2/fresh-build.log 2>&1
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python evidence/mvpfix/wp2/run_python_checks.py > evidence/mvpfix/wp2/fresh-python.log 2>&1
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python evidence/mvpfix/wp2/consumer_probe.py > evidence/mvpfix/wp2/fresh-consumer.log 2>&1
git diff --check
```

Expected: 218/218 frontend tests in 25 files; typecheck/build exit 0; 48/48 Python tests, no skips; probe tagged 9 rows/9 lanes/4 speaker IDs and legacy 5 rows/0 lanes/2 IDs. Probe includes full state; input/readback order and text must agree, not just counts. Public corpus fixture is committed; no private transcript/audio. Probe reads the two public source reference.jsonl files, writes only own worktree. SQLite tests override exact-runtime check in the existing conftest (host 3.50.4 vs production 3.53.4); no production runtime claim. Runner changes only test socket paths to short relative addresses under this worktree.

Inspect `production-390.png` and `production-1280.png` in evidence/mvpfix/wp2 using view_image. Verify lane labels/readability; no human visual acceptance claim. Check `git diff --name-only 37979e53` and confirm no protected upstream/quality/identity/frame/lifecycle/sentinel files changed. Confirm rebuild leaves tracked bundle unchanged; if changed, report/reconcile before acceptance. No processes from these synchronous probes should remain.

Falsifiers: dropped/merged words, lane or canonical ID loss; wrong tie order; rename affects another ID; clipping overlapping cue times; shared-person enrollment treated as conflict; legacy failures; layout overflow; altered protected sentinel or constants. A count-only success does not override a failing assertion.

## Record and report
Write `VERIFY-RESULT.md`: fresh context provenance, verified implementation SHA, pass/fail, exact counts/timings and commands, remaining limits/deviations. Commit this file plus fresh evidence locally; final SHA should be clean. Only then final report <=60 lines in this pane: branch/final SHA, prototype question/verdict, changed files, exact tests/measurements, unresolved/blocked items and deviations. Include earlier failures/deviations from evidence/mvpfix/wp2/NOTES.md (initial shared Vite cache/temp sockets; corrected isolation; runtime limitation). No further /new needed after this verification.
