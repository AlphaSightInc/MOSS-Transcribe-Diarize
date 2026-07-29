# Authorization request — candidates 55, 65 and 60, in that order

> **CORRECTION, added in iteration 7 before you read this — one claim in §4(c) below was wrong, and
> it was the loop's own instrument that was at fault rather than the product.** Three
> `live-pipeline-probe.py` runs against the deployed `7a4f59c` measured that **the session-end sweep
> runs and publishes on a real meeting**: `POST …/stop` is reachable by *both* capture and view
> authority, the **`/live` portal's Stop button already calls it**, a stop through it **revokes view
> authority immediately (401)**, and the stop response carried **19 label-changing corrections on 31
> spans** (18 × `S00 → S01`, words byte-identical in every one). The loop had inferred the opposite
> from `identity_finalized` firing 0 times — but that event is written to an **in-memory** list,
> never to the journal, **inside** the same `stop` that revokes view authority and releases the
> session, so **no client can read it** (measured: 401 with the view token, 403 `session is not owned
> by this device.` with the capture token). Zero sightings was the expected reading whether it ran or
> not.
> **What this changes in the ask:** §4(c)'s last sentence — *"step 3's session-end sweep has never
> run in a real meeting"* — is **withdrawn**; candidate 60 is a client defect worth fixing on its own
> merits and buys neither convergence nor the event. §4(b) is **unchanged and now larger**: it should
> cover the session-end half's *payload* too, since a reader can see that labels moved but never what
> the sweep decided. **§§1–3, the whole candidate-55 case, and the ordering are untouched** — the
> probe's meeting held 2 canonical speakers for 2 real voices, so it says nothing against iteration
> 5's measurement that at F2's 8.4 references per voice the sweep is 84.1 % `kept_ambiguous`.


*Written by the loop for the operator, run `20260729-094359` iteration 6. Nothing here has been
implemented; every number below is measured, and every proposal is a proposal.*

This is the loop's request for a **ninth** amendment. `merge-keeper.sh`'s `expected_main` guard
refuses a ninth merge, and candidates 55, 60 and 65 are tracked product source under the
post-merge freeze, so none of it can start without you.

---

## 1. The one-sentence finding

**Fourteen of the sixteen canonical speakers a real 300-second meeting produced were minted from
audio the system had already refused to embed** — and that, not the album and not the sweep's
logic, is why neither half of Phase N step 3 publishes a correction on the deployed system.

## 2. What is measured

`scripts/ralph-afk/birth-floor-probe.py`, rc=0, offline, no host and no product change, over the
two real meetings whose span bodies survive: **F2** (300 s certification on the deployed
`7a4f59c`, album live) and **F3** (17-minute soak on `42abc5a`). Evidence
`/tmp/i6-birth-floor.txt` and `/tmp/i6-birth-floor.json`.

Every canonical speaker is classified by what its **birth span** gave it:

| birth state | what the speaker holds | F2 | F3 |
| --- | --- | --- | --- |
| **no_reference** — no segment cleared the 0.5 s evidence floor, so the encoder was never asked for a vector | nothing at all | **14** | **13** |
| **provisional** — cleared the evidence floor, not the 1.0 s album admission | one stand-in, never averaged, **unmergeable** | 1 | 1 |
| **banked** — cleared admission at birth | an admitted exemplar, mergeable | **1** | **2** |

The words those fourteen slots were spent on, verbatim from the published transcript:

```
S02  span 16  spoken 0.600 s  embedded 0.000 s  '........................'
S03  span 16  spoken 0.600 s  embedded 0.000 s  '........................'
S04  span 19  spoken 0.260 s  embedded 0.000 s  '...'
S05  span 20  spoken 0.160 s  embedded 0.000 s  'Mm-hmm.'
S09  span 36  spoken 0.400 s  embedded 0.000 s  "I'm sorry, I can't assist with that request."
S10  span 39  spoken 0.120 s  embedded 0.000 s  'Hi.'
...
```

One span (`16`) of pure ellipsis — the decoder emitting *no words at all* on the silence window —
minted **two** canonical speakers. F3's list is the same shape with `Hi.` in place of `...`.

*The mechanism is one site with no duration condition on it.*
`BoundedCausalIdentityPreparer.prepare` (`live_identity.py:129`) births a canonical speaker for
every local speaker that did not match, unconditionally. The evidence floor is a layer down
(`live_provider_bundle._speaker_intervals_by_label`, `min_segment_samples` 8000) and is applied
**per segment**, so F3's `S04` — 1.08 s of speech in nine 0.12 s fragments — produced no vector
either.

## 3. Why this is the load-bearing item, and why the ordering matters

Iteration 5 (`sweep-multiplicity-probe.py`, real encoder geometry, controls on both sides)
measured that the inert sweep has a **product** cause, not a single factor:

| reference set | refs/voice | `kept_ambiguous` |
| --- | --- | --- |
| album as built (control) | 1.40 | **1.1 %** |
| multiplicity alone — split over 2, banked | 1.40 | **1.1 %** |
| stand-ins alone — no split | 1.40 | **3.8 %** |
| **both — split over 2, stand-in** | 2.40 | **74.4 %** |
| **both, at F2's own ratio** | **8.40** | **84.1 %** |

`_album_view`'s **merge** is the sweep's defence against multiplicity, and an unbankable
reference disables it. This probe measures the two quantities that product is made of, on the
real meetings, and they are the same defect: **one birth condition produces both.**

And it predicts what a birth floor would buy, on the quantity the album's admission gate already
uses:

| birth floor | F2 canonical speakers | refs/voice | F3 | refs/voice |
| --- | --- | --- | --- | --- |
| none (deployed) | 16 | **8.0** | 16 | **8.0** |
| ≥ 0.5 s (the evidence floor) | 2 | **1.0** | 3 | **1.5** |
| ≥ 1.0 s (album admission) | 1 | 0.5 | 2 | 1.0 |

1.0–1.5 references per voice is the fixture's own regime (1.40), where iteration 5 measured
**1.1 % ambiguity and 99.26 % final accuracy**. At a floor equal to the album's admission the
survivors are **banked at birth by construction**, so "a canonical speaker with no admitted bank"
stops being representable and the merge defence can never be disabled again.

*This is why 55 comes first.* Wiring `stop` (candidate 60) while 55 is open buys the
`identity_finalized` event and a sweep that abstains on roughly five units in six.

## 4. The ask

One cycle, inside `moss_transcribe_diarize/` and `tests/`, in this order.

**(a) Candidate 55 — a birth must not be minted from audio the system refused to embed.**
Three decisions this cycle must make **explicitly, with the reasoning recorded before the
patch** (the fifth amendment's shape):

1. **What is the birth condition?** The measured options, none of which the loop should pick for
   you:
   - *A floor at the album's admission (1.0 s of embedded speech).* Makes every canonical
     speaker banked at birth; predicted 16 → 1–2 on these two meetings. **Cost:** a genuinely new
     speaker whose first turn is short is unlabelled until they speak once at length — the span
     publishes under `S00` (J2), the ledger retains it (decision 8), and the sweep can relabel it
     retrospectively. That is deferred labelling, not lost labelling — *provided* a sweep
     publishes, which is why (c) belongs in the same cycle.
   - *A floor at the evidence floor (any embedded speech at all).* Weaker and simpler: refuses
     only births that hold literally nothing. Predicted 16 → 2–3.
   - *Neither — let the sweep merge unbankable references instead* (relax Phase N decision 7).
     Restores the defence without touching birth semantics, but a merge would then be decided by
     vectors the admission gate exists to distrust.
   - **Measured wrong, recorded so it is not re-proposed:** raising `max_speakers` 16 → 32/64.
     Iteration 16 measured +4.5 pp of *live* album accuracy on the fixture, but by iteration 5's
     mechanism it raises references per voice, so it should make the sweep **more** inert on a
     real meeting. That last clause is an inference from the mechanism, not a measurement.
   - **Also measured wrong:** lowering `min_segment_samples` so short turns do produce vectors.
     At 0.5 s two samples of the *same* speaker agree at 0.378 while two *different* speakers
     reach 0.360; the distributions overlap.
2. **What does a refused birth publish?** The loop's reading is that it is J2's existing abstain
   path — the span commits, unattributed, under `S00`, and never ends the meeting. Confirm or
   replace it.
3. **Does this contradict ADR-0002?** Phase N decision 3 records that *"ADR-0002 requires birth
   semantics to be unchanged"*, and a birth floor changes them. The loop believes the ADR's
   constraint was about the *album* not altering birth, not about birth being correct as
   written — but that is your document and your call, and it is the reason this needs an
   amendment rather than being covered by *"Phase N remains authorized."*

**(b) Candidate 65's diagnosability half** — the cheap half, and it should ship in the same cycle
because it is how the next run measures whether (a) worked. `sweep_now` sets `_unconsumed` and
logs **only when the revision is non-empty**, so an empty cadence sweep is indistinguishable from
one that never ran. F2 crossed five 60 s deadlines and left no record of any of them. Phase N
decision 11 already records `identity_finalized` unconditionally for exactly this reason; grant
the cadence half the same ruling.

**(c) Candidate 60 — a clean stop must reach the server**, sequenced with or behind (a). A
transport call after the final drain, with the fifth amendment's rule that a stop which cannot
reach the server must still stop locally. Measured three times: view authority outlives a clean
stop by up to the 30 s helper lease (29.4 s / 29 s).
**Corrected in iteration 7:** this entry used to end *"…and `LiveServiceRuntime.
_finalize_identity_locked` hangs off that route and nothing else, so step 3's session-end sweep has
never run in a real meeting."* That is **withdrawn** — the route works, the portal's Stop button
calls it, and a stop through it revoked view authority in 0 s and published 19 corrections. What is
left is exactly what 60 was first filed as: **the Mac client does not call a route that works**, so
`mtd-capture stop` leaves view authority alive for up to 30 s and skips the final sweep the portal's
Stop would have run. Worth fixing; not the item that buys convergence.

**Coverage the cycle must close, because it is what let all of this ship green.** Nothing in the
suite asserts anything about *what a canonical speaker was born from*. Add a red-before /
green-after node per decision, and one that fails if a birth can be minted from a span with no
embedded evidence.

**Gate.** Full Swift/Python; `birth-floor-probe.py` re-run against a fresh F2, requiring
references per real voice at or below the fixture's 1.40 and a non-zero count of published
corrections; then one further reviewed no-ff merge through `merge-keeper.sh` (advance
`expected_main` **in-script**, never by CLI override), push, redeploy, and re-run F1 and F2.

## 5. Not in this ask, and why

- **Candidate 64** (the decoder-RTF clause measures per-call overhead on a sub-100-ms span) and
  **F1's latency RED** are *gate definitions*. They need a ruling from you, not a fix from the
  loop, and they are independent of everything above.
- **Candidate 58** (the replay evaluator calls a declared absence an invalid measurement) is real
  but costs nothing today.
- **The F2 system-audio-denied variant** would spend a TCC grant. The loop will not attempt it.
- **F1/F2's "two speakers" half** is bounded by m4mbp's built-in microphone, measured five times.

## 6. Honest limits of the evidence above

1. **The floor table is a counterfactual, not a simulation.** Suppressing a birth changes the
   matcher's later inputs, so a voice refused at its first short turn may birth at a later long
   one. The survivor counts are therefore a **lower bound** on the canonical count under a floor,
   and an upper bound on births suppressed.
2. **Both meetings carried two voices, both on the system lane** (candidate 51). A real
   multi-person meeting is where a birth floor's deferred-labelling cost would actually be felt,
   and this loop cannot produce one.
3. **The span bodies are a prefix** — 154 of 171 spans for F2, 414 of 443 for F3 (candidate 61).
   Every birth in both runs falls inside the prefix, so the classification is complete even
   though the coverage is not.
4. **Iteration 5's accuracy column is a model collapsing, not a forecast.** It holds the live
   labels healthy while fragmenting only the album; a real meeting fragments both together.
