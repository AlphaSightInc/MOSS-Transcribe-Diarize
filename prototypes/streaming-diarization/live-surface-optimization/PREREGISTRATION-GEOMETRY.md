# Five-case pre-Stop geometry preregistration

Written 2026-08-25 EDT before fresh candidate decodes.

## Question

Which rolling witness geometry deserves a deployed pre-Stop shadow run after accounting for text,
speaker quality, correction-age floor, and decoded-audio work?

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-surface-optimization/measure_geometry_candidates.py \
  --cache-dir /tmp/moss-live-surface-geometry-cache-20260825 \
  --output evidence/live-surface-optimization-20260825/geometry-results.json
```

The cache directory must not exist. Every unique PCM range/model/prompt input is decoded fresh
once on the production model; identical inputs shared by candidates reuse that measured result.
One request is in flight. The five fully referenced cases and evaluator are the same as the
three-surface matrix.

## Arms

All arms select whole window views and use the existing truth-blind lexical overlap stitcher.
No token voting and no reference access are allowed during construction.

- shipped `10/10`;
- quality-oriented `15/10`;
- overlap `10/5`;
- lower-latency `8/4`;
- lower-work/lower-latency `6/6`.

This offline sweep plans through the end of each WAV so every geometry is compared on full audio.
That answers context quality, not exact last-frame scheduling. Production currently leaves a final
unrefined tail before Stop; a selected arm therefore still requires deployed shadow measurement.

## Comparators, clocks, and gates

- Comparator: fresh `pre_stop_settled` pass A from the three-surface matrix, per case.
- Headline means: five case macro and three-case macro. One fresh greedy decode result per unique
  input; no confidence interval.
- Material improvement: at least `.010` absolute WER on both five-case and trio macro means.
- No-harm: no case regresses by more than `.020` absolute WER or DER.
- Report legacy DER, evaluator-v2 matched-word speaker accuracy, content recall, request count,
  decoded-audio work, measured decoder seconds, and projected base+witness RTF.
- Correction latency is only the existing structural floor
  `window_end + decode - provisional_publication`; it is not event-clock certification.
- First-publication latency is unchanged because the base 2.5-second lane is unchanged.
- Live queue depth, refusals, correction event p50/p95, and exact pre-Stop scheduling are
  **unmeasured** for alternate arms.
- File mode is not invoked or changed by this prototype.

A candidate may be recommended for deployed shadowing if it meets material improvement, no-harm,
and projected combined RTF `< 1`. No arm can be recommended for production from this prototype.

