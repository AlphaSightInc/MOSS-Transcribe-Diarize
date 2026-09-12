# Rolling queue eviction and DER — 2026-09-11

**Fix:** recover the next committed rolling window from the complete audio tape
already retained for finalization. Do not skip to newest audio, enlarge buffers,
change canonical priority or alter identity. The 16.5-second queue-wait regression
now applies three contiguous windows instead of none; no quality gain is claimed
without a fresh deployed measurement.

## F1 — What the host actually waited for

Source: round-9 pre-admission Javier pass 1 terminal diagnostics, retained in
[the prior evidence](round9-quality-retained-20260911.json). First rolling item 8
was queued at event 69, time 2790655299906629 ns; dispatched/completed at event 152,
time 2790671839423632 ns: **16.539517 seconds**. It never called its decoder:
`outcome=not_awaited`, `applied=false`, `rolling_status=pcm_evicted`.

At admission, canonical items **5, 6, 7** were already queued. During the wait,
items **9–16** arrived. All **eleven** were processed before rolling item 8. The
arbiter's documented priority is canonical before refinement; the runtime has one
in-flight item per session. Thus the first rolling request was starved behind
canonical work. The draft lane was off; no rolling decoder request existed to be
slow or waiting in vLLM during this interval.

The eleven canonical decodes total **2.633362 seconds**; their recorded
start-to-publication intervals total **4.745215 seconds**. The remaining
**11.794302 seconds** lie outside those intervals (scheduler/lock/other service
work). The retained events do not time that work. They prove canonical backlog and
dispatch delay, **not** whether cold initialization, CPU contention, a lock holder
or another session caused that remaining delay. Cold start remains unassigned;
no unsupported attribution to model latency or identity embeddings is made.

## F2 — The buffer that evicts, and the repair

The manifest's **960,000 samples / 60 seconds** limits uncommitted ingress. It is
not the rolling ring. `RollingGeometry.max_retained_samples` is **320,000 samples /
20 seconds**, twice the measured ten-second window. The queued request owns its
own immutable ten-second payload. Newer accepted PCM continues accumulating in
the ring while that request waits.

Previously, ring overflow called `_end_refinement(PCM_EVICTED)`, discarded the
in-flight bookkeeping and permanently stopped planning. `capture_refinement_item`
then rejected even the already-admitted immutable request because the converger
was no longer rolling. Event 121 already reports eviction, before item 8 dispatch.
This is not a decoder refusal and not loss of the queued payload's bytes.

The coordinator now supplies its existing complete tape's bounded interval reader
to the converger. When the ring overflows, the immutable request remains valid;
a subsequent missing window is read from the tape, **at the unchanged next rolling
prefix**, only after all its samples are committed. The tape is appended before
rolling observes each newly accepted frame. No new retention store/capacity is
introduced. If the tape is absent, degraded, released, short or does not cover the
interval, rolling still reports `pcm_evicted`; it never invents silence or advances
over the missing interval.

Newest-window re-planning is rejected: with the current monotonic prefix contract,
it would skip unrefined audio and could hide base text. Recovery reads older
already-committed audio without future evidence, preserves existing canonical-first
scheduling and leaves publication under the runtime lock. Genuine empty/failed
decodes and proposal refusals still stop rolling. Abort fences both queued and
in-flight recovered results.

[Prototype, results and one-command reproduction](../../prototypes/streaming-diarization/rolling-eviction-recovery/NOTES.md).
A regression first failed with zero calls, then passed with **[0,10), [10,20),
[20,30)** and exact original PCM. Ring peak remains **320,000 samples**. The full
tape remains subject to its existing separate deployment capacity.

## F3 — DER is high in RTFL, but the regression is elsewhere

Both passes averaged per case. DER = diarization error rate; speech DER restricts
scoring to reference speech. Old values read directly from
`evidence/live-g4-recovery-20260825/deployed-10-10/moss-results.json`, `actual[]`,
`surface_scores.pre_stop_settled`; new values from round-9 `metrics.settled`.

| Case | Aug 25 DER | Round 9 DER | Aug 25 speech DER | Round 9 speech DER |
|---|---:|---:|---:|---:|
| Javier | .113000 | .176800 | .093316 | .1370915 |
| Ackman | .128250 | .156167 | .1128355 | .149808 |
| Keyu | .111167 | .140833 | .090519 | .123669 |
| Adam | .091167 | .123944 | .077717 | .110821 |
| Jamie | .094352 | .104017 | .081653 | .092088 |
| RTFL | .430644 | .4058065 | .352785 | .3262585 |
| Macro | .161430 | .1845946 | .13480425 | .1566227 |

RTFL contributes **36.64% of the current DER macro's summed case errors** and
**34.72% of speech DER**; these are contributions to equal-case means, not pooled
speaker-error seconds. It was **already worse in August**, and improves now by
.0248375 DER / .0265265 speech DER. **Every other case worsens**, with Javier's
DER increase largest (.063800). The five-case means excluding RTFL are .1403522
DER / .1226955 speech DER; excluding it is diagnostic only, not a revised gate.
The macro miss is not a new RTFL-only regression.

## F4 — Speaker counts: distinguish available from absent evidence

Reference counts come from the corpus reference rows. August counts are distinct
non-null speaker IDs actually present on the scored settled surface, not registry
size; both passes agree:

| Case | Reference speakers | Aug 25 settled speakers | Round 9 speakers |
|---|---:|---:|---|
| Javier | 1 | 1 | not retained |
| Ackman | 2 | 2 | not retained |
| Keyu | 2 | 2 | not retained |
| Adam | 2 | 2 | not retained |
| Jamie | 3 | 3 | not retained |
| RTFL | 4 | 4 | not retained |

The round-9 content-free bundle contains neither speaker labels, speaker counts nor
full effective transcript snapshots. Counts cannot be reconstructed from DER or
segment counts. Explicit nulls are retained in
[the comparison data](../../prototypes/streaming-diarization/rolling-eviction-recovery/der-comparison.json).
This is the remaining evidence limit under the no-host boundary, not an inferred
single-/multi-speaker verdict. August RTFL's correct count of four alongside .430644
DER also demonstrates that counting identities alone cannot establish attribution
accuracy. August Jamie's final surface used two visible speakers (versus three at
settled); that separate historical observation is not a round-9 identity finding.

## Validation and decision

Focused production runtime/convergence tests: **49 passed**, including six new
runtime regressions. Full maintained Python suite: **1,417 passed + 37 subtests, two existing skips**,
98.41 seconds.
No frontend changes. QUALITY_BOUNDS, `_validate_quality`, identity policy and server
capture/lease contracts unchanged. No host operations or provider calls.

Ship this bounded plumbing recovery for the demonstrated loss; do not treat it as
resolution of the settled/DER gap. The wait's unmeasured service-time component and
round-9 speaker counts remain explicit unknowns. The unchanged quality gates decide
whether the next deployed candidate improves.
