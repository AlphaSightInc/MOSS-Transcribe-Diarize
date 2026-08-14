# Context — x4-journal-mode

Iteration 4.

Branch `afk3/x4-journal-mode` from `dev`. Every defect in the PRD was found by independent adversarial
review with a reproduction; they are facts, not hypotheses. Read `docs/phase1-afk-charter.md`
(binding) and the closed decisions in `.wayfinder/tickets/` before your first change.

`dev` (`23afb6d`) is already an ancestor of this branch, so the former merge candidate needed no
merge. The branch source does not yet contain the PRD's assumed post-F6 journal fields or torn-tail
recovery; later candidates must work from this checked-out state, not assume those fixes landed.

## Known pre-existing test failures — not yours

`l2-stage0/test_legacy_ingest.py` (55 != 92) and four `test_macos_uds_tracer.py` tests fail
identically at `pre-afk-20260813`. `l15/test_l1_baseline.py` fails with `l15_product_tree_drift`:
that guard correctly refuses to run when the product tree moved — **do not edit its pin**, that
would falsify a measurement baseline.

The bare `.venv/bin/pytest` imports
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize`, not this worktree.
Use `PYTHONPATH=. .venv/bin/pytest ...` for worktree evidence; repairing that external environment
is outside this ticket.

`PYTHONPATH=. .venv/bin/pytest -q tests/test_live_service_runtime.py
tests/test_live_provider_bundle.py` currently has one environment-dependent failure in
`test_web_cli_enabled_live_rejects_bad_manifest_before_app_construction`: its args omit a journal
path, so it reaches the real default under `~/.local/share/` before bundle admission. That existing
directory is `0775`, which the previous private-storage fix correctly rejects. The current slice
does not touch `web_cli.py` or that external directory; focused provider/runtime checks pass.

## Validation

```bash
.venv/bin/pytest -q          # ~1006 pass, 2 skip, 387 subtests
python3 scripts/afk-guardrails/preflight.py x4-journal-mode
```

## Acceptance checklist (PRD gate, recorded 2026-08-14)

- [x] Private storage: repair a pre-existing loose journal leaf file and leaf directory;
  refuse a non-sticky group/world-writable ancestor; create every intermediate directory at
  `0700`. Proven by the committed `test_declared_journal_*` probes in
  `tests/test_live_service_runtime.py`. Final raw-artifact capture remains open.
- [x] Per-observation resilience: observations now carry `exemplar_count` and `provisional` from
  the provider; invalid values and a missing field become named refusals while valid rows from the
  same batch persist. Proven by
  `test_journal_refuses_bad_contract_rows_without_dropping_valid_observations` plus the provider
  and runtime row-shape probes. Final raw-artifact capture remains open.
- [x] Reader contract: `docs/adr/0003-live-session-audio-retention.md` now requires readers to
  skip blank/malformed forensic lines while leaving them on disk. `LiveVectorJournal.read_rows()`
  implements that contract; `test_journal_terminates_a_refusal_only_torn_tail_and_reader_skips_it`
  covers a refusal-only recovery, blank and malformed lines, and a later valid row;
  `test_journal_truncation_race_does_not_create_a_leading_blank` covers the empty-truncate race.
  Final raw-artifact capture remains open.
- [x] Provenance semantics: `docs/adr/0003-live-session-audio-retention.md` now defines
  `exemplar_count` and `sample_seconds` as current capped centroid-bank provenance, not meeting
  totals, and states `provisional`'s source-tier meaning plus its current writer invariant.
  `test_session_end_journal_observation_describes_the_current_capped_album_bank` forces the
  default `k=10` bank through 40 equal-duration admissions; it proves the journal observation
  retains only spans 31--40, records `50.0` seconds rather than the `200.0` admitted seconds,
  and marks the admitted-bank centroid non-provisional. Final raw-artifact capture remains open.
- [ ] Required final evidence: `.venv/bin/pytest -q tests/test_live_service_runtime.py
  tests/test_live_api.py`, a green guardrail preflight, and committed raw artifacts plus their
  re-runnable probes under `evidence/phase1/x4-journal-mode/`.
- [ ] Before declaring done: validate after merging current `dev` into this branch; record
  criterion-by-criterion proof and stated coverage limits in `progress.txt`.  Do not emit a
  completion promise without that recorded evidence.

Iteration 1 outcome: candidate "record the PRD gate" is complete.  This checklist is the
controlling scope for later changes; it makes no product-fix or test-pass claim.

Iteration 2 outcome: storage-mode enforcement is complete. `LiveVectorJournal.declared()` repairs
existing leaf directory/file modes and rejects a peer-writable ancestor; `append_session()` reasserts
`0600` through its open file descriptor. This does not cover a hostile actor changing the path after
declaration, nor filesystems that report successful mode changes while later violating them.

Iteration 3 outcome: the observation contract is complete. The provider supplies the new album
provenance fields, the journal validates their types and reads all structural fields before
serialization, and one incomplete/invalid observation no longer aborts the complete batch.

Iteration 4 outcome: reader/recovery contract is complete. An existing journal is opened even for
a refusal-only session so a previous unterminated forensic line gains a durable separator;
readers return only complete JSON objects and leave blank/malformed bytes untouched. A read that
loses its last byte to truncation adds no leading newline. This does not solve continuous hostile
truncation or make forensic lines valid records.

Iteration 5 outcome: centroid provenance semantics are complete. A journal row now has an explicit
consumer contract for its current capped bank and source tier, and the provider-path probe verifies
the default bank evicts older equal-duration evidence rather than reporting a meeting-long total.
This focused proof does not substitute for the final runtime/API gate or raw-artifact capture.

## Ranked candidates
1. Capture committed raw artifacts and run the final runtime/API gate against the worktree, then
   record criterion-by-criterion coverage limits. Before any completion claim, merge current `dev`
   into this branch and repeat the relevant validation on that merged result.
