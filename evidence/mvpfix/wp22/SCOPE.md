# WP22 source and measurement scope

- Only writable checkout: `MOSS-Transcribe-Diarize-wt-wp22-memory-longrun`.
- Branch: `mvpfix/wp22-memory-longrun`; initial source `8938cb2c` (WP15 integrated).
- Mono source: local `git archive 37979e53` extracted under `.wp22/base`.
- Before/after long profiles run in independent processes. Before loaded original
  encoder code before the production edit. After loaded the four-line change.
- Both compare the same two public 60-second corpus clips, repeated for 1,800 audio
  seconds; mic -10 dB throughout Part A. Half-second frames, original capture clock.
- Part A uses the existing 9,600,000-byte tape limit; expected exhaustion after five
  minutes is recorded, not hidden. Part C alone gets the authorized 57,600,000-byte copy.
- Runtime descriptor provider is explicitly `wp22-stub-asr`; its synthetic source
  marker is not claimed as release identity. Real source identity is recorded here.
- Tracemalloc and explicit `gc.collect` affect overhead. RSS is current `ps` resident
  memory; tracer metadata separately reported. It is neither system RAM nor peak RSS.
- Structure bytes are recursive Python-owned estimates, deduplicated within each
  owner, not a sum of independent physical allocations. Native ONNX state excluded.
- First encoder use loads libraries/model; cold process baseline must not be treated
  as a promise that Stop unloads a deployment-scoped model.
- Main profile: production V2 ingress, mixer, VAD, ONNX identity, coordinator,
  rolling and terminal runtime; fake speech decoder; no HTTP/SQLite/MP3.
- Supplemental HTTP publication profile: production transport/SQLite/audio pipeline,
  fake ASR/identity and always-speech VAD; synthetic PCM, 1,800 audio seconds.
  Publication queue counts sampled after each pair of HTTP frame posts; no claim
  that transient queue occupancy between samples was zero.
- No GPU request, tunnel, shared service restart, deployment, push, merge or GitHub
  mutation occurred. Part C remains pending the user's WP12 confirmation.
