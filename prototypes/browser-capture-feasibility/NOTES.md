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
