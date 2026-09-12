> Historical report, copied from `/tmp/moss-draft-headroom-20260911/REPORT.md` (MacStudio-local source, not in repo). Only reference annotations changed; results and original decisions are preserved. This is not current host status. Uncopied artifacts remain local.

# Draft lane: ship-on pre-validation not established

Candidate **5c74ddf9**, isolated 17863 stack. No repository/product code changed; 17861 and its database untouched. Temporary stacks are stopped; separate state and artifacts remain.

**Decision: the strict four-session non-regression criterion fails in the corrected repeat.** All four sessions finalize, but pooled canonical coverage p95 increases from **13.66s off to 13.69s on**, and worst-session p95 from **16.09s to 18.50s**. The initial comparison passed (13.72s to 13.59s pooled); therefore the evidence is mixed. The 30ms pooled difference is below the 100ms observation cadence and does not establish a causal draft slowdown. It also does not establish the requested predictable non-regression. Keep lane-off as the conservative shipping choice until that criterion is met.

Eight-session overload preserves completion: **8/8 closed/final**, with p95 **59.82–65.71s** and **8/8 accepted stop_in_progress outcomes** before eventual completion. No helper_lease_expired, terminal failures, frame errors, or Stop HTTP timeouts in the corrected cohorts. No policy changes are proposed.

## Cohort summary

| Cohort | Pooled coverage p95 s | Worst-session p95 s | KV-cache peak | Runtime requests / vLLM successful requests | Closed/final |
|---|---:|---:|---:|---:|---:|
| 4 off | 13.66 | 16.09 | 5.47% | 124 / 124 | 4/4 |
| 4 on | 13.69 | 18.50 | 5.35% | 127 / 127 | 4/4 |
| 8 on | 62.71 | 65.71 | 5.47% | 209 / 209 | 8/8 |

## Per-session results

Times in seconds. Coverage/label delays use 71 half-second audio buckets from 5–40s, timed from bucket end. First text includes canonical preview or draft and is timed from replay start; it is an API observation, not browser paint. `*` marks a draft providing first text. Every session accepted/accounted exactly 800,000 samples (50s); maximum start skew was 7.6ms.

| Cohort/session | Coverage p50 / p95 | First text | Label p50 | Draft ticks skipped | Decoder requests/audio-s | Final | Stop response |
|---|---:|---:|---:|---:|---:|---|---|
| 4 off/1 | 2.72 / 13.42 | 3.62 | 2.92 | — | 0.62 | closed/final | completed |
| 4 off/2 | 3.22 / 16.09 | 4.49 | 3.38 | — | 0.62 | closed/final | completed |
| 4 off/3 | 2.97 / 13.07 | 4.07 | 3.09 | — | 0.62 | closed/final | completed |
| 4 off/4 | 3.16 / 16.05 | 4.85 | 3.21 | — | 0.62 | closed/final | completed |
| 4 on/1 | 2.86 / 13.27 | 2.05* | 3.04 | 96% (48/50) | 0.66 | closed/final | completed |
| 4 on/2 | 3.26 / 18.50 | 3.48 | 3.29 | 100% (50/50) | 0.62 | closed/final | completed |
| 4 on/3 | 3.25 / 15.69 | 3.91 | 3.28 | 100% (50/50) | 0.62 | closed/final | completed |
| 4 on/4 | 2.72 / 13.05 | 2.16* | 2.94 | 98% (49/50) | 0.64 | closed/final | completed |
| 8 on/1 | 19.72 / 63.39 | 4.38 | 20.44 | 100% (50/50) | 0.52 | closed/final | stop_in_progress |
| 8 on/2 | 20.21 / 64.07 | 3.98 | 21.09 | 100% (50/50) | 0.52 | closed/final | stop_in_progress |
| 8 on/3 | 17.86 / 60.38 | 2.20* | 18.86 | 98% (49/50) | 0.54 | closed/final | stop_in_progress |
| 8 on/4 | 21.23 / 65.16 | 5.28 | 22.21 | 100% (50/50) | 0.52 | closed/final | stop_in_progress |
| 8 on/5 | 18.45 / 61.58 | 3.53 | 19.45 | 100% (50/50) | 0.52 | closed/final | stop_in_progress |
| 8 on/6 | 20.71 / 65.71 | 4.91 | 21.69 | 100% (50/50) | 0.52 | closed/final | stop_in_progress |
| 8 on/7 | 19.10 / 62.21 | 2.71 | 19.95 | 100% (50/50) | 0.52 | closed/final | stop_in_progress |
| 8 on/8 | 21.91 / 59.82 | 5.81 | 22.70 | 100% (50/50) | 0.52 | closed/final | stop_in_progress |

## Interpretation and limits

- F1: Draft backoff protects canonical work: corrected four-on skipped **197/200** ticks; eight-on skipped **399/400**. Only two of four and one of eight sessions received drafts. This measures the implemented backoff behaviour, not continuous concurrent draft inference at one request per second per session.
- F2: Eight-session latency degrades substantially without failing sessions. The shared upstream waiting queue peaked at **6**, versus **2** for four sessions; requests running peaked at **2** in every cohort. Low KV-cache use alone is not a throughput/headroom guarantee.
- F3: Coverage includes missing short-path text filled by later rolling/terminal revisions, explaining p95 values much larger than first-text latency. All 71 denominator buckets are present for every session; no uncovered buckets were silently dropped. No WER or identity-quality qualification is claimed.
- F4: The first probe version had incomplete first-text/request accounting and timed out on eight-session Stop at its own 30s HTTP limit. Initial coverage/completion results remain in off4/on4/on8. The corrected v2 results above include all visible preview sources, pre-fence runtime accounting, and a 180s Stop HTTP budget with the unchanged 30s server drain deadline. Runtime request totals match sampled vLLM successful-request deltas exactly: **124, 127, 209**. Terminal heartbeat refusals say “live Meeting is terminal”; these are distinct from lease expiry.

## Evidence and reproduction

All structured results: `/tmp/moss-draft-headroom-20260911/all-results.json` — MacStudio-local (not in repo), method/probe corrections: `/tmp/moss-draft-headroom-20260911/NOTES.md` — MacStudio-local (not in repo), probe: `/tmp/moss-draft-headroom-20260911/latency_probe.py` — MacStudio-local (not in repo), isolated launcher: `/tmp/moss-draft-headroom-20260911/headroom_stack.py` — MacStudio-local (not in repo), concurrent coordinator: `/tmp/moss-draft-headroom-20260911/run_group.py` — MacStudio-local (not in repo). Each cohort/measurement/sN contains result.json, public events.json, final-snapshot.json, and (v2) runtime-events.json. Metrics are retained as cohort/measurement/metrics.jsonl. Each row maps to its actual session ID in all-results.json. Cookie and database files are private setup artifacts; never include them in a handoff bundle.

Gauge sampled every 250ms through http://127.0.0.1:18000/metrics; no metric-fetch errors. Reported peaks are sampled, not a claim about unsampled shorter spikes. All six cohorts (32 sessions across the initial and corrected runs) are retained. No host deployment or official round-10 capacity gate was run by this agent.
