# Context — Phase 1 ticket #5

Iteration 8. Server-owned status and background-worklet lease mechanics are measured. The loop
has reached the charter's stop gate after three consecutive client-integration blockers: ticket
#1 has not landed, and the preflight-authority contradiction has no owning answer.

## Where things stand

- Branch: `afk/t5-capture-health`, cut from `dev` at `8fec841`. Worktree 5 of 6 (treehouse pool).
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.
- Target repo `frontend/` is empty. `/` currently serves the inline Subtitle Studio.
- Live routes are default-off and enabled via `create_app(live_enabled=True, ...)`.
- GitHub issue #5 remains open and declares `Blocked by #1`. Server-side work can proceed;
  browser/client work must integrate after #1 lands.

## Acceptance checklist — issue #5 (authoritative)

- [x] Extend `HelperLaneHealth.failure_code` additively with browser conditions; one vocabulary
  shared by native and browser helpers, no browser-side enum.
- [ ] Browser reports raw facts only; no client capture-health judgment or state machine.
- [ ] Snapshot publishes one server-authored `capture_phase` and one plain-language status line;
  client only renders the line.
- [ ] Heartbeats are driven by worklet messages, never `setInterval`; a measured background-tab
  run sustains cadence without tripping `live_helper_lease_seconds`.
- [ ] Mid-session lane death yields the correct status line while the surviving lane continues
  wherever the mixer permits.
- [ ] Product UI omits per-lane accounting, device epoch, replay-prune watermark, queue depth,
  and 429 counts; these remain in `/live` and logs.
- [ ] Silent microphone preflight status names how to change Chrome's default input device.

Source: live issue #5 read 2026-08-13. T-02's 2026-08-13 correction supersedes its earlier
client-owned health ruling and confirms server authority plus worklet-driven heartbeats.

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
  native-helper effort. **It is not yours. Ignore it.** Your loop lives in `scripts/afk-t5/`.
- Frame geometry is deploy-manifest data, never a code constant.
- 429 on the v2 lane path is non-terminal; on the legacy mono path it is terminal. Only ever send
  v2 lane frames.
- `setInterval` in a backgrounded tab collapses to ~1/min. Worklet port messages do not.
- `source_revision` comes from the provider manifest and must be re-finalized per host.

## Validation baseline

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_live_api.py tests/test_live_auth.py tests/test_live_mixer.py
bash -n scripts/afk-t5/ralph-afk.sh
```

- `.venv/bin/pytest` is not available in this fresh worktree (exit 127). Host `python3` is
  pyenv 3.12.10 with pytest importable, so the commands above are the working entrypoints.
- Full discovery after restoring ignored prerequisites: **986 passed, 4 skipped, 2 failed,
  475 subtests**. Raw result: `evidence/phase1/t5/iteration-4-full-validation.txt`.
  The two reds are not ticket #5 behavior: the L1 frozen-baseline guard detects this branch's
  product-tree additions relative to certified commit `9089b332...`, and the unchanged macOS
  Launch Services lifecycle lookup cannot resolve the launched app from this test-runner session.
  Do not weaken either gate; baseline re-certification and GUI-session execution need their owners.
- Focused live API/auth/mixer baseline: **65 passed, 351 subtests**. Covers existing live HTTP
  contract/auth/mixer behavior; does not cover browser capture, background throttling, or issue
  #5's new failure vocabulary/status rendering.
- Loop shell syntax: **PASS**. Covers parsing only.
- Raw result: `evidence/phase1/t5/iteration-1-validation.txt`.

## Iteration 4 validation-prerequisite verdict

- Built ignored local `MOSSCaptureApp` and `mtd-capture` Swift products. Restored the ignored
  `acquired_alphabet` legacy cache/reference pair at their repository-pinned SHA-256 values
  `fd13bacb...f3947be5` / `28dc9a5b...bdc0759`; its focused suite is now **8 passed,
  94 subtests**. Raw artifact: `evidence/phase1/t5/iteration-4-prerequisites.txt`.
- The lifecycle failure is reproducible, but the product reaches `applicationDidFinishLaunching`
  (the UDS server is started only there), answers a real status request, and macOS logs the same
  PID as `CHECKEDIN`, `Registered`, and `SignalReady`. `lsappinfo` and the Swift
  `NSRunningApplication` lookup from the test process nevertheless return no application. This
  isolates an execution-session lookup blocker rather than an app-start failure. Raw artifact:
  `evidence/phase1/t5/iteration-4-lifecycle-probe.txt`.
- The L1 failure is the rail's intended behavior: `load_a2_instrument()` rejects any
  `moss_transcribe_diarize/` diff from its frozen certified source commit. Ticket #5 necessarily
  adds product files, so making full discovery green requires separately authorized baseline
  re-certification, not a ticket-local workaround.
- Findings were recorded on issue #5 as comment `#issuecomment-5276809001` by authenticated actor
  `yugao-aisight`. No remote service or unrelated product code was changed.

## Iteration 2 seam verdict

- `HelperLaneHealth.failure_code` is one additive, cross-helper string field. The production
  parser enforces non-empty shape but intentionally does not use a closed allowlist.
- A production-path probe passed a native reference code, seven proposed browser codes, and an
  unregistered sentinel through `HelperHeartbeat` → `HelperPresenceRegistry` →
  `LiveHelperFailureCoordinator`. Every value survived unchanged.
- A `failed` browser fact calls `LiveV2Session.fail_lane` only for the named lane and keeps the
  lease/peer live. A `degraded` fact remains observational and does not fail a lane.
- Use these observation-shaped browser values on the shared field:
  `browser_microphone_permission_denied`, `browser_capture_request_rejected`,
  `browser_surface_audio_missing`, `browser_track_ended`,
  `browser_audio_context_suspended`, `browser_sustained_clipping`, and
  `browser_microphone_silent`. Do not call an ambiguous Chrome rejection
  `picker_cancelled`.
- Do not add a parallel browser enum/schema/coordinator or tighten the parser into an allowlist.
  Server authority belongs in the named status projection that interprets these additive facts.
- Raw probe: `evidence/phase1/t5/iteration-2-helper-vocabulary-probe.txt`; durable verdict:
  `prototypes/browser-capture-feasibility/NOTES.md`.

## Iteration 3 server projection

- `live_capture_status.py` owns the seven browser strings and projects existing helper presence
  into reference-compatible `starting` / `recording` / `failed` phases plus one status line.
- Snapshot responses now publish top-level `capture_phase` and `status_line`. Raw
  `helper_presence` remains unchanged for `/live` diagnostics and logs.
- Failed facts deterministically outrank degraded facts. One failed lane with a live peer remains
  `recording`; its line says the peer continues. Known browser facts get actionable copy, while
  unregistered future/native codes get a generic line and remain accepted by the open parser.
- Silent-microphone copy names Chrome's `Settings > Privacy and security > Site settings >
  Microphone` remedy. This proves the server wording, not the still-blocked preflight delivery.
- Prototype + focused result: **83 passed, 351 subtests**. Raw artifact:
  `evidence/phase1/t5/iteration-3-capture-status-projection.txt`; durable verdicts:
  `prototypes/streaming-diarization/NOTES.md` and
  `prototypes/browser-capture-feasibility/NOTES.md`.

Open integration seam: the charter creates a server session only after both preflight meters are
non-zero, while issue #5 requires a server-authored silent-microphone preflight line and the
existing heartbeat is session-scoped. Ticket #1 commit `0bdff41` now implements that exact
ordering, so a silent microphone prevents creation of the only current server resource able to
author and deliver the line. Do not invent a browser judgment or create a session early. The
supervisor has been asked for an owning contract decision.

## Iteration 5 G7 mechanism verdict

- Ticket #1 remains open and `dev` remains at `8fec841`; no client/session flow is available to
  integrate.
- A headed isolated Chrome 151 tab stayed hidden for **65.01 s** while two descriptor-driven
  worklets delivered 130 ticks per lane. The microphone worklet drove serialized browser
  heartbeats; the page/worklet contained no `setInterval` or `setTimeout`.
- The locally run production heartbeat route accepted all **136/136** requests. During the hidden
  interval, server arrival p50/p95/max was **497.69/506.82/507.35 ms**. A deliberately strict
  **2 s** lease remained live; runtime status stayed `active`, the v2 session remained present,
  and no terminal failure occurred.
- This proves the worklet-to-production-lease mechanism, not issue acceptance: the local service
  used the repository test runtime provider and synthetic 48 kHz sources. Keep the G7 checkbox
  open until ticket #1's product client repeats the run against a local production-provider
  service. Raw artifact: `evidence/phase1/t5/iteration-5-g7-worklet-lease.txt`; durable verdict:
  `prototypes/browser-capture-feasibility/NOTES.md`.

## Iteration 6 dependency-gate verdict

- At `2026-08-13T06:46:10Z`, live issue #1 remained open, `private/dev` and local `dev` both
  remained at `8fec841`, and no `afk/t1-*` branch was published to `private`.
- The local `afk/t1-gate2-canary` worktree had four committed iterations through descriptor-driven
  geometry and exact v2 frame keys. Its own context labels both proofs stub-only.
- Ticket #1's next production-route slice was present only as uncommitted work in its worktree.
  Reading that state established liveness; this ticket did not edit, validate, or depend on it.
- Therefore there is still no landed client/session flow to merge or test. Integrating the local
  branch now would couple ticket #5 to incomplete, unpublished work and violate the serialized
  `dev` integration contract.
- Raw gate evidence: `evidence/phase1/t5/iteration-6-dependency-gate.txt`.

## Iteration 7 preflight-authority blocker

- At `2026-08-13T06:48:38Z`, issue #1 remained open, local and `private/dev` remained at
  `8fec841`, and no `afk/t1-*` branch was published to `private`.
- Ticket #1 advanced cleanly to commit `0bdff41`. Its production-route client meters both lanes
  locally, creates a session only after both report signal, and admits no preflight audio.
- Ticket #5's server-authored line is derived from session-keyed helper presence and returned in
  that session's snapshot. It cannot author or deliver the silent-microphone preflight line when
  the required session does not yet exist.
- A client-authored line would violate C11 and issue #5; earlier session creation would violate
  charter section 4. No product change is authorized until the owner chooses a pre-session
  server path or revises the ordering contract.
- Supervisor decision requested on issue #5 at comment `#issuecomment-5277007717`. Raw evidence:
  `evidence/phase1/t5/iteration-7-preflight-authority-blocker.txt`.

## Iteration 8 terminal blocked verdict

- At `2026-08-13T06:51:47Z`, issue #5 had no owner/supervisor reply after the blocker request;
  issue #1 remained open, local and `private/dev` remained at `8fec841`, and no private
  `afk/t1-*` branch existed.
- This is the third consecutive iteration blocked on ticket #1's unlanded client/session flow.
  Per charter section 8, the loop stops instead of polling or coding around the dependency.
- Every remaining ticket-local acceptance item needs ticket #1's product client. The silent-mic
  item additionally needs an owning pre-session authority decision. Final validation also needs
  separately owned L1 re-certification and a GUI-visible lifecycle runner.
- Those inputs cannot be produced within this loop's authority. The existing issue comment is
  the supervisor request; no redundant comment was posted. Raw evidence:
  `evidence/phase1/t5/iteration-8-terminal-blocker.txt`.

## Blocked continuation gates

1. Owner chooses a pre-session server-authored status path or explicitly revises the preflight
   session-ordering contract.
2. Ticket #1 lands its product client/session flow on `dev`.
3. Then implement raw-fact worklet heartbeats and line-only rendering, and repeat G7 through the
   product client plus a local production-provider service.
4. Before final merge, obtain L1 baseline re-certification and a GUI-visible lifecycle test run.
