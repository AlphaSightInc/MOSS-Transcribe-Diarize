# WP29 fresh-context verification

Start in a NEW Codex session via `/new` in the same pane. Read and execute this file
without the implementation conversation. Modify only this worktree. No push, merge,
deploy, GitHub, shared services, GPU calls, or other worktrees. All processes you start
must exit. The original briefs are COMMON.md then WP29-tape-exhaustion.md under
`/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/`.

## 1. Resolve code and interpreter

```sh
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp29-tape-exhaustion
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/.wp29/t"
mkdir -p "$TMPDIR"
git branch --show-current
git rev-parse HEAD
git status --short
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -c 'import moss_transcribe_diarize as m; print(m.__file__)'
```
Expected branch `mvpfix/wp29-tape-exhaustion`, clean starting tree, import inside this
worktree. Record starting SHA. Wrong branch/import falsifies all subsequent results.

## 2. Execute complete suites, preserving output and exit status

Use the environment above for every Python command.

```sh
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests > evidence/mvpfix/wp29/fresh-python.txt 2>&1
npm --prefix frontend test -- --run > evidence/mvpfix/wp29/fresh-frontend.txt 2>&1
npm --prefix frontend run typecheck > evidence/mvpfix/wp29/fresh-typecheck.txt 2>&1
npm --prefix frontend run build > evidence/mvpfix/wp29/fresh-build.txt 2>&1
```
Expected: Python 1,932 passed / 2 skipped / 37 subtests; frontend 265 passed / 28 files;
typecheck/build exit 0; no generated asset difference. Read the logs for actual counts.
Failure is not a pass. If the pre-existing unsynchronized scheduler test fails, inspect
its exact failure and `prototypes/streaming-diarization/tape-exhaustion/NOTES.md`;
report it explicitly and rerun that one test, not silently replacing the full-run result.
The full regression includes eight HTTP scenarios (nine meetings): normal Stop,
accepted Stop then departure, pre-Stop lease expiry, silent mic, each lane alone,
mixed-only exhaustion and two concurrent sessions. Tests use portable synthetic PCM;
retained standalone evidence used public real speech. Five lower-level cases cover
all/one/no lane gaps and all-zero refusal. UI test covers notice and partial download.

## 3. Audit retained measurements (no repeat model run needed)

```sh
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/streaming-diarization/tape-exhaustion/audit.py > evidence/mvpfix/wp29/fresh-audit.json
```
Expected 9/9 exhaustion sessions and 2/2 ten-minute RSS sessions. Read the exact RSS
numbers printed, including second-minus-first. This is current process RSS, not peak;
the same runtime/ONNX encoder survives both sessions. HTTP/MP3 are excluded from the
RSS bench, so this does not certify the previous real-service absolute footprint.
Falsifiers: lost committed failed-lane words; false complete audio or wrong 60 s duration;
generic `failed` after capacity exhaustion; missing gap accounting/notice; nonempty
terminal queues/tapes or armed leases; saved/reopened disagreement. Before-Stop client
departure MUST remain interrupted. All-zero no-transcript is a named refusal, not a defect.

## 4. Record, commit locally, report

Review `git diff --check` on source/tests/docs and confirm frontend assets unchanged.
Write `docs/verify/wp29/VERIFY-RESULT.md`: fresh-session declaration, tested SHA,
commands/exit statuses/exact counts, audit numbers, failures and limits. Commit this
result and fresh logs locally; report final SHA and clean status. No approval needed.

Then give the user the <=60-line report IN THIS PANE: branch/final SHA; prototype
question/verdict; changed files; exact test counts including failures; nine-session
outcomes and RSS; remaining limits/deviations. Read NOTES.md's measured RSS verdict
and preserve its qualification. Do not imply deployment or real ASR accuracy was tested.
