# Round 4 run C — offline verification

**PASS, within the offline lifecycle boundary.** Run C closes the acceptance
review's durable File/URL ownership consequences: account revocation cannot
restart or unfence retained work; valid retained work cannot block or abort
startup; and terminally refused, cancelled, or storage-failed work releases
only its own retained directory. It also promotes the replay invariant into
product controls and keeps the acceptance corpus internally consistent.

## Mental model

A retained directory is an input owned by one durable Meeting. The Meeting
reaches a durable terminal truth first; only then may its owner directory be
removed. Startup claims valid owners and schedules their resumption in the
background. Every unclaimed File row and every Live row retains the existing
terminal fallback, so the unchanged global active-Meeting assertion still sees
no active leftovers. Live capture has no restart-resume path.

## C1--C7 closed controls

- **C1 — revoked accounts stay fenced.**
  `test_account_revocation_does_not_resume_retained_file_work`,
  `test_host_revoke_waits_for_file_quiescence_and_fences_late_result`, and
  `test_revocation_fences_late_file_result_commit` prove revocation sends no
  retained decoder work, creates no new transcript, and rejects late result
  publication. The revocation caller is not a valid account-startup claimant;
  it does not release the settled fence to resume work.
- **C2 — startup stays available.** The held-resume and injected
  commit/publication/cleanup controls in
  `tests/phase2/test_retained_file_claim.py` prove the descriptor serves while
  resume remains pending and each failure is a durable, operator-visible
  Meeting outcome instead of a lifespan failure.
- **C3 — terminal owner cleanup.**
  `test_lifespan_refuses_missing_retained_url_copy_without_decoder_dispatch`
  and `test_url_cancellation_reclaims_only_its_terminal_retained_directory`
  prove `interrupted` truth precedes deletion and a sibling owner's marker
  survives.
- **C4 — source-record failure terminates.**
  `test_url_retained_source_failure_becomes_visible_terminal_failure` injects
  the post-download persistence error and proves visible terminal failure,
  zero decoder calls, and owner-local cleanup.
- **C5 — ladder evidence is described honestly.**
  `SYSTEM_LADDER_REFERENCE` has one consumer:
  `test_r4_6_ladder_reference_is_bounded_by_captured_audio`. It is a 24-second
  offline fixture. The deployed ladder consumes no reference row; its PASS
  means six finalizations, while its solo-lane unique-vocabulary retention is
  not transcript accuracy.
- **C6 — replay is a product invariant.** The retained URL resume and
  mid-window-crash controls require the `[0..40, 40..100]` delegate sequence
  and `101 == len(texts) == len(set(texts))`: no lost or duplicated saved
  segment after a replayed window.
- **C7 — corpus rows do not overlap.**
  `test_r4_6_corrected_full_reference_rows_do_not_overlap` preserves every
  scored word while requiring Bill's corrected 29.25-second boundary to meet
  the following row exactly.

## Required current-tree gates

Run from repository root with:

```sh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
$PY -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
```

Results on this tree:

- Backend: **2,158 passed, 0 failed, 5 skipped, 2 xfailed, 37 subtests** in
  168.60 seconds (21 upstream deprecation warnings).
- Frontend: **312/312** tests across 28 files.
- Typecheck: clean.
- `git diff --name-only round4/integration...HEAD -- frontend`: empty; no
  frontend source changed, so the PRD's conditional build/asset-parity gate is
  inapplicable.

`_assert_no_active_meetings` remains byte-identical to Run B's fixed base;
the two Jamie controls remain `xfail(strict=True)`. No decoder, network,
tunnel, proxy, or GPU request was made for this run. Historical S17 remains
**UNMEASURED** and `capacity_2x1800` remains **REQUIRED-NOT-RUN**.

## Falsifiers and boundary

This PASS is false if a revoked account publishes after revocation; startup
waits for a held resume or aborts on its failure; a retained directory is
deleted before its own terminal transition or a sibling is removed; a
source-record failure leaves an active URL Meeting with no task; replay loses
or duplicates a segment; corrected corpus rows overlap; or the deployed ladder
starts scoring the offline reference fixture.

This verifies offline lifecycle, persistence, and deterministic replay
semantics. It does not qualify live browser capture, decoder-backed S17 repair,
acoustics, provider behavior, or 2x1800-second capacity.
