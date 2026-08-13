# Context — Phase 1 ticket #2

Iteration 1. Issue contract captured; local validation baseline measured.

## Where things stand

- Branch: `afk/t2-shared-token-auth`, currently at `e3cd276`. Worktree 2 of 6
  (treehouse pool).
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.
- Target repo `frontend/` is empty. `/` currently serves the inline Subtitle Studio.
- Live routes are default-off and enabled via `create_app(live_enabled=True, ...)`.

## Acceptance checklist — issue #2 (verbatim meaning, no extra gates)

- [ ] Server accepts a shared bearer token supplied by config; a fresh browser needs no pairing
  exchange.
- [ ] Existing pairing flow continues unchanged when the shared token is not configured.
- [ ] Existing auth gate and mutation batteries pass unmodified.
- [ ] Token stays in page memory only: never a query parameter and never `localStorage`.
- [ ] Reviewer-facing documentation states that any token holder can read any session.
- [ ] Session ownership and routing still resolve per server-issued session id, so sessions remain
  individually addressable.
- [ ] Evidence explicitly records that historical `403` cross-read isolation is no longer an
  acceptance criterion under this single-trust-domain posture.

Charter G5 still applies: transcript text must never cross sessions. T-01 removes cross-read
authorization isolation, not per-session addressing or transcript routing integrity. Do not add a
client-asserted `device_id`.

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
  native-helper effort. **It is not yours. Ignore it.** Your loop lives in `scripts/afk-t2/`.
- Frame geometry is deploy-manifest data, never a code constant.
- 429 on the v2 lane path is non-terminal; on the legacy mono path it is terminal. Only ever send
  v2 lane frames.
- `setInterval` in a backgrounded tab collapses to ~1/min. Worklet port messages do not.
- `source_revision` comes from the provider manifest and must be re-finalized per host.

## Validation commands

This worktree has no `.venv`; pyenv Python 3.12.10 has the installed test dependencies. Build the
two local Swift products before the repo suite because integration and packaging tests consume the
existing build products:

```bash
swift build --package-path macos/MOSSCapture --product mtd-capture
swift build --package-path macos/MOSSCapture --product MOSSCaptureApp
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_live_api.py tests/test_live_auth.py tests/test_live_mixer.py
bash -n scripts/afk-t2/ralph-afk.sh
```

Iteration-1 baseline:

- Focused live set: **65 passed, 351 subtests passed**; syntax check passed.
- `tests/` after both Swift builds: **862 passed, 4 skipped, 373 subtests passed, 1 failed**.
  The sole failure is the out-of-ticket macOS Launch Services lifecycle tracer: its UDS status
  request succeeds, then `NSRunningApplication(processIdentifier:)` cannot resolve that PID. An
  isolated rerun fails identically. Record and preserve; do not fix under ticket #2.
- Unscoped repo-root discovery also collects prototype tests: **965 passed, 4 skipped, 3 failed,
  11 errors, 383 subtests passed**. Eleven errors were eliminated by the Swift builds; two
  remaining prototype failures need the absent real-corpus `harness_cache.npz`; the remaining
  failure is the same lifecycle tracer. Use `tests/` as the product regression suite and run any
  ticket-specific prototype/mutation gates explicitly.
- Raw JUnit: `evidence/phase1/t2/iteration-01-*.xml`.

## Ranked candidates

1. Audit the existing `LiveAccessRegistry` configuration seam and auth tests; identify the
   smallest test-first vertical slice for configured shared-token session creation.
2. Implement that vertical slice without changing pairing-mode behavior or authority logic.
3. Identify and run the existing auth mutation battery unchanged.
