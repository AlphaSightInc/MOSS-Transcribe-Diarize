# Context — Phase 1 ticket #5

Iteration 2. Existing helper-health seam measured; browser vocabulary and next server slice chosen.

## Where things stand

- Branch: `afk/t5-*`, cut from `dev` at `a05a7f6`. Worktree 5 of 6 (treehouse pool).
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.
- Target repo `frontend/` is empty. `/` currently serves the inline Subtitle Studio.
- Live routes are default-off and enabled via `create_app(live_enabled=True, ...)`.
- GitHub issue #5 remains open and declares `Blocked by #1`. Server-side work can proceed;
  browser/client work must integrate after #1 lands.

## Acceptance checklist — issue #5 (authoritative)

- [ ] Extend `HelperLaneHealth.failure_code` additively with browser conditions; one vocabulary
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
- Full discovery baseline: **965 passed, 4 skipped, 3 failed, 11 errors, 383 subtests**.
  Red prerequisites are missing real-corpus `harness_cache.npz`, unbuilt `mtd-capture` and
  `MOSSCaptureApp` Swift products, plus one macOS Launch Services lifecycle failure. Resolve
  these before claiming G10; no ticket #5 code existed when measured.
- Focused live API/auth/mixer baseline: **65 passed, 351 subtests**. Covers existing live HTTP
  contract/auth/mixer behavior; does not cover browser capture, background throttling, or issue
  #5's new failure vocabulary/status rendering.
- Loop shell syntax: **PASS**. Covers parsing only.
- Raw result: `evidence/phase1/t5/iteration-1-validation.txt`.

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

Open integration seam: the charter creates a server session only after both preflight meters are
non-zero, while issue #5 requires a server-authored silent-microphone preflight line and the
existing heartbeat is session-scoped. Do not invent a pre-session browser judgment. Resolve this
with ticket #1's actual client/session flow before the client half.

## Ranked candidates

1. Implement the smallest server vertical slice: one server-owned capture-status projection over
   the existing helper presence, with the seven measured browser codes and stable native/fallback
   behavior, published as `capture_phase` plus one plain-language `status_line` in snapshots.
   Focused tests must prove failed/degraded facts, one-lane continuation, and additive unknown-code
   compatibility; keep raw `helper_presence` for `/live` diagnostics.
2. Restore the full-suite prerequisites (Swift products and real-corpus cache), investigate the
   macOS lifecycle baseline failure, then rerun the full command before the merge gate.
3. Recheck issue #1/dev and resolve the preflight/session-ordering seam before beginning the
   browser/client half.
