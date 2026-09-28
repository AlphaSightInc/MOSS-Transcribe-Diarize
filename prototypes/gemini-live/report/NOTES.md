# D6 scorecard prototype

## Stress cost denominator amendment, 2026-09-28

**Structural question.** What does a measured Gemini meeting-hour cost mean when retained stress receipts come from different runtime SHAs? **Minimum primitives:** a complete non-fault session with engine cost, accepted audio duration, and one receipt/SHA; its cost is total engine dollars divided by total meeting seconds. Mixing two SHAs removes the identity of the measured implementation. **Invariant:** one cost cell uses sessions from one complete scenario receipt; prefer the complete long60 meeting because it covers the requested sustained workload, else the complete concurrent2 receipt. **Unknown:** the final SHA long60 cost is not yet measured. **Falsifier:** the selected long60 receipt lacks a completed terminal state, a cost counter, or an accepted duration, or the reducer still includes concurrent2 dollars after selecting it. **Tool decision:** an offline arithmetic probe over real P62 long60 (6c5776e3) and P64 concurrent2 (c58595da) measures the contamination; no provider call or new data structure is needed.

One-command probe printed full inputs: P62 long60 2586 s, $1.767767, $2.460929/h; P64 concurrent2 600 s, $0.167457, $1.004744/h; pooling across SHAs gives $2.186695/h, which describes neither measured implementation. **Verdict:** use the complete long60 stress receipt alone when present, else concurrent2 alone; retain the exact source path in the cell. The final 56513e30 long60 run will test this selection.

## Zero-call silence eligibility amendment, 2026-09-28

**Structural question.** How can the scorecard accept the intended zero-provider result for 600 s silence without mistaking missing counters for zero? **Minimum primitives:** verified Gemini runtime descriptor, full named silence10 receipt, exact 600 s accepted and saved tape, final empty transcript, measured engine counters with zero calls/sent audio/cost. Removing any one loses provider identity, workload completeness, terminal evidence, or the actual zero-cost observation. **Invariant:** 0/0 anomaly rates stay `UNMEASURED`; other stress scenarios still require positive measured calls and per-call anomaly rates. **Unknown:** one digital-zero corpus clip cannot prove all possible quiet rooms. **Falsifier:** the final-SHA real silence receipt is excluded, or a short stub smoke/positive-call receipt is accepted by this exception. **Tool decision:** call `stress_receipt` on the real final zero-call receipt plus a short stub and prior paid S12 receipt before/after the narrow change; this tests the exact eligibility branch with no provider call.

Before change, `runtime-final-silence10-full1/summary.json` was excluded as `stub, short smoke, or provider unverified` despite 600/600 s tape, final empty transcript, `calls_by_kind={}`, `calls_total=0`, `audio_seconds_sent=0`, `cost_usd=0`, errors/retries/anomalies0. This is a real eligibility false negative. The exception is limited to that complete measurable zero-call shape; after-change probe outcome is recorded below.

After change: final zero-call silence `eligible=True`; prior paid full S12 silence `eligible=True` under the ordinary positive-call branch; short stub silence smoke `eligible=False`. **Verdict:** the narrow exception admits the measured S-4 result without converting a 0/0 anomaly rate into zero or weakening other scenario eligibility.

## Structural contract

**Question.** Can a reader compare MOSS and Gemini on the same public population and three transcript surfaces without promoting a stub, a partial run, or an unrelated provider call into product evidence?

**Minimum primitives.** A cell is a measured value plus exact receipt path, population, surface, and status. A population is the frozen H1 six cases × two passes, E1's four-voice fixture, or a named stress session; they cannot be merged. A gate applies its declared inequality to one eligible cell. A timed reference second and a timed word-bearing hypothesis row are the minimum available primitives for a dropped-passage check. These concepts cannot be removed without losing source custody, comparability, or a reachable falsifier.

**Invariants.** Use unweighted 12-pass macros for D6 DER, with D45b ruled settled DER and raw settled DER shown separately. Never substitute duration-weighted, partial, sparse-reference, stub, or transport-probe numbers. Strict live DER `<0.145`; final DER `<=0.110`; E1 visible labels at Stop `<=5` (true 4). A soft p50 requires a named clock and denominator; per-run p50 summaries are not raw bucket observations. Meeting-hour cost requires a complete per-session engine cost and audio duration. Missing fields are `UNMEASURED`, never zero. Every numeric Markdown cell links its receipt.

**Assumptions and unknowns.** The eight H1 bound coordinates are the authoritative acceptance set. A three-surface comparison will additionally show each available underlying production metric on immediate, settled, and final; only the bound's designated surface is an H1 bound. Existing H1 content-free receipts omit timed word-bearing rows, so the new dropped-passage predicate remains `UNMEASURED` until pane 6.2 exports its sidecar. Segment intervals with nonempty text witness words somewhere inside their span; they do not provide individual word timestamps and could hide a gap inside an unusually long segment. The scorecard names that limit. MOSS E1 has no timed reference. The historical MOSS 50-second latency clock differs from the new bucket and DOM clocks; show it as context, not a D6 verdict. The exact final Gemini runtime and words source are still unmeasured.

**Falsifier.** If baseline recomputation fails to reproduce its 12-case macro, or a stub receipt fills a Gemini D6 cell, or a source-less value passes, reject the generator. With timed reference and word rows, one isolated reference second without any word inside a ±3-second window must fail the no-drop gate, while covered seconds must pass. This synthetic passage check validates the reducer only; it is not a product claim.

**Tool decision.** Read JSON receipts with the Python standard library; no network, GPU, or new scorer. Recompute only the baseline macros from retained per-case numbers to detect schema/mapping errors. Consume the production quality projection directly for future Gemini runs. Use explicit optional paths instead of auto-promoting every JSON file under evidence. Test one baseline-plus-stub invocation and one synthetic timed-word passage input. The first checks evidence eligibility; the second changes whether the passage predicate is trusted. Output one JSON and one Markdown file with matching cell records.

## Run

One read-only command from the Gemini-live worktree (the default baseline and archived MOSS E1 paths are built in):

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/report/scorecard.py \
  --gemini-quality /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P62 \
  --gemini-e1 /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64/stub-E1/summary.json \
  --latency /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P62/latency-summary.json \
  --stress /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64/stress-concurrent2-full1/summary.json \
  --ledger prototypes/gemini-live/.ledger/P64.jsonl \
  --out-dir /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64/scorecard-stub3
```

The full cell state and eligibility decisions are in `scorecard-stub3/scorecard.json`; `scorecard.md` is the linked table. Replace the optional receipt paths with **complete real Gemini** run directories/summaries when those exist. A complete eligible H1 run automatically loads `h1-timed-segments.json` from its own output directory; `speaker` is retained in the sidecar but irrelevant to the passage-presence predicate. No provider calls occur in the scorecard command.

Current smoke verdict: four Gemini hard bars `UNMEASURED`; P62 stub H1, P64 stub E1, and full-duration MOSS stub stress are excluded from Gemini product gates. MOSS H1 12-case-pass baseline: ruled live settled DER `0.144626` PASS under `<0.145`; final DER `0.110022` FAIL under `<=0.110`. Archived real MOSS E1 shows 10 labels at Stop, FAIL under `<=5`. Archived MOSS dropped passages remain `UNMEASURED` because the retained H1 receipt lacks timed words. Its DOM p50 values remain context only because the origin is approximate. Ledger experiment cost is never divided by meeting duration.

The 10-label value comes from `evidence/P64/moss-real-E1-summary.json`'s recorded DOM reduction at Stop. `harness/BASELINE.md` cites 11 visible labels from the earlier recorded E1 summary; these are distinct reductions, and both fail the five-label bar. The scorecard uses the DOM-visible value because the Gemini E1 side will use the same DOM reducer.

The D6 H1 comparison uses the corrected H1 #3 six-case reference manifest and no gold9/bench5m aggregate. For later qualification beyond this scorecard: gold9 benchmark:acquired_jamie_dimon is sparse (12.3/60 s) and diagnostic only; acquired_nfl and acquired_rolex are near complete (52.9/60 and 51.1/60 s), so small untimed gaps can inflate misses. Complete benchmark_5m lex_bill_ackman, lex_keyu_jin, lex_javier_milei and long30m lex_bill_ackman are the long-form qualification references. Sparse acquired 5m/30m references stay diagnostic.

## Prototype measurement

Throwaway one-command Python probe over the retained MOSS baseline recomputed all eight H1 bound coordinates from 12 per-case passes: maximum absolute delta from the published macro was `1.11e-16`. A synthetic 10-second reference span with a lone word at 0–1 seconds left reference seconds 4–9 uncovered under ±3-second tolerance; a true 0–10-second timed word interval covered all ten. Full state: `evidence/P64/scorecard-prototype.json`. Verdict: the macro mapping and interval predicate are sufficient for the generator; no production scorer or provider call is needed. The synthetic word interval is a reducer check, not evidence of speech quality.

The integrated 12-case synthetic sidecar check repeats that interval for both Stop-settled and final: 72 missing seconds per surface, 144 combined, yields `FAIL`; full coverage yields 0/240 missing and `PASS`. The first check invocation asserted 72 combined and failed because it omitted the second surface from its expected count; the corrected assertion passed without changing the reducer.

**Eligibility falsifier found and fixed.** A local one-command probe copied the complete P62 stub metric projection and paired it with 12 Gemini-named replay manifests. Descriptor-only eligibility returned `eligible=True` even though there was no runtime call receipt. The generator now also requires all 12 engine counter rows, positive total calls, and positive recorded provider cost before filling H1 Gemini product cells. Rerun: without engine receipt `False`; with a synthetic positive 12-case receipt `True`. The positive branch checks the reducer only, not real provider provenance. A future real run lacking usage/cost remains `UNMEASURED` until its accounting is repaired; provider name alone is insufficient.

The same counterexample applied to E1 and full-length stress: setting only a Gemini descriptor on copied stub receipts yielded `eligible=True` before repair. E1 now requires a terminal runtime snapshot with positive call count and recorded provider cost; stress requires measured positive calls, per-call anomaly counters, and session engine diagnostics. Local before/after eligibility results: E1 `True` descriptor-only → `False` without calls / `True` with a synthetic paid-call counter; stress `True` descriptor-only → `False` without calls / `True` with synthetic measured calls. Fault scenarios can legitimately spend zero if Google is down, so stress requires call attempts rather than positive cost. These synthetic positive branches test custody rules, not product performance.
