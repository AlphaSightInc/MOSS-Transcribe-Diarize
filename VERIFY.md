# WP1 fresh-context verification

This is the final verification stage of the user's WP1 execution assignment.
First cd `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp1-lane-decode`.
Modify nothing outside this worktree. Do not push, merge, deploy, write GitHub,
message other panes, or touch shared services. Read this file literally and finish
with VERIFY-RESULT.md, a local commit, then a <=60-line report in this pane.
Do not repeat prototype/provider runs: 646/650 requests consumed; no further ASR
requests are authorized by this verification recipe. All task servers are stopped.

The prior session should have entered `/new` in the assigned pane %20 (MOSS:3.1).
`.wp1/new-pane.txt` and `.wp1/new-dispatch.json` retain the transition evidence.
If this is not actually a fresh chat after `/new`, say so and do not claim that bar.
Do not use /compact, /fork, or a subagent as a substitute.

## Read

Read in order:
1. `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/COMMON.md`
2. `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/WP1-lane-decode.md`
3. `docs/design-lane-decode.md` and the final sections of `prototypes/lane-decode-proto/NOTES.md`.
The user superseded COMMON's 200-request cap with 650, <=2 in flight,
single-meeting load, queue check before batches and tunnel shutdown during pauses.
That work is complete; this session verifies and reports, not restarts execution.

## Execute

Use this interpreter, always from this worktree:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`
with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:prototypes/lane-decode-proto`.

1. Record `git branch --show-current`, `git rev-parse HEAD`, `git status --short`.
   Expected branch `mvpfix/wp1-lane-decode`, clean tree before verification outputs.
   Production commits: 2cb9d014 and 644833ee. Later commits are bench/evidence.
   Verify imports for `moss_transcribe_diarize`,
   `moss_transcribe_diarize.app.live_lane_decode` and
   `moss_transcribe_diarize.live_service_replay` resolve inside this worktree,
   not a prototype overlay or the editable venv's other checkout.
2. Run the full suite with this exact test-location adapter (keeps temporary
   sockets in the worktree without changing test assertions):
   ```sh
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:prototypes/lane-decode-proto TMPDIR="$PWD/.wp1/test-tmp" /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider -p pytest_local tests --basetemp=.wp1/pytest-fresh > evidence/mvpfix/wp1/fresh-full-tests.txt 2>&1
   ```
   Expected: 1718 passed, 3 failed, 2 skipped, 37 subtests passed. Expected failures:
   - `test_staging_dry_run_deletes_nothing[True]` and `[False]`: fixture is under
     the protected checkout; unchanged staging code correctly excludes it.
   - `test_name_latency_is_independent_of_observer_polling_delay`: known WP4 HTML
     fixture missing the Meeting history / Voiceprints tab.
   Do not call the full suite green. A new failure must be reported distinctly.
   Earlier cold isolated `decode_failed` Stop test sometimes returned 202 within
   its 2-second deadline; retain and disclose any recurrence, don't change bounds.
3. Run:
   ```sh
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/lane-decode-proto/audit_evidence.py > evidence/mvpfix/wp1/fresh-evidence-audit.txt
   ```
   Expected: 646 unique request IDs 1..646, max concurrency 1, 26/26 raw saved/final
   text+identity matches, 17/17 resumed/fixed falsifier runs, 6 fixed-build cases,
   3 E2E scripts passing, 99 individual fixed 2.5-second decodes (median
   0.14452375000109896 s, max 1.133293874998344 s). This audit reads retained raw
   public-corpus surfaces from ignored scratch, not only the claims in scores.json.
   Failure-state evidence must preserve system's original crossing segment and
   apply 2 microphone revision windows. Read saved WER edits in scores.json;
   omissions include unplayed full-reference audio. Native persisted source_lane
   is not claimed; WP2 owns that consumer.
4. Run `git diff --check` and confirm no listeners on local ports 17871 / 18101
   with `lsof -nP -iTCP:<port> -sTCP:LISTEN`. Empty output/exit 1 is expected.
   Do not kill unknown processes. Check source diff from 37979e53: no numeric
   QUALITY_BOUNDS/identity/readiness changes, nine-key wire untouched, mixed
   recording unchanged. New fields are additive; replay retains them.
5. Write `VERIFY-RESULT.md`: fresh-context provenance, tested SHA, exact counts,
   PASS/FAIL of lane/replay/evidence checks, and the full-suite exceptions. Read
   `evidence/mvpfix/wp1/full-tests-final.txt` for comparison. Include deviations:
   - fixed-build coverage six cases; full final-SHA 11-case ladder not rerun under
     650 cap (noise/48s alternation/Stop/two-voice reshare/system -15 have prototype
     evidence); final E2Es pass after production absorption;
   - E2E lifecycle concurrent case omitted for single-meeting limit; demo 20 s;
   - saved lane scores use exact final/saved positional correspondence;
   - initial suite temp sockets used existing tests' hardcoded /tmp paths before
     local redirect adapter was added; subsequent test runs redirected them.
6. Commit ONLY VERIFY-RESULT.md and fresh verification logs locally. Then report
   <=60 lines in this pane: branch + final SHA, prototype question/verdict, changed
   files, exact test/E2E counts, measured saved word/vocabulary/edit counts and
   timing/request costs, limits/remaining failures/deviations. No recommendation
   of numeric acceptance, no claim of complete final-SHA ladder or green full suite.

## Falsifiers

Wrong import tree; dropped source fields in replay; cross-lane identity collapse;
zero-lane decoding; failed lane erased while healthy revision advances; mismatched
saved/final evidence; request cap/concurrency mismatch; non-additive policy change.
An expected fixture/environment failure is not an architectural falsifier, but
still makes the full-suite result FAIL and must be reported as such.
