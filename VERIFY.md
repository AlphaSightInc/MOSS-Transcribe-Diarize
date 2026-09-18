# WP3 fresh-context verification — execute literally after `/new`

This is the user's WP3 execution assignment; verification/report still outstanding.
First `cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp3-capture-guards`.
Modify only this worktree. No push, merge, deploy, GitHub, shared service, other worktree,
model requests, microphone capture, or background server. Do not repeat the prototype.
Read the original COMMON then WP3 briefs at:
`/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/COMMON.md`
`/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/WP3-capture-guards.md`.
Read `evidence/mvpfix/wp3/IMPLEMENTATION.md` and
`prototypes/streaming-diarization/capture-guards/NOTES.md` for claim boundaries.

## Verify
1. Confirm branch `mvpfix/wp3-capture-guards`, current SHA, initially clean tracked state.
2. Run `bash evidence/mvpfix/wp3/verify.sh > evidence/mvpfix/wp3/fresh-verification.log 2>&1`.
   This checks imported checkout, zero/silent bypass, quiet signal admission, F4 media cleanup,
   rate rejection/no sequence advance, runtime/lifecycle accounting, frontend behaviour,
   typecheck/build, stable bundled assets and kit syntax. A failure blocks PASS; inspect and
   fix only WP3-owned issues, retain failed log, rerun affected checks. Never weaken assertions.
   Expected Python: 452 passed, 19 subtests. Frontend: 25 files, 215 passed.
   Expected typecheck/build/syntax exit 0; rebuilt assets match committed assets.
3. Independently inspect the relevant source/tests for these falsifiers:
   a. zero or fully silent fixture reaches a model; or low-bit nonzero audio gets discarded;
   b. leaked acquired track after source/worklet failure and Reset; sync chooser throw escapes;
   c. 8000-Hz frame accepted by 16000-Hz service or advances lane sequence;
   d. telemetry suppresses leakage or claims physical AEC qualification;
   e. changed QUALITY_BOUNDS/readiness/identity policy, nine frame keys or lifecycle checks.
   Test fixtures intentionally changed from zero to nonzero only where asking a stub to
   produce speech. Restored original F4 defects failed 7/9 new tests; source restored.
4. Write `VERIFY-RESULT.md`: fresh-context pass/fail, exact command/counts/timing, inspected
   SHA, limits/failures. Commit result + fresh log locally (run tests before commit as above).
   Logs are globally ignored: use `git add -f evidence/mvpfix/wp3/fresh-verification.log`.
5. Report in this pane, <=60 lines: branch/final SHA; prototype verdict; changed files;
   exact tests/measurements; remaining P4/physical unmeasured, integration boundary; deviations.
   Include no claims that the other WPs, real microphones, deployment or full product passed.

## Already completed
F5 cherry-pick `b7695017`; zero guards + reporting-only signal telemetry; F4 fixes + nine
behaviour cases; rebuilt frontend; attended recorder/scorer + protocol; numeric evidence.
Prototype: 0/108 full-span quiet cases flagged, but 80/12960 half-second quiet spans flagged.
Targeted lane-alone decode contained 1/2/1 words; mixed audio already lost those words.
Leak suppression rejected. 52 real requests total; own tunnel stopped. No physical capture.
See IMPLEMENTATION.md for all failed attempts and deviations, including initial default
pytest scratch directory outside worktree. No external publication permitted.

Memory navigation in prior context used MEMORY.md:587-588 only, no unverified historical
claim. If reporting its use, append one memory citation with those lines and empty rollout_ids.
