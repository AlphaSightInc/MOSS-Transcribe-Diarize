# WP15 fresh-context verification

Start in this exact worktree; modify no other checkout:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp15-stop-lease-longrun`
Expected branch: `mvpfix/wp15-stop-lease-longrun`. No push/merge/rebase/deploy/GitHub.
This file is the fresh verification instruction, not a prior-verdict authority.

## Contract and falsifiers

Question: can a helper lease interrupt an accepted Stop? Acceptance is witnessed
by the real runtime's `stop_requested` event. Capture closes first; helper failure
coordination is released before awaiting raw Stop. Other teardown is unchanged.
Browser sends one final heartbeat then stops; polling does not hold a lease.
Deadline bounds the caller wait, not the server work. Genuine terminal decoding
failure must stay explicit, preserve committed words, and save a non-final surface.

Inspect `live_transport.py` change, ADR-0004 addendum, and regression/bench code.
Falsifiers: accepted Stop interrupted by late helper activity; caller cancellation
kills server drain; deadline 0 misreports final; failed refinement loses committed
words; SQLite restart changes the saved document; pre-acceptance expiry/explicit
abort or refused/unconsumed Stop changes behavior. Existing full suite covers the
latter lifecycle boundaries. Report any gap; do not manufacture a pass.

## Run literally (from this worktree)

Use this Python throughout:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`
Set `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.` and `TMPDIR="$PWD/.wp15/t"`.
Prescribed frontend/node_modules symlink already exists; do not npm install.

1. `git branch --show-current`, `git rev-parse HEAD`, `git status --short`.
   Verify source import resolves inside this worktree:
   `python -c 'import moss_transcribe_diarize as m; print(m.__file__)'`.
   Wrong tree/source means stop verification and report, not a test pass.
2. `python -m pytest -q -p no:cacheprovider tests`
   Save output as `evidence/mvpfix/wp15/fresh-python-full.txt`.
   Expected: 1860 passed, 2 skipped, 37 subtests. Any failure requires adjudication.
3. `npm --prefix frontend test -- --run`
   Save as `evidence/mvpfix/wp15/fresh-frontend-full.txt`.
   Expected 27 files / 242 tests passed.
4. `npm --prefix frontend run typecheck` and `npm --prefix frontend run build`.
   Save each output to fresh-frontend-typecheck.txt / fresh-frontend-build.txt
   inside evidence/mvpfix/wp15. Both must exit 0; assets should remain identical.
5. `python prototypes/stop-lease/run.py --delay 90 --output evidence/mvpfix/wp15/fresh-prototype.json`
   Save stdout/stderr as `evidence/mvpfix/wp15/fresh-prototype.txt`.
   Expected 8/8; simulated lease time, not measured inference latency.
6. Read `wall-drain-45.json`, `wall-terminal-90.json`, `gpu-preflight.json`,
   `REAL-DECODER.md` and `longrun-prepared.txt` in evidence/mvpfix/wp15.
   Confirm measured versus UNMEASURED claims: wall controls final/completed,
   45.088459 / 90.096846 s total experiment time; three saved words each.
   Real 600 s and 1800 s have NOT run. Stop-to-final, saved words, MP3 duration,
   RSS plateau and tape bound durability for those durations are UNMEASURED.
   COMMON permits 200 total decoder requests. A question requesting 3000 was sent
   but no answer received before reset; no larger budget may be inferred.
   Run no inference as part of fresh verification unless a new explicit instruction
   authorizes it. Prepared runner alone proves no long-run behavior.
7. Full Python suite rewrites evidence/mvpfix/wp2/production-1280.png. Restore only
   that generated screenshot with `git show HEAD:evidence/mvpfix/wp2/production-1280.png > evidence/mvpfix/wp2/production-1280.png`.
   Existing suite fixtures create and remove short /tmp sockets; all WP15 scratch
   stays in .wp15. No authored file outside this worktree was modified.
   `git diff --check`; confirm no owned 18115/17875 listener, no probe process.

## Finish

Write `VERIFY-RESULT.md`: actual fresh source SHA, pass/fail, exact counts/timings,
findings, and explicit real-decoder UNMEASURED limitation. Do not call WP15's
long-meeting durability accepted. Commit verification evidence and result locally.
Write <=60-line `evidence/mvpfix/wp15/REPORT.md`, then report in this pane with
branch + final SHA, prototype verdict, files changed, tests, measurements,
remaining/blocked and deviations. The final pane report must be self-contained.
Do not send keys/messages to Fable or another pane. This is the assigned WP15 pane.
