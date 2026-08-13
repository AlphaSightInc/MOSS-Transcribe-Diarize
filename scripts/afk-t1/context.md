# Context — Phase 1 ticket #1

Iteration 11. Chrome now creates a locally-owned production session, sends both lanes through the
real v2 ingress route, polls/renders production reads, renews the production helper lease from the
worklet frame path while hidden, and can autonomously pair fake-device `getUserMedia()` microphone
audio with an explicitly synthetic system lane. The kept server can select a manifest-admitted
real provider/model, and the page now stops lease-safely before detaching. One real-model session
closed with exact accounting; simultaneous two-session stop/isolation remains open.

## Where things stand

- Branch: `afk/t1-*`, cut from `dev` at `a05a7f6`. Worktree 1 of 6 (treehouse pool).
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.
- Target repo `frontend/` is empty. `/` currently serves the inline Subtitle Studio.
- Live routes are default-off and enabled via `create_app(live_enabled=True, ...)`.
- This worktree has no `.venv`; pyenv Python 3.12.10 + pytest 9.0.2 is the working runner.
- Focused live API/auth/mixer baseline is green: 65 passed + 351 subtests.
- The kept browser harness fetches `/api/live/descriptor` before creating its `AudioContext`,
  rejects invalid/non-positive geometry and `frame_samples > bounds.max_frame_samples`, and uses
  the response for context rate, worklet size, capture timestamps, and frame `sample_rate`.
- Chrome stub proof with deliberately nonhistorical 3,200-sample frames produced 19 frames/lane,
  exact 200 ms capture-clock deltas, zero gaps, and matching descriptor geometry. This is contract
  wiring evidence only; it does not satisfy the real-service acceptance gate.
- The harness now sends exactly the nine v2 frame keys. Its strict stub observed one exact key set
  across 75 frames/lane, rejected injected `client_visibility` with HTTP 400, and received cadence
  telemetry separately for all 150 frames. This remains stub-only contract evidence.
- Capture credentials stay in closure memory: an operator can paste one into the password field,
  while the loopback-only production-route probe supplies an ephemeral no-store credential without
  printing or persisting it. The page creates a server-issued session only after both lane meters
  are non-zero, then uses `/api/live/sessions/{id}/frames`; the historical `/frames` path is gone.
- Chrome 151 + locally-run `create_app` accepted 329 consecutive descriptor-sized frames per lane
  (sequences 0–328, all HTTP 200, zero failed samples, no terminal failure). This proves the real
  auth/session/v2/mixer/runtime route stack with a deterministic fake provider, not model inference.
- The returned view bearer now drives 250 ms production `/snapshot` + `/events` polls. An injected
  pre-render failure retained both cursors at 0/0; retry repeated 0/0, rendered six deterministic
  commits plus a clearly labelled synthetic provisional fixture and 31 event rows, then advanced
  to 13/31. The provisional fixture proves renderer wiring only, not provisional inference.
- Worklet frame messages now serialize/coalesce strict production helper heartbeats across both
  lanes; no timer or visibility callback drives them. With Chrome hidden for 12.000 s against a
  2.0 s local lease, all 417 heartbeats returned 200 with zero sequence gaps. Hidden heartbeat
  p50/p95/max 64/64/65 ms matched visible 64/65/70 ms; both frame lanes had 65 ms hidden and
  visible p95, and the session remained active.
- Chrome's fake-device microphone path now composes with a synthetic system lane without invoking
  display capture. A known 60 s fixture with three reference speakers entered through
  `getUserMedia()`; 1,254 frames/lane crossed the production route with zero gaps or failed samples.
  Its microphone frame-RMS envelope matched the source over 959 frames at 0.99957 correlation
  (MAE 0.00085), proving real fixture samples rather than mere track presence. The provider was
  still `api-fake`, so this does not satisfy the model/transcript gate.
- The immutable MOSS snapshot at revision `e8681d68...` is now fully cached locally (1.833 GB;
  weight SHA-256 `9a0ceb4a...07026c4`). Production `ModelRunner` on CPU/float32 transcribed the
  known 60 s fixture in 29.066 s and emitted 538 tokens with four speaker ids. This direct smoke
  proves local model admission only; it does not exercise the live runtime, routes, or browser.
- The kept production-route server now accepts paired `--model` and `--live-provider-manifest`
  inputs while preserving its deterministic default. A locally finalized copy of the deployed,
  measured WebRTC/WeSpeaker bundle passed production preflight on Mac ARM64; its pinned asset and
  config hashes stayed fixed, while the bit-exact host golden output was regenerated locally.
- Chrome fake-device microphone plus synthetic system then sent 236 exact 8,000-sample frames per
  lane (sequences 0–235, zero gaps, all HTTP 200) through the real model runtime. The runtime
  accepted 1,888,000 samples; before teardown it committed 46 spans, and the browser rendered
  model ids S01–S04 plus four canonical speaker identities. This satisfies automated G1's real
  model/render requirement and still does not prove display capture.
- The stop path now requests production drain while capture and the worklet heartbeat remain live,
  validates HTTP 200 plus exact runtime/v2 accounting, then detaches. A real-model stop began with
  pending work and took 2.720 s, longer than the 2 s helper lease; six in-drain heartbeats returned
  200. Runtime and both v2 lanes closed at 1,912,000 accepted/accounted samples with zero pending
  work. This proves one clean session only, not the two-session acceptance item.
- Full Python collection is red on one unchanged-`dev` macOS Launch Services lifecycle node:
  978 passed, 4 skipped, 475 subtests, 1 failed. The app binds/responds over UDS, then
  `NSRunningApplication(processIdentifier:)` returns nil. Do not waive or fix it under ticket #1.

## Read these first (do not re-derive)

| Path | Why |
|---|---|
| `docs/phase1-afk-charter.md` | **Binding.** Authority, limits, capture spec §4, fidelity method §5, gates §6, attended checklist §7 |
| `.wayfinder/map-001-phase1-chrome-client.md` | Premises C1–C11 and the decision index |
| `.wayfinder/tickets/` | The 12 closed decision tickets with full rationale |
| `docs/research-chrome-capture-mvp-2026-08-03.md` | Gate 1 measured verdict. Frame geometry, worklet clock anchoring, activation ordering, error taxonomy — all settled |
| `AGENTS.md` | Measure-before-implement is mandatory |
| `CONTEXT.md` | Domain glossary. Use its vocabulary |

## Known traps, already paid for once

- `scripts/ralph-afk/` holds a **stale 285 KB `context.md` and an old PRD** from the earlier
  native-helper effort. **It is not yours. Ignore it.** Your loop lives in `scripts/afk-t1/`.
- Frame geometry is deploy-manifest data, never a code constant.
- 429 on the v2 lane path is non-terminal; on the legacy mono path it is terminal. Only ever send
  v2 lane frames.
- `setInterval` in a backgrounded tab collapses to ~1/min. Worklet port messages do not.
- `source_revision` comes from the provider manifest and must be re-finalized per host.

## Issue #1 acceptance checklist

Source: live issue body read 2026-08-13. Criterion 1 now has local production-route evidence;
the tracker issue remains open for supervisor closure.

- [x] Read `/api/live/descriptor` at start; honor `frame_samples`, `sample_rate`, and bounds;
  no hardcoded frame geometry.
- [ ] Post both `microphone` and `system` lanes to the deployed service, origin including the
  explicit port `:7861`.
- [ ] Send exactly the nine v2 frame keys; server rejects unknown keys; telemetry never rides in
  a frame.
- [x] Drive frame POSTs from worklet port messages, never timers; a backgrounded-tab run matches
  foreground cadence. Helper heartbeats share that path and do not trip the lease.
- [x] A known two-speaker fixture played in the selected tab produces transcript text with
  distinct generic speaker ids.
- [x] Poll `/snapshot` and `/events` per T-02; render committed spans plus provisional tail; only
  advance cursors after render.
- [ ] A second simultaneous browser runs its own session and sees only its own transcript text.
- [ ] Both sessions stop cleanly; revoke only test credentials.
- [ ] Record p50/p95 commit-to-render latency, dropped/discontinuous frames, 429 counts, GPU
  memory/utilization, and queue depth.
- [ ] Judge the verdict from raw artifacts, never track presence or a claimed pass.

Criterion 1 is satisfied on the locally-owned production route: Chrome used the returned
1,000/16,000 geometry, the production server accepted 329 exact frames/lane, and its v2 snapshots
reported 329,000 accepted samples/lane. Raw evidence:
`evidence/phase1/t1/iteration-05-production-routes.json`. This says nothing about model behavior.

Criterion 3 implementation status: the locally-run production route accepted the exact nine-key
bodies, but the explicit unknown-key rejection probe remains stub-only. Keep the item open until
that rejection is captured on the production route. Raw stub rejection evidence:
`evidence/phase1/t1/iteration-04-nine-v2-keys.json`.

Production-route transport evidence: `evidence/phase1/t1/iteration-05-production-routes.json`.
It proves session creation and accepted strict-v2 lane frames only; it explicitly excludes real
inference, transcript polling/rendering, clean stop, concurrency, background lease, and display.

Production-route read evidence: `evidence/phase1/t1/iteration-06-production-read-path.json`.
It proves authenticated snapshot/event polling, committed/runtime text rendering, explicit-fixture
provisional rendering, and cursor retention across a failed render. It excludes real model and
real provisional inference.

Background/lease evidence: `evidence/phase1/t1/iteration-07-background-heartbeat.json`. It proves
synthetic worklet-driven frames and strict helper heartbeats stayed live for 6.0 local lease
periods in a hidden Chrome tab. It excludes real microphone, display capture, and model inference.

Fake-microphone ingress evidence:
`evidence/phase1/t1/iteration-08-fake-mic-production-routes.json`. It preserves raw per-frame RMS
and cadence telemetry, production v2 state, fixture/reference hashes, and the source-envelope
correlation. It proves Chrome fake-device audio reached `getUserMedia()` and the production ingress
route while system stayed synthetic. It excludes model inference and real display capture.

Real-model browser evidence: `evidence/phase1/t1/iteration-10-real-model-browser.json`. It proves
the fake-device microphone and synthetic system lanes reached the manifest-admitted local provider
and production `ModelRunner`, and Chrome rendered 46 commits with S01–S04. It explicitly records
that real display capture is unproved and teardown failed after the worklet heartbeat was detached.

Lease-safe stop evidence: `evidence/phase1/t1/iteration-11-lease-safe-stop.json`. It proves one
real-model browser session kept six HTTP-200 worklet heartbeats alive through a 2.720 s production
drain, received exact closed runtime/v2 accounting, and detached only after the response. It does
not satisfy the two-simultaneous-session criterion.

### Binding proof interpretation

- PRD + charter supersede the issue body's older remote/display procedure without deleting any
  acceptance criterion: run a locally-owned real service; the remote host stays read-only.
- Automated real-audio proof is the `microphone` lane, using Chrome's fake media device with a
  known two-speaker WAV. Exercise `system` synthetically through the same production routes and
  label it explicitly as not proving display capture. Real two-lane display proof remains the
  attended checklist only.
- Criterion 7 means transcript text never crosses between the two session render paths. Under the
  accepted single-trust-domain posture, cross-session reads need not return `403`.
- G7 additionally requires background cadence not to trip `live_helper_lease_seconds`; heartbeat
  work must share the worklet-driven path.

## Validation commands

Working command set for this worktree:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_live_api.py tests/test_live_auth.py tests/test_live_mixer.py
# PASS: 65 passed, 351 subtests; contract/auth/mixer only, no browser or real model.

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
# BASELINE RED: 978 passed, 4 skipped, 475 subtests, 1 failed at
# tests/test_macos_uds_tracer.py::test_built_macos_app_finishes_launch_and_honors_application_terminate

bash -n scripts/afk-t1/ralph-afk.sh
# PASS; shell syntax only.
```

Full-suite local prerequisites are ignored artifacts, not product changes:

- Build both Swift products: `swift build --package-path macos/MOSSCapture --product
  MOSSCaptureApp` and the same command with `--product mtd-capture`.
- Restore the archived `acquired_alphabet` cache/reference pair. Required SHA-256 values are
  `fd13bacb...f3947be5` and `28dc9a5b...bdc0759`; the exact full pins live in
  `run_legacy_anchor_fidelity.py` and `tests/fixtures/live_identity_real_corpus/`.

## Ranked candidates

1. Run two simultaneous browsers, prove their rendered text never crosses, and
   capture per-session stop/revocation evidence plus remaining latency/queue/429 metrics.
2. Capture explicit unknown-key rejection on the locally-owned production route; current rejection
   evidence remains stub-only.
3. Preserve the unrelated full-suite lifecycle failure as a visible baseline blocker; do not
   fix it under ticket #1.
