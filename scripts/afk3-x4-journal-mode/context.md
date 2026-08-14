# Context — x4-journal-mode

Iteration 2.

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
- [ ] Per-observation resilience: validate `exemplar_count` and `provisional`; a missing
  Protocol attribute must become that speaker's named refusal without losing valid rows from
  the same session.  Prove it with a committed probe.
- [ ] Reader contract: document that consumers skip blank and malformed forensic lines, and
  test a journal containing one of those lines.  Recovery must also cover a refusal-only
  session and a truncation race without creating a leading blank line.
- [ ] Provenance semantics: document that `exemplar_count` is the current capped centroid-bank
  size, not total admitted speech; pin its eviction behavior in a test.  Keep `provisional`
  only with a documented distinction from `exemplar_count == 0`.
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

## Ranked candidates
1. Close the observation contract from the checked-out baseline: add and validate
   `exemplar_count`/`provisional`, and turn a missing attribute into a per-speaker named refusal
   without losing valid rows from the same session.
2. Establish and document the reader contract, including refusal-only torn-tail recovery and the
   truncation-race no-leading-blank property.
3. Document and test capped-bank provenance/eviction semantics, including why `provisional` remains.
4. After all functional criteria pass, capture committed raw artifacts and run the final two-suite
   gate against the worktree, then record criterion-by-criterion coverage limits.
