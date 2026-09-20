# R4-3 — terminal-only identity gap

**Verdict: SUPPORTED.** S17's `S00` is not a live identity reset after silence. It is
created only during terminal finalization when an uncovered 0.27-second terminal segment
cannot reach the unchanged 0.5-second embedding floor. The terminal revision path then
creates a temporary second display label that cannot project into the settled one-speaker
session, so the saved segment becomes unresolved.

## Structural contract

- **Question:** Which one mechanism changes known Adam → `S00` → known, and does it act
  live or at finalization?
- **Primitives:** source span, acoustic evidence, album state, live publication, terminal
  mapping. Each separates what was heard, what can identify it, and when it was published.
- **Invariants:** 8,000-sample evidence floor, 1.0-second birth floor, 2.0-second album
  admission, 0.35 match score, and 0.1 margin stay unchanged; unknown is not identified;
  no neighbour assignment.
- **Unknown:** S17 did not retain raw terminal decoder labels. Whether the 0.27-second
  segment shares a terminal-local partition with longer Adam evidence is `UNMEASURED`.
- **Falsifier:** A distinct returning voice assigned to its own terminal-local partition is
  absorbed into Adam, or retained raw labels show the short segment had no eligible evidence
  in its partition.
- **Tool decision:** CPU ONNX replay is necessary to distinguish no-vector from low-score
  abstention and to test distinct-voice safety. Decoder replay is neither available nor
  authorized; retained public audio and publication state are sufficient for the mechanism.

## One-command reproduction

From the clone:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  prototypes/gap/run.py
```

It prints all 26 retained causal spans and all 15 saved spans: durations, production
thresholds, CPU WeSpeaker scores, album exemplars, dispositions, diagnostics, and decisions.
It makes zero decoder requests.

## Exact mechanism

1. Pre-Stop has 12/12 known Adam segments and no segment at 50.51–50.78 seconds.
2. Finalization adds `seg_0012`, text `Right?`, 4,320 samples / 0.27 seconds. It has no
   overlap with the pre-terminal surface.
3. `live_lane_decode.py:278-304` sends that uncovered/unmapped terminal segment through
   `revision_segments`.
4. `live_provider_bundle.py:665-667,1108-1123` drops it before embedding because 4,320 is
   below `min_segment_samples=8,000`. Thus score state is empty; neither 0.35 nor 0.1 is
   evaluated. The 2.0-second album admission threshold is downstream and irrelevant.
5. `revision_reader()` intentionally has no album. Therefore its birth-deferral hook is
   inactive; `live_identity.py:158-171` proposes `speaker-0002` despite the 0.27-second
   evidence gap. This is revision-only state, not a session birth.
6. `live_lane_decode.py:171-177` projects display label `S02` against the settled session's
   sole canonical `speaker-0001`; index 2 has no canonical, producing `None`. The saved layer
   renders it as `S00` / `Speaker uncertain`.

The silence hypothesis is excluded. Retained spans 10–14 are digital zeros and skip decode;
the album keeps ten Adam exemplars. Span 15, the first post-gap causal span, matches Adam at
0.836607. All later causal scores are 0.796373–0.906296. No lane or album reset occurs.

## Hypothesis rulings

- **H1 min evidence:** supported. 4,320 < 8,000 samples. Album admission not reached.
- **H2 birth floor:** excluded as the operative guard: revision reader has no album, so the
  1.0-second deferral is inactive; temporary assignment is `S01->speaker-0002`.
- **H3 score/margin:** excluded. There is no vector and no score, not a score below 0.35.
- **H4 deferred birth:** excluded for the same revision-reader reason.
- **H5 terminal mapping:** supported: no pre-terminal coverage, `S02` projects to `None`.
- **H6 silence reseed:** excluded by retained album state and post-gap scores.

## Proposed remedy — design only

Preserve the terminal decoder's local-speaker partition through finalization. For each
unmapped local partition, aggregate its **eligible** intervals and make one acoustic match
against the lane album. Apply the resulting canonical only to that same partition. Do not use
temporal neighbours, do not lower the per-interval evidence floor, and keep 0.35/0.1.

Production seam for later implementation:

- `moss_transcribe_diarize/app/live_transcript_convergence.py:1015-1071` — retain the
  terminal-local label after overlap resolution instead of discarding it from the proposal.
- `moss_transcribe_diarize/app/live_lane_decode.py:278-308` — lead-owned; replace isolated
  per-segment fallback with one partition-scoped evidence decision, then project segments.

Measured controls with the pinned CPU encoder and reconstructed S17 album:

- Healthy Adam return, eligible 50.81–53.99 evidence: 0.909091 ≥ 0.35 ⇒ one identity.
- Different returning Keyu, 0–3.18 evidence: 0.017033 < 0.35 ⇒ abstain; never absorb.
- Exact S17 remedy outcome remains `UNMEASURED` because raw terminal-local labels are absent.

## Offline controls

- `test_r4_3_same_terminal_partition_reuses_eligible_voice_evidence` is
  `xfail(strict=True)`. `--runxfail` fails on base: `[speaker-0001, None, speaker-0001]`.
- `test_r4_3_different_returning_voice_is_not_absorbed` passes on base:
  `[speaker-0001, None, None]`.

The first is the violating control for the proposed partition remedy. The second is its
falsifier. No product, threshold, gate, decoder, or lead-owned file changed.

## Full-suite gate

- Backend: **2,117 passed / 0 failed / 5 skipped / 1 expected xfail / 37 subtests**
  in 196.05 seconds.
- Frontend: **311/311 passed**.
- TypeScript: clean. Vite: clean.
