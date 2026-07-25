# Context Glossary

## Live Capture

- **Live session**: Default-off, local-only session state for ordered 16 kHz
  mono PCM16 frames. It is separate from the batch job workflow.
- **Mono runtime frame**: The existing `AudioFrame` accepted by
  `LiveSession`, with `sequence`, `sample_rate`, `sample_count`, and PCM bytes.
- **Live v2 lane contract**: Additive JSON contract named
  `moss-live-service.v2` for source-labelled capture frames and
  acknowledgements. It admits source lanes independently before any canonical
  mono mixing.
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
  wire facts: sequence, lane-local sample range, lane-local accepted samples,
  lane-local retained samples, and frozen span ids.
- **Lane ingress**: Independent admission and bounded in-memory retention of
  validated source-lane frames before canonical mono mixing.
- **Live v2 session**: In-process lifecycle authority for one live session's v2
  lane ingress. It owns reconnect facts, accounting, failure, stop, abort,
  explicit expiry, and terminal release for source lanes before mixing.
- **Live v2 session registry**: In-process map from live session ids to their
  live v2 sessions. It retains non-terminal retry state and releases terminal
  sessions.
- **Live v2 session snapshot**: Additive HTTP-visible status object with
  independent per-lane next sequence, accepted/accounted/failed/retained
  samples, device epoch, replay-prune watermark, health, and stable failure
  code.
- **Retained lane frame**: Complete immutable accepted v2 source frame,
  including PCM bytes and capture metadata, awaiting the compatibility mixer.
- **Ingress conservation**: Each successful v2 acknowledgement corresponds
  exactly once to one retained lane frame, or admission fails without changing
  ingress state.
- **Accounted lane frame**: Retained source frame whose whole lane-local prefix
  has been accepted by the downstream consumer and removed from retained PCM.
- **Accounted lane prefix**: Highest contiguous lane sequence accounted in one
  atomic request. Invalid, future, gapped, regressing, partial, or
  consumer-failed prefixes leave every lane unchanged.
- **Failed lane samples**: Samples conserved from retained frames after a typed
  lane failure. Failed samples are terminal accounting, not clean completion.
- **Clean finality**: Terminal live v2 state where every lane has accepted
  samples equal to accounted samples, with zero failed, retained, or pending
  work.
- **Explicit expiry**: Caller-declared terminal lifecycle outcome for an
  abandoned live v2 session. It is a cleanup mechanism, not helper-crash
  detection.
- **Terminal release**: Registry and retained-PCM cleanup after clean stop,
  abort, terminal failure, or explicit expiry. Rejected non-terminal stop keeps
  state available for retry or abort.
- **V2 descriptor**: JSON-compatible descriptor with protocol range `2..2` and
  capabilities `lanes=true`, `binary=false`, `idempotent_frames=true`, and
  `resumable=true`.
- **Protocol negotiation**: Highest-common-version selection between a client
  range and the server v2 descriptor.
- **Obsolete client**: Typed negotiation failure for a client range below the
  server minimum. The HTTP adapter maps it to a 426-style response payload.
- **Prior acknowledgement replay**: Bounded v2 contract behavior keyed by
  `(lane, sequence)` that returns a stored acknowledgement for an accepted
  duplicate without mutating accepted or retained totals. Its transport-local
  window automatically prunes the oldest acknowledgement instead of blocking
  new frames.
- **Pruned replay**: Typed failure when a duplicate key is older than an
  explicit v2 replay-store prune boundary.
- **Default-off transport adapter**: Existing FastAPI live route attachment
  that is absent unless live is explicitly enabled. It validates v2 JSON frames
  before lane ingress, and continues to send v1 mono frames to the mono runtime.
