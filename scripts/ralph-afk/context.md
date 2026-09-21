# Context - MOSS round 4, ralph run C

## Ground

- Repo: `/Users/gao/Documents/Codex/2026-09-20/moss-round4/candidate` — branch `round4/ralph-b` (base = `round4/integration`
  after the round-4 merges: run A + six pane branches; the lead merges this branch back afterwards).
- **D27 (user decision on the fixture correction): YES** — adopt the corrected reference/cut for the acceptance arm and
  ladder; only class-(d) edits may change; the three class-(a) decoder additions must remain visible. Candidate 4 is in
  scope. **Canonical text of D27 and D28 (verbatim question + answer):**
  `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/moss-mvp-review/grilling-decisions-20260920-addendum.md`
  — read it before acting on either; it also records that the **pre-terminal** arms stay UNMEASURED and are not closed
  by D27.
- Read before editing: `AGENTS.md`; `prototypes/batch-startup/NOTES.md` (§Minimal production seams, §Controls run B must
  carry); `prototypes/gap/NOTES.md` (§Proposed remedy — design only); `evidence/round4/overlap/attribution.md` and
  `evidence/round4/overlap-review/second-opinion.md` (if D27 = YES); `docs/adr/0002-*`, `docs/design-streaming-diarization.md`
  §7 (settled identity architecture — extend, don't re-litigate).
- Key code paths and why they matter:
  - **A3 seams** (from 3.3's prototype, all verified at base): `moss_transcribe_diarize/app/phase2_file.py:105-141,162-211,332-417`
    — `FileMeetingTasks`; the normalised local source + checkpoint must move to a Meeting-keyed durable directory after
    Meeting creation; URL acquisition retained locally; owner/source/checkpoint validated; the real checkpoint passed at
    `:417` (today `"checkpoint_dir": None`); removal only after durable terminal truth; `file-work` transient root stays
    separate (`clear_transient_work` `:139-141`). `phase2.py:1927-1941` `lifespan` — invoke the File retained-work
    claim/resume **before** `recover_active_meetings` (`:1934`), keep `clear_transient_work()` (`:1941`) after recovery.
    `phase2.py:716-749` `_recover_active_file_meetings` — stays the fallback for unclaimed/invalid/non-resumable rows
    (they finish `interrupted`); if claimed rows become terminal-owned first, no skip list is needed. `phase2.py:751-763`
    `_assert_no_active_meetings` — **unchanged**. `phase2_lifecycle.py:215-236` — apply the same File claim before the
    account-scoped recovery caller (do not call it "after login": base has no real login caller, only account revoke).
    `windowed_transcription.py:197-255` — checkpoint validation/wiring already sufficient.
  - **Gap seams** (from 3.1's diagnosis): `live_transcript_convergence.py:1015-1071` — retain the terminal-local label
    after overlap resolution instead of discarding it from the proposal; `live_lane_decode.py:236 finalize_lanes`,
    `:278-308` — replace the isolated per-segment fallback with one partition-scoped evidence decision (aggregate the
    partition's eligible intervals, one album match at 0.35/0.1, apply the canonical only within that partition), then
    project segments. Lead ruling: run B **may** edit `live_lane_decode.py` for this item only, with one violating
    control. Evidence floors: `live_identity_album.py:45-46,56-57`; `min_segment_samples` = 8,000 (0.5 s) from the manifest.
  - **Fixture seam** (D27): `tests/e2e/verify_demo_lanes.py:60-75` couples the audio cut to the coarse reference row;
    `:27 DEFAULT_MIC_GAIN = 0.03` unchanged; `tools/qualify/run.py:30 CASES`, `:452` ladder feed (24 s meetings).
    Corpus reference: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/interview_bill_ackman_60s/reference.jsonl`
    is the **dev tree's** copy — read-only; the candidate carries its own copy under `evidence/live-policy-sweep-20260825/`
    if the tests read it from the repo — check which path the test actually loads before editing.

## Current state

- **2026-09-21 ~04:00 — run D opened by the lead after an adversarial acceptance review of run C.**
  The review confirmed and this run must not regress: C2's narrowed startup assertion is safe (a Live row can never
  enter `claimed_file_meetings` — `claimed` is built only from `active_file_meetings`,
  `WHERE m.mode = 'file' AND m.status = 'active'` at `phase2.py:638`, and only for handles `claim_retained_work`
  accepted, `phase2_file.py:209-213`; `_assert_no_active_meetings` byte-identical and still used when nothing is
  claimed, `phase2.py:605-606`, `:624`; the exclusion is recomputed each boot and needs a fresh flock + manifest +
  checkpoint validation, so it cannot be defeated on a later boot); C3's deletion order and blast radius hold
  (`removal_statuses == ["interrupted"]`; `_remove_retained_work_dir` refuses any path whose
  `parent.parent != retained_root`, `phase2_file.py:585-589`); C4, C5, C6 (both invariants asserted against the real
  `app.router.lifespan_context`), C7 all hold; D13 holds
  (`test_lifespan_refuses_nonresumable_file_and_live_rows_without_dispatch`, `tests/phase2/test_retained_file_claim.py:726-753`);
  no orphaned background task — `file_tasks.stop()` runs in lifespan's `finally` before `store.close()`
  (`phase2.py:2086-2107`) and `_task_done` releases the flock; audio publication is still `asyncio.shield`-ed.
- **The defect this run closes (review F1, reproduced).** `_revoke_account` fences and terminalizes but never removes
  the owner directory: with no registered task `settle_fenced(())` removes nothing (`phase2_file.py:379-393`), and
  `_recover_active_file_meetings` only calls `recover_interrupted_file_audio` + `finish("interrupted")`
  (`phase2.py:765-769`). On later boots `active_file_meetings` joins `a.enabled = 1` (`phase2.py:637`), so a disabled
  account's row is never claimed, refused or reclaimed, and `clear_transient_work` touches only `_work_root`
  (`phase2_file.py:159-179`). Probe result: `owner_dir` still holds `['checkpoint', 'input.wav', 'owner.json']` after
  revoke, source bytes intact, still present after a second boot. **Run B's `assert not owner_dir.exists()` was removed
  with no successor** — the only unreplaced assertion deletion in run C's whole test diff.
- Smaller items the review named: **F2** `release_settled_account_fence` (`phase2_file.py:356-361`) and
  `resume_retained_work`'s `account=` parameter (`:205`) are now dead outside prototypes; **F3** `_complete`'s commit
  and publication arms changed `raise` → `return` for *both* modes (`:772-784`, `:807-819`), silently dropping the
  non-resumed path's quiesce signal; **F5** `_mark_failed` (`:668-673`) swallows `AccountRevoked` (`:603-606`) and does
  not guard other `handle.finish` failures, so a failed outcome write leaves the row `active` with only a log line;
  **F6** progress.txt iteration 4 cites a test file run C never touched.
- Reachability caveat recorded by the review, pre-existing since run B, not a run-C regression: because `_mark_failed`
  swallows `AccountRevoked`, a `finish` failure on an authority mismatch could in principle delete a still-`active`
  Meeting's retained dir. No reachable case was constructible (`finalize_account_revoke` requires zero active rows and
  `fence_account` cancels tasks first). If run D's work makes it reachable, stop and report.
- Lead's own verification of run C: backend **2,158 passed / 0 failed / 5 skipped / 2 xfailed**; exactly two XFAILs,
  both Jamie; frontend 312/312; typecheck clean; tree clean.

## Validation

```bash
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
# narrowest: the flipped controls
$PY -m pytest -q -p no:cacheprovider $(grep -rl "R4-5\|R4-3" tests/ | tr '\n' ' ')
# prototype cases as product tests (A3) and the gap replay
$PY -m pytest -q -p no:cacheprovider tests/phase2 -k "retained or resume or startup or recover"
$PY prototypes/gap/run.py
# widest (required before completion)
$PY -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run && npm --prefix frontend run typecheck
```

## Remaining candidates

**None.** C1--C7 are closed and the Run-C verifier records the required final
offline gates. Historical S17 and `capacity_2x1800` remain explicitly unmeasured
outside this PRD's offline scope.

## Iteration 1 outcome

- **C0 — context repair (complete):** this file said Run B had no remaining
  candidates although the active Run C PRD names C1-C7. The ranked queue above
  comes from that PRD and the Run C opening progress entry. No product code or
  acceptance claim changed.
- **Next:** C1. Locate every `resume_retained_work` and
  `release_settled_account_fence` caller, then make the existing revoked-account
  publication control assert no resume, no unfence, and no new transcript.

## Iteration 2 outcome

- **C1 / F1 (complete):** account revoke no longer resumes retained File work or releases its
  account fence. The corrected retained-prefix control was RED on the old path and is now green:
  no decoder dispatch, durable `interrupted` without a transcript, and the owner fence retained.
  The retained directory is deliberately not asserted here; C3 owns terminal directory reclamation.
- **Next:** C2 — move retained resume off the lifespan critical path and contain its failures.

## Iteration 3 outcome

- **C2 / F2 prototype (supported; product work remains):** C12 extended the existing
  batch-startup bench with real lifespan composition. A claimed retained File Meeting
  remained active while boot completed; an unclaimed active File Meeting reached
  `interrupted`; releasing one resumed window produced one completed publication; and a
  controlled resume failure became durable `failed/resume_failed`. Both retained
  directories were removed only after terminal truth. It used zero decoder, network,
  tunnel, or GPU requests. The bench uses the production checkpoint/window path but a
  SQLite 3.50.4 semantic-store allowance, so it is design evidence only.
- **Next:** implement the measured composition: make `FileMeetingTasks` return claimed
  retained ownership without joining it, exclude only those owners from generic File
  fallback and its zero-active check, and turn commit/publication/post-terminal-cleanup
  exceptions into durable Meeting outcomes without blocking lifespan.

## Iteration 4 outcome

- **C2 / F2 (complete):** valid retained File work is claimed in the background and
  represented only by its `(account, meeting)` owner pair. Generic recovery terminalizes
  all other File rows and every Live row; its new narrow assertion permits only that
  exact claimed set, leaving `_assert_no_active_meetings` byte-identical. The real
  lifespan serves while a resumed window is held. Commit, audio-publication, and
  post-terminal-cleanup mutants each stay inside the retained task and create visible
  `resume_failed` durable outcomes; the latter preserves completed transcript truth and
  marks review.
- **Next:** C3 — make refusal and URL-download cancellation remove only their own
  retained owner directories, and correct the existing retain-forever assertion.

## Iteration 5 outcome

- **C3 / F3 (complete):** startup retains only exact owners whose validation refused,
  then reclaims them only after the existing generic fallback has durably made that
  Meeting terminal. The corrected missing-URL-source control was RED before the product
  edit: `interrupted` still retained its owner directory. It now proves removal occurs
  after durable `interrupted` truth and preserves a sibling owner's marker. A new
  held URL-acquisition cancellation control proves the already-correct task-settlement
  path also removes only its terminal owner directory.
- **Next:** C4 — make retained-source recording failure terminalize its URL Meeting
  rather than leaving an active row without a task.

## Iteration 6 outcome

- **C4 / F5 (complete):** after a successful URL download, retained-source persistence now has the same durable
  `storage_failed` outcome as an ordinary source-storage failure. The focused product control was RED when that
  exception escaped the task; it is now green and proves no decoder dispatch, visible failure reason, terminal-owner
  cleanup, and sibling-owner preservation.
- **Next:** C6 — turn the batch bench's unique-segment/no-replay guarantee into product controls for both resume and
  mid-window crash.

## Iteration 7 outcome

- **C6 / F8 (complete):** the retained-URL resume and File mid-window-crash
  product controls now use the batch bench's 101-window geometry. Each asserts
  the replayed window's exact delegate calls and that the persisted transcript
  has exactly 101 distinct segment texts. The first RED exposed only a fixed
  seed assumption; the second showed the fixture placed every post-first segment
  in an overlap the product correctly discards. Moving its deterministic segment
  to the owned interior made the real persistence assertion reachable without
  changing product code or production windowing.
- **Next:** C7 — audit the Bill neighbouring boundary or document the overlap;
  preserve every scored text.

## Iteration 8 outcome

- **C7 / F9 (complete):** the only bad boundary was the second row's stale 29.0 s
  start. Existing retained transcripts place Lex's next utterance at 29.55--29.63 s;
  moving the coarse source boundary to the corrected preceding endpoint (29.25 s)
  removes the 0.25 s overlap without changing a word. The new full-row non-overlap
  control was RED on the old corpus and is green alongside all D27 controls.
- **Next:** C5 — make the Run-B verifier state what the deployed ladder actually
  scores, then make its remaining falsifier executable or remove it with cause.

## Iteration 9 outcome

- **C5 / F7 (complete):** the Run-B verifier now distinguishes the 29.25-second
  acceptance population from the standalone 24-second fixture. The latter belongs
  only to `test_r4_6_ladder_reference_is_bounded_by_captured_audio`; the deployed
  ladder reads no reference row and reports finalization plus non-accuracy
  unique-vocabulary retention. Its third falsifier now names the fixture's reachable
  captured-audio bound instead of an impossible ladder-score comparison.
- **Next:** write the Run-C verifier and run the required final offline gates.

## Iteration 10 outcome

- **Final certification (complete):** `docs/verify/round4-run-c/VERIFY.md` records
  C1--C7's durable-owner mental model, controls, falsifiers, and boundaries. The
  required backend gate passed **2,158 / 0 failed / 5 skipped / 2 xfailed / 37
  subtests** in 168.60 s; frontend passed **312/312** and typecheck is clean. No
  frontend source changed from `round4/integration`, so conditional build/asset parity
  is inapplicable. No decoder, network, tunnel, proxy, or GPU request was made.
- **Next:** acceptance bar met; the lead may integrate this branch. Do not turn the
  historical S17 or 2x1800 capacity limits into a false offline qualification.

## Non-candidates

- Jamie / lone-participant aggregation — FALSIFIED; user decision D1 vs D15 pending; no code.
- Any change to `tools/qualify/` (run A's territory) beyond consuming its preflight.
- Any threshold/floor/constant; Stop cap; separator; hidden-tab (needs an Aqua session — measurement, not product);
  runtime packaging (4.1's receipt + `MOSS_TEST_REAL_SQLITE` conftest guard are merged as-is; no pin change).
- `docs/known-limitations-20260918.md` — lead-owned; the lead rewrites L1/L9 rows after the round.
