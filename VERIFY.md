# WP4 fresh-context verification — user-authorized execution

You are the NEW session in tmux MOSS:3.4. Do not use the previous context.
First cd to `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp4-oracles-n1`.
Only modify this worktree. No push, merge, GitHub, deploy or shared-service changes.
Read this file and the repo AGENTS.md. The implementation has already been committed.
Read COMMON.md and WP4-oracles-n1-summaries.md under
`/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/` for scope.

## Execute literally

From the WP4 root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python evidence/mvpfix/wp4/verify_offline.py
```

Allow about 2 minutes; poll and report progress. This runs the full Phase-2 suite,
F6 separately, full frontend suite, typecheck, build, and both deterministic bench
reproducers. Logs go to `evidence/mvpfix/wp4/fresh/`. Expected: **805 Phase-2 tests,
2 F6 tests, 209 frontend tests** pass; typecheck/build exit 0; all script checks true.
Import must resolve into this worktree, not the borrowed Python environment's tree.
The frontend node_modules symlink is authorized; Vite caches stay in this worktree.

Then:
- Inspect fresh logs/counts and `git diff --check`; generated assets should be unchanged.
- Independently inspect the relevant code/tests if a claim or failure is uncertain.
- Write `VERIFY-RESULT.md`: actual fresh-session provenance, exact counts/exit codes,
  overall offline PASS/FAIL, and the live limitations below. Do not call live acceptance PASS.
- If tests fail, diagnose/fix within scope and repeat relevant checks; record all attempts.
- Commit the result and fresh numeric/test evidence locally (no private transcripts/audio).
- Report in this pane, <=60 lines: branch/SHA, corrected prototype verdict, changes,
  counts, measurements, limitations and deviations. This is the final WP4 report.

## Falsifiers and retained limits

Oracle must accept the documented overlap with **0 duplicates** and reject injected
playback with **5 duplicates**. Counts-only G7 evidence must now fail. F6 assertions
and its original clock remain unchanged. Exports: real TypeScript renderer controls
accept 5/5 and corrupt downloads reject 5/5; retained actual browser downloads from
the real saved meeting also pass 5/5. No private download bytes are retained.
N1: 8 bench cases => 7 failed with safe reasons, 1 confirmed speechless completed
empty with notice. Tests also verify URL 403/404/timeout, User-Agent, persistence,
owner isolation, malformed output rejection and UI display.

The live run did NOT satisfy the requested positive/negative ladder:
- Alternation completed: final/reopened system WER **11/106**, mic **6/48**;
  pre-terminal **16/106**, **16/48**. Final lexical attribution and duplication
  witnesses: **2 each**. Existing QUALITY_BOUNDS were used unchanged, not relaxed.
- Overlap interrupted at the enforced **40 total decoder-call cap**. Recovered
  failure snapshot: mic WER **1.0**, zero mic words. This is INCONCLUSIVE as a
  completed semantic negative control, not an expected-failure PASS.
- At most two calls permitted concurrently; no extra decoder budget remains.
  Do NOT restart any service/tunnel or make more decoder calls in verification.
- No OpenRouter key found in permitted environment/operator shell files. Flash Lite
  wiring tested locally; the 50 s/180 s paid functional check is BLOCKED. Paid calls: 0.
- G7 real attendance was not scripted or claimed. Lexical ownership of legacy
  speaker IDs is inferred, not acoustic identity proof. Shared-vocabulary playback
  alone is outside the lane-unique duplication witness.

Known failed attempts are retained: initial raw shared-word predicate, malformed
heartbeat before any audio, fixture failures in the first two full suites, and the
budget-interrupted overlap. Read `evidence/mvpfix/wp4/STATUS.md` for their disposition.
All processes started for measurements have been stopped. User-data staging under
`.wp4runtime` is disposable, ignored and never committed.
