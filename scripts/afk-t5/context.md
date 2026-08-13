# Context — Phase 1 ticket #5

Iteration 1. Issue contract inventoried; pre-change validation baseline measured.

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

## Ranked candidates

1. Inventory current `HelperLaneHealth.failure_code`, snapshot, and failure-coordinator seams;
   choose the smallest server-side vertical slice for acceptance criterion 1.
2. Restore the full-suite prerequisites (Swift products and real-corpus cache), investigate the
   macOS lifecycle baseline failure, then rerun the full command before the merge gate.
3. Recheck issue #1/dev before beginning the browser/client half.
