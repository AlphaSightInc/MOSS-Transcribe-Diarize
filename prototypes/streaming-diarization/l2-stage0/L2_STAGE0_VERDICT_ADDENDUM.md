# L2 Stage-0 verdict addendum — independent-review correction

Status: Campaign A remains **BLOCKED**; Campaign B remains unauthorized. This is a
post-verdict correction. It does not replace or modify the sealed verdict (SHA-256
`f9f8b27d82d043716ec74f7ae33db573f97437b5a2e3ee180f97d65051fbb338`) or the
464-row evidence seal (SHA-256
`0591924533c4f4ec243c9f53dbe7db67572fb07408c4d1bc0d263c1376fa0130`).

## Critical D8: candidate measurements used golden-partitioned units

The independent reviewer traced a truth leak across the evaluator-to-candidate
boundary:

1. `run_candidates.py:401` loads the golden reference before candidate execution.
2. `production_cache.py:166-218` indexes truth speakers and groups each planned span
   into `(span_id, true_speaker)` evidence units.
3. `candidate_engine.py:827-835` pools tape-window evidence over those supplied unit
   intervals.

The reviewer changed golden labels from A,B to A,A while holding the runtime input
otherwise fixed; candidate runtime shape changed from two units to one. The original
no-golden-path audit at `run_candidates.py:104` inspected only
`candidate_engine.py`. It did not audit the evaluator, cache planner, or the complete
input boundary.

Consequently, the recorded development gains (+1.860557 pp over L1 and +1.432022 pp
over ledger-only) and candidate-arm holdout scores are truth-flattered upper bounds,
not valid blind feasibility measurements. This strengthens rather than reverses the
terminal decision: even the favored, truth-conditioned candidate missed both
predeclared holdout gain gates (+0.917431 pp over L1 and +0.0 pp over ledger-only,
each requiring +1.0 pp). No measurement was rerun; no threshold or gate changed; no
tuning or verdict flip occurred. Future feasibility campaigns must audit the full
evaluator-to-candidate input boundary.

## Certification limitations

- D4: the single opening is procedurally demonstrated by the guard, one recorded
  harness run, and no post-freeze tuning. It is not access-control-proven; holdout
  paths were plaintext in-tree from A1 commit `5be0455745629c6410d48285d5d90a55c9d7bd95`.
- D7: family v1→v4 preregistrations and their results were co-committed in
  `a16c6d811031cac826878200256af0b69224add8`. NOTES sequencing and run transcripts
  support ordering, but do not independently seal it. Future campaigns must commit
  each family preregistration before its first run.
- Corpus scope: the blind holdout was three short, near-saturated cases. Both
  30-minute cases remained exploratory pending human audits in
  `operator-questions-A1.md`. The result binds the current gated corpus, not the
  30-minute class.
- Planner frame: accuracy is frame-dependent; only same-production-planned-frame
  comparisons are meaningful. The seam inventory still defers every proposed seam.

## Decision and ruling provenance

The supervisor cured D6 by archiving contemporaneous rulings in the control repo at
`docs/handoffs/rulings/`, with preserved mtimes from 2026-08-03 17:44 through
2026-08-04 00:32. `ruling-a2-anchor.md` (19:21, SHA-256
`fd94bebc7b5aeadb22ee175f3b6789ced0e19689f377d42d104ab63d4b54f138`) and
`ruling-a2-complete.md` (20:52, SHA-256
`207e69ff1822ae2a587c80b59237b0d1877f2913d089efdf5d76bb9bfd81684f`) predate
the 21:04 completion. The append-only decision-authority file at verdict time is
reconstructible as lines 1–39, SHA-256
`b8edf95713e3620072ed480d3b5ab7f924724b1f24b8cb20cebc5129518ac4e7`.

## Reproducibility-surface corrections

The sealed verdict's command map is not edited. Its A3 command name is corrected to
`run_lifecycle_tests.py --test ... --json-output ... --transcript-output ...`, with
`evaluate_lifecycle.py` composing the matrix/verdict afterward. Its A4 placeholder is
superseded by the exact nice-10 command in
`evidence/a4/optimized/a4-optimization-run-transcript.txt:21` (transcript SHA-256
`8b83f6378ee62a37d66ca3f22bd6ebc156c5d8c5afdd6023ecbd7030edc7514b`), reproduced
verbatim in the JSON addendum. Exact chronological campaign commands and decisions
are in `prototypes/streaming-diarization/NOTES.md`; there is no
`l2-stage0/NOTES.md`.
