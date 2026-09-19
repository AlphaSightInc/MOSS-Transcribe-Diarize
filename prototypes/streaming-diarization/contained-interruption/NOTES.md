# Contained same-stream interruption

## Contract before measurement

- **Structural question:** can the terminal surface retain decoder-emitted speech from two
  people over the same source-time interval without republishing a window-seam duplicate?
- **Minimum primitives:** source interval (when speech occurred), decoder-local speaker track
  (which concurrent stream emitted it), and normalized word content (the only retained clue that
  two differently labelled contained segments repeat one decoding). Removing interval loses
  concurrency; removing track collapses people; removing content cannot control label-drifted
  duplicates.
- **Invariants:** clean and touching segments do not move; the measured same-track seam keeps its
  current union and word stream; distinct concurrent words survive; rolling publication remains
  single-owner; terminal overlap never creates a timestamp.
- **Assumptions/unknowns:** real decoder emission of contained speakers is unmeasured; text-based
  cross-label deduplication covers exact contiguous repetitions, not paraphrased duplicate
  decodes; retained corpora contain no cross-speaker overlap.
- **Falsifier:** reject the candidate if it loses either distinct turn, duplicates the negative
  control, changes the retained seam, changes clean input, or if leased source-backed decoding
  cannot emit a second speaker in the mixed condition.
- **Tool decision:** this deterministic probe is necessary to expose post-decoder loss and test
  candidate arithmetic. A bounded decoder matrix is separately necessary for acoustic recovery;
  its result changes whether this is described as reachable recovery or representation-only.

Run:

```bash
PYTHONPATH=. .venv/bin/python prototypes/streaming-diarization/contained-interruption/probe.py
```

## Deterministic result

All five preregistered assertions pass:

- Current normalization drops the contained interruption: 6 input words become 4; candidate
  retains all 6 and both source intervals.
- The cross-label contained duplicate stays suppressed as one segment.
- The retained 2.34-second same-track seam is byte-for-byte identical: one union segment,
  15-word stream, one merge, no displacement.
- Distinct partial overlap retains both segments and all 5 words instead of moving the later
  start by 40 samples.
- Clean non-overlap is unchanged.

**Deterministic verdict:** the old one-owner terminal representation is incompatible with a
decoder-emitted same-stream interruption. The measured candidate is: terminal proposals may carry
distinct concurrent speaker segments after producer-side same-track seam merge and contained
duplicate suppression; rolling proposals remain disjoint. This establishes arithmetic, not a ship
decision or acoustic recovery.

## Source-backed decoder result

Lease: global requests 251→257, six calls, peak one during this run, no retries. Calls seven and
eight were conditional on a promising overlap result and were not used. Generated WAV inputs and
raw responses are retained under `source-backed/`; `analyze_source_backed.py` records exact
source-time and normalizer outcomes.

- The non-overlap sequential control recovered the 1.44-second BOSS source as a second local
  speaker: `S02`, 20.27–21.51 s, exact target words.
- Every true overlap mixture at signal-to-interference ratio −3, 0, and +3 dB emitted only `S01`.
  The target words were absent, while the outer speaker's segment covered 19.27/19.32–24.93 s.
- Therefore neither old nor candidate normalization sees a second segment in any overlap arm.
  Their outputs are identical on all three mixtures.
- The isolated 1.44-second clip produced no parsed segment. The initial harness persisted the
  request but stopped before saving the exception attributes; it was not retried. The 50-second
  outer control validated non-empty, but its raw response was lost by the same harness defect and
  was not retried. This does not affect the paired sequential-vs-overlap adjudication.

**Acoustic verdict: rejected for this decoder/configuration.** The narrow publication change can
prevent proven post-decoder deletion when distinct concurrent segments exist, but it does not
recover this source-backed interruption because the decoder omitted it first. Do not claim
same-stream acoustic recovery or a met release gate.

## Downstream review and round decision

Independent read-only review is retained at the coordination path
`publication-OVERLAP-REVIEW.md`. Its end-to-end falsifier found that a future overlap slice must
land together, not as this normalizer alone:

- **F1:** terminal admission must permit ordered overlap while rolling stays disjoint.
- **F2:** terminal explicit unknown must remain unknown instead of being temporally projected onto
  the outer known person. Publication owns the separately reachable fix; identity must not
  duplicate it.
- **F3:** overlapping unknown rows must remain separate correction targets.
- **F4:** visible, copied, Markdown, and plain-text output must show start-end ranges or it hides
  concurrency even when both rows survive. JSON, SRT, WebVTT, persistence, and backend passage-ID
  correction already retain both intervals.

**Round decision: do not ship overlap architecture.** No retained or freshly constructed decoder
output contains the required concurrent second segment. Promoting only the normalizer would fix no
currently measured product output and would leave F1/F3/F4 incomplete. Preserve this prototype as
the next seam if a decoder witness appears. Ordinary interruption and Jamie remain explicit unmet
release gates.
