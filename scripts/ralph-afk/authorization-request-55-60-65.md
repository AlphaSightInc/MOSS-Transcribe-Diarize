# Authorization request — candidates 55, 65, 60, the latency remedy, 66, and Phase N step 4

*Written by the loop for the operator, run `20260729-094359` iteration 6, and **kept current in
place** — corrections are applied to the body, not stacked on top of it, so what you read below is
what the loop currently believes. Nothing here has been implemented; every number is measured, and
every proposal is a proposal.*

This is the loop's request for a **ninth** amendment. `merge-keeper.sh`'s `expected_main` guard
refuses a ninth merge, and every item below is tracked product or test source under the post-merge
freeze, so none of it can start without you.

> **ANSWERED — 2026-07-29, prd.md's ninth amendment (Phase Q, operator commit `6e3e4fe`).** This
> document is kept because the amendment tells the loop to read it, and because §2, §3b and §6 are
> the measurements behind the decisions. **Its status, item by item:**
>
> | item | outcome |
> | --- | --- |
> | **(a)** candidate 55, the birth floor | **GRANTED**, and the operator chose **option 1** — the floor sits at the album's admission, **1.0 s of embedded speech** |
> | **(b)** candidate 65, the empty cadence sweep | **WITHDRAWN.** Both sweeps publish; the two *"it never runs"* readings were the loop's own blind instruments. Do not re-file it |
> | **(c)** candidate 60, the clean stop | **GRANTED**, on its own merits — it buys neither convergence nor `identity_finalized` |
> | **(d)** the latency remedy / cadence | **GRANTED as a rule, not a value:** move **both** constants or neither, and ship the **enforcing node** regardless of what is decided about the cadence |
> | **(e)** candidate 66, browser-storage regression | **not mentioned.** Still needs an authorization |
> | **(f)** Phase N step 4, batch unification | **DEFERRED in as many words** — *"Out of scope … worth its own authorization later"* |
> | §5's candidate 64, the RTF gate | **GRANTED as a definition, not a filter:** state a minimum span duration, **derive** it from measurement rather than choosing it to pass, and **always report the excluded count** |
>
> §5's other three deferrals (candidate 58, the system-audio-denied variant, the two-speaker half)
> are untouched and still stand.

> **What has changed since this was written, so you can see which of your own earlier readings are
> stale.** Each correction is already applied in the body.
>
> | when | what the loop had wrong, and what it measured instead |
> | --- | --- |
> | it. 7 | §4(c) said *"step 3's session-end sweep has never run in a real meeting."* **Withdrawn.** The session-end sweep runs and publishes on the deployed service — `POST …/stop` is reachable by *both* authorities, the `/live` portal's Stop button already calls it, a stop through it revokes view authority **immediately (401)**, and it carried **19 label-changing corrections on 31 spans**. The loop had inferred the opposite from `identity_finalized` firing 0 times; that event is written to an **in-memory** list no client can read, so zero sightings was the expected reading whether it ran or not. |
> | it. 9 | §3 predicted the sweep would *consider and refuse* candidate 55's minted labels (`kept_ambiguous`). It does not — **it never sees them.** §3b carries the corrected mechanism. |
> | it. 12 | §1's headline — *"neither half of Phase N step 3 publishes a correction"* — is **FALSIFIED**. The **cadence** sweep published three mid-meeting revisions during the 17-minute F3 soak on the deployed `7a4f59c`. Both halves publish. §1 and §4(b) are rewritten; the ask is *narrower and better founded*, not weaker. |
> | it. 15 | Counts brought current (**49** corrections across **four** deployed swept meetings, not 46 across three). **§4(d) is new** and prices F1's latency RED, which §5 previously deferred to you with no number attached. **§4(e) is new** — candidate 66, the cheapest item on the list. |
> | it. 16 | §4(d)'s cost paragraph said the change makes the portal issue *"twice as many snapshot+events pairs (F3: 381 polls → ~760)"*. **Wrong stream.** The gated fetch p95s are measured by the **app's own probe** at a fixed **0.25 s** cadence (4001 samples over F3's 1019.7 s); the 381 was the *soak driver's* view polls. Halving the portal's poll adds load only from a **real browser**, and no certification run opens one — so the risk is that the gate **under-counts** the cost, not that the benefit shrinks. The §4(d) trap and §6(5) are rewritten; the ask itself is unchanged. |
> | it. 18 | **§4(f) is new** — Phase N step 4 (batch unification). Nothing here is a correction: the item is added because it now has a *price* on both sides. Iteration 17 measured the engine it replaces (**80.07 % / 63.33 %**, Tier B worth **0.00 pp**), and iteration 18 measured the counterfactual (**100.00 %**, **+19.93 pp**, one canonical per true speaker) on the identical corpus and scorer. The work is already authorized by prd.md; the **ninth merge** is what is not, which is why it appears in this document at all. §6(6) and §6(7) carry its two limits. |
> | it. 20 | **§6(7) is closed and §6(6) has a floor, and one of §4(f)'s two readings is FALSIFIED.** Iteration 18's +19.93 pp was measured with a *perfect* local diarization, which made the two readings of step 4 indistinguishable at 100 % each. Degrade the causal pass and *"the album replaces both tiers"* is **worse than the engine it replaces** (−27.34 pp at 30 % over-segmentation) while *"the album replaces Tier B only"* wins everywhere (+21.50). **Step 4 must keep Tier A.** The sweep is also no longer untested: 25 corrections / 6 merges worth **+14.30 pp** — and, in the other direction, **−4.06 pp** under label confusion. §4(f), §6(6) and §6(7) are rewritten and §6(8)/§6(9) are new; the ask itself is unchanged. |

---

## 1. The one-sentence finding

**Fourteen of the sixteen canonical speakers a real 300-second meeting produced were minted from
audio the system had already refused to embed** — and because a sweep can only re-match evidence
that exists, those fourteen labels are unreachable by any sweep at any cadence: **all 49 corrections
the deployed sweep has published across four real meetings are `S00 → Sxx` fill-ins of a *missing*
label, and not one is a reassignment.**

*The earlier form of this sentence — "…which is why neither half of Phase N step 3 publishes a
correction on the deployed system" — was falsified by direct measurement in iterations 7 and 12.
Both halves publish. The defect is not that the sweep is silent; it is that the sweep has never been
observed to move a label that was already set, which is exactly what repairing candidate 55 would
require.*

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
`identity_finalized` event and a sweep that cannot reach the labels 55 minted — see §3b, which
measured that on the deployed service and changed the reason.

## 3b. The deployed measurement, and it CORRECTS §3's mechanism

Run `20260729-094359` iteration 9 reproduced §2's shape on the **deployed** `7a4f59c` on demand —
`live-pipeline-probe.py --lane-audio fragmented`, 150 s, one bankable voice plus sub-floor
interjections every 3 s — and ran a 150 s `continuous` control through the same instrument. Both
committed exactly 61 spans, 0 non-200s, `stop` 200.

| | fragmented | continuous (control) |
| --- | --- | --- |
| canonical speakers | **16** | 4 |
| labels appearing on ≤ 2 spans | **15** | 3 |
| spans containing `S00` | 8 | 34 |
| `speaker_capacity_exceeded` abstains | 7 | 0 |
| session-end sweep revisions | **7 (11.5 %)** | **20 (32.8 %)** |
| of the abstained spans | **7 of 8 (87.5 %)** | 20 of 34 (58.8 %) |
| reassignments (`Sxx → Syy`) | **0** | **0** |

**§3's table predicted the sweep would consider these units and refuse them (`kept_ambiguous`).
It does not. It never sees them.** A speaker born from audio below the evidence floor has no
embedded unit, so it has no ledger entry, so it is not in the sweep's input at all — the sweep's
*conditional* repair rate on the fragmented meeting is **higher** than the control's. What
fragmentation destroys is the **supply** of repairable spans, by converting a span that would have
abstained into one carrying a confident junk label.

**The confound-free fact, and it is the strongest one here.** Across all **four** deployed meetings
this loop has swept — iteration 7's 19 corrections, iteration 9's 7 and 20, and iteration 12's 3 —
**every one of the 49 published corrections is `S00 → Sxx`, and not one is a reassignment.** The
deployed sweep's only observed product is filling in a label that was missing. It has never been
observed to move a label that was already set, which is precisely what repairing candidate 55's
fragmentation would require.

*Updated in iteration 12, and it strengthens the case rather than weakening it:* the fourth meeting
is the **16-minute F3 soak on the deployed `7a4f59c`**, which minted **16 canonical speakers for 2
real voices** and saturated the cap at **t+138.1 s of a 1029 s meeting** — so ~87 % of a real
17-minute meeting ran with no slot left for an arriving voice. Its **cadence** sweep crossed ~17
deadlines, repaired **3** of 122 abstained spans, and all three were `S00 → Sxx`. Candidate 55's
cost therefore survives the first cadence sweep this loop has ever observed to publish.

*Honest limit:* the two runs differ in two variables, not one — fragmentation **and** the number of
embeddable voices (the fragmented run's peer lane carries one voice, the control two), so
11.5 % vs 32.8 % is not a single-variable contrast and part of the control's larger abstain pool is
two-voice ambiguity. The reassignment count and the 16-for-one-voice shape do not depend on the
contrast.

*What this changes in the ask:* nothing about **(a)**, which gets stronger — a birth floor is now
the only one of the three items that touches this defect at all, because 60 and 65 govern *reaching*
and *reading* the sweep and the sweep provably cannot repair a minted label whatever cadence it runs
at.

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

**(b) Candidate 65 — *an empty cadence sweep leaves no record to tell "found nothing" from "never
ran."*** The cheap half, and it should ship in the same cycle because it is how the next run
measures whether (a) worked. `sweep_now` sets `_unconsumed` and logs **only when the revision is
non-empty**, so a cadence deadline that produced nothing is indistinguishable on every surface from
a deadline that never arrived. Phase N decision 11 already records `identity_finalized`
unconditionally for exactly this reason; grant the cadence half the same ruling, and extend it to
the session-end half's **payload** — a reader can see *that* labels moved but never *what the sweep
decided*.

*This entry was re-titled in iteration 14 and its premise corrected in iteration 12.* It used to
read *"neither half of Phase N step 3 produces a correction on a real meeting"*, and that is
measured false: F2 crossed **five** deadlines and published **0**, F3 crossed **~17** and published
**3**. What separates them is meeting **length**, not a broken sweep — and **neither run's silent
deadlines said so anywhere**, which is the whole of what is still wrong. The ask shrinks from "make
the sweep work" to "make it say what it did"; it did not go away, because ~14 of F3's own deadlines
are still unaccounted for on every surface a reader has.

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

**(d) F1's latency RED — your own plan's SECOND ordered remedy is now measured, and it is the cheap
one.** *New in iteration 15. `scripts/ralph-afk/latency-remedy-probe.py`, rc=0, 14/14 checks,
offline, no host and no product change; it reads F3's real `latency-final.json` and two tracked
source constants.*

The PRD answers a latency miss with *"the plan's ordered remedies (2.0 s span cap, then 0.5 s poll
interval), never by relaxing the gate."* Until now the loop had no number for either, so §5 handed
the whole latency RED back to you unpriced. Here is the second one.

The gated number is exactly `committedP95 + portalCycle + snapshotFetchP95 + eventsFetchP95` —
verified to **0.000000000 ms residual** on F3's own report. The **portal cycle term alone is a whole
1000.0 ms, 24.4 %** of the 4106.5 ms F3 measured. Halving the poll subtracts **exactly 500.0 ms**,
because that term is additive and independent of the two measured fetch p95s:

| certification run | measured | at a 0.5 s poll | gate | verdict now → then |
| --- | --- | --- | --- | --- |
| **F1** on `7a4f59c` | **4150.8 ms** | **3650.8 ms** | 4000 | **RED → GREEN**, +349.2 ms margin |
| F2 on `7a4f59c` | 4078.6 ms | 3578.6 ms | 6000 | GREEN → GREEN |
| F3 on `7a4f59c` | 4106.5 ms | 3606.5 ms | 6000 | GREEN → GREEN |

F1 missed by **150.8 ms**; the remedy is worth **3.3×** that.

**Your plan lists the two remedies contract-expensive first.** Remedy 1, the 2.0 s span cap, changes
`hard_cap_samples` 40000 — which **this PRD's own Constraints declare a domain-contract value** to
be "implemented exactly rather than generalized away", so the loop cannot touch it under any
reading. Remedy 2's portal poll appears **nowhere** in that list (checked term by term). So the
cheaper remedy is also the only one that does not require you to move the contract.

***The trap, and it is why this needs your word and not the loop's judgement — filed as candidate
68. Sharpened in iteration 16: the two constants are causally disconnected in BOTH directions.***
That 1000 ms lives in **two constants in two languages** — `live_portal.py:146`
`const pollDelayMs = 1000` and `CaptureLatencyProbe.swift:18` `portalCycleSeconds = 1.0` — and
**nothing ties them**. No Python test asserts the portal's cadence; nothing crosses the language
boundary; and the single assertion that exists (`CaptureControllerTests.swift:5699`) compares the
Swift constant **to itself**. Measured this iteration on tracked source: `portalCycleSeconds` reaches
**no scheduling site at all** — its three sites are the declaration, a report default and the
`renderBound` sum — while `pollDelayMs`'s two sites are the constant and `schedulePoll(pollDelayMs)`
in the served script, with **0 hits anywhere under `macos/`**. So:

- editing the **Swift** constant alone takes 500 ms off a PRD acceptance number **with no change
  whatever to what a human sees** — relaxing the gate while looking like a remedy;
- editing the **server** constant alone gives a human the entire 500 ms improvement and moves the
  gated number by **0.0 ms** — the remedy would look like it did nothing.

Either half alone is wrong, in a different direction. **Any authorization here must require both
constants to move together and a test that fails when they disagree.** That test is the durable part
of this ask and is worth having whatever you decide about the cadence: today the user-visible latency
clause is measured through an unenforced duplicate.

**What it costs — measured in iteration 16, and iteration 15's draft named the wrong request
stream.** The gated `snapshotFetchP95` / `eventsFetchP95` are measured by the **app's own probe**,
which polls on `CaptureLatencyContract.pollInterval` = **0.25 s** (`main.swift` builds its scheduler
from that constant) and never on the portal's cadence: F3's report carries **4001** snapshot fetches
and 4001 events fetches over a **1019.7 s** meeting — an implied **0.2549 s** interval, +1.9 % of
0.25. The "381 polls → ~760" this paragraph used to carry was the **soak driver's** view-poll stream
(381 rows at 2.68 s), a stream the gated number never measures. So halving `pollDelayMs` doubles
**a real browser's** request rate and nothing else — and F1/F2/F3 run with **no browser open at
all**. The honest statement of the risk is therefore *smaller and different*: a certification re-run
would record the full −500 ms while **not** measuring the added server load a real viewer would
create. F2's 4766 requests all answered 200, which is headroom evidence, not proof at double the
browser rate.

**What it does not buy:** F1's *other* RED. Candidate 64 — decoder p95 RTF **2.365** carried
entirely by three spans of 0.03 / 0.06 / 0.07 s — is untouched by this and stays a gate-definition
ruling in §5.

**(e) Candidate 66 — the portal's browser-storage hygiene has evidence but no regression.** The
cheapest item on this list by a wide margin, included because it is two asserts and one accessor and
it protects a PRD clause that is currently green *by probe only*. `tests/test_live_portal.py` builds
a recording `localStorage`/`sessionStorage` Proxy and threads `storageWrites` back to Python through
two scenarios — and **no node asserts it** (measured: `grep -n storageWrites tests/test_live_portal.py
| grep -ci assert` → **0**, while the file's 14 nodes pass). Iteration 10 measured the deployed page
green on all five secret-hygiene clauses with six negative controls detected, so the PRD row is
answered **today**; nothing keeps it answered tomorrow, and nothing runs the probe automatically.
*Shape of the fix, not a decision:* assert `storageWrites == []` in the two nodes that already
receive it, and give the harness's fake `document` a recording `cookie` accessor so the surface the
static check names is the surface the runtime check can see.

**(f) Phase N step 4 — a merge slot, now that batch unification has a measured price.** ADR-0002's
own fourth of four. prd.md's *"Phase N remains authorized. Take it in ADR-0002's shape"* covers the
**work**; what it does not cover is a **ninth merge**, and `merge-keeper.sh`'s `expected_main` guard
refuses one. So the loop can write step 4 and cannot land it — and tracked product source sitting
unmerged on this branch breaks the invariant that an offline probe speaks for the deployed service.
Two iterations have priced it rather than argued it, on the same eight LibriSpeech meetings and the
same `speaker_accuracy`:

- **iteration 17** — the engine step 4 would replace scores **80.07 % mean / 63.33 % min** where the
  live album scores 93.44 / 92.18, and its Tier B moves that by **exactly 0.0000000000 pp** at the
  album's thresholds *and* at k=10, because `_tier_b_evidence:726` offers Tier B only singleton
  components (36 of 71) and `cannot_link_conflict` refuses 195 of 310 proposals.
- **iteration 18** — the counterfactual. The **production live identity engine**
  (`assign_speakers` + `FingerprintAlbum` + `sweep`) driven over the *identical* windows scores
  **100.00 % / 100.00 %** — **+19.93 pp** — with exactly one canonical per true speaker (**30 births
  for 30 speakers**) against batch's **16-17 labels for 6 speakers**. It wins at **batch's own
  0.70 / 0.20** thresholds too (+19.90 pp), so step 4 is not a recalibration in either direction; only
  **9 of 335** same-speaker cross-window node pairs fall below batch's 0.70 floor, so the floor is not
  what loses the 20 pp either; and **Tier A adds zero** once the album is present, at its most
  favourable (the probe hands it a perfect local diarization).

- **iteration 20** — the same two engines under a **deliberately imperfect causal pass**, which is
  what §6(6) and §6(7) said was missing. `scripts/ralph-afk/degraded-causal-pass-probe.py`, rc=0,
  offline, one monkeypatched `build_case` so both engines provably see the same degraded labels; the
  `none` control reproduces 80.0667 / 63.3330 / 100.0000 / 100.0000 exactly.

  | causal pass | batch | album only | +sweep | Tier A + album |
  | --- | --- | --- | --- | --- |
  | perfect (the control) | 80.07 | **100.00** (+19.93) | 100.00 | 100.00 |
  | over-segmented @0.30 | 57.84 | 30.50 (**−27.34**) | 44.80 (−13.04) | **79.34** (+21.50) |
  | over-segmented @0.60 | 42.73 | 17.74 (**−24.99**) | 27.82 (−14.91) | **58.58** (+15.85) |
  | confused @0.10 | 47.17 | 87.45 (+40.27) | 87.45 | **88.47** (+41.29) |
  | confused @0.25 | 27.06 | **51.06** (+24.00) | 47.00 (−4.06 vs unswept) | 47.00 |

  **The degradation separates two readings of step 4 that the perfect pass could not tell apart.**
  At 100 % they were both 100 %; under over-segmentation *"the album replaces both tiers"* is
  **worse than the engine it replaces** and *"the album replaces Tier B only"* wins everywhere.
  **Step 4 must keep Tier A**, and this measurement is why.

  **The mechanism is counted, not inferred.** At @0.30 the causal pass adds **44** nodes and the
  album mints only **6** extra canonicals — so **38 cut halves were matched onto an *existing*
  canonical**. `assign_speakers` is one-to-one *within a span*, so the second half of a cut turn
  cannot take its own speaker's canonical and is pushed onto another speaker's, which is worse than
  a spurious birth because it also poisons that speaker's album centroid. **A window is not a span:
  two local labels in one window can be the same person, and the live path's one-to-one rule is
  false on the batch path.** That is a design constraint on step 4, not a threshold.

*This asks for the merge slot, not a decision:* the shape is settled by ADR-0002 and by decision 5 —
the batch path calls `live_identity.assign_speakers` against a `FingerprintAlbum`, never a third
implementation. *The honest limits are §6(6), §6(7) and §6(9), and they are load-bearing: 100 % is a
ceiling, the winning arm keeps Tier A, and Tier A's own arm is an upper bound.*

**Coverage the cycle must close, because it is what let all of this ship green.** Nothing in the
suite asserts anything about *what a canonical speaker was born from*. Add a red-before /
green-after node per decision, and one that fails if a birth can be minted from a span with no
embedded evidence.

**Gate.** Full Swift/Python; `birth-floor-probe.py` re-run against a fresh F2, requiring
references per real voice at or below the fixture's 1.40 and a non-zero count of published
corrections; for (d), a node that fails when the two poll constants disagree — the durable half, and
the only thing that makes moving either constant honest — plus `F1` re-run, which confirms the
−500 ms and (see §6(5)) deliberately does **not** price a real viewer's load; then one further
reviewed no-ff merge through `merge-keeper.sh` (advance
`expected_main` **in-script**, never by CLI override), push, redeploy, and re-run F1 and F2.

**If you want to grant only part of this, the order by cost is (e), (d), (b), (c), (a), (f).** (e)
and (d) are each a handful of lines and each closes or protects a PRD acceptance clause; (a) is the
one that needs three decisions from you before any patch; (f) is the largest by far — a new resolver
on the batch path — and the only one whose *work* is already authorized and whose *merge* is not.

## 5. Not in this ask, and why

- **Candidate 64** — the decoder-RTF clause measures per-call overhead on a sub-100-ms span — is a
  *gate definition* and needs a ruling from you, not a fix from the loop. Three honest answers exist
  and the loop must not pick: **(a)** rule the clause per-span as written and accept that a meeting
  with micro-endpoints fails it; **(b)** rule it on decode *throughput* — total decode wall over
  meeting wall, which is what "the decoder keeps up" means; **(c)** keep per-span with a stated floor
  duration. Measured on the **same deployed code the same day**: F1 gave p95 **2.365** over 52 spans
  while F2 gave **0.577** over 171, with the same micro-spans present in both — at n=171 they fall
  below p95, at n=52 one of them *was* p95. F1's aggregate was **17.09 s of decode over an 86 s
  meeting (0.20, 5× headroom)**. So today the clause's verdict is a function of the meeting's span
  count rather than of whether the decoder kept up, which is (b)'s argument made by measurement.
  **Do not read that as the loop choosing (b)** — it is the operator's ruling, and the reasoning must
  be recorded before any reducer change.
- **Candidate 58** (the replay evaluator calls a declared absence an invalid measurement) is real
  but costs nothing today.
- **The F2 system-audio-denied variant** would spend a TCC grant. The loop will not attempt it.
- **F1/F2's "two speakers" half** is bounded by m4mbp's built-in microphone, measured **six** times
  now (the sixth in F3, against two MacStudio deliveries at volume 70).

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
5. **§4(d)'s 500.0 ms is arithmetic on a contract term, not a re-run.** It is exact for the
   *analytic* half by construction — the term is additive and the identity was verified to nine
   decimal places on real data. *Corrected in iteration 16:* this limit used to read "it does not
   model a fetch p95 rising under twice the request rate", which named a stream the gated number does
   not measure. The gated fetch p95s come from the **app probe's** fixed 0.25 s poll (4001 samples
   over F3's 1019.7 s), which neither constant touches. What is genuinely unmeasured is the opposite
   direction: the added load of a **real browser** polling at 2 Hz, which no certification run
   creates because none of them opens a browser. A re-run of F1 therefore confirms the −500 ms and
   still does **not** price the viewer load — say so rather than reading a green re-run as proof.
6. **§4(f)'s 100 % is a CEILING, and iteration 20 measured how far below it the engine falls.** A
   150 s window hands the matcher **20-61 s** of one speaker (median per meeting, minimum 1.0 s),
   and at that duration the worst per-meeting gap between the *lowest* same-speaker cross-window
   cosine and the *highest* cross-speaker one is **+0.190** (best +0.616). On clean read speech with
   a perfect local diarization, window stitching is a separable task. So the number to carry forward
   is **not** "batch will score 100 %" but "an engine that loses ~20 pp on a task this separable is
   losing it **structurally, not perceptually**" — the cause and the direction. *Iteration 20 put a
   floor under that:* degrade the causal pass and the winning arm falls to **79.34 %** (@0.30
   over-segmentation) and **58.58 %** (@0.60), still ahead of batch by **+21.50** and **+15.85 pp**.
   The ranking survives; the level does not. The same §7 caveat ADR-0002 carries applies: a real
   conversational recording is still required, and this corpus cannot produce one.
7. **§4(f)'s sweep half is NO LONGER untested — iteration 20 closed it.** It used to read: the
   production `sweep()` proposed **0** corrections and **0** merges on the batch path because the
   causal pass was already perfect, which is convergence by vacuity rather than evidence that step
   3's machinery helps a batch resolver. Under over-segmentation the sweep is **not** vacuous:
   **25 corrections / 6 merges** at @0.30 and **23 / 16** at @0.60, moving the mean **30.50 → 44.80**
   (+14.30 pp) and **17.74 → 27.82** (+10.08 pp), each reaching a **fixpoint** (residual 0). *The
   part that is not a win:* under label **confusion** at @0.25 the sweep moved the mean the wrong
   way, **51.06 → 47.00 (−4.06 pp)** — a merge over blended centroids can join two real speakers.
   Step 3's machinery helps a batch resolver against over-segmentation and can hurt it against
   confusion, and step 4's gate must measure both directions rather than only the repair.
8. **Iteration 20's error model is synthetic and uniform.** A real diarizer errs where the audio is
   hard — short turns, overlaps, low energy — and this one errs uniformly at random, so the degraded
   scores are optimistic about *which* units break and honest about *how many*. Read the engine gap
   and the sweep counts, not the absolute accuracy.
9. **The degradation moves labels and never boundaries, and Tier A links on boundaries**, so
   `tier_a_album` — the arm that wins under over-segmentation — is an **upper bound**. It is not a
   biased comparison: the batch baseline runs the same Tier A over the same exact intervals, so the
   inflation is shared and the gap is the comparable quantity, while `album_only` reads no boundary
   at all and is the conservative arm. **A boundary-jitter degradation is the probe that would close
   this**, and the loop can run it without an authorization.
8. **§4(d) deliberately leaves the larger term alone.** Committed latency is **2674 / 2680 ms** of
   the ~4.1 s, and that is what remedy 1 (the span cap) attacks. This ask does not touch it, so it
   buys the 4000 ms gate back and no more — a future latency regression in the committed half would
   consume the +349.2 ms margin.
