# Draft lane: retain the implementation, keep the demo default off

**D1 — Keep `draft_lane_seconds=None`.** The one-second lane materially improves a single
session, but does not meet the steady-state target with two sessions. One concurrent arm
also stalled and failed. The later successful repeat does not erase it. This is a local
measurement, not provider isolation, release qualification, or proof of unchanged gold quality.

## F1 — What changed

Implementation checkpoint: `c6acb8b7`, on `auto-mvp-0911`, private remote only.

- Optional `--live-draft-lane-seconds`; omitted means no draft requests. One request across
  the runtime, at most 2.5 seconds from the current committed audio boundary. Uses the
  existing runner/prompt resolution and a maximum of 286 generated tokens. No draft work
  enters the canonical/rolling queue or identity preparation.
- Busy canonical queues or a running draft skip the tick. Publication checks lifecycle,
  epoch, committed prefix, and canonical preview under the runtime lock. Canonical coverage
  retires draft text in the same snapshot. Stop/abort fence late results.
- `snapshot.draft` is separate from `snapshot.session`; it carries `authority: "draft"`.
  The reader renders S00 preview rows, replaces successive drafts, and discards them on
  canonical/provisional coverage, including empty/multiple-segment commits. Enabled polling
  bypasses canonical-version suppression because draft publication never changes that version.
- Canonical, rolling, settled, final, identity, `QUALITY_BOUNDS`, and `_validate_quality`
  are unchanged. Three explicit capture tests verify non-empty quality evidence is identical
  with and without a top-level draft. No markup, styling, or acceptance selectors changed.

A held draft does not occupy the canonical worker: a deterministic test commits canonical
work before releasing the draft. **An already-running provider request cannot be preempted.**
The client-side skip rule therefore does not promise GPU priority for later canonical work.

## F2 — Local measurements

Real MOSS decoder through the existing `127.0.0.1:18000` tunnel; no host operations.
Own HTTPS stack on port 17862, own private database/control socket/audio directory.
`mono_javier_intro_50s`, 50 seconds per probe, 0.5-second frames, real-time two-lane Account
Live replay, 100 ms snapshot polling. The same provider manifest and unchanged identity policy.
Eight probes total: six reached `final`; two explicitly did not.

Each pair below lists the two individual sessions; it is not a pooled percentile.
Latencies are seconds. Coverage p50/p95 uses 0.5-second buckets at audio positions 5–40 s.

| Arm | Coverage p50 | Coverage p95 | First text* | Label p50 | Skipped ticks | Decoder requests/audio second | Final word error rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| Single, off | 1.80 | 2.94 | 2.910 | 2.256 | — | 31/50 = 0.62 | 0.0885 |
| Single, 1 s | 0.77 | 2.32 | 1.552 | 2.143 | 17/50 = 34% | 64/50 = 1.28 | 0.0885 |
| Two, off | 2.23 / 2.16 | 3.36 / 3.40 | 2.459 / 2.036 | 2.652 / 2.568 | — | 62/100 = 0.62 | 0.0885 / 0.0885 |
| Two, 1 s, original Stop wait | 27.57 / 22.14† | 45.72 / 45.27† | 1.834 / 0.327 | 28.394 / 22.462† | 95/100 = 95% | 36/100 = 0.36† | **null / null — failed** |
| Two, 1 s, portal Stop wait | 1.30 / 1.72 | 3.17 / 3.36 | 0.547 / 2.252 | 2.589 / 2.539 | 79/100 = 79% | 83/100 = 0.83 | 0.0885 / 0.0885 |

\* The supplied probe subtracts the first emitted segment's audio start (0.84 s in all
these runs), **not independently measured speech onset**. From audio-stream start, first
text arrived at 3.750 → 2.392 s for the single session; at 3.299 / 2.876 s off versus
1.387 / 3.092 s for the successful concurrent on repeat. These are API-visible words,
not measured browser paint times. One single-session observation cannot establish a
first-text p50/p95 distribution.

† Failed-arm coverage quantiles include only 44 observed steady buckets per session;
completed arms have 69. These are censored failure diagnostics, not comparable successful
latency scores. The 36 issued requests include no completed final pass and are not a cost saving.

Successful single off/on both issued **31 non-draft requests**; on added 33 drafts.
Successful concurrent off/on both issued **62 non-draft requests**; on added 21 drafts.
The shared draft slot admitted 17 requests for one concurrent session and four for the other.
This implementation skips, rather than queues, optional work; the imbalance is visible.

The supplied harness called a matching-block heuristic “WER” and truncated the final text.
The retained probe instead computes full Levenshtein word error rate and preserves the old
heuristic separately as `legacy_sequence_match_error`. All six completed runs have actual
WER **0.0885** and legacy score **0.0708**, matching the brief's old number under its old
calculation. No transcript text is retained. This establishes equal final WER on this case, not identical words or unchanged
eight-metric corpus quality.

## F3 — Why the first concurrent on arm failed

Retained local snapshot diagnostics report:

- `kind=transport_pacing`, `code=aborted`, `detail.reason=helper_lease_expired` for both sessions.
  The replay client's `ServiceReplayIdentityCommitFailure` exception name was misleading.
- Completed canonical requests reached **7.17 / 6.66 s** decode time; canonical queue waits
  reached **44.01 / 37.41 s**. Only five draft requests were admitted across 100 ticks.
- Both sessions remained draining around 80 seconds after replay start. The supplied probe
  waits 30 seconds inside Stop, while the helper lease is also 30 seconds, counted from the
  last frame. The lease can expire before that wait returns. `live_helper_failure.py` then
  schedules the terminal failure. `LiveTransportControl.stop` releases the capture registries
  after the awaited stop returns or its error path runs, not before the wait.

The repeat used the portal's five-second Stop wait, with the same product source and lane
option. The other arms had finished Stop within five seconds, so their wait ceiling never
bound. Both repeat sessions finalized, and label p50 did not worsen. **Provider speed also
recovered:** the repeat finished in 53.19 / 53.44 s total. Thus this is not a controlled proof
that the wait change caused recovery, or that drafts caused the earlier slowdown. The final rebase supplied independent peer evidence (`2b5eb340`): its local stack used
this same decoder tunnel, and network records overlap the failed arm (approximately
23:43:54–23:45:14 UTC, reconstructed from our monotonic clock). The peer recorded summary
responses at 23:44:43 and 23:45:03, then another Live session and frames from 23:45:04.
See `peer-overlap.json`. **This arm was not an isolated two-session test.** Exact GPU
occupancy and the causal contribution of peer activity remain unmeasured. No host inspection,
provider tuning, policy change, or helper-lifecycle fix was performed.

## F4 — Validation and decision boundary

- Full application suite: **1,355 passed, 2 skipped, 37 subtests passed**.
- Frontend: **195 passed**; TypeScript check passes; bundle rebuilt after the source-map rebase.
- New runtime/reader checks are browser-free. They cover default off, queued work across
  sessions, canonical progress with a blocked draft, abort/Stop/stale-result fences, draft
  failure isolation, generation replacement, empty and multiple-segment commit retirement,
  same-version account projection, and all three quality-capture boundaries.
- The default remains off. Consider enabling only after representative concurrent runs meet
  the latency target without sacrificing canonical progress and final quality. The present
  evidence supports a useful optional single-session experiment, not a demo-wide default.

## Retained evidence and reproduction

`prototypes/streaming-diarization/draft-lane/results.json` is the aggregate;
individual `single-*`, `two-*` JSON files retain numeric bucket series. The failed arm is
preserved. `*-diagnostics.json` contains selected content-free runtime events.
`decoder-requests.jsonl` counts actual `VllmRunner._post_multipart` calls (including terminal),
using monotonic timestamps and a draft/non-draft bit. Concurrent cost uses the union of the
pair's time interval divided by 100 audio seconds, not duplicated per-session counts.

The measurement used a private copy of the supplied local launcher with the same SQLite-pin
bypass, source checkout, request counter, and draft flag exposed by the retained launcher.
The off process loaded the pre-rebase source; the rebase added only peer source-map/test fixes.
The canonical implementation was identical. Production SQLite qualification was not exercised.

See the bench `NOTES.md` for runnable local commands. Scratch local servers were stopped after
measurement; the existing tunnel and deployment host were left alone.
