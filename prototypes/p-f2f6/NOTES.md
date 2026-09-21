# P-F2F6 — raw terminal custody and pure observation

## Verdict

**F2 SUPPORTED; F6 SUPPORTED.** The smallest sufficient seam retains decoder-local
spans before overlap normalization, then returns an immutable normalized decision
record beside the native result. A separate observer can copy both streams without
importing, constructing, wrapping, or calling the identity preparer.

This is a throwaway prototype. It changes no product code, threshold, or constant.
It sends zero decoder requests and makes no tunnel or network connection.

## Structural contract

- **Question.** Can evidence distinguish what the decoder emitted from what the
  normalized identity decision used, while observation stays outside that decision?
- **Minimum primitives.** `RawTerminalSpan`; explicit raw-to-normalized mapping;
  owner-bound normalized partition decision; pure diagnostics copier. Removing raw
  custody loses the historical question; removing mapping makes the two populations
  incomparable; removing the native decision record forces the observer to re-decide.
- **Invariants.** Published proposal bytes are identical capture off/on/writer refusal;
  raw records are pre-normalization; partition membership equals the decision's actual
  normalized partition; the 8,000-sample floor and 0.35/0.10 identity thresholds stay
  unchanged; observation has no preparer dependency.
- **Assumptions / unknowns.** Deterministic scores prove the seam, not acoustic quality.
  The historical S17 partition remains **UNMEASURED** until the authorized rerun.
- **Falsifier.** Contained `S02` missing from raw capture; any normalized mismatch;
  any observer dependency on the preparer; or different publication bytes.
- **Tool decision.** The production overlap resolver and identity preparer are needed
  to exercise live semantics. A deterministic provider isolates custody without a
  decoder, GPU, tunnel, or network. Any control failure rejects the seam.

## One command; full state

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/p-f2f6/run.py \
  --out evidence/round4/p-f2f6/prototype-output.json
```

Measured contained case: raw `S01` is 32,000 samples; raw `S02` is 4,320 samples
inside it. Frozen capture reports only normalized `S01`. The prototype reports both
raw spans and maps raw index 1 to `null` / `dropped_by_normalization`. The normalized
`system:S01` decision remains eligible at 32,000 ≥ 8,000 samples, scores Adam
`0.909091`, and publishes `speaker-0001`.

## Later implementation seams and required controls

- **F2:** `live_transcript_convergence.py:999-1002,1040-1097` — construct immutable
  raw spans after parsing (`:1061-1072`) and before normalization (`:1076`); carry them
  with the terminal result. `live_lane_decode.py:300-408` — emit a separate normalized
  partition record with member raw indexes, decision, identity, owner, and schema.
- **F6:** `live_lane_decode.py:137-203,319-408` — the native partition decision must
  return its diagnostics. `terminal_label_capture.py:1-147` becomes a pure copier and
  must not expose `prepare_revision`, wrap evidence, or import the preparer.
- Run E must carry: capture off/on/writer refusal byte equivalence; contained-`S02`
  raw custody; raw→normalized mapping; captured/native partition equality; observer
  import/call isolation; Adam/Keyu partition controls from `round4/labels2`.

If the authorized S17 rerun later shows the historical raw span was isolated from
eligible Adam evidence, `S00` was correct: the row is **explained, not repaired**.

## Separate runner-boundary note

`phase2_file.py:22,551-583,768` reaches private window-runner symbols. A later run
should expose `WindowedRunner.validate_resume(source, checkpoint_dir,
inference_options) -> bool`; the runner owns duration/window planning, checkpoint
contract construction, identity contract, and prefix loading. File ownership code
then acts only on valid/invalid. The separate private `_accepted_speechless` import
should likewise become a public runner/result predicate. No fix is made here.
