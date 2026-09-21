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
  - **F3 → C3 (closed, iteration 5).** Refused retained work is recorded by exact owner during claim and reclaimed
    only after generic fallback durably makes that Meeting terminal; a held URL-acquisition cancellation uses its
    existing terminal settlement. Both product controls prove terminal-before-removal and preserve a sibling owner
    directory, with zero decoder/network dispatch.
  - **F5 → C4 (closed, iteration 6).** A retained-source record failure after a successful URL download now follows
    the existing durable `storage_failed` path and terminal-owner cleanup. The product control forces that precise
    write failure and proves a visible `failed/storage_failed` Meeting, no decoder call, normal task return, and a
    preserved sibling owner directory.
  - **F7 → C5 (closed, iteration 9).** `SYSTEM_LADDER_REFERENCE`
    (`tests/e2e/verify_demo_lanes.py:27`) has one consumer
    (`tests/test_round4_overlap_diagnosis.py:28`): the offline bounded-audio diagnostic.
    The deployed ladder (`tools/qualify/run.py:583-597` → external `ir_lane_ladder.py`)
    reads no reference row; it records finalized cases and non-accuracy solo-lane
    vocabulary retention. The Run-B verifier now says so and names the diagnostic's
    reachable fixture-bound falsifier rather than an impossible scoring claim.
  - **F8 → C6 (closed, iteration 7).** Product controls now require `[0..40, 40..100]` delegate calls and
    `101 == len(texts) == len(set(texts))` after both retained URL resume and File mid-window recovery; a lost or
    duplicate persisted segment fails at the production seam.
  - **F9 → C7 (closed, iteration 8).** The corrected Bill row now ends at the next
    row's `29.25` start, so the Bill corpus has no overlapping adjacent records. The
    retained production transcripts locate Lex's actual utterance later (29.55--29.63 s),
    so the conservative boundary repair preserves its audio and every scored text.
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
