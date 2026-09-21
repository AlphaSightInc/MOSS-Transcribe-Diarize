# R4-10 pre-terminal rerun receipt

## Verdict

**UNMEASURED.** This preparation adds a receipt harness only. It sent **zero** decoder requests. The historical alternation pre-terminal system (16/106) and microphone (11/53) rows remain unmeasured until the frozen R4-10 pass runs this harness against the adopted D27 reference/cut.

## Structural contract

**Question.** What must one pre-terminal run retain so a later word dispute is settled without rerunning a decoder?

**Minimum primitives.** Each lane retains: (1) raw decoder window responses, (2) canonical segments, (3) published pre-terminal segments, (4) the exact audited reference row, and (5) actual source/cut geometry. None is replaceable: raw establishes decoder output; canonical distinguishes convergence; publication distinguishes the visible surface; reference establishes what was scored; geometry establishes what audio existed.

**Invariants.** Every scored edit has one class and a receipt path: `a` raw decoder, `b` raw-to-canonical change, `c` canonical-to-published change, or `d` audited reference/cut. A missing layer, ambiguous raw-lane attribution, or edit with no first evidenced stage is a hard receipt failure, never a rerun or guessed class. The harness reads the D27 fixture at execution time; it never applies the proposal itself.

**Assumptions / unknowns.** The R4-7 supported runtime and frozen manifest/model must be supplied by the later pass. The current prep base predates the D27 fixture merge, so plan-only reports `MISSING` and execution refuses. No quality conclusion, raw response, or request count has been measured here.

**Falsifier.** Any rerun edit not attributable from the five retained layers falsifies the harness; any raw word absent in canonical/published changes the class away from `a`; any reference/cut mismatch is class `d` rather than a product error.

**Tool decision.** The production `lane_word_oracle.distance` scorer and current `tests/e2e/verify_demo_lanes.py` corpus seam avoid a second oracle. The stack instrumentation is necessary only in the later decoder-backed run, because API snapshots alone cannot prove raw decoder custody.

## Command for the budgeted frozen pass

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  prototypes/preterm-rerun/run.py --run \
  --decoder-base-url http://127.0.0.1:<lead-owned-proxy>/v1 \
  --budget 56 --out evidence/round4/preterm/rerun-<frozen-sha>
```

The harness prints/records the 56-request estimate before stack startup: alternation system 15, alternation microphone 13, overlap system 15, overlap microphone 13. It refuses a smaller budget, an absent corrected fixture, ambiguous lane attribution, or absent layers before a quality verdict.

## Expected receipt layout

```text
rerun-<sha>/<case>/<lane>/
  raw-<lane>.json
  canonical-<lane>.json
  published-<lane>.json
  reference-<lane>.jsonl
  cut-geometry.json
  scored-edits.json
```

`raw-events.jsonl` remains adjacent to those per-arm receipts so every retained raw window can be traced to its session, lane, and span. The scorer control reproduces the 19 already-attributed final rows: alternation system `a=2,d=7`; alternation microphone `a=5`; overlap microphone `a=5`.
