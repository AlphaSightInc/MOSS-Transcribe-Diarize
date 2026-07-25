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
server-side mixer inside the v2 ingress/session lifecycle.

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
admitted into one in-process `LiveV2Session` for its live session. V2
acknowledgements are lane-local and report the current mono snapshot version.
V2 ingress acknowledgement is not mono admission; IDEA-030 owns compatibility
mixing into canonical mono `AudioFrame`s.

Lane ingress independently sequences `system` and `microphone`, fences
device-epoch transitions, enforces per-lane retained-sample capacity, stores
complete immutable accepted frames including PCM and capture metadata, and
returns prior acknowledgements for bounded lane-qualified duplicates. A corrected
same-sequence retry after a rejected gap, capacity overflow, or epoch transition
can succeed because failed admissions do not mutate ingress state.

One in-process `LiveV2SessionRegistry` owns v2 session lifetime at the transport
seam. Each session exposes additive per-lane reconnect state, accounts only
whole retained frame prefixes after downstream consumer success, releases
capacity only after accounting, conserves typed lane failures as failed samples,
uses loop-owned async stop notification, supports explicit expiry, and releases
terminal registry/PCM state after clean stop, abort, terminal failure, or
explicit expiry. A rejected unaccounted stop is non-terminal and retains state
for retry or abort.

Protocol negotiation selects the highest common version. An obsolete client
range below the server minimum returns a typed payload with required minimum
version and maps to an HTTP 426-style response.

One in-process `LiveCompatibilityMixer` plus a per-session registry bridges
retained `system` and `microphone` lane frames into the unchanged mono runtime.
It interprets `capture_timestamp_ns` as the frame's first PCM sample time,
seals lane intervals with successor timestamps or final nominal ends, resamples
onto a shared 16 kHz mono grid, applies exact per-lane headroom and the
registered soft limiter, then calls `LiveServiceRuntime.accept_frame`. Source
lane prefixes are accounted only after successful mono admission.

Binary framing and non-HTTP transports are deferred to protocol v3.

## Consequences

- The current mono decoder, coordinator, scheduler, transcript grammar,
  accounting, finality, provider selection, and batch behavior remain unchanged.
- Lane-labelled v2 data now terminates at an in-process source-lane session
  lifecycle and a server-owned compatibility mixer. This proves local
  retention, compatibility mixing, downstream accounting, failure, finality,
  explicit expiry, and cleanup mechanics only; it does not prove helper-crash
  detection, provider quality, deployment, or live enablement.
- Prior acknowledgements use an ingress-local 256-entry replay window,
  independent of retained PCM/metadata and the runtime event-ring bound. The
  oldest acknowledgement is pruned when the window fills, so new frames continue
  and replaying a pruned key returns the typed `v2_pruned_replay` conflict.
- Device-epoch advancement requires a marked discontinuity, stale epochs return
  a typed conflict, retained-sample overflow returns typed backpressure, and
  stop fails closed while accepted v2 lane frames remain unaccounted by the
  future mixer. Clean stop requires exact accepted/accounted equality with zero
  failed, retained, or pending work. Abort and explicit expiry may discard a
  session with terminal accounting.
- Clients can discover the v2 contract through the default-off descriptor and
  can fail with a stable machine-readable obsolete-client response.
- JSON plus base64 is less efficient than binary transport, but keeps the MVP
  auditable and compatible with the existing disabled HTTP route seam.
- Server-owned mixing keeps JSON/HTTP and independent source retention intact,
  but makes the server responsible for timestamp alignment, limiter behavior,
  mono runtime admission, and post-admission source accounting.
