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
- At completion of Parts A/B: no GPU request or tunnel; no shared service restart,
  deployment, push, merge or GitHub mutation. The subsequent user instruction
  authorizes merging integration 1745b96f and running Part C with 2,600 requests.
  Real-run source SHA and request counts are recorded separately in its result.

Additional controls: native `--arena production --varying` exercises the changed
constructor without overriding options; 80/80 vectors exactly equal to default
baseline. Count-only replay computes 60 unique embeddings and reuses 1,440 identical
inputs; its final 1,440-segment transcript equals the uncached before run. Its RSS
and byte estimates are excluded. Exact entries: system 15/20/20, mic 20/20/20 at
5/15/30 minutes. R1 (missing terminal-refusal `gaps`) is pre-existing and remains open.

Part C ran on a28eecd9 (merge parent 1745b96f) after the full merged-tree gates.
Actual decoder budget 1,080/2,600, peak two simultaneous; one 1,800-second capture,
zero load-based pauses. Own 18122/17882 processes exited. Real-run evidence is
`real-1789715856876413000/`; draft identity mode remained off. Local stack uses the
prescribed SQLite-version bypass; this is measurement, not deployment qualification.
