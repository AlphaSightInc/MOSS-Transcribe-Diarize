# Capture-health observation contract

Status: metadata carrier implemented; user-facing policy remains deferred.

## Problem demonstrated

`LiveV2SessionSnapshot` has cumulative sample accounting and current lane health, but no
server arrival time or histories of silence and rejected requests. The committed probe and raw
output under `evidence/phase1/x3-capture-health/` demonstrate four indistinguishable snapshot
pairs: silent versus voiced input; a snapshot before versus after elapsed server time; a
snapshot before versus after repeated sequence gaps; and a snapshot before versus after repeated
per-lane capacity rejections.

Therefore `project_live_capture_status()` must not infer any of those conditions from the
current snapshot fields.

## Minimal carrier

`LiveCaptureObservationRegistry` is session-scoped and metadata-only in
`live_capture_status.py`; the v2 frame route in `live_transport.py` mutates it after classified
ingress outcomes. Those two paths are owned by x3. It stores no PCM, client-provided timestamps,
or retained frame objects.

Each lane records only:

| Observation | Writer | Reset condition | Why |
| --- | --- | --- | --- |
| `last_server_arrival_monotonic_ns` | successful v2 acceptance | never except session removal | measures freshness from the server's clock |
| `consecutive_silent_samples` | successful v2 acceptance | a non-silent accepted frame | preserves sustained silence after accounting releases frames |
| `consecutive_sequence_rejections` | out-of-order v2 rejection | a successful v2 acceptance | exposes an unresolved sequence gap without treating a one-off retry as persistent |
| `consecutive_backpressure_rejections` | v2 retryable 429 | a successful v2 acceptance | distinguishes server saturation from a sequence conflict |
| `last_rejection_monotonic_ns` | either v2 rejection above | never except session removal | lets later policy require a recent condition |

The registry accepts an injectable server-monotonic clock and the snapshot projection receives a
typed immutable copy of the record. A later measured policy must derive age there, never from the
browser's `capture_timestamp_ns`. Lane accounting and reported lane health continue to come from
`LiveV2SessionSnapshot`; browser-only facts continue to come from helper presence, as ruled in
`.wayfinder/tickets/T-02-poll-contract-event-model.md`.

The route creates the record with its v2 session, updates it only after the corresponding
accept/rejection outcome is known, and passes it to `/snapshot` projection. A lifecycle facade
releases or expires the observation with the v2 session, including helper-lease expiry, which
prevents stale observations from leaking across session ids.

## Deliberately deferred policy

This proposal does **not** choose a stale-age, silence duration, or rejection-count threshold,
and does not map the facts to `capture_phase` or product wording. No existing lease duration or
frame geometry is silently reused as a health threshold. A subsequent prototype must measure
real browser frame cadence and endpoint recovery, then record the policy verdict before this
carrier drives a status claim.

Terminal reason reachability remains x6-owned in `live_service_runtime.py`; this carrier does
not change terminal cleanup or authorization behaviour.
