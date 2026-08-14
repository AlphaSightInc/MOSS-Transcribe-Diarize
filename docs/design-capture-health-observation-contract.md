# Capture-health observation contract

Status: metadata carrier and measured projection policy implemented.

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

## Measured policy inputs

Iteration 6's committed local-route probe and raw output record the policy inputs. The probe
drives `create_app`'s authenticated production v2 frame, heartbeat, and snapshot routes with the
Chrome harness's measured descriptor geometry (8,000 samples at 16 kHz). It measures server
arrival cadence, a post-frame stall, sustained silence, repeated classified sequence/capacity
rejections, and recovery after the next accepted route frame.

The Chrome worklet harness is the browser-cadence source: visible p95 508.1 ms, hidden p95
506.5 ms, and a maximum 512.4 ms, with no hidden-tab degradation. The route probe's decision is:

| Server observation | Non-healthy threshold | Why | Recovery fact |
| --- | ---: | --- | --- |
| No accepted arrival | 2,000 ms | Four descriptor periods, about 3.9× hidden-tab p95 | Next accepted frame refreshes the server arrival time |
| Consecutive silence | 32,000 samples | Four 8,000-sample descriptor frames = 2,000 ms | Next voiced accepted frame resets to zero |
| Sequence rejection | 4 consecutive outcomes | Does not flag one resync, but detects the repeated wedge | Correct accepted frame resets to zero |
| Retryable backpressure | 4 consecutive outcomes | Does not flag one retry, but detects sustained refusal | Peer-lane drain plus accepted retry resets to zero |

The evidence is `evidence/phase1/x3-capture-health/iteration-06-live-route-thresholds.json`,
written by its committed adjacent probe. `LiveCaptureHealthPolicy` now derives the two
duration/sample thresholds from the runtime descriptor: four `frame_samples` periods at its
`sample_rate`; rejection thresholds remain four classified outcomes. The projection accepts an
injectable server-monotonic clock, evaluates only active lanes which have accepted audio, and
returns a server-authored non-healthy line for sustained sequence rejection, backpressure,
silence, or an expired accepted arrival. A successful accepted frame still resets the relevant
transient counters and refreshes the server arrival time.

## Terminal reason readback observation

Iteration 9's committed local-route probe captures the terminal-helper path that the ordinary
snapshot projection cannot see after cleanup. A helper heartbeat reports the server-owned
`browser_microphone_permission_denied` code, then the helper-failure coordinator records it in
the runtime's terminal detail, aborts the mono runtime, and releases helper, v2, mixer, tape,
and access state. The persisted runtime snapshot says `aborted` / `helper_failed` and still
contains the typed microphone code, but the next authenticated `/snapshot` returns only `403`
for the former capture credential (and `401` for the former view credential). Neither response
contains `capture_phase`, a plain-language status line, or the permission reason.

The raw output is
`evidence/phase1/x3-capture-health/iteration-09-terminal-reason.json`, written by its committed
adjacent probe. This refutes the earlier assumption that x6's terminal-runtime snapshot work
settles x3 terminal readability: x6 is not yet reconciled into `dev`, and its explicit-abort
distinction does not preserve access after the helper path releases it. Terminal reason
reachability remains an open x3 acceptance item; the next change must choose and prove one
server-authored terminal response contract without exposing credentials.
