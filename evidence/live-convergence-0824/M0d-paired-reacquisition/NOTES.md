# M0(d) — paired re-acquisition on campaign code (2026-08-25)

Four strictly-sequential measurement passes against the deployed dev service after it was
restarted onto campaign-branch code (pid 82706, started 2026-08-25 00:43:48 local, repo
working tree @ `e291624`; `restart-pre.txt` / `restart-post.txt` hold the before/after
descriptors — identical, so the restart changed the build and nothing else).

**Verdict: four of five gates pass. G2 fails, on the 5-minute case only, and the cause is
measured: the deployed decoder is not bit-reproducible.** The M0(d) row stays unsigned on G2
pending an owner ruling; nothing about the convergence approach is refuted by it.

## What was run

```bash
prototypes/streaming-diarization/live-convergence/run_paired_reacquisition.sh /tmp/m0d-iter4-20260825-005440
prototypes/streaming-diarization/live-convergence/verify_paired_reacquisition.py --fresh-root /tmp/m0d-iter4-20260825-005440
prototypes/streaming-diarization/live-convergence/probe_decode_determinism.py --repeats 12
prototypes/streaming-diarization/live-convergence/diff_live_runs.py <trace-A> <trace-B>
```

Passes: `trio-A` 04:55:23–04:59:38Z, `trio-B` 04:59:38–05:03:53Z, `keyu5m-A` 05:03:53–05:09:09Z,
`keyu5m-B` 05:09:09–05:14:25Z (UTC). One in-flight vLLM request throughout. The trio driver
exits 1 on its fifth case (`acquired_nfl`, an empty `text` field in its reference) — that is
pre-existing, it happens *after* every promotion-denominator case is measured and written, and
the 2026-08-24 baseline run stopped at the same wall.

## Gates

| Gate | Verdict | Evidence |
| --- | --- | --- |
| G1 file arms byte-identical to the 2026-08-24 baseline | **PASS** | 5/5 cases × 2 runs, full-file sha256 match |
| G2 fresh-vs-fresh live transcripts hash-identical | **FAIL** | 4/4 sixty-second cases pass; `keyu-5m` differs |
| G3 5-minute terminal snapshot shows the revisions `identity_finalized` reports | **PASS** | A 2 == 2, B 1 == 1; baseline 0 vs 2 — the M0a defect this retires |
| G4 measured service runs campaign code | **PASS** | 240/240 `canonical_processed` carry `canonical_decode_generated_tokens`; baseline control 0/115 |
| G5 one provenance across runs, matching the baseline | **PASS** | `combined_config_hash 431efb3f…`, greedy, 150/120 |

Full detail: `gates.json`. Per-pass artifacts are under `passes/<pass>/` (`results.json`,
`console.txt`, every `*-hypothesis.jsonl`, and the two 5-minute traces gzipped); probe outputs are
under `probes/`. The directory is `passes/`, not `runs/`, because the repo's root `.gitignore`
ignores any directory named `runs/` (and any `*.log`, hence `console.txt`) — the
evidence would otherwise have been silently dropped.

## Measured numbers

Trio, both fresh runs (A / B). File arms are byte-identical to the baseline, so one column each:

| case | file WER | file DER | live WER A/B | live DER A/B |
| --- | --- | --- | --- | --- |
| lex_bill_ackman | .1591 | .0755 | .2727 / .2727 | .2237 / .2237 |
| lex_javier_milei | .0880 | .1518 | .1440 / .1440 | .1945 / .1945 |
| lex_keyu_jin | .0647 | .0790 | .1942 / .1942 | .1122 / .1120 |

5-minute case (`benchmark_5m/lex_keyu_jin`): file WER .0506 / DER .0579 (byte-identical to
baseline both runs); live A WER .1464 / DER .1130 / 3 speakers / 2 revisions, live B WER .1477 /
DER .1100 / 4 speakers / 1 revision.

Two deltas against the checked-in 2026-08-24 baseline are worth naming:

- **bill live WER .2614 → .2727** (30 → 31 published segments). One extra span, one decode flip
  (below). The PRD's M2 comparator names .2614; that number is preregistered and stands — this
  re-acquisition does not move it, it explains its noise.
- **5-minute live DER .1315 → .1130.** Not noise: the M0a replay-client fix restored
  `revised_transcript` / `label_revision_version`, so the scored hypothesis now carries the
  label revisions the session actually applied. The old number scored un-revised labels.

## Why G2 fails — the decoder, measured

`diff_live_runs.py` walks both traces span by span with wall-clock fields excluded.

- **Trio: zero differing spans.** All three cases, 24/31/24 spans, every `span_frozen` bound and
  every `canonical_processed` payload identical between A and B. Endpointing is deterministic.
- **5-minute: 114/114 span bounds identical, and the earliest divergence is exactly one span** —
  span 55, differing in one field, `canonical_decode_generated_tokens` 24 vs 26. The other 51
  differing spans are all downstream identity cascade (49× `identity_revision_version`, 2×
  `identity_status` `abstain`→`prepared`). One decode flip changed the parsed speaker turns,
  which changed the embedding evidence, which changed album decisions, which produced 3
  speakers / 2 revisions in one run and 4 / 1 in the other.

`probe_decode_determinism.py` settles the root without any live session. It extracts the span
that flipped in the first pairing (lex_bill_ackman samples 760000–800000, a 2.5 s hard-cap span)
and sends the *same* multipart greedy request through the *same* `VllmRunner` the service uses:

- **cold-first batch: 12 requests → 2 distinct outputs.** Request 0 returned 20 tokens; requests
  1–11 returned 37. Request 0 was the first after a ~3-minute idle gap.
- **immediately again while warm: 12 requests → 1 distinct output.** 12/12 at 37 tokens.

So the deployed vLLM host is bit-reproducible while warm and can answer differently on the first
request after an idle gap. Live mode issues ~24 small requests per minute of audio where file
mode issues one large one, so live has one to two orders of magnitude more chances to land on a
flip — which is also why the file arms reproduce byte-for-byte and the live arms do not.

There is no in-repo lever for this: the 4070 Ti host is read-only infrastructure by PRD
constraint, greedy decoding is mandated, and the model and prompt are frozen. G2 as literally
worded ("hash-identical") is not achievable against a decoder that is not itself a function.

## Two further findings this pass produced

**F3 — every 5-minute replay trace is truncated, including the checked-in baseline.**
`bounds.max_events = 1000` is enforced as `deque(maxlen=…)` in `live_service_runtime.py:499`,
and `live_service_replay.py:446` drains the stream once with `since_seq=0` *after* the session
ends. A 5-minute session emits ~1600 events, so the first ~30 s is evicted before anyone reads
it: both fresh traces and the baseline trace start at frame 60 and span 13, holding 114 of 127
spans. Metrics are unaffected (the hypothesis is built from the terminal snapshot, not the event
stream), but every span-level analysis of the 5-minute case — M1's salvage corpus, M4's sample
accounting, the RTF evaluation in `_canonical_decode_rtf_evaluation` — silently reads a
truncated window. This is fixable in-repo and is the next candidate.

**F4 — extent jitter is provider-side and survives identical decodes.** On the trio, where every
span and every decode matched, published segment boundaries still moved by ±10–20 ms (one
webrtcvad frame) on 3 of 26 keyu segments and 6 of 32 jamie segments, and one jamie segment
changed speaker label. WER is blind to this; DER, TSA and coverage are not. Per-case DER
comparisons in M2/M3 need that noise term quantified before a ±.002 difference is read as signal.

## What this leaves open

1. **G2 needs an owner ruling** (unsigned row). The measurement it was protecting is intact:
   file mode is byte-exact, endpointing is deterministic, and live text is reproducible on every
   60-second case. What it cannot promise is bit-equality of an external decoder.
2. **The noise floor is not yet quantified.** One A/B pairing shows the 5-minute case can flip;
   it does not say how often. N≥4 repeats of the 5-minute pair would give the spread that M1's
   "no per-case WER regression" and M3's per-case DER gates have to clear.
