# Chrome capture MVP feasibility — measured diagnosis

Date: 2026-08-03; independently reviewed and updated 2026-08-09  
Scope: diagnosis/prototypes only; no production change, deployment, restart, or running-job control.

## Bottom line

The browser architecture is technically feasible for a **Chrome-only attended MVP**. On this
MacStudio, Chrome 151 simultaneously captured two distinct live tracks:

- a Bose QC Ultra microphone through `getUserMedia()` (16 kHz mono); and
- the selected window's `System Audio` loopback through `getDisplayMedia()` (48 kHz stereo).

Both meters moved, both lanes reached the local HTTP prototype with zero fetch errors, and a 997 Hz
fixture was detected only on the system lane. This proves local Chrome capture and two-lane framing.
Separate attended runs also proved all three product-relevant Chrome picker classes on this Mac:
tab + Tab audio, window + System Audio, and full monitor + System Audio.
It does **not** yet prove audio-to-4070 transcription: the attended run used the local stub, while
the earlier direct-browser production-route probe used synthetic frames.

The word **speaker** is ambiguous here. The browser does not receive permission to control or read
the speaker hardware. It receives an audio `MediaStreamTrack` for the user-selected tab/window/
screen when Chrome and the selected surface offer audio. The display-share chooser does not include
the microphone; microphone capture is a separate `getUserMedia()` permission. Therefore:

- "Chrome works with system/window audio and microphone" — **correct**, using two APIs/tracks.
- "Chrome offers speaker audio but not microphone access" — **false for Chrome overall**; true only
  if it means that the display-share chooser itself does not bundle a microphone.
- "Safari can send Safari-page audio but not local microphone" — **reversed** for arbitrary meeting
  capture. Safari can obtain local microphone audio with `getUserMedia()`, but current Safari does
  not expose arbitrary tab/window/system output audio through `getDisplayMedia()`.

Safari 26.5 has now produced correctly framed local-microphone PCM through the same browser graph and
stub. It can send that lane to the 4070 once production transport is wired. A page may also process
media that the **same page owns** through Web Audio when origin/CORS/DRM rules permit; that narrow
case is not permission to capture another Safari tab or macOS system output and is not implemented
by this MVP.

The FastAPI HTTPS/session transport is not Chrome-specific. Safari can call it under the same TLS,
pairing, token, and frame contract. What is Chrome-specific is the required arbitrary meeting-output
capture. The kept prototype also intentionally warns outside Chrome; it is a diagnostic harness,
not a finished Safari client.

The production-facing design remains:

- two independent browser-side streams, resampled/downmixed to the deployed MOSS contract;
- HTTPS frames tagged with the server-issued session ID and authorized by a device token;
- transcript/event polling authorized by a separate, session-scoped view token.

The failed 2026-08-03 automated attempt is retained below as history, not the current verdict. Its
virtual microphone was silent and CDP source-selection flags produced `NotReadableError`. The
ordinary attended chooser on 2026-08-09 superseded that result.

Browser-to-server correlation **was proved**. Two isolated Chrome profiles concurrently sent frames
over HTTPS through the production FastAPI live routes. Each posted 100/100 frames, retained its exact
400- versus 600-sample total, read its own session, and received HTTP 403 when reading the other.

A real Chrome-audio-to-4070 transcription was deliberately not run. It remains Gate 2 and must wait
for a safe GPU window. The live service is explicitly TLS port **7861**, not default HTTPS port 443:
`https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861` and
`https://100.64.0.8:7861` answered during the final review. Port 443 timed out because it is not the
configured listener; that was a probe-target error, not evidence of a tailnet outage. No service or
job was restarted, signalled, or otherwise touched.

## Current implementation boundary

What exists now:

- the kept diagnostic harness under `prototypes/browser-capture-feasibility/`;
- measured Chrome and Safari capture evidence in this report and the harness `NOTES.md`;
- the deployed FastAPI live service on TLS port 7861 with protocol-v2 lane ingestion;
- measured two-browser session/token isolation using synthetic frames.

What does **not** yet exist or pass:

- a production browser capture page integrated into `/live`;
- descriptor-driven framing/auth/pairing in the kept harness (it still posts prototype extras to a
  local stub and hardcodes 8000/16000);
- real Chrome audio → 4070 inference → diarized transcript → browser rendering (Gate 2);
- certified bounded multi-session inference (Gate 3) or Windows Chrome capture (Gate 4).

## Browser capability matrix

| Browser/source | Chrome 151 on this Mac | Safari 26.5 | Meaning |
|---|---:|---:|---|
| Local microphone (`getUserMedia`) | **Yes, measured signal** | **Yes, measured signal** | Separate browser permission; not part of the display chooser. |
| Selected Chrome tab audio | **Yes, measured signal (2026-08-09 evening)** | No equivalent arbitrary-tab audio track | Chrome 151 returned a dedicated "Tab audio" track (`displaySurface=browser`, 44.1 kHz stereo); 997 Hz Goertzel 0.926 on the system lane. |
| Selected window + system output | **Yes, measured signal** | **Video=1, audio=0 measured** | Chrome returned `System Audio`; Safari returned window video only. |
| Entire-screen/system output | **Yes, measured signal (2026-08-09 evening)** | **Video=1, audio=0 measured** | Chrome returned `displaySurface=monitor` plus "System Audio" loopback (48 kHz stereo); Safari returned monitor video only. |
| Direct speaker-device access | **No** | **No** | The browser captures an offered media track, not speaker hardware. |
| Media played by the MOSS page itself | Conditional | Conditional | Web Audio may tap page-owned, non-protected media; not arbitrary browser/system capture. |

Evidence labels used below:

- **Measured:** raw output from this MacStudio or production-route tests.
- **Supported/inferred:** standards/vendor behavior not directly exercised in the attended run.
- **Open:** still requires a clean manual run or scheduled 4070 canary.

## Validation addendum — 2026-08-09 re-verification

An independent re-check of the separate Claude session's raw pane/session evidence, prototype
artifacts, current source, focused tests, macOS permission state, and browser specifications
confirmed the core feasibility verdict. It also corrected three overstatements: the Safari run did
not exercise capture buttons; one Mac's inline permission flow is not universal; and URL navigation
must not be treated as guaranteed user activation.

**Code claims confirmed** by file inspection. Claude reported the broader live/contract suites
passing; the independent review reran the six isolation/fairness/mixer/lane tests: 6/6 passed in
3.82 s initially and 2.68 s after the final document audit. Refinements an implementer must know:

- The 8000-sample frame, queue depth 16, 60 s retention, and 2.5 s hard cap are
  **deploy-manifest values, not code constants** (the in-code default would be
  16000-sample frames). The browser client must read `/api/live/descriptor` at start
  and honor `frame_samples`, `sample_rate`, and bounds from it, never hardcode them.
- Frame validation is strict: **exactly the nine v2 keys**, unknown keys rejected,
  `silent`/`discontinuity` must be JSON booleans, and `pcm_base64` must decode to exactly
  `sample_count * 2` little-endian bytes. Telemetry belongs elsewhere, never in frames.
- Client status semantics: 400 = malformed frame (client bug); 409 = sequence conflict or
  terminal session (resync or recreate); 429 on the v2 lane path = **non-terminal**
  backpressure (retry). The legacy mono path's backpressure is terminal for the session —
  always send v2 lane frames.
- The mixer aligns lanes by `capture_timestamp_ns` across lanes (origin is the max of the
  lanes' first-frame stamps; tails seal by cross-lane comparison), so the shared-clock
  rule below is load-bearing, not stylistic.

**Platform claims confirmed** with one correction, fixed in place in the snippet below:
`systemAudio`/`windowAudio` are top-level options, not audio constraints. `windowAudio`
shipped in Chrome 141. `restrictOwnAudio` is a real constraint and is supported by the
local Chrome (present in `getSupportedConstraints`, verified live).

The first accidental Safari 26.5 run proved only gesture enforcement and API presence. A
subsequent attended run directly proved Safari microphone capture: Bose QC Ultra at native
16 kHz, 110 HTTP-200 frames, zero sequence gaps/fetch/decode errors, exact 8000-sample
frames and 500 ms capture timestamps, PCM range -10024..11558, RMS mean 0.0186. This is
enough to certify Safari's local mic-to-browser-framer path; it is not a 4070 canary.

Its first `system` verdict (86 frames, 997 Hz ratio 0.9988) came from the synthetic
oscillator, not Safari display audio.
Accordingly, `both_lanes_present=true` does not mean Safari captured both sources.
`microphone_is_440hz=false` and `sine_amplitude_sane=false` are expected for a real voice
microphone because those checks score the synthetic two-oscillator experiment.
The display button failed before the picker because the harness awaited worklet/context
setup before calling `getDisplayMedia()`, allowing Safari's transient activation to
expire. After the harness fix, attended Safari sharing measured both offered surface
types. Window selection returned `video=1 audio=0`, `displaySurface="window"`, 1876×960
at 30 fps. Full-screen selection returned `video=1 audio=0`, `displaySurface="monitor"`,
1920×1080 at 30 fps. Safari supplied no audio track in either case. This closes the
Safari display-output question on this Mac and agrees with WebKit compatibility evidence.

**Key reframe — meeting-tab audio needs no macOS permission.** Sharing a *Chrome tab* with
"also share tab audio" has worked on macOS since Chrome 74 and never touches the
Screen-Recording TCC service — Chrome captures its own tab compositor and audio. The
Chrome 142 / macOS 14.2 change cited below gates only *entire-screen/window system
loopback* audio. The preferred meeting-tab path should therefore work on this Mac today
with zero TCC grants, and the missing TCC row blocks only the entire-screen fallback. The
2026-08-03 `NotReadableError` — which hit tab capture too, where TCC does not apply — is
attributable to the CDP test-flag selection path, not OS permission. During this
re-verification, real (non-flagged) Chrome 151 opened the display chooser normally.
Gate 1 below should test tab-share first and treat entire-screen as the separately
TCC-gated case.

**Environment drift since 2026-08-03**: Chrome is now 151.0.7922.76 (version gate still
comfortably met). Descriptor checks on the configured TLS listener, port 7861, returned
HTTP 200 over both tailnet DNS and `100.64.0.8`, source revision `9089b332…`. A separate
check that omitted `:7861` timed out on default port 443; a side-by-side final review
reproduced 443=timeout and 7861=HTTP 200 for both addresses. This was a port-selection
mistake, not a proved network flap or service recovery. Make the explicit port part of
every origin/preflight. No remote service was restarted or probed with a mutating request.

**TLS decision (operator, 2026-08-09): certificate trust is explicitly out of scope for
the MVP.** The service is reachable only from the guarded LAN/tailnet, so the MVP keeps
the existing self-signed/untrusted certificate and testers click through the browser
interstitial ("Advanced → Proceed") once per browser profile for the service origin. This
works only because capture UI and API share that origin: after the click-through the page
is a secure context (capture APIs available) and all frame POSTs are same-origin. Two
hard constraints remain: plain `http://` can never host the capture page (not a secure
context — `navigator.mediaDevices` is absent), and a capture page on any *other* origin
cannot fetch this API (subresource fetches to untrusted-cert hosts fail with no
click-through option). Revisit real certificates only when the MVP graduates beyond
LAN/tailnet operators.

**Recommended lane design empirically validated** (prototype kept at
`prototypes/browser-capture-feasibility/` as the attended Gate-1 harness): synthetic
48 kHz two-lane streams (997 Hz system, 440 Hz microphone) through the exact recommended
graph produced, over ~3 minutes, 372 frames per lane with zero sequence gaps, every frame
exactly 8000 samples at 16 kHz, amplitude-faithful PCM16 (measured RMS 0.3534 = the
theoretical 0.5/√2), perfect tone isolation (Goertzel ratio 0.999/0.997 on the intended
lanes, 0.000 cross-bleed), and `capture_timestamp_ns` deltas of exactly 500,000,000 ns.
With frame POSTs driven by worklet port messages instead of timers, cadence in a
**backgrounded tab** (p50/p95 499.7/506.5 ms) was indistinguishable from foreground
(499.7/508.1 ms) — background timer throttling never touches the path. Implementation
notes from this run are folded into "Recommended lane design" below.

**Gate 1 PASSED — attended operator run, 2026-08-09 (Chrome 151, Bluetooth headset).**
The microphone lane captured a real Bose QC Ultra Bluetooth mic; Chrome delivered a
native 16 kHz mono telephony-mode track with echo cancellation, noise suppression, and
auto gain honored off. The display lane captured a **window** surface plus a
"System Audio" loopback track (48 kHz stereo, deviceId `loopback`) — `windowAudio:
"system"` worked, carrying the 997 Hz fixture tone at Goertzel ratio 0.82 on the system
lane. Permissions happened **entirely inline on this Mac**: macOS 26 used the OS-mediated
just-in-time picker for window video (no `kTCCServiceScreenCapture` row exists even
after the run) and silently added a `kTCCServiceAudioCapture` (System Audio Recording
Only) grant for Chrome mid-flow — no System Settings visit occurred. This does not prove
that every macOS version/permission state avoids System Settings; denied, revoked, or
older configurations still need a fallback path. Operational findings: (1) a
surface picked without the share-audio toggle yields `audio=0` and preflight correctly
fails — the lane-meter preflight is genuinely necessary; (2) this harness launch happened
to let an on-load probe open the picker, but the standard requires transient activation;
do not depend on URL/omnibox navigation as activation, and call capture only from an
explicit button; (3) the loopback lane hit full-scale PCM (±32767), so the production
page should meter and warn on sustained clipping. Verdict checks that failed in the raw
attended run (`seq_gaps`, clock deltas) traced to a harness bookkeeping bug — synthetic
and real streams interleaved on one lane name at the accumulating stub — since fixed
(double-attach now refused; stub gained `/reset`); clean-phase cadence was p95 ≤ 508 ms
on both lanes with zero fetch errors.

**Attended completion runs — 2026-08-09 evening (clean state, post-fix harness).** The
tab surface — the MVP's preferred path — is now measured: Chrome 151 returned
`displaySurface=browser` video plus a dedicated **"Tab audio"** track (44.1 kHz stereo,
2.9 ms latency) for the 997 Hz tone tab. Clean verdict: 112/112 microphone and 57/57
system frames, zero sequence gaps, every frame exactly 8000 samples at 16 kHz,
capture-clock deltas exactly 500,000,000 ns on both lanes, system-lane 997 Hz Goertzel
0.9264 with zero 440 Hz bleed, cadence p95 ≤ 508 ms foreground and background. Both
attach points logged `context running`, proving the reordered handler did not regress the
tested mic-first Chrome flow. It does **not** prove that `resume()` changed a suspended
context after the picker: the shared context was already running, so the sticky-activation
mechanism was not isolated. A second run
captured **entire screen + "System Audio" loopback** (`displaySurface=monitor`,
`deviceId=loopback`, 48 kHz stereo; 30/30 frames HTTP 200) — page-log evidence only,
because "Reset recorded data" was clicked after Stop and cleared the stub before
`/verdict` was read (operational lesson: reset before a run, never after; `/reset` returns
the discarded verdict, while the page displays only its frame counts/checks). Even after
monitor capture, the queried per-user TCC database still had **no**
`kTCCServiceScreenCapture` row — screen video ran through the just-in-time picker; the
only durable display-capture-related row observed was `kTCCServiceAudioCapture`. One
Chrome-151 behavior note: the gestureless `getDisplayMedia` probe now rejects with
`NotAllowedError` ("Permission denied by user") rather than the spec's
`InvalidStateError`. Do not infer the exact cause from Chrome's exception name:
`NotAllowedError` also represents an explicit denial/dismissal. Production must invoke
capture only from a click, stop on either error, and offer a user-driven retry rather
than retrying automatically.

## Decision table

| Question | Result | Evidence |
|---|---|---|
| Can Chrome obtain a microphone track here? | **Yes, measured signal** | Chrome 151 returned the Bose track; meter moved, accumulated lane RMS mean ≈ 0.064, zero fetch errors. The 08-03 virtual-mic track was silent. |
| Was live microphone signal proved? | **Yes — 2026-08-09 attended** (No on 08-03) | Bose QC Ultra Bluetooth mic: native 16 kHz mono track, EC/NS/AGC honored off, nonzero PCM/RMS. The mixed-state stub run did not independently prove speech intelligibility. |
| Can Web Audio run at MOSS's 16 kHz? | Yes | `new AudioContext({sampleRate:16000})` reported 16,000 Hz. The input track remained 48 kHz, so Chrome performed the graph conversion. |
| Was Chrome tab/window/monitor audio captured here? | **Yes — all three picker classes measured 2026-08-09** | Tab: dedicated 44.1 kHz `Tab audio`, clean Goertzel 0.9264. Window and monitor: 48 kHz `System Audio` loopback. Monitor evidence is page-log/HTTP-ACK level because its verdict was reset. |
| Is the platform/version gate theoretically met? | Yes | macOS 26.5.1; Chrome 150 on 08-03, 151.0.7922.76 at the 08-09 attended runs. Chromium enabled macOS system-audio capture by default from Chrome 142 on macOS 14.2+. |
| Can two Chrome clients map to separate server sessions? | Yes | Direct two-profile HTTPS prototype passed all own/cross routing checks. |
| Are MOSS's two lanes already supported? | Yes | Deployed descriptor reports protocol v2, `lanes=true`, 16 kHz, 8,000 samples/frame; targeted lane/mixer tests passed. |
| Can current inference execute multiple sessions concurrently? | Not yet proved; current dispatcher is serial | One canonical pump worker drains sessions round-robin. Ingestion is concurrent and fair; decode calls are not parallel on this path. |
| Can multiple full model instances fit this 4070 Ti now? | No evidence; current state argues no | 16,376 MiB total, 15,641 MiB used, 423 MiB free during inspection. Prefer measuring one vLLM engine's batching first. |
| Does Safari lack microphone capture? | **No — measured** | Safari 26.5 sent 110 cleanly framed Bose-mic frames to the local stub with nonzero PCM/RMS and zero transport/decode errors. |
| Can Safari capture arbitrary Safari-tab/window/system output? | **No — measured for window and full screen** | Safari 26.5 returned `video=1 audio=0` for both `displaySurface=window` and `displaySurface=monitor`; page-owned media remains a separate narrow case. |

## What was observed

### Mac/Chrome — 2026-08-03 baseline, superseded where noted

- macOS 26.5.1; Google Chrome 150.0.7871.187.
- Audio devices include BlackHole 2ch, Mac Studio Speakers, Virtual Desktop Mic, Virtual Desktop
  Speakers, and a TV + BlackHole multi-output device.
- On 08-03 Chrome had microphone permission but no readable `kTCCServiceAudioCapture` or
  `kTCCServiceScreenCapture` row. During the 08-09 attended run macOS created an allowed
  `kTCCServiceAudioCapture` row for Chrome; no screen-capture row appeared.
- Microphone constraints disabling echo cancellation, noise suppression, and auto gain were honored;
  the requested mono channel count was not. Returned settings remained two-channel/48 kHz.
- The 08-03 display-capture failure was later superseded by an ordinary chooser success;
  the failure was specific to the automated/CDP selection path.

### Deployed 4070 service — read-only observations at inspection times

- Configured origin: `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861` (or
  `https://100.64.0.8:7861`). `/live` and `/api/live/descriptor` returned HTTP 200 on
  port 7861. Default HTTPS port 443 has no configured listener and timed out. The LAN
  address `192.168.68.38:7861` timed out from this MacStudio during the original check.
- TLS is encrypted but not trusted by the Mac trust store: normal `curl` failed with
  `unable to get local issuer certificate`; `curl -k` succeeded. ~~This is a browser-MVP blocker unless
  the CA is trusted or the service receives a normally trusted certificate.~~ *Superseded
  2026-08-09: MVP deliberately keeps the untrusted certificate and uses a one-time
  interstitial click-through on the same-origin capture page — see the TLS decision in the
  validation addendum.*
- Descriptor: source revision `9089b332...`, protocol `moss-live-service.v2`, two lanes, JSON rather
  than binary frames, idempotent/resumable frames, 16 kHz, 8,000 samples per frame, queue depth 16,
  60 seconds retained audio, 2.5-second hard span cap.
- `moss-live-web`, `moss-web`, and `moss-vllm` remained active with `NRestarts=0`. No service or
  existing helper was stopped, restarted, signalled, or reused.

## Browser capture contract

This is not a generic “speaker permission.” The browser must ask for two different sources:

```js
const microphone = await navigator.mediaDevices.getUserMedia({
  audio: {
    echoCancellation: false,
    noiseSuppression: false,
    autoGainControl: false,
  },
});

// Must run inside a click handler. The user chooses a tab/window/screen every run.
// CORRECTED 2026-08-09: systemAudio / windowAudio are TOP-LEVEL DisplayMediaStreamOptions
// members (W3C + MDN); nested inside `audio: {}` they are silently ignored. Only
// constrainable properties such as restrictOwnAudio belong in the audio dictionary.
const display = await navigator.mediaDevices.getDisplayMedia({
  video: true, // required by the web standard even when only audio is consumed
  audio: { restrictOwnAudio: false },
  systemAudio: "include",   // offer system audio when a monitor surface is picked
  windowAudio: "system",    // Chrome 141+: audio offer when a window is picked
});

const systemTrack = display.getAudioTracks()[0];
if (!systemTrack) throw new Error("The selected surface supplied no audio track");
```

The display chooser is irreducible. The standard requires a fresh user choice every capture and
does not allow persistent `granted` display permission. Audio is optional even when requested, and
audio-only `getDisplayMedia()` is invalid. The MVP must show a clear preflight screen:

1. click **Start capture**;
2. allow microphone;
3. choose the meeting tab (preferred) or entire screen;
4. explicitly enable **share tab/system audio**;
5. verify both lane meters are non-zero before creating a server session.

For browser meetings, selecting the meeting tab with “share tab audio” is the narrowest and likely
most reliable path. Entire-system audio is broader, more privacy-sensitive, and OS-permission
dependent. Either gives mixed remote audio, not participant metadata. MOSS diarization and its
voiceprint/name layer remain responsible for speaker identity.

## Recommended lane design

Keep microphone and display audio separate in the browser and send the existing `microphone` and
`system` v2 lanes. Do not premix in the browser for the first MVP.

- Both lanes should enter one `AudioContext({sampleRate:16000})` so timestamps share one monotonic
  clock and the graph handles 48 kHz → 16 kHz conversion.
- Use an `AudioWorklet`, not `MediaRecorder`. Aggregate 128-sample render quanta into exactly 8,000
  mono float samples, clamp/convert to signed PCM16, and POST every 0.5 seconds.
- Derive `capture_timestamp_ns` from the audio render clock/current frame, not `Date.now()`.
- Maintain an independent `sequence` and `device_epoch` per lane. Increment the epoch when a track is
  replaced or restarted; mark discontinuities explicitly.
- Retain the display video track for the capture lifetime but do not transmit or render it.
- If a selected surface has no audio track, fail preflight. Do not silently call that a system lane.

Implementation notes validated by the 2026-08-09 prototype run:

- Fetch `/api/live/descriptor` first and take `frame_samples`, `sample_rate`, and bounds
  from it — they are deployment-manifest values, and the in-code default differs (16,000
  samples per frame, i.e. 1-second frames).
- Drive frame POSTs from the worklet's port-message handler, never from `setInterval`/
  `setTimeout`. Background tabs throttle timers to as little as once per minute; port
  messages from the real-time audio thread are not throttled (measured: hidden-tab p95
  506.5 ms vs foreground 508.1 ms).
- 8000 samples is 62.5 render quanta, so frame boundaries land mid-quantum. Anchor the
  lane's clock once at the first delivered sample (`currentFrame`) and advance
  arithmetically by `frames_sent × 8000`; stamping each frame with `currentFrame` at fill
  time jitters by up to ±128 samples (measured exact 500,000,000 ns deltas with anchoring).
- Both lanes' worklets read the same context frame counter, so per-lane anchors stay
  cross-lane comparable — which the server mixer depends on for origin/tail alignment.
- Keep each lane's graph attached to `ctx.destination` through a zero-gain node so the
  context is unambiguously active without audible playback.
- Send exactly the nine v2 keys; the server rejects unknown fields.
- **Activation ordering (cross-browser, learned from the 2026-08-09 Safari failure):**
  invoke `getDisplayMedia()` synchronously before the handler yields — awaiting
  worklet/context setup first caused Safari to lose transient activation and reject with
  `InvalidStateError`. The attended Chrome certification started the microphone first,
  so the shared context was already `running` when display capture began; it proves this
  mic-first ordering is regression-free, not that a suspended context can always resume
  after a long picker interaction. For the two-lane MVP, require mic/audio-engine preflight
  and verify `ctx.state === "running"` before enabling **Start display**. Prototype a
  display-first/system-only bootstrap separately before supporting that mode. The Web
  Audio specification permits user agents to gate initial start on sticky activation,
  but do not substitute that mechanism inference for a measured fresh-profile path.
  `getUserMedia()` has no transient-activation requirement, so the microphone handler may
  resume first — measured working in both browsers.

Echo policy (decided by operator, 2026-08-09): the preflight screen asks whether the
client hears the meeting through **headphones or speakers**. Headphones mode captures the
microphone raw as specified above. Speakers mode enables `echoCancellation` on the
microphone lane only — Chrome AEC then removes the re-captured meeting audio from the mic
lane at some cost to raw voice features; the system lane stays raw either way. Record the
chosen mode with the session so diarization quality can be interpreted per mode.

The deployed JSON payload is:

```js
await fetch(`/api/live/sessions/${encodeURIComponent(sessionId)}/frames`, {
  method: "POST",
  cache: "no-store",
  headers: {
    "Authorization": `Bearer ${deviceToken}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    lane: "system",                 // or "microphone"
    sequence,
    capture_timestamp_ns,
    device_epoch,
    pcm_base64,                     // mono signed little-endian PCM16
    sample_count: 8000,
    sample_rate: 16000,
    silent: false,
    discontinuity: false,
  }),
});
```

Raw audio is 32 kB/s/lane. Base64 raises this to about 42.7 kB/s/lane, or about 85.3 kB/s for two
lanes before JSON/TLS overhead. This is modest for LAN/Tailscale. Binary WebSocket frames are an
optimization, not an MVP requirement.

Client-side premixing is feasible with a `ChannelMerger`/gain graph, but loses lane health,
provenance, independent restart, and server-side echo/mixing choices. Use it only as an explicit
fallback mode after separate-lane certification.

## Why transcripts do not cross clients

The current server has four reinforcing boundaries:

1. `POST /api/live/sessions` generates a random session ID; the browser must use the returned ID.
2. The capture token resolves to a device principal. Every frame/snapshot/events path checks that
   the requested session's `owner_device_id` equals that device.
3. The view token is generated for exactly one session and cannot send frames. A token for session A
   receives 403 when used against session B.
4. Runtime state, v2 lane state, mixer, tape, event deque, decoder wrapper, and identity preparer are
   created per session and indexed by session ID.

The direct Chrome prototype intentionally raced session creation. Profile A happened to receive
server ID `browser-B` and profile B received `browser-A`; both still routed correctly because each
used the ID returned in its own response rather than assuming creation order.

Measured direct-browser result:

```text
Chrome profile A: accepted=100, own snapshot=200, other snapshot=403, samples=400
Chrome profile B: accepted=100, own snapshot=200, other snapshot=403, samples=600
```

An additional in-process production-route probe gave the same result and also proved that view
tokens could read only their own session and could not write frames. Six existing targeted tests
passed for capture/view scope, device ownership, round-robin fairness, lane mixing, independent lane
capacity, and lane-specific replay acknowledgements.

Independent review command (2026-08-09; latest run 6 passed in 2.68 s):

```bash
.venv/bin/pytest -q \
  tests/test_live_auth.py::LiveAccessRegistryTest::test_capture_and_view_authority_have_exact_action_and_session_scope \
  tests/test_live_auth.py::LiveAccessRegistryTest::test_device_ownership_revocation_and_session_release \
  tests/test_live_service_runtime.py::test_ready_sessions_drain_round_robin_without_hot_session_starvation \
  tests/test_live_mixer.py::test_mixer_emits_16k_mono_from_capture_timestamp_anchors_and_accounts_after_admission \
  tests/test_live_api.py::LiveApiTest::test_v2_http_replays_prior_ack_and_keeps_lane_sequences_distinct \
  tests/test_live_api.py::LiveApiTest::test_v2_http_maps_lane_capacity_to_429_without_mutating_or_sharing_capacity
```

For an eventual WebSocket transport, preserve the same rule: authenticate once, bind the socket to
an immutable server-issued session, and never accept a target session ID on later messages. Use a
per-session outbound queue; never publish transcripts through an unfiltered global broadcaster.

## Real multi-client bottleneck

Browser correlation is not the limiting part. Current inference scheduling is.

`LiveServiceRuntime` owns one `_TransientCanonicalPumpScheduler`, which owns at most one worker
thread. That worker drains ready sessions round-robin. This prevents starvation but serializes
canonical decode work. Each session gets its own decoder wrapper, but all wrappers share the same
lazy runner/vLLM endpoint. Therefore:

- concurrent clients can upload, receive acknowledgements, poll, and queue independently;
- queued transcription spans are fair but not currently dispatched in parallel by this service;
- the observed 16-item queue bound is per session, so decode lag eventually produces 429
  backpressure independently for each client;
- vLLM cannot exploit request-level continuous batching if the application sends it only one decode
  request at a time.

Do **not** solve this by starting multiple Uvicorn workers. Device state, session ownership, runtime
objects, mixers, event queues, and view grants are process-local. Without sticky routing plus an
external authoritative registry, two workers can disagree about a token/session and create failures
or unsafe routing behavior.

The lowest-risk concurrency research path is one FastAPI process plus a measured, bounded inference
dispatcher (for example 2 concurrent spans) feeding one vLLM engine. Measure before increasing it.
Duplicating the full model is unlikely to fit the currently observed 16 GB GPU state and is not the
first lever to try.

## Authentication/onboarding constraints

- The current pairing-code issue endpoint is loopback-only by design. Zero install is feasible, but
  an operator must still deliver a five-minute, single-use pairing payload to each new browser.
- The native helper pins the server certificate. A normal webpage cannot reproduce custom TLS
  pinning. For this operator-only tailnet MVP, the accepted temporary policy is a one-time manual
  interstitial click-through on the **same API/UI origin**. A production/public rollout requires a
  trusted certificate; never depend on click-through for cross-origin API requests.
- Keep capture and view tokens in JavaScript closure memory for the first prototype. Putting bearer
  tokens in query parameters leaks into history/logs; the current server rejects query-only tokens.
- Persistent browser pairing requires an explicit security decision. IndexedDB/localStorage are
  exposed to same-origin script/XSS and are not equivalent to Keychain/DPAPI. A short-lived,
  `HttpOnly; Secure; SameSite=Strict` server session is preferable if the API is adapted for it.
- Serve capture UI and API from the same HTTPS origin. This avoids CORS complexity and gives one
  origin a clear microphone permission identity. For the current deployment that origin must
  include `:7861`; omitting it silently changes the target to unconfigured port 443.

## What still must be measured

### Gate 1 — attended Chrome capture on this Mac — **PASSED 2026-08-09**

Result recorded in the validation addendum: mic (Bluetooth, native 16 kHz mono) and
window+system-loopback audio both captured; permissions granted inline (JIT picker +
automatic `kTCCServiceAudioCapture` row) with no System Settings visit on this machine.
Raw track metadata, moving meters, lane RMS/tone analysis, and zero fetch errors are
sufficient for the capture verdict. The stub had accumulated synthetic and real samples,
so a clean-state rerun was recommended — and completed the same evening: tab-audio and
entire-screen surfaces both captured (see the attended-completion paragraph in the
validation addendum). All three product-relevant Chrome picker classes—tab, window, and
monitor—are now measured on this Mac. A display-first/system-only suspended-context
bootstrap is intentionally outside the two-lane mic-first MVP and remains unmeasured.

Use ordinary Chrome, not automation selection flags. The harness at
`prototypes/browser-capture-feasibility/` serves the page, a 997 Hz tone tab at `/tone`,
and a `/verdict` endpoint that scores the run. The server is not expected to be running.
Manual clean rerun:

```bash
python3 prototypes/browser-capture-feasibility/stub_frame_server.py
```

1. Open `http://127.0.0.1:8899/` in ordinary Chrome and click **Reset recorded data**.
2. Do **not** run the synthetic source during this clean phase.
3. Click **Start mic**, allow the intended microphone, and speak a unique marker for 10–20 s.
4. Open `http://127.0.0.1:8899/tone` in another tab/window and start the tone.
5. Click **Start display**. Select that tab/window and explicitly enable its audio option.
6. Confirm both meters move independently; run 30–60 s; stop both tracks.
7. Open `http://127.0.0.1:8899/verdict` and preserve the page log plus verdict JSON.

Expected minimum: mic and system each have nonzero RMS, system has a strong 997 Hz ratio,
no decode/fetch errors, exact 8000-sample frames, no clean-run sequence gaps, and 0.5 s
timestamp deltas. Also record returned track counts, labels/settings, surface type, and
`mute`/`unmute`/`ended` behavior.

Useful surface sub-gates:

**1a — tab share, no TCC change (measured passing 2026-08-09):** without touching System
Settings, click the page's capture button, select the 997 Hz *tab* with **share tab
audio** enabled. Tab capture does not use the Screen-Recording TCC service, so this
isolates the product's preferred path from OS permission entirely.

**1b — window/entire screen + system audio (both measured passing 2026-08-09):** this
Mac's macOS 26 flow prompted inline
and created Chrome's System Audio Recording grant. Do not assume that behavior everywhere.
If Chrome offers no audio or the capture fails after a prior denial, inspect **Privacy &
Security → Screen & System Audio Recording**; do not silently downgrade to an empty lane.

### Safari diagnostic — **PASSED; capability boundary measured**

Safari 26.5 on this Mac supports the local microphone and the shared 16 kHz framing path.
It also supports display **video**, but supplies no accompanying audio track:

```text
window: video=1 audio=0, displaySurface=window, 1876x960 @ 30 fps
screen: video=1 audio=0, displaySurface=monitor, 1920x1080 @ 30 fps
```

Therefore Safari can be a microphone-only MOSS client under the current architecture. It
cannot be the required zero-install meeting-output client for arbitrary Safari tabs,
windows, or macOS system output. The Chrome MVP remains the correct scope. Re-test only
after a material Safari/WebKit release claims display-audio support.

### Gate 2 — scheduled end-to-end 4070 canary

Only when no competing GPU job is active:

1. verify `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/api/live/descriptor`,
   establish the same-origin TLS exception accepted for this MVP,
   and generate a unique browser device/pairing;
2. play a known two-speaker fixture in the selected Chrome meeting/source tab;
3. send separate system/microphone v2 lanes for 30–60 seconds;
4. verify frame ACKs, exact samples, transcript text, generic speaker IDs, and browser rendering;
5. prove a second simultaneous browser receives only its marker/transcript;
6. cleanly stop both test sessions and revoke only the two test devices.

Record end-to-end p50/p95 commit-to-render latency, dropped/discontinuous frames, 429s, GPU memory,
GPU utilization, and queue depth. Do not call this complete from track presence alone.

### Gate 3 — bounded inference concurrency

Prototype concurrency values 1, 2, and 4 using real 0.5-second ingress and real speech spans. For
1, 2, 4, and 8 simultaneous meetings, measure real-time factor, p95 transcript lag, fairness,
per-session queue depth, GPU OOM/errors, and vLLM active/queued request counts. Pick the largest
concurrency that remains below the latency and memory gates; then regression-test cross-session
markers under overload and reconnect.

### Gate 4 — Windows Chrome

Run the same page and measurements on supported Windows Chrome. Do not infer Windows parity from
the Mac result. Test meeting-tab audio, entire-system audio, microphone sharing with the meeting app,
device hotplug, sleep/wake, and permission revocation.

Two 2026-08-09 notes: Windows Chrome has offered entire-screen *system* loopback audio for
years (it predates the macOS 142 change), and tab audio since Chrome 74 — so Windows is
expected to be the easier platform, which serves the stated goal of macOS+Windows client
coverage. And the inference host (`ga0-alienware-rtx4070ti`) is itself a Windows machine,
so Gate 4 can run attended on existing hardware without new provisioning.

## Standards/vendor sources

- [W3C Screen Capture](https://www.w3.org/TR/screen-capture/) — mandatory user choice, transient
  activation, mandatory video, optional audio, non-persisted permission.
- [W3C Media Capture and Streams](https://www.w3.org/TR/mediacapture-streams/) — microphone and media
  track model.
- [W3C Web Audio](https://www.w3.org/TR/webaudio-1.1/) — graph/resampling and worklet foundation.
- [WebKit display-capture implementation discussion](https://bugs.webkit.org/show_bug.cgi?id=186294)
  — WebKit treats microphone as a separate `getUserMedia` track and documents display output as
  video without system-output audio; this is the primary Safari/WebKit basis for the distinction.
- [WebKit: Safari 16.1 media features](https://webkit.org/blog/13399/webkit-features-in-safari-16-1/)
  — vendor description of `getDisplayMedia` producing a screen/window video stream.
- [Chromium macOS system-audio launch change](https://chromium.googlesource.com/chromium/src.git/+/67570055fc09f0ac5abe0931f35fa33e9a95bc8c%5E%21/)
  — enabled by default from milestone 142 with macOS 14.2 minimum.
- [Chromium capture-source test switches](https://chromium.googlesource.com/chromium/src.git/+/refs/heads/master/chrome/common/chrome_switches.cc)
  — automation flags used only to minimize the local failure; not a product mechanism.
- [Apple: allow apps to use screen and audio recording](https://support.apple.com/en-gb/guide/mac-help/mchl592e5686/mac)
  — macOS operator permission path.
- [MDN: getDisplayMedia options](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia)
  — confirms `systemAudio`/`windowAudio` are top-level options, not audio constraints (2026-08-09 correction).
- [Chrome Platform Status: windowAudio](https://chromestatus.com/feature/5072779506089984)
  — `windowAudio` shipped in Chrome 141.
- [Browser compatibility data: `getDisplayMedia`](https://chromium.googlesource.com/external/github.com/mdn/browser-compat-data/+/refs/heads/flat-diff/api/MediaDevices.json)
  — current compatibility dataset marks Safari system/window-audio options unsupported.
- [addpipe: capturing screen with system sounds on Chrome/macOS](https://blog.addpipe.com/getdisplaymedia-allows-capturing-the-screen-with-system-sounds-on-chrome-on-macos/)
  — secondary operational history: tab audio predates the macOS system-loopback launch.
