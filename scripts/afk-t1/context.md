# Context — Phase 1 ticket #1

Iteration 7. Chrome now creates a locally-owned production session, sends both lanes through the
real v2 ingress route, polls/renders production reads, and renews the production helper lease from
the worklet frame path while hidden. The provider remains deterministic/fake; no real model
behavior yet.

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
- [ ] A known two-speaker fixture played in the selected tab produces transcript text with
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

1. Drive the microphone lane from Chrome's fake-audio device with a known two-speaker WAV against
   a locally-owned real provider/model; never send inference traffic to the read-only remote host.
2. Preserve the unrelated full-suite lifecycle failure as a visible baseline blocker; do not
   fix it under ticket #1.
