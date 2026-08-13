---
id: T-06
map: map-001-phase1-chrome-client
title: Browser capture page spec, including the two-lane preflight
type: prototype
status: closed
assignee: claude
blocked_by: [T-01, T-05]
---

## Question

C6 puts both lanes in Phase 1. Turn the measured Gate-1 lane design into an implementable
spec, and design the preflight screen that has no reference pixels.

**Most of the mechanism is already settled by measurement.** Read
`docs/research-chrome-capture-mvp-2026-08-03.md` §"Recommended lane design" and the harness
`prototypes/browser-capture-feasibility/NOTES.md` first, and treat these as given:

- One `AudioContext({sampleRate:16000})` shared by both lanes so timestamps share a monotonic
  clock; the graph handles 48 kHz → 16 kHz.
- `AudioWorklet`, not `MediaRecorder`; aggregate 128-sample quanta into exactly
  `frame_samples` mono samples; clamp to PCM16.
- **POST from the worklet's port-message handler, never a timer** — background tabs throttle
  timers to ~1/min; measured hidden-tab p95 506.5 ms vs foreground 508.1 ms.
- Anchor each lane's clock **once** at the first delivered sample and advance arithmetically
  by `frames_sent × frame_samples`; per-frame `currentFrame` stamping jitters ±128 samples.
- Read `/api/live/descriptor` for `frame_samples` / `sample_rate` / bounds. Never hardcode.
- Send **exactly the nine v2 keys**; unknown keys are rejected. Telemetry never rides in frames.
- Keep each lane attached to `ctx.destination` through a zero-gain node.
- `systemAudio` / `windowAudio` are **top-level** `getDisplayMedia` options, not audio
  constraints; nested in `audio: {}` they are silently ignored.
- Retain the display video track for the capture lifetime; never transmit or render it.

Resolve what is **not** yet settled:

1. **Preflight screen design.** The research doc fixes the *sequence* (start capture → allow
   mic → choose surface, tab preferred → explicitly enable share-audio → verify both meters
   non-zero before creating the server session). It does not fix the pixels. Design it in the
   reference's visual language — this is new UI, so state how fidelity is judged.
2. **Activation ordering.** Certified path is **mic-first**, with `ctx.state === "running"`
   verified before enabling "Start display". `getDisplayMedia()` must be invoked
   synchronously inside the click handler before the handler yields (awaiting worklet setup
   first cost Safari its transient activation). Display-first / system-only bootstrap is
   **unmeasured** — rule it out of Phase 1 or prototype it separately.
3. **Echo policy UI.** Operator decision: preflight asks headphones vs speakers. Headphones →
   mic captured raw; speakers → `echoCancellation` on the **mic lane only**, system lane raw
   either way. The chosen mode must be recorded with the session so diarization quality is
   interpretable per mode. Where does that record live, given Phase 1 has no session history?
4. **Error taxonomy → UI.** 400 = malformed frame (client bug); 409 = sequence conflict or
   terminal session (resync or recreate); 429 on the v2 lane path = **non-terminal**
   backpressure (retry). Chrome raises `NotAllowedError` for both gestureless calls *and*
   explicit user dismissal, so never infer cause from the exception name: stop on error and
   offer a **user-driven** retry, never an automatic one.
5. **Lane failure and restart.** Bump `device_epoch` when a track is replaced or restarted;
   mark `discontinuity` explicitly. What does the user see when one lane dies mid-meeting —
   and does the session continue on one lane? (A failed lane contributes exact zero while its
   sealed peer may still reach mono.)
6. **Clipping and silence.** The measured loopback lane hit full-scale ±32767, so the page
   must meter and warn on sustained clipping. Define the threshold and the warning.
7. **Surface with no audio track.** Fail preflight. Never silently call it a system lane.
8. **Session creation ordering.** `POST /api/live/sessions` returns the id the client must
   use — never assume creation order (the two-profile prototype raced and still routed
   correctly only because each used its own returned id). Where does this sit relative to
   preflight, and what happens if preflight fails after a session exists?
9. **TLS click-through.** The one-time same-origin interstitial is the accepted MVP posture.
   Plain `http://` can never host the capture page (`navigator.mediaDevices` absent outside a
   secure context) and a capture page on any *other* origin cannot fetch this API. What does
   the user see on first visit?

Deliver a spec, and extend the kept harness at `prototypes/browser-capture-feasibility/`
rather than starting a new one. Note its current gaps: it posts prototype extras to a local
stub and hardcodes 8000/16000 instead of reading the descriptor.

## Resolution (2026-08-13) — ruled by the supervisor on the operator's behalf

The operator delegated overnight decision authority. This ticket is resolved in
**`docs/phase1-afk-charter.md` §4** — capture page + preflight spec.

It lives there rather than here because it is **binding on the AFK fleet**: every ralph-afk agent
reads that charter as its contract, and a decision split between two documents would drift. The
charter is committed to `dev` before any worktree is created, so all six agents see the same text.

Do not re-litigate. If new evidence contradicts it, bring numbers and update the charter in the
same change.
