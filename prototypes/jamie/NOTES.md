# R4-4 — lone brief participant evidence aggregation

## Verdict

**FALSIFIED; implementation REJECTED.** P0–P3 do not make Jamie a person from the
retained evidence in one 180 s source occurrence. Each also births ids for the real
laughter control and the synthetic applause/noise falsifiers under unchanged birth
semantics. Run B should implement nothing from this slice.

Jamie remains **UNMEASURED** semantically: all six source occurrences in
`snippets.json` need attended speaker/boundary adjudication. This does not rescue the
policy: the source-owned retained vector is only 0.78 s, while the other two candidate
voice spans (0.38 s and 0.26 s) are below the deployed 8,000-sample evidence boundary.

## Structural contract

- **Question:** can retained span vectors and durations make one lone brief person,
  without inventing a non-person or merging distinct people?
- **Minimum primitives:** retained vector plus duration; a hypothesis as a set of
  mutually matching spans; unchanged match, birth, and admission rules. Removing any
  one removes acoustic identity, evidence support, or the existing decision boundary.
- **Invariants:** words/times unchanged; one source person maps to at most one local id;
  different people never merge; non-persons get no id; provisional is not admitted;
  constants remain 0.35 score, 0.10 margin, 1.0 s birth, 2.0 s admission, 8,000 samples.
- **Assumptions/unknowns:** candidate Jamie identity and spill are unadjudicated; the
  retained corpus has no source-owned labelled applause interval; the applause control
  is therefore a named synthetic proxy, not a real-row claim.
- **Falsifier:** any policy that covers Jamie but creates an id for laughter/applause/
  noise, duplicates a returning voice, merges the labelled different-person pair, or
  reduces another person's coverage is rejected.
- **Tool decision:** production CPU ONNX is necessary because vector compatibility is
  the claim. Fresh embeddings would change the decision if genuine separated spans
  mutually matched at the deployed rule. No decoder call can adjudicate speaker truth,
  so none was made.

## Evidence and populations

- Source revision: `89f833acd4c654dd702664a17ed19783a2999c95`.
- Scorer: `r4-jamie-policy-scorer-v1`; reference SHA-256:
  `72a6173d92323d5c7ff5e6ba084063970966d4bd4e146c23e24d57949ad1a01b`.
- One 180 s source: Jamie reference rows total **4.221 s**.
- Retained 600 s capacity run: the same source repeated three times, hence **12.663 s**.
  The three 0.78 s vectors have cosine 1.0 because the audio is byte-identical; this is
  not independent evidence and cannot validate a repeated-utterance rule.
- The brief's ten-session claim was not replayed here: sessions replayed **0**; no
  claim is made about their wire-level population.
- Real applause is **UNMEASURED** because the retained corpus has no labelled interval.

## Measured policy result

All four policies have the same scored outcome on identical retained inputs:

| policy | Ben correct/wrong/unknown | David correct/wrong/unknown | Jamie correct/wrong/unknown | false births | duplicates | merges | provisional/admitted births |
|---|---:|---:|---:|---:|---:|---:|---:|
| P0 current | 2.03/0/0 | 2.72/0/0 | 0/0/4.221 | 3 | 0 | 0 | 3/0 |
| P1 cross-span pool | 2.03/0/0 | 2.72/0/0 | 0/0/4.221 | 3 | 0 | 0 | 3/0 |
| P2 deferred re-evaluation | 2.03/0/0 | 2.72/0/0 | 0/0/4.221 | 3 | 0 | 0 | 3/0 |
| P3 terminal sweep | 2.03/0/0 | 2.72/0/0 | 0/0/4.221 | 3 | 0 | 0 | 3/0 |

False births are real laughter plus synthetic applause/noise. The real laughter alone
is sufficient to falsify the zero-non-person-id invariant. ENG_A and ENG_B each supply
two separated source-known utterances; same-person cosines are 0.058275 and 0.146357,
below 0.35. Their closest cross-person cosine is 0.267328. They do not merge, but neither
person accumulates support. Full decisions and scores are in `results.json`.

Words and timestamps are immutable inputs and are unchanged. Unknown means abstained or
not human-adjudicated; it is not silently counted as correct or wrong. Missed selected
speech is therefore Jamie 4.221 s, ENG_A 1.458333 s, ENG_B 1.713412 s.

## Proposed targets for owner approval

- Ben selected return controls: 2.03/2.03 s correct, 0 wrong.
- David selected return controls: 2.72/2.72 s correct, 0 wrong.
- All people: 0 s misattribution; no participant excluded from denominators.
- Non-person: 0 id assignments and 0 births.
- Jamie coverage target: **not proposed** until R4-11 adjudicates the six snippets.

## Later production seam — only if new evidence reverses this verdict

- Retention: `moss_transcribe_diarize/app/live_provider_bundle.py:665-695`.
- Birth deferral/re-evaluation: `moss_transcribe_diarize/app/live_provider_bundle.py:715-751`
  and `moss_transcribe_diarize/app/live_identity.py:158-173,240-272`.
- Provisional aggregation representation: `moss_transcribe_diarize/app/live_identity_album.py:97-100,197-209`.

The later implementation must carry the falsifier above, preserve every frozen
constant, and prove on source-owned adjudicated evidence that its gain is not caused by
pooling exact repeated audio. This prototype makes no production change.

## Reproduce

```sh
PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/jamie/run.py
```
