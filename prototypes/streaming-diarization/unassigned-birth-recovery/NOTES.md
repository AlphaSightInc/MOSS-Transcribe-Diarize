# Recurring short-person recovery

## Contract

- **Question:** Can repeated, individually sub-floor observations establish one new person without lowering the 1.0-second birth floor?
- **Minimum primitives:** one unassigned acoustic observation (vector + duration); the existing bounded sweep ledger; the existing 0.70 same-person merge rule; the existing album and retrospective sweep.
- **Invariants:** one 0.78-second fragment cannot birth; only acoustically compatible unassigned units accumulate; cumulative support must reach 1.0 seconds; existing people and incompatible voices do not contribute; history is relabelled only by the existing sweep.
- **Falsifier:** the three retained Jamie fragments fail the 0.70 compatibility rule, a Ben/David control contributes to Jamie support, one fragment births, or the sweep cannot recover earlier Jamie evidence after birth.
- **Tool:** production pinned encoder on the actual retained 600-second meeting MP3 and exact committed span coordinates. No decoder calls.

## Run

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
  prototypes/streaming-diarization/unassigned-birth-recovery/probe.py
```

## Verdict

**Rejected for production.** The three retained Jamie fragments are repetitions of the
same source utterance; their pairwise cosine is 1.0, and Ben/Jamie and David/Jamie are
0.011 and 0.077. This proves the existing ledger could deduplicate and recover that
looped fixture, but not that distinct short Jamie utterances generalize.

The available real short-turn control falsified the proposal. Two distinct `ENG_A`
utterances scored 0.058; two distinct `ENG_B` utterances scored 0.146. Both are far
below the existing 0.70 same-person rule, so neither pair accumulated. Cross-person
scores were 0.000–0.267 and did not merge, but safety alone is insufficient: the remedy
cannot recover distinct short utterances. No live birth code or threshold change ships.
