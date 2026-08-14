# Context — x4-journal-mode

Iteration 1.

Branch `afk3/x4-journal-mode` from `dev`. Every defect in the PRD was found by independent adversarial
review with a reproduction; they are facts, not hypotheses. Read `docs/phase1-afk-charter.md`
(binding) and the closed decisions in `.wayfinder/tickets/` before your first change.

## Known pre-existing test failures — not yours

`l2-stage0/test_legacy_ingest.py` (55 != 92) and four `test_macos_uds_tracer.py` tests fail
identically at `pre-afk-20260813`. `l15/test_l1_baseline.py` fails with `l15_product_tree_drift`:
that guard correctly refuses to run when the product tree moved — **do not edit its pin**, that
would falsify a measurement baseline.

## Validation

```bash
.venv/bin/pytest -q          # ~1006 pass, 2 skip, 387 subtests
python3 scripts/afk-guardrails/preflight.py x4-journal-mode
```

## Acceptance checklist (PRD gate, recorded 2026-08-14)

- [ ] Private storage: repair or refuse an existing loose journal leaf file, repair the
  journal leaf directory, and refuse or repair a loose ancestor.  Prove the pre-existing
  loose-file and loose-directory cases with committed probes.
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

## Ranked candidates
1. Merge `dev` in, confirm preflight OK.
2. Smallest vertical slice toward the fix — storage-mode enforcement plus its focused proof.
3. Close the observation-contract and reader-contract gaps, each with the required probes.
