# Agent instructions — MOSS-Transcribe-Diarize

Method norms for every agent session in this repo (interactive, ralph iterations,
codex). An active ralph run's `scripts/ralph-afk/prd.md` governs WHAT to build and in
what order; this file governs HOW.

## Prototype before you implement

For any new algorithm, data structure, threshold, or policy choice: build or extend a
throwaway prototype and MEASURE, before writing production code. Pitfalls must die in
prototypes, not in certification runs. In Claude sessions the `/prototype` skill
scaffolds this; the bar is the same regardless of tooling:

- State the question the prototype answers. One command to run. Print full state.
- Measured, not asserted — numbers over adjectives, on the production code path where
  possible (real encoder, deployed thresholds, live-path semantics).
- Record the verdict (`NOTES.md` beside the prototype, then the relevant design doc or
  ADR), then delete the prototype or absorb it into the bench.

## The standing measurement bench

`prototypes/streaming-diarization/` is the shared bench for identity/diarization
questions: the production `_OnnxWeSpeakerEmbedder` + pinned ONNX, live-path span
semantics, synthetic meetings built from real human speech, and the real golden
interview corpora under `data/real/` (see its `README.md` for one-command setup).
Extend the bench instead of rebuilding measurement scaffolding. Verdicts to date:
its `NOTES.md` and `docs/design-streaming-diarization.md` §7.

## Settled evidence — extend, don't re-litigate

- ADR-0002 + `docs/design-streaming-diarization.md`: two-tier identity architecture
  (album/centroid + durable tape + retrospective sweep), accepted on measured gates.
- Re-embedding from inception is measured-rejected (quadratic cost, worst short-probe
  match). The 150 s/request bound is context arithmetic, not configuration.
- New evidence that contradicts settled evidence is welcome: bring numbers and update
  the doc in the same change.
