# WP35 fresh verification — Stop-time drain on the per-lane build

Execute this file literally, in a **new** shell with no prior context:
`bash --noprofile --norc`, started from `/`. First
`cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp35-stop-drain`
and modify nothing outside it. Branch `mvpfix/wp35-stop-drain`.

**No GPU and no network are needed and none may be used.** The real 4×300 confirmation is
COMPLETE (549 of the 800-request budget, retained under `evidence/mvpfix/wp35/`); do not open
a tunnel, do not start a stack, do not touch ports 7861/7862, do not re-run the campaign.
No push, merge, rebase, PR, deploy or GitHub call.

## Environment

Use `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`
as `python`. Export `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPATH=.`. No package installs; do
not `npm install` (`frontend/node_modules` is already a symlink).

1. Record branch, `git rev-parse HEAD`, `git status --short` (expect a clean tree) and
   `python -c 'import moss_transcribe_diarize as m; print(m.__file__)'` — it must resolve
   **inside this worktree**. Expected HEAD at hand-off: `d2044f33` or a later commit on this
   branch that only adds `docs/verify/wp35/**` and `prototypes/stop-drain/NOTES.md`.

## What the change is, and what must still be true

2. `git diff integration/mvp-fix-20260917 HEAD -- moss_transcribe_diarize` must touch exactly
   two files and nothing else:
   - `app/live_service_runtime.py`: `_finish_stop` now ends rolling **before** the drain when
     `_terminal_supersedes_rolling_locked` holds (a finalizer, a retained tape and a
     converger — the same preconditions `_begin_terminal_locked` checks), plus that new
     predicate. The later `state.terminal_plan = state.coordinator.stop_rolling()` call is
     unchanged and idempotent.
   - `concurrency_evidence.py`: `prestop_inference_projection` counts a `not_awaited` rolling
     completion as a closed admission and skips it as compute.
   Falsifier: any change to `QUALITY_BOUNDS`, identity policy values, readiness thresholds,
   lease seconds, the Stop deadline, `max_queue_depth`, the nine-key frame protocol, the
   two-Refresh sentinel, or any other bound or timeout. Check with
   `git diff integration/mvp-fix-20260917 HEAD -- moss_transcribe_diarize | grep -nE '^[-+].*(QUALITY_BOUNDS|max_queue_depth|lease|deadline|threshold|min_match|birth_min|hard_cap|max_retained|frame_samples)'`
   — expect no output.

## Suites (full, not a subset)

3. `python -m pytest -q -p no:cacheprovider tests`
   → expect **1974 passed, 5 skipped, 37 subtests passed**, zero failures. The measured
   baseline on this branch without the change is 1966 passed / 5 skipped / 37 subtests, so
   the delta is exactly the 7 new `tests/test_live_stop_drain.py` cases and the 1 new case in
   `tests/phase2/test_acceptance_stop_pending.py`. Any failure falsifies the change.
4. `npm --prefix frontend test -- --run` → expect **28 files, 271 tests, all passing**.
   `npm --prefix frontend run typecheck` and `npm --prefix frontend run build` → exit 0, and
   `git status --short` must stay clean (no frontend change was needed, so
   `moss_transcribe_diarize/app/frontend_assets/*` must not move).

## The behaviour itself

5. Red/green, to prove the new tests actually bind. The change is committed, so put the file
   back to its pre-WP35 content rather than stashing (a stash of a clean tree is a no-op and
   would silently report green as red):
   `git checkout integration/mvp-fix-20260917 -- moss_transcribe_diarize/app/live_service_runtime.py`
   — this branch changed no other commit in that file, so this is exactly the fix reverted.
   Then `python -m pytest -q -p no:cacheprovider tests/test_live_stop_drain.py`
   → expect **3 failed, 4 passed**: `..._decodes_no_rolling_window_after_stop`,
   `..._never_mutates_the_surface_after_stop` and
   `..._four_concurrent_stops_all_reach_final_with_no_post_stop_rolling` fail; the two
   "unchanged behaviour" guards, the WP15 accepted-Stop guard and the §7.4 accounting guard
   pass either way. Then
   `git checkout HEAD -- moss_transcribe_diarize/app/live_service_runtime.py` and re-run
   → **7 passed**, and `git status --short` empty.

## Measurements (read the retained evidence; do not re-measure)

6. Stub bench, `evidence/mvpfix/wp35/stub-{1,4}x600-{before,after}.json`. Read
   `max_stop_to_outcome_seconds`, `decoder_requests_after_first_stop`, `all_final` and each
   session's `rolling_admitted_after_stop`, `terminal_started`, `accepted_samples`,
   `accounted_samples`, `words_at_stop_request`, `words_at_final`. Expected:
   - 1×600: before 4.314 s to final, 1 rolling request after Stop → after 3.710 s, 0.
   - 4×600: before **no session final** (all four hit the 600 s cap, `finalization_status`
     `not_started`, `stop_error` `LiveServiceStopPending`), **143** rolling requests after the
     first Stop, `terminal_started` false 4/4 → after **final 4/4** at
     5.518 / 5.544 / 8.537 / 8.544 s, **0** rolling admitted after Stop, `terminal_started`
     true 4/4.
   - In every arm `accepted_samples == accounted_samples == 9_600_000` and `words_at_final`
     is 960: nothing acknowledged was lost by cancelling the superseded work.
   Falsifier: an after arm with a rolling window admitted after Stop, a session not `final`,
   or fewer words at final than before.
7. Real run: `python prototypes/stop-drain/rescore.py evidence/mvpfix/wp35/real-4x300-after`
   (offline, no decoder calls). Expect `decoder_calls` 549, `maximum_own_inflight` 2,
   `foreign_load_detected` false, `clean_rescored` true, pre-Stop `rtf` 0.0804…, and per
   session: `final`, Stop→final 32.443 / 18.325 / 35.355 / 29.247 s,
   `accepted_samples == accounted_samples == 4_800_000`, 1200 acknowledged frames,
   `rolling_admitted_after_stop` **0**, one `not_awaited` completion, `terminal_started` true.
   `clean_as_run` is false and `excluded_failures` names
   `inference_evidence:rolling completion has a non-healthy terminal outcome` — that is the
   pre-repair scoring of the run and is the reason step 2's second file exists.
8. Confirm the budget and the isolation from the retained log:
   `wc -l evidence/mvpfix/wp35/real-4x300-after/decoder.jsonl` → 1098 (549 start + 549 finish),
   and `python -c "import json;rows=[json.loads(l) for l in open('evidence/mvpfix/wp35/real-4x300-after/decoder.jsonl')];print(max(r['active'] for r in rows), sum(r['kind']=='start' for r in rows))"`
   → `2 549`.

## Known limits to restate, not to fix

- 4×600 on the real decoder was **not** run: 1,060 requests > the 800 budget. 4×300 costs 549
  and keeps the four near-simultaneous Stops, but does not confirm the absolute Stop→final at
  600 s nor the campaign's 90 s bar at that length.
- The stub bench replaces the WeSpeaker forward pass with a deterministic stand-in
  (`--real-voiceprints` keeps the real one) and prices a whole 600 s terminal lane at 3.0 s,
  so its Stop→final is a lower bound on the real one by construction.
- Per-session WER in the real run is not comparable to `QUALITY_BOUNDS`: each session loops a
  50–180 s clip to fill 300 s and session 4's reference is partial.

## Finish

9. Leave no process running: no tunnel, no stack, nothing on 18135 or 17835. Confirm with
   `lsof -nP -iTCP:18135 -sTCP:LISTEN` and `lsof -nP -iTCP:17835 -sTCP:LISTEN` (both empty).
   Other agents' processes (WP30 on 17890/18130) are not yours — leave them alone.
10. Write `docs/verify/wp35/VERIFY-RESULT.md`: the new session's own identity, the SHA
    inspected, every command's exact pass/fail denominator, each falsifier's verdict, and any
    deviation. Commit locally on this branch. Do not push.
