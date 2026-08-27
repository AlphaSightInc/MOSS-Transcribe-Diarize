# Live-surface optimization notes

## Question

Can MOSS measure what a reader sees before Stop separately from Stop-time and file results, then
identify a rolling geometry worth testing without changing production from intuition?

## Verdict

**Measured: no production change passes.** `15/10:lexical` is the recommended deployed-shadow
candidate. It improved pass-A settled pre-Stop WER from `.138666` to `.106269` across five cases
and from `.156445` to `.107466` on the 60-second trio. Five-case DER also improved from `.118094`
to `.105403`. But its production event-clock correction latency, queue behavior, and exact final-tail
scheduling are unmeasured; it therefore cannot pass the production gates.

Production code was not changed.

## Mental model

The same audio has five distinct readable surfaces:

- `pre_stop_immediate`: the reader's screen after the final frame, before Stop;
- `pre_stop_settled`: admitted rolling work drained before Stop; the wait is visible and measured;
- `stop_return`: Stop has already begun and can flush extra work;
- `post_stop_final`: terminal re-decode finished;
- `file`: identical WAV/PCM through file mode.

The earlier `.131357` trio WER was close to the freshly measured `stop_return` `.132808`, not the
true settled-before-Stop `.155498`. Stop-time flushing had hidden part of the live gap.

## Three-surface measurement

Two paired passes covered five fully referenced cases: 10 observations and 1,320 audio-seconds
per surface. The separate stability denominator was five Bill sessions and 300 audio-seconds.

| surface | five-case WER | five-case DER | trio WER | trio DER |
|---|---:|---:|---:|---:|
| pre-Stop immediate | .165390 | .142521 | .196590 | .170694 |
| pre-Stop settled | .138098 | .117610 | .155498 | .133806 |
| Stop return | .120583 | .101614 | .132808 | .113194 |
| post-Stop final | .097726 | .086098 | .103946 | .102111 |
| file | .097726 | .083498 | .103946 | .102111 |

Event clocks across the 10 headline sessions: first publication p50/p95 `3.211/3.545 s`,
correction age p50/p95 `5.438/10.433 s`, Stop-to-final p50/p95 `2.962/11.607 s`.
Pre-Stop combined RTF was `.138950-.162047`; queue depth was at most 1; failures and refusals
were zero. File output was byte-identical on 10/10 runs. All five Bill stability runs produced
one hash per surface. One of the two earlier paired Bill runs produced a different rolling
surface; terminal and file remained identical.

## Geometry arms

Fresh-cache production-model sweep: five cases, one request in flight. Work is witness decoded
audio divided by source audio. Correction age is a structural floor, not an event-clock measure.

| arm | five WER | five DER | trio WER | work | max projected combined RTF | floor p95 max | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| 10/10 lexical | .121151 | .102098 | .133755 | 1.000x | .214 | 9.019 s | shadow-eligible |
| 15/10 lexical | **.106269** | .105403 | **.107466** | 1.500x | .241 | 14.146 s | **recommended shadow** |
| 10/5 lexical | .117812 | .117481 | .123512 | 1.882x | .324 | 8.186 s | shadow-eligible |
| 8/4 lexical | .138363 | .134813 | .152120 | 1.906x | .317 | 6.884 s | rejected: immaterial gain/harm |
| 6/6 lexical | .145394 | **.096889** | .159159 | 1.000x | .260 | **5.628 s** | rejected: WER loss/harm |

`15/10` is preferred over the other shadow-eligible arms because it has the largest five-case
and trio WER gain while staying within the `.02` per-case WER/DER no-harm gate. The 2.5-second
base lane is unchanged, so this prototype does not claim a new first-publication measurement.

## Other candidate verdicts

- **Selective overlap router (O2): unmeasured on this five-case run.** Existing branch-only
  evidence has seven unique material events, too small to select a production policy; branch
  disposition remains an owner decision.
- **Whole-view reconciliation (O3): measured only as truth-blind lexical whole-window selection.**
  It produced the geometry results above. Speaker-aware routing remains unmeasured; no token
  voting was used.
- **Speaker-boundary refinement (O4): unmeasured here.** Prior evidence locates most remaining
  speaker error at true-turn boundaries, but no fresh five-case boundary policy was proposed or
  measured, so none is recommended.
- **Peer actual-live surfaces: unmeasured.** LiveTranscribe needs attended AV/TCC capture;
  ProjectClerk has no deterministic timestamped live export path in committed code.

## Reproduce

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-surface-optimization/measure_three_surfaces.py \
  --out /tmp/moss-live-surfaces-20260825 \
  --deployed-code-revision 22dc5b8de3ed31a94dcb1b93d2256f8cb8ac75d8 \
  --passes 2 --stability-runs 5

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-surface-optimization/measure_geometry_candidates.py \
  --cache-dir /tmp/moss-live-surface-geometry-cache-20260825 \
  --output evidence/live-surface-optimization-20260825/geometry-results.json
```

Raw results: `evidence/live-surface-optimization-20260825/results.json` and
`evidence/live-surface-optimization-20260825/geometry-results.json`.
