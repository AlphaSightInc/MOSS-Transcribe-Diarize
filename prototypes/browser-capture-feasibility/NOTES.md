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

The stub accepts prototype-only extra fields (`client_visibility`, `client_wall_ms`,
`quanta`). The deployed v2 contract rejects unknown keys — strip extras before pointing
this page at the real service, and read `frame_samples`/`sample_rate` from
`/api/live/descriptor` instead of hardcoding 8000/16000 (they are deploy-manifest values).

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
