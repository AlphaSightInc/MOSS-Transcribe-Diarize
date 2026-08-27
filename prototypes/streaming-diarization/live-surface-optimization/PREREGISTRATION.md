# Three-surface live stress preregistration

Written 2026-08-25 EDT, before this bench sent live traffic.

## Question

What text and speaker quality does a reader receive immediately before Stop, after already
admitted work settles but before Stop, after terminal finalization, and through file mode when
all surfaces hear the same PCM bytes?

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-surface-optimization/measure_three_surfaces.py \
  --out /tmp/moss-live-surfaces-20260825 \
  --deployed-code-revision 22dc5b8de3ed31a94dcb1b93d2256f8cb8ac75d8
```

The service is not restarted. Runs are sequential and paced at 1.0x, with one inference request
in flight. One decoder warm-up is discarded before the measured matrix.

## Corpus and denominators

Headline accuracy uses only five fully referenced real cases:

| case | duration | case directory |
|---|---:|---|
| `lex_bill_ackman` | 60 s | `data/real/benchmark_diarization_1min/samples/lex_bill_ackman` |
| `lex_javier_milei` | 60 s | `data/real/benchmark_diarization_1min/samples/lex_javier_milei` |
| `lex_keyu_jin_1m` | 60 s | `data/real/benchmark_diarization_1min/samples/lex_keyu_jin` |
| `lex_adam_frank_3m` | 180 s | `data/real/calibration_diarization_3min/samples/lex_adam_frank` |
| `lex_keyu_jin_5m` | 300 s | `data/real/benchmark_5m/lex_keyu_jin` |

- Pass A runs in table order; pass B runs in reverse order: 10 paired observations and 1,320
  observed audio-seconds per surface.
- Macro means first average the two passes per case, then average five case means. Duration-
  weighted means weight all 10 observations by WAV duration.
- Trio means use the three 60-second cases: 6 observations and 360 audio-seconds per surface.
- Stability uses five additional back-to-back Bill Ackman sessions. It is reported separately
  and never enters headline accuracy.
- `acquired_*` cases never enter a denominator.
- No confidence interval is produced for deterministic duplicates.

## Surfaces

Each run writes the full transcript rows as JSONL, plus the full service snapshots:

1. `pre_stop_immediate`: first snapshot after the final frame returns, before Stop.
2. `pre_stop_settled`: snapshot after `pending_work_items == 0`, or after the declared 20-second
   wait bound. The wait duration and whether it drained are fields, not hidden latency.
3. `stop_return`: asynchronous Stop response.
4. `post_stop_final`: first polled snapshot whose `finalization_status` is settled; certification
   requires `final`.
5. `file`: the same WAV/PCM bytes through `/api/jobs`.

Prefix checkpoints are omitted. The evaluator has no reference slicer proven to exclude future
truth at an exact time boundary, so a 25/50/75 percent curve would not be a valid live measure.

## Clocks and work

- Client capture clocks use local `monotonic_ns` and UTC wall time at snapshot observation.
- Settled wait is from the immediate snapshot to the settled snapshot.
- Stop-to-final is from the Stop request to the first observed settled terminal snapshot; polling
  resolution is recorded.
- Base first-publication age follows plan G5. The meeting clock origin is the minimum over base
  spans of `canonical_queued.runtime_monotonic_ns - span_end_audio_time`; publication time is the
  matching `canonical_processed.runtime_monotonic_ns`; first spoken-word time is the earliest
  base-hypothesis word/segment start in that span. Only non-empty spans enter p50/p95.
- Correction age follows plan G6. An applied rolling completion enters only when the final
  pre-Stop rolling surface differs lexically from the base surface over its owned interval. One
  latency is recorded for each provisional span midpoint it owns: rolling publication minus base
  publication. P50/p95 use linear interpolation.
- Base, rolling, terminal, pre-Stop combined, and all-pass RTF divide summed decoder seconds by
  WAV duration. Decode request count is the count of completed base, rolling, and terminal decode
  events. Decoded-audio work is the corresponding input seconds reported by those events.
- Rolling depth is admitted `rolling_decode_queued` minus `rolling_decode_completed` in event
  order. Refusals, stale completions, failed windows, accepted/accounted samples, and terminal
  failures are reported without reinterpretation.
- Browser capture-to-paint and portal render time remain **unmeasured** in this bench.

## Accuracy evaluator

Every surface uses the same reference and the same evaluator:

- deployed TBSA composite, WER, text coverage, text-speaker accuracy, and DER;
- duration-weighted speaker accuracy;
- evaluator v2 content recall, reference-speech DER, and matched-word speaker accuracy.

Golden truth enters only scoring, after a transcript surface has been captured. No production
component or reconciler can read it.

## Baseline checks and stopping rules

- Runtime descriptor/provider/config must stay constant across the run.
- Every session must have exact accepted/accounted sample equality, rolling depth `<= 1`, final
  depth zero, zero admission refusals, zero stale completions, and zero failed windows.
- Combined pre-Stop RTF must be `< 1`.
- Current file JSONL must remain byte-identical to the checked-in M4 comparator for each case.
- A run without `post_stop_final.finalization_status == final` is incomplete and stops the matrix.
- Fresh measurements differing materially from the handoff baseline trigger diagnosis, not an
  adjusted denominator or threshold.
