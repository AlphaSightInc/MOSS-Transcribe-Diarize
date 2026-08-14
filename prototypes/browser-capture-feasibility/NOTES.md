# Browser-capture feasibility prototype — NOTES

**Status: prototype, throwaway-grade code — but intentionally kept** as the attended
Gate-1 harness required by `docs/research-chrome-capture-mvp-2026-08-03.md`.

## Question

Does the research doc's recommended lane design actually behave as specified in real
Chrome — one `AudioContext({sampleRate:16000})`, an `AudioWorklet` aggregating
128-sample quanta into exact 8000-sample frames, PCM16 JSON frames at 0.5 s cadence,
per-lane sequence/epoch — including with 48 kHz source streams and in a background tab?

## Method (2026-08-09, autonomous run)

`python3 prototypes/browser-capture-feasibility/stub_frame_server.py`, then Chrome 151
(temp profile, `--autoplay-policy=no-user-gesture-required`, same Chrome.app bundle so
TCC state is identical to the user's browser) at `http://127.0.0.1:8899/?autostart=1`.
Two synthetic lanes generated in a separate 48 kHz context (system=997 Hz, mic=440 Hz)
and piped as MediaStreams into the 16 kHz capture context — the same cross-rate resample
path a real capture track takes. ~3 min streamed; capture tab backgrounded for ~1 min of it.

## Verdict — design VALIDATED, all checks pass

- 372 frames/lane, zero sequence gaps, every frame exactly 8000 samples @ 16 kHz, zero
  PCM16 decode errors, RMS 0.3534 = the exact theoretical 0.5/√2 (amplitude-faithful).
- Tone isolation perfect: Goertzel ratio 0.999 @997 Hz on system lane, 0.997 @440 Hz on
  mic lane, 0.000 cross-bleed — lanes do not leak into each other.
- `capture_timestamp_ns` deltas exactly 500,000,000 ns after anchoring the worklet clock
  arithmetically (8000 samples = 62.5 quanta, so naive `currentFrame` stamping jitters ±128 samples).
- **Background tab: no degradation.** Arrival cadence hidden p50/p95/max = 499.7/506.5/~510 ms
  vs visible 499.7/508.1/512.4 ms. Worklet-port-message-driven POSTs are immune to
  background timer throttling (timers would collapse to 1/min).
- Probes: `AudioContext({sampleRate:16000})` honored (rate=16000, baseLatency 8 ms);
  `getSupportedConstraints` includes `restrictOwnAudio`, `suppressLocalAudioPlayback`,
  `echoCancellation`, `voiceIsolation`; UA Chrome/151.
- Command-line-opened tabs carry user activation, so the "no-gesture" `getDisplayMedia`
  probe opened a real picker instead of rejecting — launcher artifact, but also evidence
  the chooser pipeline works on this Mac (the 2026-08-03 `NotReadableError` came from
  CDP test flags, not from the chooser path).

## Attended Gate-1 run — PASSED 2026-08-09

Operator ran the page in Chrome 151: mic lane captured a Bose QC Ultra Bluetooth mic
(native 16 kHz mono, EC/NS/AGC honored off); display lane captured a **window** surface
plus a "System Audio" loopback track (48 kHz stereo) via `windowAudio: "system"`, tone
at Goertzel 0.82. Permissions were granted entirely inline — macOS 26 JIT picker for
video (no `kTCCServiceScreenCapture` row exists) plus an automatic
`kTCCServiceAudioCapture` grant mid-flow. No System Settings visit. A no-audio pick
(`audio=0`) correctly failed preflight. Bonus finding: typed-URL navigations carry user
activation, so an on-load `getDisplayMedia` can open a picker — production page must
capture only from an explicit button. Raw-run `seq_gaps`/clock-delta check failures were
a harness bug (synthetic + real interleaved on one lane name), fixed since: double-attach
refused, stub gained `POST /reset` + a Reset button (restart the stub server once to
pick up `/reset`).

## Contract caveat vs the real server

The page now reads `frame_samples`, `sample_rate`, and `bounds.max_frame_samples` from
`/api/live/descriptor` before creating its capture context. The stub deliberately advertises
3,200-sample frames so a browser run exposes either historical 8,000/16,000-frame fallback. Frame
bodies now contain exactly the nine v2 keys and the stub rejects missing or unknown keys. Prototype
cadence fields (`client_visibility`, `client_wall_ms`, `quanta`) travel separately through
`/prototype/telemetry`.

## Production-route probe — PASSED 2026-08-13

Question: can Chrome create a server-issued session and send the same descriptor-driven frames
through the real `create_app` auth, session, strict-v2, mixer, and runtime routes instead of the
historical `/frames` stub?

Run `PYTHONDONTWRITEBYTECODE=1 python3
prototypes/browser-capture-feasibility/production_route_server.py`, then open
`http://127.0.0.1:8899/capture-harness?autostart=1` in Chrome with autoplay enabled. The runner
uses the production app and a deterministic fake provider; its ephemeral bearer stays in closure
memory and is never printed or persisted.

Chrome 151 created `api-session` only after both synthetic lanes metered non-zero. It sent 329
frames per lane through `/api/live/sessions/api-session/frames`: all HTTP 200, sequences 0–328,
exactly 1,000 samples per descriptor frame, 329,000 accepted samples per lane, zero failed samples,
and no terminal runtime failure. Raw state: `evidence/phase1/t1/iteration-05-production-routes.json`.

This proves browser-to-production-route wiring, not the ticket's model gate. The provider and
transcript are deterministic fakes; no two-speaker WAV, real inference, clean stop, concurrency,
background lease, or real display capture was exercised.

## Production-route strict-key rejection — PASSED 2026-08-13

Question: does the locally-run production v2 frame route reject a telemetry field without
consuming the lane sequence, while the browser's ordinary nine-key frames remain admissible?

Run the production-route probe above and open
`http://127.0.0.1:8899/capture-harness?autostart=1&probe_unknown_frame_key=1` in Chrome. The opt-in
probe sent the nine v2 fields plus `client_visibility` to the authenticated production frame
route. It returned HTTP 400 naming the unknown field. Both lanes then admitted valid sequence 0
and advanced to sequence 177 with zero failed samples, proving the rejection did not mutate lane
state. Cadence telemetry continued over `/prototype/telemetry`, outside frame bodies.

Verdict: the production route, not only the strict stub, enforces the exact nine-key body. This
uses the deterministic provider and does not prove inference or display capture. Raw evidence:
`evidence/phase1/t1/iteration-15-production-unknown-key.json`.

## Production read-path probe — PASSED 2026-08-13

Question: can Chrome use the server-returned view bearer to poll the production `/snapshot` and
`/events` routes, render committed text plus a provisional tail, and retain both cursors when a
render fails?

The same server command above plus
`http://127.0.0.1:8899/capture-harness?autostart=1&fail_render_once=1` ran the deterministic
provider through the production routes. The runtime supplied committed `S01` text. Because this
runtime has no provisional inference scheduler, a clearly labelled snapshot wrapper supplied only
the synthetic `S02` provisional tail used to exercise that render branch.

The injected pre-render failure requested cursor `0/0` and retained `0/0`. The next production
poll repeated `0/0`, rendered six commits plus the provisional tail and 31 event rows, then advanced
to snapshot/event cursors `13/31`. Raw state:
`evidence/phase1/t1/iteration-06-production-read-path.json`.

Verdict: render-then-advance works across both production read routes. This does not prove real
model inference or a real provisional inference publisher.

## Worklet-driven background heartbeat — PASSED 2026-08-13

Question: can either live lane drive the production helper heartbeat route from worklet frame
messages, without a timer, while a hidden Chrome tab renews a deliberately short local lease?

The harness serializes and coalesces heartbeat POSTs across both lane handlers and sends one
strict `moss-live-helper-health.v1` body per descriptor frame interval. Chrome's DevTools target
API activated a blank sibling tab, leaving the capture target hidden for 12.000 s against a
2.0 s local helper lease, then reactivated it.

All 417 heartbeat POSTs returned HTTP 200 with zero heartbeat sequence gaps. Hidden heartbeat
p50/p95/max was 64/64/65 ms versus visible 64/65/70 ms; both production frame lanes had hidden
p95 65 ms, matching visible p95 65 ms. The production v2 session remained active with both lanes
healthy after 6.0 lease periods hidden. Raw measurement:
`evidence/phase1/t1/iteration-07-background-heartbeat.json`.

This proves the synthetic Chrome background-cadence and local production lease seams. It does
not prove real model inference, microphone input, or real display capture.

## Automated fake-device microphone seam

Question: can the acceptance fixture enter through Chrome's real `getUserMedia()` microphone
path while the system lane is explicitly synthetic, without automating display capture?

Launch Chrome with `--use-fake-device-for-media-stream`,
`--use-file-for-fake-audio-capture=<known-two-speaker.wav>`,
`--use-fake-ui-for-media-stream`, and open
`/capture-harness?autostart_mic_canary=1`. The page starts the microphone through
`getUserMedia()` and supplies only the system lane from its 997 Hz oscillator. It records the
microphone track label/settings and the two source APIs separately in prototype telemetry; the
host fixture path remains outside the page and evidence.

This is the automatable G1/G2 source shape. A run against the deterministic provider proves only
the Chrome microphone-to-production-route seam; the gate remains open until the same path renders
real model transcript text with at least two speaker ids.

Measured 2026-08-13 with Chrome 151 and a 60 s, 16 kHz fixture whose reference contains three
speakers and three switches. The browser exposed `Fake Default Audio Input` at 44.1 kHz stereo,
then the production capture graph resampled it to the descriptor's 16 kHz / 1,000-sample frames.
Across 1,254 frames per lane there were zero sequence gaps, 1,254,000 accepted samples per lane,
zero failed samples, and no terminal failure. The microphone frame-RMS envelope matched the source
WAV over 959 frames at correlation 0.99957 (mean absolute error 0.00085); this proves the fixture,
not merely an extant fake track, reached `getUserMedia()` and the production ingress route. Raw
frame measurements: `evidence/phase1/t1/iteration-08-fake-mic-production-routes.json`.

The server provider was still the deterministic `api-fake`; its rendered text is not model output.
Therefore neither real transcription nor the two-speaker-id gate passed in this measurement.

## Local production-model admission — PASSED 2026-08-13

Question: can this host load the exact immutable MOSS snapshot through the production
`ModelRunner` and emit a non-empty diarized transcript with at least two speaker ids from the
known acceptance fixture?

One-command probe:

```bash
PYTORCH_ENABLE_MPS_FALLBACK=1 python3 \
  prototypes/browser-capture-feasibility/direct_model_smoke.py \
  --model <snapshot-directory> --audio <multi-speaker-wav>
```

Revision `e8681d68e7042738ffca8ac8212bc8fcb1131ab8` (1,833,163,202 snapshot bytes;
weight SHA-256 `9a0ceb4a...07026c4`) loaded through the production runner. The 60 s fixture produced
538 tokens and four distinct speaker ids in 29.066 s inference / 30.663 s wall time. Although
PyTorch reports MPS available, production `device=auto` resolved to CPU with float32.

Verdict: this host can run the exact real model fast enough for the next live-path experiment.
This does not exercise the live runtime, provider bundle, HTTP routes, Chrome, or rendered output,
so G1 remains open. Raw output: `evidence/phase1/t1/iteration-09-direct-model-smoke.json`.

## Real model through Chrome/live routes — PASSED, teardown still open 2026-08-13

Question: can Chrome fake-device microphone audio traverse the production v2 routes, the
manifest-admitted live provider bundle, and the local production `ModelRunner`, then return to the
same browser as diarized text with at least two speaker ids?

One-command server:

```bash
PYTORCH_ENABLE_MPS_FALLBACK=1 python3 production_route_server.py \
  --model <snapshot-directory> --live-provider-manifest <host-finalized-manifest>
```

Chrome sent 236 descriptor-sized frames on each lane (sequences 0–235, zero gaps, all HTTP 200)
and 236 worklet-driven heartbeats (all HTTP 200). The runtime accepted 1,888,000 samples, exactly
236 × the manifest's 8,000-sample frame geometry. Before teardown it committed 46 real-model spans
and Chrome rendered four distinct model ids, S01–S04. The system lane was a synthetic oscillator;
this does not prove display capture.

Verdict: the browser → production routes → provider bundle → real model → production reads → same
browser G1 path passes. Clean stop does not: the probe detached its lanes before asking the runtime
to drain, which also stopped worklet heartbeats. The 2 s prototype helper lease expired during the
real-model drain, so stop returned 429 with two pending items and the runtime aborted. Keep the
ticket open and make stop-before-detach/lease-safe drain the next probe. Raw evidence:
`evidence/phase1/t1/iteration-10-real-model-browser.json`.

## Lease-safe real-model stop — PASSED 2026-08-13

Question: can the production stop route drain genuine pending model work while worklet-driven
heartbeats remain active, then detach capture only after the server returns exact closed
accounting?

Run the real-model server command above, launch the same fake-device Chrome canary with
`stop_deadline_seconds=30`, and invoke `stopCapture(realOut)` while the production snapshot reports
pending work. The stop request began with one pending work item. It took 2.720 s, longer than the
2.0 s helper lease; six worklet-driven heartbeats crossed that interval and all returned 200.
Stop returned HTTP 200 with the runtime and both v2 lanes closed at 1,912,000 accepted/accounted
samples and zero pending work. The page detached capture 1 ms after recording the stop response.
Six frames per lane raced after terminal stop began and correctly returned 409; none were admitted.

Verdict: stop-before-detach fixes the measured lease expiry without extending the lease. This is
one real-model browser session only; the issue's two-simultaneous-session clean-stop criterion
remains open. Raw evidence: `evidence/phase1/t1/iteration-11-lease-safe-stop.json`.

## Concurrent real-model browsers — isolation/latency PASSED, teardown RED 2026-08-13

Question: can two independent Chrome processes stream distinct fake-microphone fixtures at once,
render only their own real-model transcript, record commit-to-render latency, and stop cleanly?

Two server-issued sessions ran simultaneously. Client A rendered 2,256 characters with S00–S03
and its JP Morgan marker but no football marker. Client B rendered 1,123 characters with S00–S07
and its football marker but no JP Morgan marker. Across 53 canonical commits, commit-to-render was
152 ms p50 / 247 ms p95 / 260 ms max. Both clients had zero sequence gaps, dropped frames,
discontinuities, or fetch errors. The local model resolved to CPU/float32, so GPU memory and
utilization are recorded as not applicable rather than invented.

Teardown failed. Continued looping ingress filled the configured 16-item per-session queues
(17 pending including in-flight work). Client B observed 238 v2-frame 429s; one
`InferenceArbiterBackpressure` escaped the frame route as ASGI 500 and terminalized its runtime
instead of remaining non-terminal. Client A's awaited stop crossed the browser automation timeout
and was retried, producing a conflicting 409; its original drain then returned 429. Client B also
returned 429. Both stopped
view tokens became 401, and the sole prototype capture credential was revoked HTTP 200 and then
rejected for reuse HTTP 401.

Verdict: simultaneous rendered-text isolation and latency measurement pass, but the two-clean-stop
criterion remains open. First fix the proven 500/terminal backpressure mapping with a regression;
then stop each one-pass fixture before saturation and trigger each drain exactly once without
awaiting through the automation timeout. Raw evidence:
`evidence/phase1/t1/iteration-12-concurrent-browser-probe.json`.

## Bounded concurrent clean stop — PASSED 2026-08-13

Question: after the v2 backpressure fix, can two bounded one-pass Chrome sources retain the
passing isolation/latency result and each issue exactly one clean drain before queue saturation?

Both independent Chrome processes used the same distinct 60 s fixtures with the fake-audio
`%noloop` suffix. Each rendered its own marker and multiple speaker ids with no cross-marker.
Across 43 commits, commit-to-render latency was 150/246/263 ms p50/p95/max; no pre-stop frame
returned 429 or 500, and telemetry had zero sequence gaps. Each non-reentrant fire-and-monitor
trigger produced exactly one stop request. The drains completed in 44.062 s and 41.402 s with
HTTP 200, closed runtime/v2 state, exact accepted/accounted samples, zero pending work, and
revoked view credentials. The sole test capture credential was then revoked and rejected on reuse.

Verdict: the two-simultaneous-session clean-stop criterion now passes on the locally-owned real
model route. System lanes remained synthetic, so this still does not prove display capture. Raw
evidence: `evidence/phase1/t1/iteration-14-concurrent-clean-stop.json`.

## Safari attended diagnostic — 2026-08-09

Safari 26.5 captured the Bose QC Ultra microphone successfully: 110 HTTP-200 frames,
zero sequence gaps/fetch/decode errors, exact 8000-sample frames at 16 kHz, exact 500 ms
capture-clock deltas, nonzero PCM range (-10024..11558), and RMS mean 0.0186. This
directly refutes "Safari cannot capture the local microphone."

The same run did **not** test Safari display-audio output. The 86-frame 997 Hz `system`
lane was the synthetic oscillator left active after a partial synthetic/real collision.
Thus `both_lanes_present=true` was not two-source Safari evidence; the failed 440 Hz and
sine-amplitude checks were expected because the microphone lane contained real voice,
not the synthetic 440 Hz oscillator.
The initial attended display attempts failed before a picker with `InvalidStateError` because
the harness awaited `captureContext()`/`resume()` before invoking `getDisplayMedia()`;
Safari had correctly expired transient user activation. The harness now invokes
`getDisplayMedia()` first, refuses partial synthetic startup when any lane is active,
preflights busy real lanes, and labels reset as server-data-only. After refresh, the
attended rerun opened Safari's picker and measured:

- window: `video=1 audio=0`, `displaySurface=window`, 1876×960 at 30 fps;
- full screen: `video=1 audio=0`, `displaySurface=monitor`, 1920×1080 at 30 fps.

Safari 26.5 therefore captures the local microphone and display video, but exposes no
audio track for either a shared window or full screen on this Mac.

## Attended completion runs — 2026-08-09 evening (Chrome 151, clean state)

- **Tab surface (MVP-preferred), first-ever measurement — PASSED**: `displaySurface=browser`
  plus a dedicated "Tab audio" track (44.1 kHz stereo, 2.9 ms latency). 112 mic + 57
  system frames, zero gaps, exact 8000 @ 16 kHz, exact 500 ms capture clocks on both
  lanes, 997 Hz Goertzel 0.9264 with zero 440 Hz bleed, cadence p95 ≤ 508 ms. Both
  attaches logged `context running` — the getDisplayMedia-first reorder is verified not
  to regress the tested mic-first Chrome flow. Because the context was already running,
  this does not isolate post-picker resume or prove the sticky-activation mechanism.
- **Entire screen — PASSED**: `displaySurface=monitor` + "System Audio" loopback
  (48 kHz stereo), 30/30 frames HTTP 200. Verdict JSON was lost because Reset ran after
  Stop (lesson: reset BEFORE a run; `/reset` returns the verdict it discards, while the
  page shows only the discarded frame counts/checks).
- Still no `kTCCServiceScreenCapture` row after monitor capture — screen video runs via
  the macOS 26 just-in-time picker; the only durable grant is `kTCCServiceAudioCapture`.
- Chrome 151 rejects gestureless `getDisplayMedia` with `NotAllowedError`
  ("Permission denied by user"), not the spec's `InvalidStateError`. That error name is
  ambiguous with real denial: production should call only from a click, stop on either
  error, and offer a user-driven retry rather than retrying automatically.

**All three product-relevant Chrome picker classes are measured on this Mac:** tab,
window, monitor. The certified two-lane startup is mic-first; a display-first/system-only
suspended-context bootstrap remains a separate, non-MVP experiment. Remaining required
work: Gate 2 (4070 canary), Gate 3 (bounded concurrency), Gate 4 (Windows).

## Server helper-vocabulary probe — 2026-08-13

**Question:** can browser-only capture facts extend the existing
`moss-live-helper-health.v1` `failure_code` field without a parallel browser enum or
health path, and what semantics does the production coordinator apply?

**Method:** a throwaway Python probe passed one native reference code, seven proposed
browser codes, and one unregistered sentinel through the production
`HelperHeartbeat.from_dict` → `HelperPresenceRegistry.observe` →
`LiveHelperFailureCoordinator.observe` path. One command:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 prototypes/browser-capture-feasibility/probe_helper_failure_vocabulary.py
```

The throwaway script was deleted after its output was captured at
`evidence/phase1/t5/iteration-2-helper-vocabulary-probe.txt`.

**Verdict:** the existing string field and coordinator are already the correct shared,
additive transport. All codes survived unchanged. A `failed` fact invoked
`LiveV2Session.fail_lane` only for its named lane and kept the lease/peer alive; a
`degraded` fact remained in helper presence without failing a lane. The unregistered
sentinel also survived, so the parser deliberately enforces stable non-empty shape, not
a closed code allowlist. Do not tighten it and break additive helper/version
compatibility.

The smallest production extension is therefore a server-owned named vocabulary and
status mapping on this existing path, using observation-shaped browser codes:
`browser_microphone_permission_denied`, `browser_capture_request_rejected` (not
`picker_cancelled`, because Chrome's rejection name is ambiguous),
`browser_surface_audio_missing`, `browser_track_ended`,
`browser_audio_context_suspended`, `browser_sustained_clipping`, and
`browser_microphone_silent`. Failed versus degraded remains the existing `state` field;
no browser-only health schema or coordinator is justified.

## Server capture-status projection — 2026-08-13

The measured vocabulary above is now absorbed by the server projection in
`moss_transcribe_diarize/app/live_capture_status.py`. Snapshot responses publish exactly one
`capture_phase` and one `status_line` while retaining raw `helper_presence` for `/live`
diagnostics. Failed facts outrank degraded facts deterministically; a single failed lane stays
`recording` when its peer remains usable; unknown additive codes receive generic server copy.
The silent-microphone line names Chrome's Settings > Privacy and security > Site settings >
Microphone remedy. The focused production-path suite passed 83 tests and 351 subtests; raw output
is `evidence/phase1/t5/iteration-3-capture-status-projection.txt`.

## G7 worklet-driven lease probe — 2026-08-13

**Question:** does a heartbeat triggered only by descriptor-sized AudioWorklet frame messages
keep the production server lease alive when Chrome remains backgrounded for longer than one
minute?

**Method:** a throwaway probe served a local `create_app(live_enabled=True)` instance with the
production heartbeat route and lease coordinator, plus a headed isolated Chrome 151 profile. Two
synthetic 48 kHz MediaStreams traversed a 16 kHz AudioContext and descriptor-driven worklets. The
microphone worklet message serialized one heartbeat; the page and worklet contained neither
`setInterval` nor `setTimeout`. A second tab held the foreground for 65.01 s. The probe used a
strict 2 s lease. Its script was deleted after capture.

**Verdict:** mechanism **passed**. While `document.visibilityState` stayed `hidden`, both worklets
delivered 130 frames each. The server accepted 130 hidden-tab heartbeats with arrival p50/p95/max
497.69/506.82/507.35 ms; all 136 total heartbeat requests returned 200. The runtime remained
`active`, its v2 session remained present, and no terminal failure occurred.

This is not final G7 acceptance. Chrome and the production heartbeat/lease path were real, but
the local service used the repository test runtime provider and synthetic sources because ticket
#1's product client has not landed. Repeat this measurement through that client and its local
production-provider service before checking the issue criterion. Raw output:
`evidence/phase1/t5/iteration-5-g7-worklet-lease.txt`.

## X1 slow-POST characterization — 2026-08-14

**Question:** when a strict-v2 frame POST takes longer than the route's frame period, does the
actual worklet page lose frames, serialize them, or accumulate in-flight HTTP requests?

**Method:** `probe_slow_post_characterization.py` starts the existing local production-route
harness and headless Chrome with its normal synthetic two-lane worklets. Middleware delays each
frame response by 100 ms only after the real strict-v2 route has admitted it. The page still uses
its own descriptor (1,000 samples at 16 kHz: 62.5 ms per frame), transport, telemetry, and
heartbeat path. One command:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/browser-capture-feasibility/probe_slow_post_characterization.py \
  --output evidence/phase1/x1-frame-drop/iteration-2-slow-post-characterization.json
```

**Verdict:** the checked-out page did not silently lose frames at this measurement point, but it
did not queue or backpressure them either. Each lane emitted and the strict-v2 route admitted 50
frames over about 3.065 s (the elapsed cadence estimate is also 50), while four frame responses
were simultaneously held. The durable assertion joins route admission to elapsed worklet cadence,
so a return to a one-in-flight drop guard would fail it. The measurement is not G7 and uses the
deterministic provider, synthetic sources, and the harness descriptor.

The smallest next policy is one descriptor-driven FIFO and one serial sender **per lane**: derive
its bounded frame capacity from `max_retained_samples / frame_samples`, assign a sequence only as
the head is sent, and keep the exact head for the route's established retry taxonomy. If that FIFO
fills, drop only with a cumulative `dropped_frames` count and a discontinuity mark on the first
post-gap frame; do not silently advance the wire sequence. Raw arrays and server response-hold
metrics: `evidence/phase1/x1-frame-drop/iteration-2-slow-post-characterization.json`.

## X1 descriptor-bounded FIFO regression — 2026-08-14

**Question:** after replacing concurrent frame POSTs with the measured per-lane FIFO, does a
slow strict-v2 response preserve admitted frames at worklet cadence while keeping each lane to one
in-flight POST?

**Method:** `probe_slow_post_characterization.py` again drove real headless Chrome, the page's
two 48 kHz synthetic sources, and the local production strict-v2 route. The middleware held each
frame response for 100 ms, longer than the 62.5 ms descriptor frame period. The page derived its
per-lane queue capacity from the live descriptor's `320000 / 1000 = 320` frames; raw worklet
timestamps, wire sequences, queue depths, route admissions, and held-response arrays are in
`evidence/phase1/x1-frame-drop/iteration-3-slow-post-fifo.json`.

**Verdict:** passed. Over about 2.93/3.00 s, microphone/system admitted 49/50 frames versus
48/49 elapsed-cadence frames (the permitted one-record observation race). Both lanes held exactly
one frame response at a time, wire sequences were 0..47 and 0..48 in worklet order, and queued
depth peaked at 21 of 320 without drops. The sender retains its FIFO head across an unsuccessful
response; overflow increments the heartbeat's real `dropped_frames` and marks the first later
admitted frame discontinuous.

This proves the P0 slow-POST transport case only. It does not exercise an overflow, 409/recreate,
production 8000-frame geometry, a five-minute hidden tab, display capture, or a real provider.
