# R5B-FIX5B — measured correspondence and independent admission

## Contract

**Question:** can two request groups continue the same evidence partition without a common-word collision pooling different people? Can rejected groups coexist with a valid reply without vetoing it?
**Primitives:** committed timed word owns speech custody; request source partition owns evidence; positive correspondence continues it; local run owns its denominator; published identity labels the admitted speech. None substitutes for another.
**Invariants:** no pooling across unrelated sources; rejected groups neither lend nor veto; existing H hole/ownership/edge/time-shift/fallback rules, sustained .4s/80%/weight15/.6s joins, counters/anchors/caches and final neighbour labels unchanged.
**Unknowns:** fresh provider collision/identity frequency, physical echo cancellation, full two-hour Stop latency. Two-word text correspondence is not acoustic identity proof.
**Falsifiers:** required seam<5/5, stray>0, valid reply<4/4, distinct2+2>0, any recorded negative restored, frozen surface change, cost120>=10s or counter/cache/anchor mutation.
**Tools:** copied pass5 attacks detect the failures; earlier14 pass2/3/4 closure probes detect reopened custody defects; frozen recorded replay measures exact parity; shared-scan cost probe detects unbounded work; full backend checks integration. All provider answers replayed; no provider calls.

## Smallest measured rule

D1 Require two distinct old AND two distinct new timed occurrences on each correspondence edge, using existing text/numeral equality and .1s endpoint tolerance. Deduplicate text/start/end occurrences. Retain ALL raw matches in the existing ambiguity graph: a weak competing label/partition can prevent a join but cannot authorize one. Only qualifying edges continue a partition or move uniquely matched old witnesses. No raw-label/published-ID shortcut.

D2 `LocalVoiceEvidence.local_words` already checks sustained audio,80% and weight15 independently per source partition/run. Remove the redundant outer whole-hole80% veto. Only eligible local words enter the remaining guards and surviving per-run weight15 check; labels assigned afterwards as today. No new audio threshold, cache or counter behavior.

A one-word re-heard prefix is insufficient for correspondence; each separated piece must qualify on its own. Measured English five-word seam saves the four-word suffix4/5 and withholds the weight5 prefix. Two-word-prefix seams remain5/5 across unassigned/born/changed-label/reassigned identities. Minimum positive prefix2 has no spare word margin; prefix1 is deliberately insufficient. Same-request provider misgrouping remains an inherited limit.

## Prototype before absorption

Initial V1 passed original attacks/frozen population but removed weak edges before ambiguity. Two supported split/merge controls then failed V1: the weaker edge's removal hid a possible competing source. V1 is measured-rejected on that shape; sources/results retained under owned evidence `candidate_source_partitions_v1.py`, `prototype-v1/`, `product-v1/weak-ambiguity-red.log`. V1 product replay/backend were deliberately interrupted, not certification results.

Before final product edits, amended in-memory prototype custody16 and19 attack/closure/boundary probes passed. The amendment preserves the original raw ambiguity invariant; no population, metric or decision rule was retuned. Final prototype and unpatched product both completed the full frozen population below. Prototype implementation absorbed; snapshots retained only in owned evidence for review/reproduction.

## Final verdict — PASS

| Gate | Final prototype | Product |
|---|---:|---:|
| Pass5 short-word stray / valid reply |0 /4 of4|0 /4 of4|
| Rejected partition beside same valid reply |4 of4|4 of4|
| Two-person2+2 collision control |0|0|
| Required two-word-prefix identity seams |5 of5|5 of5|
| One-word English prefix boundary |4 of5|4 of5|
| Attack/earlier/boundary probes |19 pass|19 pass|
| Recorded negatives,56 conditions/28 samples/908 words |0 restored|0 restored|
| Isolated controls / whole-engine injections |24 /4 pass|24 /4 pass|
| Frozen C2,127 cells x4 surfaces |exact|exact|
| F2 live/Stop/saved,denominator343 |206 /291 /310|206 /291 /310|
| System names,denominator250 |236|236|
| H100 pairs,lost names /adjacent duplicates |4 /0|4 /0|
| Cost120 candidates,seconds |1.595804|1.611255|
| Cost120 mode1 frames /restored words |720000 /360|720000 /360|
| Empty candidate frames |0|0|

Exact word text/time/labels and saved row states against immutable pass5 C2: zero differences. All131 terminal states match prototype/product except measured wall clocks, which are retained separately per cell. Every non-cost probe state matches exactly. Counters5->5; caches/anchor unchanged; real encoder crop maximum difference0.0. H missing/extra means2.06/1.25; truth error.0907/.1217 unchanged. All131 engine receipts use this worktree's production modules and replayed answers, cost$0. Inherited sweep echo-proxy flags remain with exact microphone output; no scoring changes.

Seven new regression cases fail original integration8c12d38b and pass final product; added weak-partition merge control passes original/final (fails V1). Existing tests unchanged. Targeted141 passed. Required full backend:2851 passed,9 skipped,2 xfailed,27 warnings,37 subtests passed;480.35s. No frontend changes.

## Reproduce / evidence

From worktree, one full product command:
`PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python prototypes/gemini-live/mic-speaker-echo/c5/run.py product`
Use `prototype` for the retained in-memory snapshots; `--probes-only` for just attack/closure controls. Full state printed and retained per probe/cell.

Evidence: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-FIX5B/` — `test-before-after.md`, `copy-adaptations.patch`, `cost-comparison.json`, `product-vs-prototype.json`, each mode's `recorded-comparison.json`, `all-engine-source-custody.json`, `frozen/verdict.json`, original red/candidate/green logs, and `product/full-backend.log`. Original review sources/receipts untouched. File-only local commit; no push/merge/PR/provider/host/port/private-data work.
