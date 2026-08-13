# Context — Phase 1 ticket #1

Iteration 2. Validation baseline established; no product behavior measured yet.

## Where things stand

- Branch: `afk/t1-*`, cut from `dev` at `a05a7f6`. Worktree 1 of 6 (treehouse pool).
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.
- Target repo `frontend/` is empty. `/` currently serves the inline Subtitle Studio.
- Live routes are default-off and enabled via `create_app(live_enabled=True, ...)`.
- This worktree has no `.venv`; pyenv Python 3.12.10 + pytest 9.0.2 is the working runner.
- Focused live API/auth/mixer baseline is green: 65 passed + 351 subtests.
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

Source: live issue body read 2026-08-13. All criteria remain open.

- [ ] Read `/api/live/descriptor` at start; honor `frame_samples`, `sample_rate`, and bounds;
  no hardcoded frame geometry.
- [ ] Post both `microphone` and `system` lanes to the deployed service, origin including the
  explicit port `:7861`.
- [ ] Send exactly the nine v2 frame keys; server rejects unknown keys; telemetry never rides in
  a frame.
- [ ] Drive frame POSTs from worklet port messages, never timers; a backgrounded-tab run matches
  foreground cadence.
- [ ] A known two-speaker fixture played in the selected tab produces transcript text with
  distinct generic speaker ids.
- [ ] Poll `/snapshot` and `/events` per T-02; render committed spans plus provisional tail; only
  advance cursors after render.
- [ ] A second simultaneous browser runs its own session and sees only its own transcript text.
- [ ] Both sessions stop cleanly; revoke only test credentials.
- [ ] Record p50/p95 commit-to-render latency, dropped/discontinuous frames, 429 counts, GPU
  memory/utilization, and queue depth.
- [ ] Judge the verdict from raw artifacts, never track presence or a claimed pass.

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

1. Smallest vertical slice toward criterion 1: descriptor read with no hardcoded geometry.
2. Preserve the unrelated full-suite lifecycle failure as a visible baseline blocker; do not
   fix it under ticket #1.
