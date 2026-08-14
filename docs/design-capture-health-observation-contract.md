# Capture-health observation contract

Status: prototype finding, not yet a production policy.

## Problem demonstrated

`LiveV2SessionSnapshot` has cumulative sample accounting and current lane health, but no
server arrival time or histories of silence and rejected requests. The committed probe and raw
output under `evidence/phase1/x3-capture-health/` demonstrate four indistinguishable snapshot
pairs: silent versus voiced input; a snapshot before versus after elapsed server time; a
snapshot before versus after repeated sequence gaps; and a snapshot before versus after repeated
per-lane capacity rejections.

Therefore `project_live_capture_status()` must not infer any of those conditions from the
current snapshot fields.

## Minimal carrier proposal

Keep a session-scoped, metadata-only capture-observation registry in
`live_capture_status.py`; mutate it at the v2 frame route in `live_transport.py`. Those two
paths are owned by x3. Do not store PCM, client-provided timestamps, or retained frame objects.

Each lane records only:

| Observation | Writer | Reset condition | Why |
| --- | --- | --- | --- |
| `last_server_arrival_monotonic_ns` | successful v2 acceptance | never except session removal | measures freshness from the server's clock |
| `consecutive_silent_samples` | successful v2 acceptance | a non-silent accepted frame | preserves sustained silence after accounting releases frames |
| `consecutive_sequence_rejections` | out-of-order v2 rejection | a successful v2 acceptance | exposes an unresolved sequence gap without treating a one-off retry as persistent |
| `consecutive_backpressure_rejections` | v2 retryable 429 | a successful v2 acceptance | distinguishes server saturation from a sequence conflict |
| `last_rejection_monotonic_ns` | either v2 rejection above | never except session removal | lets later policy require a recent condition |

The snapshot projection receives a typed immutable copy of this record and its clock. It derives
age there, not from the browser's `capture_timestamp_ns`. Lane accounting and reported lane health
continue to come from `LiveV2SessionSnapshot`; browser-only facts continue to come from helper
presence, as ruled in `.wayfinder/tickets/T-02-poll-contract-event-model.md`.

The route must create the record with a v2 session, update it only after the corresponding
accept/rejection outcome is known, return it in `/snapshot`, and remove it with the v2 session.
That lifecycle pairing prevents stale observations from leaking across session ids.

## Deliberately deferred policy

This proposal does **not** choose a stale-age, silence duration, or rejection-count threshold,
and does not map the facts to `capture_phase` or product wording. No existing lease duration or
frame geometry is silently reused as a health threshold. A subsequent prototype must measure
real browser frame cadence and endpoint recovery, then record the policy verdict before this
carrier drives a status claim.

Terminal reason reachability remains x6-owned in `live_service_runtime.py`; this carrier does
not change terminal cleanup or authorization behaviour.
