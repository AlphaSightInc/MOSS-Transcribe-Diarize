# Authorization request — candidates 55, 65, 60, the latency remedy, and 66

*Written by the loop for the operator, run `20260729-094359` iteration 6, and **kept current in
place** — corrections are applied to the body, not stacked on top of it, so what you read below is
what the loop currently believes. Nothing here has been implemented; every number is measured, and
every proposal is a proposal.*

This is the loop's request for a **ninth** amendment. `merge-keeper.sh`'s `expected_main` guard
refuses a ninth merge, and every item below is tracked product or test source under the post-merge
freeze, so none of it can start without you.

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

**If you want to grant only part of this, the order by cost is (e), (d), (b), (c), (a).** (e) and
(d) are each a handful of lines and each closes or protects a PRD acceptance clause; (a) is the one
that needs three decisions from you before any patch.

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
6. **§4(d) deliberately leaves the larger term alone.** Committed latency is **2674 / 2680 ms** of
   the ~4.1 s, and that is what remedy 1 (the span cap) attacks. This ask does not touch it, so it
   buys the 4000 ms gate back and no more — a future latency regression in the committed half would
   consume the +349.2 ms margin.
