# R4-6 same-stream interruption diagnosis

## Contract

- **Question:** At which first layer does every scored system-lane edit appear: raw decoder, canonical lane text, published text, or reference/cut?
- **Hypothesis:** Retained publication and one bounded raw capture can distinguish decoder information limits from downstream loss and reference defects.
- **Minimum primitives:** raw window text; canonical lane text; published text; reference word plus interval. Removing any layer makes its adjacent loss boundary unobservable.
- **Invariant:** Attribute each edit exactly once at the first causal layer. Preserve lane identity and the measured population.
- **Assumptions / unknowns:** The corpus supplies only one coarse `[0, 29]` interval, so per-word timing is **UNMEASURED**. The prior full-audio transcript is timing evidence, not an independently listened reference.
- **Falsifier:** Any word present in raw output but absent from canonical or published text disproves the zero-(b)/(c) finding. A corrected reference/cut that removes class-(a) additions disproves the proposed correction.
- **Tool decision:** Reuse retained S17 artifacts first. One production decoder request was necessary only because no retained raw-window artifact survived; its result changes whether loss is assigned before or after decoding. No further request can change the observed raw-to-published equality.

## One-command reproduction

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/overlap/build_attribution.py
```

Expected: 83 attributed system edits across the demo, `overlap@1`, and `overlap@0.316`; the generator asserts raw-to-demo publication equality and identical ladder prefixes.

## Verdict: SUPPORTED

- Demo system lane: 13/106 = 2 substitutions, 6 omissions, 5 additions. Attribution: class (a) 3; class (b) 0; class (c) 0; class (d) 10.
- Demo microphone lane: 5/53 = 0 substitutions, 0 omissions, 5 additions.
- `overlap@1` and `overlap@0.316` system lanes: each 35/106 = 2 substitutions, 29 omissions, 4 additions. Attribution per row: class (a) 2; class (d) 33. Each microphone lane: 2/53 = 0 substitutions, 1 omission, 1 addition.
- The diagnostic rows use 24,000 ms of retained meeting audio against a 29 s reference. The demo cuts at 29.0 s while retained full-audio output ends `the book` at 29.25 s.
- One exact 29 s production `VllmRunner` request produced the same system word stream as the retained demo publication. Usage: 1/40 requests, peak in flight 1, retries 0; pre/post service metrics 0 running and 0 waiting.
- Therefore no change to `live_transcript_convergence.py`, lead-owned `live_lane_decode.py`, or another product module is supported. The later change is qualification/reference construction at `tests/e2e/verify_demo_lanes.py:60-75`, using the separate proposals in `evidence/round4/overlap/reference-correction-proposal.json`.

## Controls

- `test_r4_6_demo_reference_matches_corrected_audio_population`: strict expected failure on base; proves the current 29 s reference population differs from the audited proposal.
- `test_r4_6_ladder_reference_is_bounded_by_captured_audio`: strict expected failure on base; proves the current ladder reference extends beyond captured audio.
- Targeted result: 10 passed, 2 xfailed.

## Evidence limits

Per-word acoustic boundaries remain **UNMEASURED** because the source reference has record-level timing only. No listening, new alignment model, separator, alternative decoder, threshold, or product change was authorised or needed for the causal layer result.

The first full-backend attempt used the wrong virtualenv and is retained in `evidence/round4/overlap/suite-attempts.md`; it is excluded from acceptance counts.
