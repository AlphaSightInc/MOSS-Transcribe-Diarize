# Context — Phase 1 ticket #6

Iteration 7. Acceptance criteria and a reproducible local validation baseline are captured. The
provider exposes immutable, encoder-pinned observations from the completed album. The measured
single-process writer runs after exact clean-stop accounting and never on abort. Live deployment
wiring now makes the journal default-on at an operator-configurable path outside the checkout;
raw-audio retention remains default-off. The consent/right-to-remove documentation remains open.

## Where things stand

- Branch: `afk/t6-*`, cut from `dev` at `a05a7f6`. Worktree 6 of 6 (treehouse pool).
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.
- Target repo `frontend/` is empty. `/` currently serves the inline Subtitle Studio.
- Live routes are default-off and enabled via `create_app(live_enabled=True, ...)`.
- Issue #6 is OPEN and remains blocked by OPEN issue #1 (rechecked 2026-08-13).
- This worktree has no `.venv`; use the host's pyenv Python 3.12.10 / pytest 9.0.2.
- The full suite requires both Swift products to be built first. After those builds, the current
  baseline is 862 passed / 4 skipped / 373 subtests plus one persistent out-of-ticket failure:
  `tests/test_macos_uds_tracer.py::test_built_macos_app_finishes_launch_and_honors_application_terminate`
  exits 2 because `NSRunningApplication(processIdentifier:)` cannot resolve the just-launched PID.
  Do not fix it under ticket #6; keep it visible in every full-gate result.

## Acceptance checklist — issue #6 (binding)

- [ ] At session end, append one record per speaker containing `session_id`, `speaker_label`,
  `centroid`, `sample_seconds`, `embedder_id`, `embedder_state_sha`, `created_at`, and
  `echo_mode`.
- [ ] Every row contains both `embedder_id` and `embedder_state_sha`.
- [ ] Records are keyed by session, never by device; Phase 1 has no `device_id`.
- [x] Vector journaling defaults ON while raw-audio retention remains OFF.
- [x] The journal path is operator-configurable and outside the checkout.
- [ ] A refused or unusable observation is declined by name and never aborts the session.
- [ ] Documentation states that the journal is not a consent decision and that rollout beyond
  the guarded LAN requires an explicit consent and right-to-remove ruling first.

Source: <https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/6>, read live on
2026-08-13. T-12 confirms this is only an append-only, session-keyed journal of live-album
centroids; CRUD, enrollment, naming, matching, UI, and D-7 are out of scope.

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
  native-helper effort. **It is not yours. Ignore it.** Your loop lives in `scripts/afk-t6/`.
- Frame geometry is deploy-manifest data, never a code constant.
- 429 on the v2 lane path is non-terminal; on the legacy mono path it is terminal. Only ever send
  v2 lane frames.
- `setInterval` in a backgrounded tab collapses to ~1/min. Worklet port messages do not.
- `source_revision` comes from the provider manifest and must be re-finalized per host.

## Validation commands

Build the local Swift prerequisites once per clean worktree:

```bash
swift build --package-path macos/MOSSCapture --product mtd-capture
swift build --package-path macos/MOSSCapture --product MOSSCaptureApp
```

Then run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/test_live_api.py tests/test_live_auth.py tests/test_live_mixer.py \
  -q -p no:cacheprovider
bash -n scripts/afk-t6/ralph-afk.sh
```

- Full gate, after Swift builds: 862 passed / 4 skipped / 373 subtests and the one named
  pre-existing/out-of-ticket failure above. Raw JUnit:
  `evidence/phase1/t6/iteration-2-full-suite-after-build.xml`.
- Ticket-relevant live subset: 65 passed / 351 subtests. It covers HTTP live routes and lifecycle,
  shared-token authorization, v2 lane semantics, and compatibility mixing. That iteration-2
  baseline predates the journal contract and no application implementation exists yet. Raw JUnit:
  `evidence/phase1/t6/iteration-2-live-subset.xml`.
- Provider observation projection: GREEN. `journal_observations()` deterministically emits one
  frozen record per album speaker with the duration-weighted centroid, summed support seconds,
  provider/revision embedder id, and state SHA. The focused contract passes 1/1 and the full
  provider-bundle suite passes 45/45. Raw JUnit:
  `evidence/phase1/t6/iteration-4-journal-projection.xml` and
  `evidence/phase1/t6/iteration-4-provider-bundle.xml`.
- Journal append prototype: PASS. Under 32 concurrent session-end calls, a process lock around a
  pre-encoded batch plus `O_APPEND`, write-all, and `fsync` produced 512/512 parseable rows in
  contiguous session batches; all 32 non-finite observations were named-refused and every file
  row was mode `0600`, session-keyed, and encoder-pinned. Raw measurement:
  `evidence/phase1/t6/iteration-5-journal-prototype.json`. This does not yet prove production
  lifecycle integration, operator path configuration, multi-process writes, or power loss.
- Production lifecycle: GREEN. The concrete JSONL writer pre-encodes a session batch, appends it
  under a process lock with write-all and `fsync`, and creates a mode-`0600` file. Runtime clean
  stop adds session id, stop time, and the session's settled echo choice after identity finalization
  and exact accepted/accounted equality. A non-finite speaker is omitted, named in the runtime
  event and host warning, and does not abort the clean stop; abort writes nothing. The combined
  runtime/provider/live subset passes 141 tests / 351 subtests. Raw JUnit:
  `evidence/phase1/t6/iteration-6-journal-and-live-subset.xml`. This does not prove default-on
  deployment wiring, an operator-configurable path outside the checkout, multi-process writes, or
  power-loss survival.
- Deployment wiring: GREEN. Direct `--live` construction installs a journal under the service
  user's local data directory by default. The tracked live profile requires an explicit
  `MOSS_LIVE_VECTOR_JOURNAL_PATH`, passes it through the adapter and CLI into the real provider
  runtime factory, and rejects relative or checkout-contained paths. The same tracked profile
  still declares no `MOSS_LIVE_RETENTION_*` keys. Deployment/provider/runtime/live regression:
  191 passed / 351 subtests. Raw JUnit:
  `evidence/phase1/t6/iteration-7-default-on-journal-wiring.xml`. This does not prove a filled-in
  host profile, multi-process writes, or power-loss survival.
- Loop script syntax: PASS.

## Ranked candidates

1. Add the required consent/right-to-remove documentation and prove the configured production
   factory uses the real completed provider observations rather than stub evidence.
