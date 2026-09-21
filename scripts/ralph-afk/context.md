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

- **2026-09-21 ~03:00 — run C opened by the lead after an adversarial acceptance review of run B (HEAD `16fd908e`).**
  The review independently confirmed, and this run must not regress: `_assert_no_active_meetings` byte-identical to
  base and still reached from both entrypoints (`phase2.py:599`, `:617`); **no live-resume path** — the claim loop
  iterates only `active_file_meetings` (`WHERE m.mode = 'file' AND m.status = 'active'`, `phase2.py:626`) and live rows
  still go to `_recover_active_live_meetings` (D13 holds); ordering right — `resume_retained_work` at `phase2.py:1960`
  precedes `recover_active_meetings` (`:1961`) and `clear_transient_work()` (`:1968`), and the retained root is a
  *sibling* of `file-work` (`phase2_file.py:135`) so transient cleanup cannot reach it; every
  `_remove_terminal_work_dir` call site is preceded by a durable `finish(...)`/`_mark_failed(...)`; the gap remedy
  partitions by terminal-local label and writes back only to indices carrying that label
  (`live_lane_decode.py:279-341`), with both branches asserted (`tests/test_r4_gap_terminal_identity.py:113-121`,
  `:137-142`, and isolated-stays-unattributed at `:145-153`); no constant moved; the fixture rows are byte-equal to the
  audited proposal and the falsifier still shows exactly 3 additions, 102/105.
- **Findings this run closes** (all introduced by run B, none falsifying the three mandated behaviours):
  - **F1 → C1 (closed, iteration 2).** `_revoke_account` no longer releases its File-account fence or resumes
    retained work. The retained-prefix product control is RED against the prior behaviour (the fence is cleared before
    it can publish) and now proves `decoder.calls == []`, durable `("interrupted", None)`, and the retained fence after
    revocation. Existing owner-bound controls still prove ordinary in-flight and late File results cannot publish.
  - **F2 → C2 (closed, iteration 4).** Retained startup now claims valid `(account, meeting)` owners without joining
    their re-decode; generic File recovery and its active-row check exclude exactly those claims, while Live and
  `_assert_no_active_meetings` are unchanged. Held work permits startup and a 200 root response; injected retained
    commit or audio-publication failure becomes durable `failed/resume_failed`, and injected post-terminal cleanup
    failure stays `completed` with the same visible failure plus `needs_review`.
  - **F3 → C3.** When `_verified_retained_input` refuses work (`phase2_file.py:510-545`) nothing ever deletes
    `retained_root/<account>/<meeting>`: the Meeting is terminal so `active_file_meetings` never lists it again and
    `clear_transient_work` only touches `file-work` (`:155-177`). `tests/phase2/test_retained_file_claim.py:316`
    enshrines it with `assert owner_dir.exists()`. Same for a URL Meeting cancelled mid-download — the old
    `_remove_work_dir(staging_dir)` was deleted at `:611-612`, leaving an owner dir with no `owner.json`. Unbounded
    disk growth and raw user media retained past terminal truth.
  - **F5 → C4.** `_record_retained_source` at `phase2_file.py:619` is uncaught inside `_acquire_and_run`; an I/O
    failure right after a successful download leaves the URL Meeting `active` with no task until the next restart.
  - **F7 → C5.** `SYSTEM_LADDER_REFERENCE` (`tests/e2e/verify_demo_lanes.py:27`) has one consumer
    (`tests/test_round4_overlap_diagnosis.py:28`); the deployed ladder (`tools/qualify/run.py:583-596` → the external
    `ir_lane_ladder.py`) scores solo-lane vocabulary retention and reads no reference row, so VERIFY.md's claim and its
    falsifier 3 are not testable as written.
  - **F8 → C6.** The "101/101 unique saved segments / no duplicate after the replayed window" property is asserted only
    inside `prototypes/batch-startup/prototype.py`, which pytest never runs; the product controls assert only the
    delegate-call list and `transcript_version == 1` (`tests/phase2/test_retained_file_claim.py:235-237`).
  - **F9 → C7.** The corrected Bill row `[0.0, 29.25]` overlaps the next row `[29.0, 33.0]` in the same corpus file.
- **Ratified by the lead, do not re-open (F6):** the three fixture controls were retargeted rather than
  marker-removed, because `evidence/` is read-only and a control reading a frozen snapshot could never flip. The
  proposal JSON was not edited to fit; run B disclosed this in `progress.txt:79`. Accepted.
- **Accepted limitation, do not fix here (F4):** `_owner_dir` keys on `account_id` only
  (`phase2_file.py:432-434`) with no `authority_generation` in the manifest (`:461-475`), so "wrong owner" is enforced
  at account+meeting granularity, not across generations. Record it in known limitations; no generation concept exists
  elsewhere in the product.
- **Also flagged, already justified:** `tests/phase2/test_owner_bound_file_meeting.py:949` changed a terminal status
  from `failed` to `completed` because cleanup now runs after the durable terminal transition and a cleanup failure
  only logs (`phase2_file.py:791-794`). If C3's work changes that path, keep the operator's ability to learn that a
  source could not be removed.
- Lead's own verification of run B: backend **2,152 passed / 0 failed / 5 skipped / 2 xfailed / 37 subtests**; the
  xfail inventory contains only the two Jamie controls; frontend 312/312; typecheck clean; rebuild left the tree clean.

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

The preceding Run-B-completion snapshot is stale. Run C's PRD and opening
progress entry are authoritative for the following ranked work:

1. **C3 / F3 — reclaim terminal-owned retained input.** Refusal and URL
   cancellation remove only that Meeting's directory, after durable terminal
   truth.
2. **C4 / F5 — close the post-download active/no-task window.** A retained-source
   record failure durably fails the URL Meeting with a visible reason.
3. **C6 / F8 — product-test batch uniqueness.** Collected resume and mid-window
   crash controls prove unique saved segments and no replay duplicate.
4. **C7 / F9 — make the corrected Bill corpus internally consistent.** Audit and
   adjust only the neighbouring time boundary, or document an intentional overlap;
   never alter scored text.
5. **C5 / F7 — correct the Run-B verifier.** The deployed ladder measures
   solo-lane vocabulary, not `SYSTEM_LADDER_REFERENCE`; its falsifier must be
   testable or removed with explanation.

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

## Non-candidates

- Jamie / lone-participant aggregation — FALSIFIED; user decision D1 vs D15 pending; no code.
- Any change to `tools/qualify/` (run A's territory) beyond consuming its preflight.
- Any threshold/floor/constant; Stop cap; separator; hidden-tab (needs an Aqua session — measurement, not product);
  runtime packaging (4.1's receipt + `MOSS_TEST_REAL_SQLITE` conftest guard are merged as-is; no pin change).
- `docs/known-limitations-20260918.md` — lead-owned; the lead rewrites L1/L9 rows after the round.
