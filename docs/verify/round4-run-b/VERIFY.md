# Round 4 run B — offline verification

**PASS, within its stated boundary.** Run B makes File/URL restart work durable under
its existing Meeting, makes terminal identity recovery conditional on the decoder's
own local partition, and corrects the approved acceptance references. It does **not**
qualify 30-minute capacity, repair historical S17, or make a decoder request.

## What changed and what stayed fixed

- **F1 — File/URL restart ownership.** A Meeting owns the normalized local source,
  checkpoint, and owner record under its durable retained-work directory. At startup,
  only an exact owner/source/checkpoint contract is claimed before the existing generic
  File recovery; all unclaimed work still follows that interruption path. The ten
  `prototypes/batch-startup` cases now have real lifespan/account-lifecycle controls:
  valid File/URL resumes, mid-window replay, cancellation, duplicate startup, invalid
  provenance/prefix, retained URL copy, account-scoped recovery, legacy File fallback,
  and unchanged Live fallback.
- **F2 — Conditional terminal identity.** Each terminal-local partition gets at most
  one match using only its eligible evidence; a result is projected only into that
  same partition. The shared-partition control matches Adam at **0.909091**; the
  different-voice control abstains at **0.017033**; an isolated short partition stays
  `S00`. No identity threshold, duration floor, or neighbor assignment changed.
- **F3 — Correct acceptance population.** D27's corrected Bill/Keyu references make
  the acceptance row 29.25 seconds and the ladder row 24 seconds. Replaying the
  retained 29-second publication still gives exactly three additions (`you`, `know`,
  repeated `to`) and no substitutions or omissions. The pre-terminal arms remain
  **UNMEASURED**.
- **F4 — Explicit limits.** Historical S17 remains **UNMEASURED** because its raw
  terminal-local decoder labels were not retained. The deferred capacity row remains
  `capacity_2x1800: REQUIRED-NOT-RUN`. This run used no decoder, tunnel, proxy, GPU,
  or network request.

## Strict-control accounting

The following six former strict expected failures are ordinary passes:

1. `tests/phase2/test_batch_startup_prototype_controls.py::test_r4_5_base_lifespan_resumes_valid_retained_prefix[file]`
2. `tests/phase2/test_batch_startup_prototype_controls.py::test_r4_5_base_lifespan_resumes_valid_retained_prefix[url]`
3. `tests/test_r4_gap_terminal_identity.py::test_r4_3_same_terminal_partition_reuses_eligible_voice_evidence`
4. `tests/test_round4_overlap_diagnosis.py::test_r4_6_demo_reference_matches_corrected_audio_population`
5. `tests/test_round4_overlap_diagnosis.py::test_r4_6_ladder_reference_is_bounded_by_captured_audio`
6. `tests/test_round4_alternation_diagnosis.py::test_r4_keyu_source_reference_matches_audited_audio_population`

Only the two Jamie controls remain strict expected failures. They are intentional:
R4-4's lone-participant aggregation is falsified, not deferred implementation work.
`_assert_no_active_meetings` is byte-identical to `71f23c0c`.

## Reproduce

Run from this repository root with the pinned interpreter:

```sh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python

# Focused product seams and the offline partition replay.
$PY -m pytest -q -p no:cacheprovider \
  tests/phase2/test_batch_startup_prototype_controls.py \
  tests/phase2/test_retained_file_claim.py \
  tests/phase2/test_workspace_lifecycle.py
$PY prototypes/gap/run.py
$PY -m pytest -q -p no:cacheprovider \
  tests/test_r4_gap_terminal_identity.py \
  tests/test_round4_overlap_diagnosis.py \
  tests/test_round4_alternation_diagnosis.py \
  tests/phase2/test_demo_lane_measurement.py \
  tests/phase2/test_lane_word_oracle.py

# Required final gates.
$PY -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
```

Expected current-tree final gate: **2,152 passed, 5 skipped, 2 xfailed, 0 failed,
37 subtests** (169.56 seconds); frontend **312/312** across 28 files; typecheck clean.
No `frontend/` source changed from `71f23c0c`, so the PRD's conditional frontend build
and asset-parity check is inapplicable.

## Falsifiers

This PASS is false if any reachable result shows:

1. A valid retained File/URL prefix is interrupted rather than resumed; a cancelled
   resume dispatches a later window; duplicate startup proceeds twice; or invalid
   owner/source/contract/prefix data dispatches or publishes.
2. A different voice is absorbed across terminal-local partitions, an isolated
   sub-floor partition resolves instead of remaining `S00`, or a partition receives
   more than one album match.
3. The corrected replay hides one of the three decoder additions, changes an
   uncorrected decoder error, scores the 24-second ladder against the 29.25-second
   population, or claims a pre-terminal arm is measured.
4. More or fewer than the six named controls converted, either Jamie control passes,
   the unchanged active-meeting assertion differs from base, a final gate fails, or
   the capacity row disappears from a later summary.

## Evidence boundary

The evidence is offline unit/lifespan behavior plus the retained CPU ONNX replay.
It establishes the conditional rule and restart ownership, not decoder-backed S17
repair, live browser behavior, acoustic qualification, or the deferred 2x1800-second
capacity run.
