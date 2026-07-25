# ADR 0001: Live v2 uses JSON over HTTP

## Status

Accepted.

## Context

The live path is a default-off local substrate. IDEA-028 adds a
`moss-live-service.v2` contract for two source-labelled capture lanes while
preserving the existing mono inference runtime and six-operation
`LiveServiceRuntime` interface.

The hard contract needs strict validation, deterministic JSON-compatible domain
objects, highest-common protocol negotiation, lane-qualified acknowledgements,
typed obsolete-client errors, and independent pre-mixer source-lane admission.
It must not add deployment enablement, a binary transport, WebSockets, or a
server-side mixer.

## Decision

V2 live transport remains JSON over the existing default-off HTTP adapter.
Frame PCM is base64-encoded PCM16. The descriptor declares protocol range `2..2`
and capabilities:

```json
{
  "lanes": true,
  "binary": false,
  "idempotent_frames": true,
  "resumable": true
}
```

The adapter continues to accept the existing v1 mono frame payload shape. A v2
frame is detected by its v2-only metadata fields, strictly validated first, then
admitted into one in-memory lane ingress instance for its live session. V2
acknowledgements are lane-local, keep `queued_item_ids` empty, and report the
current unchanged mono snapshot version. V2 admission does not call
`LiveServiceRuntime.accept_frame`; IDEA-030 owns compatibility mixing into
canonical mono `AudioFrame`s.

Lane ingress independently sequences `system` and `microphone`, fences
device-epoch transitions, enforces per-lane retained-sample capacity, stores
complete immutable accepted frames including PCM and capture metadata, and
returns prior acknowledgements for bounded lane-qualified duplicates. A corrected
same-sequence retry after a rejected gap, capacity overflow, or epoch transition
can succeed because failed admissions do not mutate ingress state.

Protocol negotiation selects the highest common version. An obsolete client
range below the server minimum returns a typed payload with required minimum
version and maps to an HTTP 426-style response.

Binary framing and non-HTTP transports are deferred to protocol v3.

## Consequences

- The current mono decoder, coordinator, scheduler, transcript grammar,
  accounting, finality, provider selection, and batch behavior remain unchanged.
- Lane-labelled v2 data now terminates at independent in-memory ingress. It
  does not prove mixing, recovery, reconnect, lifecycle cleanup, provider
  quality, deployment, or live enablement.
- Prior acknowledgements use an ingress-local 256-entry replay window,
  independent of retained PCM/metadata and the runtime event-ring bound. The
  oldest acknowledgement is pruned when the window fills, so new frames continue
  and replaying a pruned key returns the typed `v2_pruned_replay` conflict.
- Device-epoch advancement requires a marked discontinuity, stale epochs return
  a typed conflict, retained-sample overflow returns typed backpressure, and
  stop fails closed while accepted v2 lane frames remain unconsumed by the
  future mixer. Abort may explicitly discard the session ingress.
- Clients can discover the v2 contract through the default-off descriptor and
  can fail with a stable machine-readable obsolete-client response.
- JSON plus base64 is less efficient than binary transport, but keeps the MVP
  auditable and compatible with the existing disabled HTTP route seam.
