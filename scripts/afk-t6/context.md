# Context — Phase 1 ticket #6

Iteration 12. Acceptance criteria and a reproducible local validation baseline are captured. The
provider exposes immutable, encoder-pinned observations from the completed album. The measured
single-process writer runs after exact clean-stop accounting and never on abort. Live deployment
wiring now makes the journal default-on at an operator-configurable path outside the checkout;
raw-audio retention remains default-off. ADR-0003 now states the derived-vector distinction and
the explicit consent/right-to-remove gate. A configured production factory has also been exercised
end to end from an accepted audio frame through the real provider/coordinator/runtime path to the
complete journal row. After merging current `dev`, both Swift products build and all 871 in-scope
tests plus 373 subtests pass. The only full-suite failure is the established out-of-ticket Launch
Services lifecycle node. Raw merged evidence is committed, local `dev` is fast-forwarded, the
ticket branch is published to `private`, and issue #6 has the required criterion-by-criterion
evidence and explicit coverage limits. Ticket work is complete; the supervisor retains issue
closure authority, and issue #6 remains open behind open issue #1.

## Where things stand

- Branch: `afk/t6-vector-journal`, published to `private`. Worktree 6 of 6 (treehouse pool).
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

- [x] At session end, append one record per speaker containing `session_id`, `speaker_label`,
  `centroid`, `sample_seconds`, `embedder_id`, `embedder_state_sha`, `created_at`, and
  `echo_mode`.
- [x] Every row contains both `embedder_id` and `embedder_state_sha`.
- [x] Records are keyed by session, never by device; Phase 1 has no `device_id`.
- [x] Vector journaling defaults ON while raw-audio retention remains OFF.
- [x] The journal path is operator-configurable and outside the checkout.
- [x] A refused or unusable observation is declined by name and never aborts the session.
- [x] Documentation states that the journal is not a consent decision and that rollout beyond
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
- Production-factory journal path: GREEN. A configured bundle accepted an audio frame, used the
  concrete `WeSpeakerLiveEvidenceProvider`, completed a clean stop, and wrote the full
  session-keyed row through the production coordinator/runtime/writer path; the provider-bundle
  suite passes 46/46. Raw JUnit:
  `evidence/phase1/t6/iteration-8-provider-journal-e2e.xml`. The deterministic test replaces the
  external VAD and encoder adapter, so it does not prove the pinned ONNX model, multiple real
  voices, a filled-in host profile, multi-process writes, or power-loss survival.
- Consent boundary: documented in ADR-0003. Derived centroid journaling is explicitly separate
  from default-off raw-audio retention, is not a consent decision, provides no removal mechanism,
  and cannot roll out beyond the guarded LAN/tailnet without explicit consent and
  deletion/right-to-remove rulings.
- Post-implementation merged full gate: RED. `dev` was already an ancestor, both Swift products
  built, and pytest reached 868 passed / 4 skipped / 373 subtests, but two ticket-local regression
  tests still encode the old contract: one fake `build_live_runtime_factory` rejects the new
  `vector_journal` keyword, and one live `start-web.sh` fixture omits the now-required
  `MOSS_LIVE_VECTOR_JOURNAL_PATH`. The only other failure is the established out-of-ticket Launch
  Services failure. The narrower live route/auth/mixer subset remains green at 65 passed / 351
  subtests. Raw JUnit: `evidence/phase1/t6/iteration-9-full-suite-after-merge.xml` and
  `evidence/phase1/t6/iteration-9-live-subset-after-merge.xml`. The shared lock was released and
  `dev` was not advanced.
- Stale ticket-contract fixture repair: GREEN. The CLI factory fake now requires and inspects the
  concrete `LiveVectorJournal`, and the shell-adapter fixture supplies and asserts the required
  outside-checkout journal path. Both formerly failing nodes pass 2/2; the combined
  speaker-provider/deployment/provider-bundle/runtime/live regression passes 238 tests / 351
  subtests. Raw JUnit: `evidence/phase1/t6/iteration-10-stale-contract-fixtures.xml` and
  `evidence/phase1/t6/iteration-10-ticket-regression.xml`. This is not a replacement for the merged
  full gate.
- Current-dev merged gate: GREEN for ticket #6. The shared lock serialized merge of `dev` at
  `9a1d70e`; both Swift products built; pytest reached 871 passed / 4 skipped / 373 subtests with
  only the established out-of-ticket Launch Services failure; and the live route/auth/mixer subset
  passed 65 tests / 351 subtests. Raw JUnit:
  `evidence/phase1/t6/iteration-11-full-suite-after-merge.xml` and
  `evidence/phase1/t6/iteration-11-live-subset-after-merge.xml`. Loop syntax and `git diff --check`
  also pass.
- Publication: GREEN. Under the shared merge lock, `dev` at `9a1d70e` was confirmed as an
  ancestor of validated commit `db75ba8`; local `dev` was fast-forwarded and
  `afk/t6-vector-journal` was pushed to `private`. Issue comment
  <https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/6#issuecomment-5277120540> links the
  branch, maps all seven criteria to evidence, and discloses real-ONNX, real-voice, multi-process,
  power-loss, filled-host-profile, deployment, and unrelated Launch Services coverage limits.
  The comment was authored by `yugao-aisight`; issues #6 and #1 remain open.
- Loop script syntax: PASS.

## Ranked candidates

No ticket-local work remains. Do not close issue #6; wait for the supervisor and blocking issue #1.
