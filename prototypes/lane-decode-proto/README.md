# THROWAWAY WP1 lane-decoding experiment — NOT a production fix

Question: on the real runtime path, do serial lane decoding, lane-scoped identity,
and per-lane revisions preserve words and speakers through Stop and saving?

Run from this worktree (requires free local ports 18101 and 17871):

```sh
bash prototypes/lane-decode-proto/experiment.sh parity
```

The launcher constructs an import overlay from this checkout, starts its own SSH
forward and HTTPS stack, uses the real corpus/decoder, prints state after each
frame, scores the saved meeting, and stops its children. Generated modules,
SQLite, certificates, audio, and raw surfaces remain ignored inside this tree.
The request budget is cumulative across runs via scratch/latencies.jsonl; do not
remove that file to reset the budget. Current hard limit: 200 requests for WP1.

Supported cases: same, parity, system_control, mic_control, mic-10, mic-15,
system-10, system-15, alternation, zero, noise, stop_mid, reshare.

## Primitives and invariants

- P1 Audio interval: mixed audio owns endpointing/accounting; aligned lane PCM
  carries source information which cannot be recovered from the mixed waveform.
- P2 Lane identity store: each lane has its own album and retrospective sweep.
  One global speaker allocator names births. Equal voices on different lanes
  must still have different IDs.
- P3 Revision proposal: per-lane words and voice-based attribution are composed
  in start/lane/end order. Lane failure must preserve its earlier surface.
- I1 Serial dispatch; unchanged thresholds, nine-key transport and lifecycle.
- I2 Digital-zero/all-silent lane audio does not reach the decoder.
- I3 Two additional tapes each use the existing mixed-tape capacity; release at
  terminal lifetime. This bounds tape buffers at 3x existing capacity, excluding
  transient read copies and existing canonical/rolling buffers. Total peak
  memory, exhaustion behavior and lifecycle cleanup remain unverified.

## Falsifiers / limits

Lost lane words or speakers at terminal replacement; same-voice lane collapse;
zero-lane words; cross-lane speaker assignment; a saved/final mismatch.
Vocabulary changes alone are not proof of lost speech: e.g. removal of a
spurious split-word token can improve the transcript.

Reference JSONL has sentence-level intervals that cross the 24-second cut:
29 seconds for the first system sentence, 25 seconds for the first mic sentence.
Scorer reports edits against overlapping reference rows and labels that boundary
contamination. It does not invent word timestamps or call this exact clip WER.
Saved documents currently omit source_lane (WP2 owns that consumer). Lane counts
from saved speaker IDs are derived attribution, not persisted lane provenance.

## Candidate history

v1: same case; canonical lane identity, existing time-based terminal mapping.
v2: parity and controls; lane final sweeps and voice-based terminal preparation.
v4: quiet-lane ladder; read-only voice evidence for rolling and terminal
attribution, no timestamp fallback for lane revisions; span/queue instrumentation.
These versions are not pooled as one qualification result.
