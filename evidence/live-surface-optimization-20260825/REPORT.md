# Live-surface optimization report — 2026-08-25

## Conclusion

**Do not change production.** Fresh measurement shows the actual settled transcript before Stop
is farther from file quality than the campaign baseline implied. A 15-second window / 10-second
stride coherent lexical view is the best next **deployed-shadow** experiment, but it is not
production-qualified because alternate-geometry event-clock latency, live queue behavior, and
final-tail scheduling remain unmeasured.

## Decision framework

The user experiences a sequence, not one “live transcript”:

1. audio ends and the current screen is captured (`pre_stop_immediate`);
2. already-admitted rolling work may finish while the user waits (`pre_stop_settled`);
3. pressing Stop starts an extra drain (`stop_return`);
4. terminal re-decode publishes the durable result (`post_stop_final`);
5. file mode provides the same-audio reference surface (`file`).

A production candidate must improve what is readable at steps 1-2 without depending on Stop,
while keeping first publication, corrections, queueing, GPU work, failures, and file mode within
the handoff gates.

## Findings

### F1 — the previous “pre-Stop” baseline included Stop-time work

Two paired passes over five fully referenced cases yielded 10 observations and 1,320 observed
audio-seconds per surface. Macro means:

| MOSS surface | five-case WER | five-case DER | speaker accuracy | content recall | matched-word speaker | trio WER | trio DER |
|---|---:|---:|---:|---:|---:|---:|---:|
| pre-Stop immediate | .165390 | .142521 | .857479 | .898610 | .887835 | .196590 | .170694 |
| pre-Stop settled | .138098 | .117610 | .882390 | .933702 | .932018 | .155498 | .133806 |
| Stop return | .120583 | .101614 | .898386 | .948075 | .946392 | .132808 | .113194 |
| post-Stop final | .097726 | .086098 | .913902 | .954722 | .954722 | .103946 | .102111 |
| file | .097726 | .083498 | .916502 | .954722 | .954722 | .103946 | .102111 |

The old `.131357` trio WER aligns with fresh `stop_return` `.132808`, not with settled-before-Stop
`.155498`. The true settled gap to file is therefore `.051552` WER and `.031695` DER on the trio;
across five cases it is `.040372` WER and `.031512` DER.

### F2 — service mechanics remained bounded

- First publication: 546 events, p50/p95 `3.211/3.545 s`, max `3.745 s`.
- Corrections: 526 events, p50/p95 `5.438/10.433 s`, max `11.158 s`.
- Stop-to-final: 10 sessions, p50/p95 `2.962/11.607 s`, max `11.652 s`.
- Pre-Stop combined GPU real-time factor: `.138950-.162047`; queue depth `<=1`.
- Exact sample accounting, unchanged runtime descriptor, zero failed windows/refusals, zero
  terminal failures, and file byte identity all passed.

Waiting for admitted rolling work was measured, never hidden: pass-A waits were `0.0006-0.770 s`.
The settled snapshot still left an approximately 10-second final tail without rolling refinement;
Stop-time work is why `stop_return` is better.

### F3 — repeatability is bounded, not perfect

Five back-to-back Bill sessions (300 audio-seconds) produced one hash for every surface. Across
the two headline passes, Javier, Keyu 1m, Adam 3m, and Keyu 5m were identical on every surface.
Bill had one alternate rolling outcome; terminal and file remained identical. No confidence
interval is claimed from deterministic duplicates.

### F4 — peer actual-live comparison remains unmeasured

Fresh Tier-1 re-scoring reproduced the committed file-proxy accuracy metrics. `wall_s` alone became
`null` because the new symlinked rescore did not reproduce original wall clocks.

| system | mode actually measured | WER | DER | speaker accuracy |
|---|---|---:|---:|---:|
| MOSS terminal | paced live + terminal finalization | .097726 | **.086098** | **.913902** |
| MOSS file | file | .097726 | .083498 | .916502 |
| LiveTranscribe | **file proxy** | .120034 | .139331 | .880602 |
| ProjectClerk | **file-replica lineage** | **.086169** | .176329 | .823671 |

Read-only committed-code audit:

- LiveTranscribe HEAD `6a8d0c1fafe8a1a8d6ea449036dd1ca330309d70`: refined live overlay is display-only and cleared
  at Stop; actual live capture requires attended AV/TCC.
- ProjectClerk HEAD `4345b66190322216410cd56804b5fc82c1ce842c`: the app stops capture, saves the raw transcript,
  reclusters offline, then saves again; committed code has no deterministic timestamped PCM live
  export contract.

Both actual peer live surfaces are **unmeasured**. Neither dirty peer worktree was modified.

### F5 — geometry sweep selects shadow work only

The fresh-cache production-model prototype used five cases, one request in flight, and the captured
pass-A settled surface as comparator. The stitcher was truth-blind and selected coherent window
views; it never read the golden transcript.

| arm | five WER | five DER | trio WER | witness work | max projected combined RTF | structural correction floor p95 max | outcome |
|---|---:|---:|---:|---:|---:|---:|---|
| 10/10 lexical | .121151 | **.102098** | .133755 | 1.000x | .214 | 9.019 s | shadow-eligible |
| 15/10 lexical | **.106269** | .105403 | **.107466** | 1.500x | .241 | 14.146 s | **recommended shadow** |
| 10/5 lexical | .117812 | .117481 | .123512 | 1.882x | .324 | 8.186 s | shadow-eligible |
| 8/4 lexical | .138363 | .134813 | .152120 | 1.906x | .317 | 6.884 s | reject |
| 6/6 lexical | .145394 | .096889 | .159159 | 1.000x | .260 | **5.628 s** | reject |

Comparator: five-case WER/DER `.138666/.118094`; trio `.156445/.134611`. `15/10` had no case
worse by more than `.02` WER or DER, and delivered the largest material WER gain. Its latency is
only an offline structural floor, however; production event clocks and queue behavior are absent.

Selective-overlap routing, a speaker-aware reconciler, and speaker-boundary refinement remain
**unmeasured** on this five-case run. Existing selective-router evidence contains only seven unique
material events and cannot authorize a policy.

## Decision

### D1 — recommended next change: none in production

Keep shipped production unchanged. If the owner authorizes another execution stage, test
`15/10:lexical` as a deployed shadow against current `10/10`, measuring correction p50/p95 from
production event clocks, first-publication latency, exact pre-Stop tail scheduling, queue depth,
failures, request count, decoded-audio work, combined RTF, and file byte identity on the same five
cases. Only that evidence can reopen the production gate.

## Provenance and reproducibility

- Repo HEAD during capture: `7608c91ce36441d9075fbba41e18c5fae8f464ac`.
- Deployed production code: `22dc5b8de3ed31a94dcb1b93d2256f8cb8ac75d8`.
- Runtime descriptor `source_revision=29681e0...` belongs to the pinned provider manifest; process
  start and committed campaign evidence verify the deployed application revision. No restart was
  performed.
- Main results: `evidence/live-surface-optimization-20260825/results.json`.
- Geometry results: `evidence/live-surface-optimization-20260825/geometry-results.json`.
- Peer rescore: `evidence/live-surface-optimization-20260825/peer-file-rescore.json`.
- Raw JSONL: each `pass-A-*`, `pass-B-*`, and `stability-*` directory beside this report.
- Preregistrations and runnable harnesses:
  `prototypes/streaming-diarization/live-surface-optimization/`.

Campaign owner gates remain unsigned. Attended browser E2E, portal render under load, and branch
merge/push remain open human decisions. Nothing was pushed or signed.
