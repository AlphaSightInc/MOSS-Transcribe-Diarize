# L1 rolling latency probe

**Question.** Does serial WeSpeaker span embedding make a 180 s rolling cycle exceed the 15 s stride?

**Primitives.** A paced audio tick, one Gemini rolling call, and the speaker embedding of Gemini-attributed spans. The committed frontier can advance only after all three. C4's window and word ownership stay fixed.

**Invariant.** Parallel span embedding must produce the same vectors in interval order; one Gemini window call remains in flight per session.

**Unknown.** Provider latency in the paced product run may differ from the P61 cached-call log. A replay of 10 minutes is needed for the label-lag verdict.

**Falsifier.** Three embedding workers do not lower cycle time enough to reduce skipped ticks and bucket label lag, or change vectors/identity.

**Tool decision.** Run `probe_encoder.py` against the production ONNX model and public long60 window at 120–300 s. If it saves at least 2 s with equal vectors, use the existing `interval_workers` option at composition. Then run a 10-minute 1.0x HTTP replay against that candidate. P62's 6c5776e3 first 10 minutes are the before receipt.

**Measured prototype.** Two labels, three 2–10 s intervals each; serial 5.574/4.969 s, three workers 2.719/2.645 s; max vector difference 0.0 across all components. P61 cached 180 s Gemini calls ending 180–600 s: n=29, median 10.367 s, p90 11.172 s, max 11.649 s; zero calls over 15 s. P62 product first 10 minutes: 39 commits, one skipped tick, reconstructed tick-to-commit p50 17.508 s, p90 26.511 s, max 30.262 s. The rising delay before a skip is consistent with a cycle slightly above 15 s. GoAway affected W3 preview four times in the 43-minute run; rolling calls use another transport.

**Paced product verdict.** On a new 600 s 1.0x HTTP replay of the first public long60 slice, three interval workers produced 40 rolling calls, 0 skipped ticks, and two IDs at Stop. Labeled one-second buckets: 583/600, p50 18.262 s and p90 25.015 s. P62's first 600 s of its continuous 43-minute run had 597/600 buckets, p50 26.761 s and p90 37.508 s. Reconstructed tick-to-commit p50: 11.255 s after versus 17.508 s before. The two populations share audio and pace; the standalone replay ends at 600 s, whereas the prior run continued. The 14-bucket coverage difference is visible and is not a quality equivalence claim. One W3 GoAway occurred in the 600 s after run; its per-reconnect gap is not timestamped. Receipt: `evidence/P63/l1-paced-10min-130f3d39-candidate/result.json`; comparison: `evidence/P63/l1-before-first600.json`.
