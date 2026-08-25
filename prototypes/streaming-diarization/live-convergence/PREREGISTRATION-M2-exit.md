# Preregistration — M2 (plan E2) exit measurement

Written 2026-08-25, **before the four measurement passes were launched** and before any number
from them was read. The gate list and the thresholds are the PRD's M2 milestone verbatim; what
this file adds is the part a junior developer must not have to guess — how each derived quantity
is computed from the artifacts, what it is compared against, and what the campaign predicts.
Nothing here may be re-decided after a number is seen.

## Instrument

- Deployed dev stack: `web_cli` restarted 2026-08-25 05:52:14 local onto repo working tree
  `4d6cb29` (evidence `M2-e2-exit/restart-{pre,post}.txt`; descriptor identical before/after).
- Four strictly sequential passes by `run_paired_passes.sh` (the campaign protocol since M1:
  one discarded warm-up decode before each pass, one in-flight vLLM request):
  `trio-A`, `trio-B` (6 one-minute cases, file + live arms each), `keyu5m-A`, `keyu5m-B`.
- Live arm = `live_service_replay` at pace 1.0 through HTTPS, exported by
  `hypothesis_from_live_snapshot` (iteration 17: the export reads `effective_transcript`), so the
  scored live transcript is the surface the reader sees.
- Aggregation, fixed here: per case, the **mean of the two passes**; the trio mean is the mean of
  the three primary cases' per-case means. Secondary `acquired_*` cases are diagnostic only and
  never enter a promotion denominator (PRD constraint).

## Gates

| Code | Gate (PRD M2) | Threshold | Source of the number |
|---|---|---:|---|
| G-M2-1 | trio rolling WER mean | `<= .150` | `results.json` per pass, live arm `scores.tbsa.wer` |
| G-M2-2 | per-case rolling WER below baseline live | `<` .2614 / .1440 / .1942 | same, vs `prototypes/live-file-gap-baseline-20260824/trio-60s/results.json` |
| G-M2-3 | trio content recall mean | `>= .940` | evaluator v2 (`evaluator_v2.py`) over the fresh `live-hypothesis.jsonl` |
| G-M2-4 | correction-after-provisional p95 | `<= 6.0 s` | trace event stream, clock defined below |
| G-M2-5 | single-session combined RTF, bounded queues | RTF `< 1` | trace event stream, definition below |
| G-M2-6 | 5-minute-case rolling WER | `<= .0985` | `keyu5m-{A,B}/results.json` live arm |
| G-M2-7 | exact sample accounting | accepted == accounted | run summary, every scored case, both passes |
| G-M2-8 | file mode byte-identical | sha256 equal | `file-hypothesis.jsonl` vs the checked-in 2026-08-24 baseline |

### G-M2-3 — content recall

Evaluator v2's `content_recall` (plan A0.3, prototype accepted in M0c), computed with the same
`cases.json` corpus contract the M0c bundle used, over the fresh live hypotheses. The comparator
is the campaign's published live recall `.9135` and the grid's rolling projection `.9439`; the
gate is the PRD's `>= .940` on the trio mean.

### G-M2-4 — the correction clock

Plan §1.3's G6 clock, reproduced from the reference implementation
`prototypes/streaming-diarization/live-multiview-prototype/lane_rolling_terminal.py::_provisional_to_correction_latencies`:

- One **provisional observation** per `canonical_processed` event: its span bounds are
  `[committed_samples - frozen_span_sample_count, committed_samples)` and its publication time is
  the event's `runtime_monotonic_ns`.
- One **correction** per `rolling_decode_completed` event with `applied: true`: its owned region is
  `[owned_start_sample, owned_end_sample)` and its publication time is that event's
  `runtime_monotonic_ns`.
- A correction enters the distribution only if it **changed** the surface over its owned region.
  Changed-ness is decided offline from the terminal snapshot, because event payloads carry no
  meeting words by design: the base words are the `committed` spans' parsed segments whose start
  falls in the region, the surface words are the `effective_transcript` segments whose start falls
  in the region, and the correction is *changed* iff the two word sequences differ.
- For each changed correction, one latency per provisional observation whose span **midpoint**
  lies in the owned region: `correction publication − provisional publication`.
- Pooled across the primary trio and both passes. p95 by the reference's linear-interpolation
  percentile; the nearest-rank p95 is reported beside it and does not decide the gate.

### G-M2-5 — combined RTF and bounded queues

Rescoped by the PRD to a single session (two-session stress is deferred by Appendix B).

- **combined inference RTF** = (Σ `canonical_decode_elapsed_sec` + Σ `rolling_decode_elapsed_sec`)
  / audio seconds of the case. Base and witness RTF are reported separately beside it.
- **bounded queues**, all four required:
  1. rolling depth (`rolling_decode_queued` admitted, minus `rolling_decode_completed`, walked in
     event order) never exceeds 1 at any point in the session;
  2. every admitted window completes — depth is 0 when the session closes;
  3. every frozen span is processed and submitted (`submitted: true`, no dropped canonical commit);
  4. rolling `retained_high_water_samples` never exceeds the converger's `2 x window` bound
     (320000 samples).
- Rolling must not delay unresolved canonical work: reported as the base spans' `queue_wait_ms`
  distribution, compared against the M1 exit passes' distribution on the same cases.

### G-M2-7 — accounting

`accepted_samples == accounted_samples` in the run summary of every scored case in both passes,
plus `status: succeeded`. A pass whose live arm failed cannot satisfy this gate by omission: the
case list is taken from the baseline artifact, not from what happens to be on disk.

## §10.6 soak quantities (reported, not gated)

Appendix B rescopes the 30-minute soak to the 5-minute case, which these passes already are.
Reported from their event streams: base first-publication p50/p95 (the G5 diagnostic), rolling
correction p50/p95, per-kind queue delay, base/witness/combined GPU RTF, windows planned /
completed / failed / stale, admission refusals, rolling retained high-water samples, and terminal
snapshot bytes. Portal render time stays the attended browser item (morning review), unchanged.

## Predictions on record

1. **G-M2-1 passes**: trio rolling WER near the §10.4 arm's `.131861`, well inside `.150`. The
   deployed decoder is not the grid's cache (iteration 4), so exact equality is not predicted.
2. **G-M2-2 passes** on all three cases: predicted bill ≈ `.199`, milei ≈ `.096`, keyu ≈ `.101`
   against `.2614` / `.1440` / `.1942`.
3. **G-M2-3 passes**: predicted trio recall ≈ `.9439` against `>= .940` — the smallest margin of
   the text gates, and the one a single decode flip could move.
4. **G-M2-4 FAILS, and this was known before the code existed.** Iteration 10's F3 fixed the
   structural floor at this geometry from measured decode latencies: with central ownership the
   oldest owned word has age `(L+S)/2`, so `L+S <= 12` is required and `10/10` is `L+S = 20`
   (floor `8.51 s` > `6.0 s`). Measure it honestly; a miss here is the preregistered outcome, not
   a reason to re-select an arm. Predicted p95 in the 8–12 s band.
5. **G-M2-5 passes**: predicted combined RTF ≈ `0.2` (base ≈ `.10`, witness ≈ `.10`), depth never
   above 1, zero failed windows, high-water at or below `240000` (iteration 14's measurement).
6. **G-M2-6 is the coin flip**: the trio's relative improvement (`.1999 → .1319`, −34%) applied to
   the 5-minute case's `.1464` gives `.0966` against a `.0985` bound.
7. **G-M2-7 and G-M2-8 pass**: accounting has been exact in every campaign pass, and file mode has
   been byte-identical across eight production changes (sha `ad381d8b…`).

A gate that fails is E2's stop rule as written in the PRD: record the failure evidence, leave the
row unsigned, and do not tune a threshold or add an arm to recover it.
