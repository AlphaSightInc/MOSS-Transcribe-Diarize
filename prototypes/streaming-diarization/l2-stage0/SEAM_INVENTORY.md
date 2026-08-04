# L2 Stage-0 seam inventory

Measured 2026-08-03/04. This applies the plan's two-adapter rule and deletion test.
Campaign A ended `BLOCKED` at the blind-holdout accuracy gate; therefore no row
authorizes Campaign B or product code.

| Candidate | Two independently useful adapters/callers? | Hidden complexity | Deletion test: where complexity reappears | Locality / testability | Boundary | Stage-0 disposition |
| --- | --- | --- | --- | --- | --- | --- |
| Concrete tape range reader + read lease | One prospective L2 production caller plus a meaningful fault/store test adapter; no production L2 caller exists yet | Bounded ranged reads, sealing, lease ownership, TTL/reap interlock, degraded tape | Finalizer would duplicate range validation, chunk bounds, lease release, and reap exclusion | High; A3 proved lease failures and A4 measured 40,000-sample bounded reads | Internal L2 module | Shape supported, build not authorized because A5 failed |
| Immutable committed-span read model | Prototype candidate consumes exact span/unit/sample mapping; no second production caller | Immutable span IDs, local labels, sample bounds, planner reasons | Raw dictionaries and offset conversion spread through reader, refiner, and publisher | High if restricted to fields a future winner actually consumes | Internal value model | Defer; frozen candidate did not pass holdout, so consumed fields are not a winning contract |
| Concrete bounded finalization coordinator | Lifecycle prototype plus negative-control/fault callers; no production L2 finalizer | `active→closing→finalizing→closed`, one queue/CPU worker, cancel/timeout/shutdown/fallback, terminal visibility | Stop path regains queue ownership, lease cleanup, view authority, and failure-state branching | High; A3 passed 8/8 invariants and detected 3/3 bad controls | Internal deep module, not protocol hierarchy | Lifecycle shape proved; product build not authorized after A5 failure |
| Shared revision application helper | Current L1 coordinator is the only real producer/caller; L2 remains prototype-only | Safe translation of `(span_id, local_speaker)` corrections into `LiveSession.revise_labels` | Today complexity stays localized in L1; deletion creates no duplication until L2 is real | Extraction helps only when two real callers perform identical publication | Internal helper; `LiveSession.revise_labels` remains authority | Do not extract yet |
| `LiveIdentityReviser` as separate injection | No; current optional methods are discovered on the preparer and no L2 injection exists | Finalize provider state and produce L1 `SweepRevision` | Deleting the imagined injection leaves current localized behavior unchanged | No present leverage | Would be internal | Do not force |
| `SpeakerEvidenceSource` protocol | Live provider exists; tape candidate is a failed prototype, not a production adapter | Evidence vocabulary across live intervals, tape windows, and future batch/Lane-B | Premature deletion leaves no duplicated stable cross-path vocabulary | Testability possible only after two accepted consumers converge | Potential internal protocol | Defer |
| `MeetingIdentityEngine` | No second production adapter/caller | Would wrap ingest, evidence, assignment, reconcile, and publication policy | Deleting it today leaves those concerns in their existing deep modules; wrapper adds no earned locality | Fails deletion test now | Neither stable external API nor earned internal seam | Defer |
| `checkpoint()` | No authorized crash/resume caller; startup reap is not resume | Transcript, identity, mixer/lane, config, tape recovery transaction | A partial hook would distribute an incomplete recovery contract | Only valuable as an end-to-end recovery phase | Separate persistence boundary | Separate crash/resume phase |

Measured conclusions:

- A3 supports `finalizing`, bounded queue ownership, and read-lease semantics.
- A4 supports one-thread CPU finalization with 40,000-sample reads under the
  operator-authorized warm/reused envelope.
- A5 development evidence supported the frozen tape family, but the one blind opening
  failed both minimum-gain gates. It therefore does not establish an accepted L2
  evidence adapter or winning committed-span field set.
- The smallest future shared identity seam remains the revision
  data/publication boundary, but extraction waits for real L1 and L2 callers.
