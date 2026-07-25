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
and typed obsolete-client errors. It must not add deployment enablement, a
binary transport, WebSockets, or independent per-lane runtime ingestion.

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
adapted to the existing mono `AudioFrame` seam. V2 acknowledgements add the
validated lane to the existing mono acknowledgement facts.

Protocol negotiation selects the highest common version. An obsolete client
range below the server minimum returns a typed payload with required minimum
version and maps to an HTTP 426-style response.

Binary framing and non-HTTP transports are deferred to protocol v3.

## Consequences

- The current mono decoder, coordinator, scheduler, transcript grammar,
  accounting, finality, provider selection, and batch behavior remain unchanged.
- Lane-labelled v2 data is representational at this slice; it does not create
  independent per-lane retention, epochs, ingestion, mixing, recovery, or final
  drain behavior.
- Clients can discover the v2 contract through the default-off descriptor and
  can fail with a stable machine-readable obsolete-client response.
- JSON plus base64 is less efficient than binary transport, but keeps the MVP
  auditable and compatible with the existing disabled HTTP route seam.
