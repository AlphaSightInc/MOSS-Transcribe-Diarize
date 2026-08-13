# Context — Phase 1 ticket #2

Iteration 7. Shared-token authority reaches the service through a path-only deployment config and
the live portal can create a server-issued session while keeping the bearer in page memory only.
The reviewer-facing ADR states the single-trust-domain posture and the retired historical `403`
criterion; the historical auth mutation battery is not runnable unchanged on the pre-ticket
baseline.

## Where things stand

- Branch: `afk/t2-shared-token-auth`; iteration-1 baseline is `76a86b8`. Worktree 2 of 6
  (treehouse pool).
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.
- Target repo `frontend/` is empty. `/` currently serves the inline Subtitle Studio.
- Live routes are default-off and enabled via `create_app(live_enabled=True, ...)`.
- `LiveAccessRegistry(shared_token=...)` installs one process-only capture principal in the existing
  device table. `authorize`, ownership checks, session binding, and route authority stay unchanged;
  persistence omits only that configured principal.
- `ops/moss-live.env.example` declares only a shared-token file path for the host-local profile;
  `ops/start-web.sh` forwards only that path. The CLI reads exactly one non-empty line into memory
  and passes it to `create_app`. Omitting the path keeps the existing pairing mode.

## Acceptance checklist — issue #2 (verbatim meaning, no extra gates)

- [x] Server accepts a shared bearer token supplied by config; a fresh browser needs no pairing
  exchange.
- [x] Existing pairing flow continues unchanged when the shared token is not configured.
- [ ] Existing auth gate and mutation batteries pass unmodified.
- [x] Token stays in page memory only: never a query parameter and never `localStorage`.
- [x] Reviewer-facing documentation states that any token holder can read any session.
- [x] Session ownership and routing still resolve per server-issued session id, so sessions remain
  individually addressable.
- [x] Evidence explicitly records that historical `403` cross-read isolation is no longer an
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

## Iteration-2 auth seam audit

- Gap measured at iteration 2: an unpaired bearer was rejected as `LiveAccessUnauthorized: invalid bearer
  authority`; neither `LiveAccessRegistry`, `create_app`, the CLI, nor the deployment profile has a
  shared-token configuration input. Raw probe:
  `evidence/phase1/t2/iteration-02-auth-seam-probe.json`.
- Existing gate remains green unchanged: `tests/test_live_auth.py` plus the API credential-leak/query
  test pass **14 tests and 26 subtests**. Raw JUnit:
  `evidence/phase1/t2/iteration-02-existing-auth-gate.xml`.
- Smallest authority slice: configure one shared capture principal at registry construction, then
  reuse `_capture_for_digest`, `authorize`, `bind_session`, and every route check unchanged. Because
  every shared-token request resolves to that one principal, the existing owner check permits reads
  of every shared-mode session while server-issued session ids keep routing individually.
- The configured principal must be memory-only. Removing shared-token config on restart must remove
  its authority; `_persist()` must not turn the configured mode into a durable paired device.
- First RED nodes: configured token creates two sessions without `/pairings`; that token can read
  each by its own session id; wrong/missing tokens remain 401; restart without config rejects the
  shared token; the existing pairing-only test stays unmodified and green when config is absent.

## Iteration-3 registry + app slice

- Shared config now admits a fresh bearer without a pairing exchange. The same principal creates
  and addresses two distinct server-issued session ids; wrong and missing bearers remain 401.
- The configured principal is memory-only: after a normal pairing forces state persistence, restart
  without shared config rejects the shared bearer while the paired credential still works.
- The existing pairing/auth tests were not rewritten. The full focused live set passes **68 tests
  and 353 subtests**. Raw JUnit: `evidence/phase1/t2/iteration-03-shared-token-slice.xml`.
- Scope limit at iteration 3: this proved registry and direct `create_app` configuration only.
- Historical cross-read `403` isolation remains explicitly out of scope as an acceptance gate under
  T-01. Per-session addressing remains tested; charter G5 transcript-routing integrity remains.

## Iteration-4 secret-file deployment slice

- The tracked live profile contains a placeholder path, never a bearer. The adapter puts only that
  path in argv; the CLI reads the token into process memory and passes it to the existing app seam.
- A missing declaration produces no shared-token flag and returns `None`, preserving pairing mode.
  Empty or multiline files and a shared-token file outside `--live` are refused before startup.
- Deployment/CLI plus focused live validation passes **167 tests and 353 subtests**. Raw JUnit:
  `evidence/phase1/t2/iteration-04-secret-file-forwarding.xml`.
- Scope limit: this does not prove browser page-memory handling, the unchanged auth mutation
  battery, or G5 transcript-routing integrity. Historical cross-read `403` is still not a gate.

## Iteration-5 unchanged mutation-battery audit

- The exact A-025 reviewer harnesses were copied byte-for-byte and run only against isolated clones
  of this branch at `65e46b1`; source/copy SHA-256 pairs match. The working tree and both clones
  remained unmodified apart from generated evidence.
- The safer re-review runner's unmutated controls `U`, `A`, `C`, `B`, `S`, `L3`, and `D` pass. Its
  `R` control fails before any mutation because the July spike does not supply the required
  `live_helper_lease_seconds`; that requirement predates this ticket (`1f17def6`). The harness
  correctly aborts rather than counting false kills.
- The original unchanged 33-row harness kills M01 through M16 (**19 rows**, including the `b`
  variants), then aborts at M17 because its old view-expiry anchor has count zero. Session-lifecycle
  view authority replaced that anchor before this ticket (`4445a49`). No survivor result exists;
  **do not claim 33/33** from this partial run.
- Raw evidence: `evidence/phase1/t2/iteration-05-auth-mutation-battery/`. This is a historical
  harness-drift blocker, not evidence of a shared-token mutant surviving. Updating the harness
  would violate issue #2's explicit “unmodified” criterion and is therefore not this ticket's fix.

## Iteration-6 browser page-memory slice

- `/live` now accepts a bearer and creates a session through `POST /api/live/sessions`; no pairing
  route is involved. It polls the returned server-issued session id with the same bearer and keeps
  the existing manual session/view-token path intact.
- The bearer is cleared from the password input immediately, exists only in the closure's in-memory
  state for the active page, and is cleared on disconnect, terminal state, or `pagehide`. Requests
  send it only in `Authorization`; it never enters a URL, body, cookie, `localStorage`, or
  `sessionStorage`.
- Portal plus focused live validation passes **85 tests and 357 subtests**. Raw JUnit:
  `evidence/phase1/t2/iteration-06-browser-page-memory.xml`.
- Scope limit: the Node browser-contract probe proves page behavior and request construction; it
  does not claim attended display capture. Historical cross-read `403` remains explicitly not an
  acceptance gate; G5 transcript-routing integrity remains.

## Iteration-7 reviewer posture + cross-read evidence

- ADR-0001 now states that all configured-token holders resolve to one process-only principal and
  can read every live session. It distinguishes shared read authority from server-issued session
  addressing and required cross-session transcript integrity.
- The production-route test creates two distinct sessions with one configured bearer and reads
  both by their own server-issued ids; the registry test independently proves the same principal
  authorizes each session. Focused validation passes **2 tests and 4 subtests**. Raw JUnit:
  `evidence/phase1/t2/iteration-07-single-trust-domain.xml`.
- ADR-0001 records explicitly that the historical cross-read `403` result is not an acceptance
  criterion. This evidence does not test G5 transcript payload isolation under concurrency.

## Ranked candidates

1. Resolve the unchanged mutation-battery acceptance blocker through supervisor direction: the
   historical runner has two pre-ticket stale seams, and changing either is not “unmodified.”
