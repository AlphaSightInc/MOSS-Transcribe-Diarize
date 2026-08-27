# Measured MOSS voice-profile matching and abstention rule

**PROTOTYPE — reproduction artifact absorbed into the standing bench; not production code.**

## Question

On production WeSpeaker ResNet152 ONNX embeddings and live-path evidence units, what score,
runner-up margin, evidence floor, and profile aggregation recognizes an enrolled name while
abstaining when the voice is absent from the Account's bank?

## One command

```bash
prototypes/streaming-diarization/.venv/bin/python prototypes/streaming-diarization/voice-profile-matching/prototype_voice_profile_match.py --fresh
```

The command recomputes every vector in memory through the production embedder and prints the
complete evaluated state as JSON. Omitting `--fresh` is a fast development replay over the
standing bench's existing production-path caches; it is not the recorded measurement.

## Measurement frame

- Development corpus only: `benchmark_30m/acquired_jamie_dimon` and
  `benchmark_30m/lex_bill_ackman`. No sealed holdout is opened.
- Enrollment: three non-overlapping 300-second simulated named sessions from `0–900 s`.
  The longer frame is required because Ben has no production-admissible album exemplar in the
  first 300 seconds even though the reference contains short turns there.
- Probes: evidence strictly after `900 s`; no enrollment/probe audio overlap.
- Five private profiles: Ben, David, Jamie, Bill Ackman, Lex Fridman.
- Causal surface: each production live evidence unit independently sees the frozen profile bank.
- Terminal opportunity: truth-aligned speaker evidence within later 5-minute windows is reduced
  through production `FingerprintAlbum` semantics, then compared with the same frozen bank.
- Every known probe is repeated with its true profile removed. Any accepted remaining profile is
  a false name; abstention is correct.
- Selection order: require zero observed false names on both surfaces; maximize causal correct
  names, then terminal correct names; ties retain the LiveTranscribe baseline aggregation and
  nearest `0.51 / no-margin / 1.0 s` rule.

## Measured result

Fresh production-path run completed 2026-08-26. Model SHA-256:
`5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8`.
The existing caches reproduced every profile fact, distribution, selected operating point, and
reference-point outcome exactly; the verdict below comes from the fresh run.

### Denominators

- **5 speakers**, **2 English interview recordings**, **14 non-overlapping enrollment-session
  samples**.
- Causal surface: **470 known probes**, **470 leave-true-profile-out unknown scenarios**,
  **470 same-person pairs**, and **1,880 different-person pairs**.
- Terminal opportunity: **14 truth-aligned 5-minute speaker albums**, repeated as **14 unknown
  scenarios**; therefore **14 same-person** and **56 different-person pairs**.
- Evaluated **1,530 operating points**: 51 thresholds (`0.30–0.80` by `0.01`) × 5 margins ×
  3 evidence floors × 2 profile aggregations.

### Result

**VERDICT: ACCEPTED 2026-08-26.** The operator deferred to agent judgment and authorized later
optimization: cosine `>= 0.46`, no runner-up margin, and at least `1.0 s` of eligible speech.
Store multiple named-session samples and match
against their L2-normalized arithmetic mean, as LiveTranscribe does. An automatic match never
adds a sample. Below either gate, or without an embedding, abstain and keep `Speaker N`.

- Causal known probes: **441/470 correct (93.8298%)**, **29/470 abstained**, **0/470 wrong
  names**.
- Causal unknown scenarios: **470/470 abstained**, **0/470 false names**.
- Terminal opportunity: **14/14 correct**, **0 wrong/abstained**; unknown scenarios
  **14/14 abstained**.
- The best eligible impostor scored `0.449383`; `0.46` leaves a measured `0.010617` gap.
  Threshold `0.45` produced the same counts but leaves only `0.000617`, so `0.46` is the
  simplest less-fragile point on the observed plateau.
- Margins `0.00–0.20` produced the same best counts at `0.45–0.46`. Margin is therefore
  unnecessary. The wrong voice can be far ahead of its runner-up, so margin cannot replace the
  absolute score gate.

### What changed from each baseline

- **LiveTranscribe `0.51 / no margin / 1.0 s`: safe but over-conservative.** It produced
  **437/470 correct**, **33 abstentions**, and zero false names; terminal remained 14/14.
  The measured `0.46` recovers four correct causal names without adding a false name.
- **MOSS within-session `0.35 / 0.10 margin / 0.5 s`: not safe for durable names.** It produced
  455 correct, 12 abstentions, **3 wrong known names**, and **3 false names** when the true
  profile was absent. Two confusing probes carried only `0.500 s` and `0.915 s`; the third was
  a 2.5-second Lex probe that matched Bill at `0.449383` versus Lex at `0.348694`.
- **Aggregation:** arithmetic and duration-weighted profile means reached identical best
  counts. Their per-profile cosine agreement ranged `0.964901–1.0`; weighting showed no
  measured benefit. Retain the reference's simpler arithmetic mean.

### Timing semantics

- **Causal live:** apply the frozen per-account profile bank to every identity evidence unit
  once it holds at least `1.0 s`; accepted profile name is visible immediately.
- **Retrospective sweep:** apply the same rule to the current session's album centroid and allow
  that result to correct the session label. The 14/14 result proves a strong opportunity after
  aggregation; because the prototype used truth-aligned speaker groups, end-to-end future
  cluster-to-profile behavior remains unmeasured.

### Explicitly unmeasured

Every population beyond these five speakers and two English interview recordings: other
languages, children, accents outside the corpus, illness/aging, microphones and rooms, profile
banks larger than five, same-name people, adversarial impersonation, and actual end-to-end
durable-profile integration. Do not extrapolate a false-name rate from the observed zeros.
