# Context Glossary

## Live Capture

- **Live session**: Default-off, local-only session state for ordered 16 kHz
  mono PCM16 frames. It is separate from the batch job workflow.
- **Mono runtime frame**: The existing `AudioFrame` accepted by
  `LiveSession`, with `sequence`, `sample_rate`, `sample_count`, and PCM bytes.
- **Live v2 lane contract**: Additive JSON contract named
  `moss-live-service.v2` for source-labelled capture frames and
  acknowledgements. It does not create independent per-lane ingestion in the
  mono runtime.
- **Lane**: Canonical source label on a v2 frame or acknowledgement. The only
  valid lanes are `system` and `microphone`.
- **System lane**: V2 lane for captured system audio.
- **Microphone lane**: V2 lane for captured microphone audio.
- **Sequence**: Non-negative, per-lane frame counter in the v2 contract. The
  mono runtime still receives its existing single `AudioFrame.sequence`.
- **Capture timestamp**: Non-negative `capture_timestamp_ns` supplied by the v2
  frame producer.
- **Device epoch**: Non-negative `device_epoch` supplied by the v2 frame
  producer to identify a capture-device epoch.
- **Silent flag**: Exact boolean v2 frame field indicating producer-observed
  silence.
- **Discontinuity flag**: Exact boolean v2 frame field indicating a producer
  discontinuity at the frame boundary.
- **PCM16 payload**: Strict base64-encoded 16-bit mono PCM bytes. The decoded
  byte length must equal `sample_count * 2`.
- **V2 acknowledgement**: Lane-qualified acknowledgement carrying the existing
  mono facts: sequence, sample range, accepted samples, retained samples, and
  frozen span ids.
- **V2 descriptor**: JSON-compatible descriptor with protocol range `2..2` and
  capabilities `lanes=true`, `binary=false`, `idempotent_frames=true`, and
  `resumable=true`.
- **Protocol negotiation**: Highest-common-version selection between a client
  range and the server v2 descriptor.
- **Obsolete client**: Typed negotiation failure for a client range below the
  server minimum. The HTTP adapter maps it to a 426-style response payload.
- **Prior acknowledgement replay**: Bounded v2 contract behavior keyed by
  `(lane, sequence)` that returns a stored acknowledgement for an accepted
  duplicate without mutating accepted or retained totals.
- **Pruned replay**: Typed failure when a duplicate key is older than an
  explicit v2 replay-store prune boundary.
- **Default-off transport adapter**: Existing FastAPI live route attachment
  that is absent unless live is explicitly enabled. It validates v2 JSON frames
  before adapting them to the mono runtime.
