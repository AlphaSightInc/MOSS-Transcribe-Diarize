# R1 disposition and implementation plan — minimum seam earned by L2 Stage 0

Status: **READY FOR REVIEW; PLAN ONLY.** No R1 or L2 product implementation is
authorized by this document.

Date: 2026-08-03 EDT

Planning baseline: `9089b33210401111865da7abc160ab0bcb4aa266` (merged, pushed,
deployed F4b keeper). Fable input: L2 planning package at
`25f6d5d7b6541dd677b97dcb75bda6305a5c639d`. Claude/Fable R1 verdict:
"redefine to the minimum seam proved by Stage 0 — do not proceed unchanged, do
not drop."

## 1. Decision

Choose the middle option, with important scope corrections:

1. **Do not implement the proposed `MeetingIdentityEngine`,
   `SpeakerEvidenceSource`, or `checkpoint()` now.** They have no second production
   adapter and fail the deletion test.
2. **Do not rename L2 Stage 1 tape plumbing to R1.** Ranged tape reads, sample
   conversion, tape leases, and a committed-span read model are L2 substrate, not an
   identity-engine seam.
3. Keep R1 as a **deferred architectural decision gate**. L2 Stage 0 must first
   prove a tape-derived algorithm, lifecycle, resource envelope, and the exact
   duplicated policy that needs extraction.
4. If Stage 0 passes, implement only the minimum internal modules that its real
   caller needs. Reconsider a unified meeting engine only after Lane B and batch
   supply a second production adapter. Treat crash/resume checkpointing as a
   separate phase.

This means:

- Proceed unchanged: **NO**.
- Redefine to the minimum seam proved by Stage 0: **YES**.
- Drop the unification intent permanently: **NO**.

## 2. Diagnosis

### 2.1 Feedback loop used

The diagnosis used four checks against `9089b332`:

1. Symbol/caller inventory for every current identity interface and adapter.
2. Deletion test for the proposed wrapper: identify where complexity would reappear
   if the wrapper did not exist.
3. Lifecycle reproduction: prove whether a post-`closed` revision can reach a
   viewer or retain its tape.
4. Existing contract tests for preparation, final reconcile-before-sweep ordering,
   revision publication, tape retention, and default-off fallback.

Focused verification result: **248 passed** across coordinator, identity,
provider-bundle, sweep, tape, runtime, and pipeline-seam suites. Lifecycle
reproduction: `test_clean_stop_immediately_revokes_view_authority` **1 passed**,
confirming that detached work after `closed` is invisible under the current contract.

### 2.2 Hypotheses and disposition

| Hypothesis | Prediction | Evidence | Disposition |
| --- | --- | --- | --- |
| H1. Fable is substantially correct: the full engine is a shallow wrapper today | No second production adapter; deleting it leaves current complexity localized | No `MeetingIdentityEngine` or identity-path tape reader exists. Live preparation and L1 revision already work through current modules | **Confirmed, amended** |
| H2. A smaller coordinator seam is needed before L2 product work | Current stop/auth/tape ownership prevents visible asynchronous finalization | `closed` revokes view authority; transport releases tape/access immediately; runtime has no tape dependency | **Confirmed as a Stage-0 question**, not authorization to build it |
| H3. Tape or batch already acts as the second adapter, justifying the full engine | A production caller should already feed common evidence into common policy | Tape has zero identity consumers. Batch Tier B remains separate and does not implement the proposed interface | **Refuted** |
| H4. R1 should be dropped because existing seams permanently suffice | Future batch/Lane-B work would require no shared vocabulary or duplicated policy | ADR-0002 still intends live/batch convergence; future Lane B needs tape-derived speaker attachment | **Refuted** |

### 2.3 Current modules and seams

Use these terms precisely:

| Module/interface | Current adapter/caller | What it hides | Finding |
| --- | --- | --- | --- |
| `LiveIdentityPreparer.prepare(...)` | `BoundedCausalIdentityPreparer`; coordinator; test adapters | parse checks, evidence request, assignment, abstention, birth, preparation | Real internal seam; sufficient for causal live preparation |
| `LiveSpeakerEvidenceProvider.score(...)` | `WeSpeakerLiveEvidenceProvider`, no-evidence adapter, replay/test adapters | live interval embedding and score production | Real internal seam for live evidence; no tape/batch adapter yet |
| `LiveIdentityReviser` | Optional methods discovered by `getattr` on the preparer | finalize provider state and take an L1 `SweepRevision` | Useful result vocabulary, but **not a separately injected adapter seam** |
| `SweepLedger` + `sweep()` | `LiveIdentitySweeper` and tests | leave-one-out rematch, merge, correction creation | Deep reusable module; L2 may consume it directly if Stage 0 proves that path |
| `LiveSession.revise_labels(...)` | coordinator publication | word-preserving, span-local correction safety and refusals | Single authoritative label write point; keep |
| `LiveSessionTape` | recorder/transport only | durable PCM, gaps, degradation, retention | No ranged reader, read lease, or identity consumer |

The proposed full engine fails the deletion test: removing its imagined wrapper does
not scatter matching or correction policy; the existing preparer, evidence provider,
sweeper, and session still own it. Its interface would therefore expose more surface
without gaining depth, leverage, or locality.

### 2.4 Corrections to Fable's concrete wording

- L2 cannot yet be said to "bind to `LiveIdentityReviser`": no L2 adapter exists,
  and the protocol is not injected separately. L2 should produce the existing
  `SweepRevision` data shape if measurement proves it, then use the single session
  publication path.
- The L2 PRD's detached post-stop runner is infeasible as written. A revision after
  `closed` loses its viewer and the tape is released. Stage 0 must choose between a
  bounded `finalizing` lifecycle and a future persisted-job API; current evidence
  favors `finalizing` for v1.
- Energy VAD plus pooling by current labels is not independent identity evidence.
  Prior prototype: incumbent-label pooling improved **0/19** cases; unrestricted
  clustering regressed 3/19, worst **-20.3 pp**; a ledger-only 5% rewrite control
  improved mean **+0.86 pp** with no observed regression. Tape work must beat that
  no-tape control on a blind holdout.
- Warm production embedder cost on the M3 Ultra measured about **RTF 0.145**, missing
  the proposed `<=0.10` gate. The exact deployment CPU must be measured before any
  chunk/budget default is chosen.

## 3. Authority and non-goals

This plan does not authorize:

- product code, deployment, manifest, service, or host changes;
- a full `MeetingIdentityEngine` or `SpeakerEvidenceSource` protocol;
- checkpoint/crash-resume behavior;
- Lane B re-ASR, transcript-word changes, or timestamp changes;
- a production threshold learned after the holdout is opened;
- default-on retention or L2;
- reuse of an unaudited long-corpus reference as acceptance evidence.

Campaign A below is prototype-only. Campaign B requires fresh operator authorization
after Campaign A returns `READY_FOR_PRODUCT_STAGE`.

## 4. Ordered implementation plan

### Campaign A — Stage 0 feasibility; no product code

#### A0. Create the isolated execution lane

Starting point: exact `origin/main == 9089b33210401111865da7abc160ab0bcb4aa266`.

1. Create worktree `MOSS-Transcribe-Diarize-wt-l2-stage0` and branch
   `ralph/l2-retained-identity-v1` from the exact SHA.
2. Create a new `scripts/ralph-l2-afk/` control bundle. Do not reuse the mutable
   history or old ancestor pins in `scripts/ralph-afk/`.
3. Pin in the new launcher:
   - ancestor SHA;
   - branch and worktree;
   - contract id `moss-l2-retained-identity-v1`;
   - corpus-manifest hash;
   - maximum 10 Campaign-A iterations;
   - single-writer sentinel;
   - product-code denylist.
4. Permit Campaign A to change only:
   - `prototypes/streaming-diarization/l2-stage0/**`;
   - `prototypes/streaming-diarization/README.md`;
   - `prototypes/streaming-diarization/NOTES.md`;
   - `scripts/ralph-l2-afk/**`;
   - this plan and, after the verdict, the relevant design/ADR evidence text.
5. Stop immediately if the worktree is dirty before an iteration or the current SHA
   differs from the pinned ancestor/expected previous commit.

Acceptance:

- clean isolated tree;
- launcher dry-run proves the allowlist, denylist, iteration cap, and stop promise;
- no file under `moss_transcribe_diarize/`, `macos/`, `ops/`, or product tests changes.

#### A1. Freeze corpus and model truth

Add under `prototypes/streaming-diarization/l2-stage0/`:

- `README.md`: one setup command and one run command;
- `corpus-manifest.json`: case id, split, audio path/hash, reference path/hash,
  duration, speaker count, validation state;
- `model-manifest.json`: model SHA, frontend/config hash, runtime/provider versions;
- `validate_inputs.py`: hash, monotonicity, overlap, duration, and reference-status
  checks;
- `NOTES.md`: append-only questions, measurements, and verdicts.

Required data actions:

1. Replace the stale acquired-alphabet cache/reference with the accepted post-audit
   reference SHA `28dc9a5b80098db58a261b4bfa73e2975acac31ef36e7e8f057c514d8bdc0759`.
2. Rebuild all vectors derived from changed audio/reference/frontend hashes.
3. Run deletion-capable acoustic validation on every long case proposed for
   acceptance. Flagged/unaudited cases remain exploratory only.
4. Freeze development, validation, and blind-holdout splits before candidate work.
   Store only the holdout manifest hash in the candidate configuration until the
   candidate is frozen.
5. Assert prototype runtime imports cannot reach any reference/golden path.

Red-first checks:

- mutate one byte of an audio, reference, and model fixture; validation must fail;
- supply a known transcript-only line; acoustic validation must fail;
- expose a golden path through runtime candidate config; import/config audit must
  fail;
- open holdout results before candidate freeze; runner must refuse.

Exit: exact input manifests verify; all acceptance cases carry an explicit audited
state; holdout remains sealed.

#### A2. Reproduce the production L1 baseline

Add `run_l1_control.py` and tests. It must call production `SweepLedger` and
`sweep()` rather than copying their policy.

1. Reproduce every accepted L1 case twice.
2. Store revision traces, mappings, per-speaker correctness, activity precision,
   false-positive speaker seconds, DER family, and changed-duration fraction.
3. Fail if repeated runs differ or if the corrected acquired-alphabet score does not
   match the accepted evaluator within the predeclared repeatability band.
4. Preserve result JSON plus SHA-256 manifest outside model/corpus data; record only
   hash-addressed evidence in `NOTES.md`.

Exit: deterministic L1 result and revision trace on every gated case. This is the
baseline all later arms compare against.

#### A3. Prototype lifecycle ownership

Add a state-model prototype and red-first tests; do not modify product lifecycle
code.

Required model:

```text
active -> closing -> finalizing -> closed
                  \-> failed/aborted
```

The model must prove:

1. capture/write authority ends when stop is acknowledged;
2. view authority remains valid during `finalizing` and through one observable
   terminal snapshot/event;
3. the tape is sealed and protected by a read lease while finalization runs;
4. one bounded queue owns all finalizers; at most one CPU finalizer runs;
5. timeout, cancellation, process shutdown, degraded tape, and exception each
   release the lease once and fall back to L1;
6. abort never starts L2;
7. TTL zero cannot reap a leased tape and reaps it after release;
8. a new live meeting stays responsive while an older meeting finalizes.

Required negative controls:

- current `active -> closing -> closed` model must reproduce the invisible-revision
  failure;
- one-thread-per-session model must fail the bounded-concurrency invariant;
- early tape release must fail the lease invariant.

Decision:

- choose `finalizing` only if all invariants pass;
- otherwise choose a persisted job/result API and stop Campaign A for a revised
  product plan. Do not quietly run L2 synchronously inside stop.

#### A4. Measure exact resource envelope

Add `measure_runtime.py`. Run on the actual deployment CPU with the production
embedder, one-thread ONNX settings, and exact model hash.

Measure cold and warm:

- 25 s, 100 s, 5 min, and projected/measured 30 min audio;
- peak RSS and bytes read per chunk;
- finalizer queue wait;
- stop acknowledgement;
- time in `finalizing` and time to final visible revision;
- new-session p50/p95 latency with no finalizer, one queued finalizer, and one active
  finalizer.

Predeclared gates:

- finalizer RTF `<= 0.10` on deployment CPU;
- 30-minute analysis `<= 180 s`;
- no whole-tape in-memory read;
- one active finalizer maximum;
- existing user-visible live p95 remains `< 4000 ms` during contention;
- stop acknowledgement adds no more than 100 ms p95 over L2-off after canonical
  drain; background completion is reported separately.

If cost misses, prototype bounded interval selection/caching. Do not weaken the gate
or move work to the live canonical pump.

#### A5. Compare identity candidates

Add `run_candidates.py` with exactly three required arms:

1. production L1;
2. best frozen ledger-only bounded clustering/rewrite control;
3. actual tape-derived candidate using energy VAD only for speech detection, then
   sliding/overlapping speaker embeddings plus constrained grouping/change evidence.

Rules:

- current canonical label may be a prior, never the sole pooling key;
- no reference/golden path is reachable by candidate code;
- same production encoder/frontend and same correction publisher semantics in every
  arm;
- corrections remain existing `(span_id, local_speaker)` units; words, committed
  span boundaries, and word timings never change;
- one-person-per-lane is a separately reported opt-in arm, never a default;
- candidate family and thresholds freeze before holdout opens;
- a dedicated diarization/change model is a new decision, not an automatic fallback.

Development/validation gates before holdout:

- tape arm beats L1 and the ledger-only control by at least 1.0 percentage point on
  the predeclared target-error subset;
- at least 50% of L1-unreachable mislabeled seconds in sub-floor/weak-vector
  scenarios are recovered;
- no validation case regresses more than 0.5 pp;
- false-positive speaker seconds and DER do not worsen on any gated case;
- two-sided mapping remains true wherever L1 has it;
- every proposed correction reports score delta and changed-duration fraction;
- adversarial padding remains rejected.

Then open the blind holdout exactly once. The same gates apply, with no tuning or
candidate replacement afterward.

#### A6. Stage-0 verdict and seam inventory

Produce:

- `L2_STAGE0_VERDICT.json` with input hashes, commands, environment, all arm results,
  resource results, and `READY_FOR_PRODUCT_STAGE` or `BLOCKED`;
- `L2_STAGE0_EVIDENCE.sha256` over every raw result;
- `NOTES.md` verdict;
- design/ADR amendment stating only measured facts;
- a seam inventory using the two-adapter rule and deletion test.

`READY_FOR_PRODUCT_STAGE` requires every A1-A5 gate. Any failure produces
`BLOCKED`, records the failed gate, and ends the Ralph run. A failed arm must not
turn Campaign A into an open-ended tuning loop.

### R1 decision gate after Stage 0

For each proposed interface, answer:

1. Are there two independently useful adapters/callers, normally production plus a
   meaningful test adapter or two production paths?
2. Does the interface hide substantial policy, resource, or failure complexity?
3. If deleted, where exactly does that complexity reappear?
4. Does it improve locality, leverage, or testability without exposing internals?
5. Is it an internal seam or a stable external interface?

Expected disposition if Stage 0 passes:

| Candidate | Default disposition | Reopen condition |
| --- | --- | --- |
| Concrete tape range reader + read lease | Build as L2 module, tested through real store and fault adapter | Stage 0 proves ranged/chunked reads and TTL interlock |
| Immutable committed-span read model | Build minimal fields actually consumed by winner | Stage 0 proves exact sample/segment mapping |
| Concrete bounded finalization coordinator | Build as a deep module, not a protocol hierarchy | State prototype proves `finalizing` and bounded queue |
| Shared revision application helper | Extract only when L1 coordinator and L2 finalizer are both real callers | Both translate `SweepRevision` into identical `LiveSession.revise_labels` behavior |
| `LiveIdentityReviser` as separate injection | Do not force | A second independently injected reviser needs the same lifecycle contract |
| `SpeakerEvidenceSource` protocol | Defer | Tape and batch/Lane-B expose a stable common evidence vocabulary after use |
| `MeetingIdentityEngine` | Defer | Two production adapters require common ingest/reconcile policy and wrapper passes deletion test |
| `checkpoint()` | Separate crash/resume phase | Persisted transcript, identity, mixer/lane, config, and tape recovery are authorized together |

The likely minimum shared identity seam is the **revision data/publication boundary**,
not an engine object. `SweepRevision` is already the producer result. When L2 becomes
a second real producer, extract only the common safe application logic currently
private to `LiveCoordinator`; keep `LiveSession.revise_labels` as authority.

### Campaign B — product implementation; fresh authorization required

Campaign B starts only after Stage 0 is `READY_FOR_PRODUCT_STAGE`, independent review
agrees, and the operator authorizes product changes.

#### B1. Add dark read substrate

Files:

- `moss_transcribe_diarize/app/live_tape.py`;
- `moss_transcribe_diarize/app/live_session.py`;
- `tests/test_live_tape.py`;
- `tests/test_live_session.py`.

Red first:

- byte-exact ranged reads, including partial EOF, gaps, rebases, invalid ranges, and
  degraded/missing tracks;
- lease prevents TTL-zero reap, release permits reap, exceptions release once;
- committed-span read model returns immutable sample bounds and segment-level local
  labels; no mutable session internals leak.

Green implementation:

- chunked `os.pread`; no `read_track()` on long L2 paths;
- explicit sample units and checked PCM16 byte arithmetic;
- smallest read model consumed by Stage-0 winner;
- no behavior change when unused.

Rollback: revert this additive commit; no consumer exists yet.

#### B2. Add bounded finalization lifecycle

Files selected after A3, expected:

- new `moss_transcribe_diarize/app/live_finalization.py` concrete module;
- `live_service_runtime.py`, `live_transport.py`, `live_auth.py`, `live_portal.py`;
- corresponding runtime, API, auth, portal, helper-failure, and tape tests.

Red first: every A3 state invariant as a product integration test, including races,
double-stop, view-token lifetime, disconnect/reconnect, timeout, shutdown, abort,
lease release, and concurrent new meeting.

Green implementation:

- one queue, one active CPU finalizer, bounded work and cancellation;
- `closing -> finalizing -> closed` only for enabled/eligible sessions;
- L2-off retains byte-for-byte current lifecycle where externally required;
- capture authority ends promptly; view authority survives until terminal revision is
  observable;
- no embedding under runtime/session lock;
- no one-thread-per-session design.

Rollback: config/default off bypasses the coordinator; full revert restores current
stop lifecycle.

#### B3. Add the measured tape refiner

Files:

- new `moss_transcribe_diarize/app/live_identity_l2.py` concrete module;
- new shared revision-application helper only if the two-real-caller gate is met;
- `tests/test_live_identity_l2.py` and focused existing identity tests.

Implement the exact frozen Stage-0 winner. Do not retune.

Required contracts:

- input: leased ranged tape reader, immutable committed-span read model, read-only
  album view, frozen config/model hashes;
- output: `SweepRevision` or a named skip/failure result;
- no ASR, transcript text, word timing, live album mutation, or reference access;
- deterministic result for identical inputs;
- budget exhaustion applies the last fully converged safe revision or falls back to
  L1, as preregistered in Stage 0;
- missing/degraded/refused tape and every exception are named, non-terminal fallbacks.

Do not make `live_identity_l2.py` implement `LiveIdentityReviser` merely for symmetry.
Use that interface only if actual injection and lifecycle match it.

#### B4. Integrate default-off config and observability

Add hash-covered manifest/config fields proved by Stage 0. No guessed defaults.

Events must distinguish:

- disabled, missing tape, degraded tape, budget, cancellation, exception;
- queued, started, finished, skipped;
- queue wait, audio seconds, wall time, RTF, peak memory;
- corrections proposed/applied/refused by name;
- changed-duration fraction and score deltas;
- final revision version and terminal visibility.

No event/log contains PCM or transcript words.

#### B5. Focused, stress, full, and negative-control gates

Focused Python:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_live_tape.py tests/test_live_session.py \
  tests/test_live_identity_sweep.py tests/test_live_identity_l2.py \
  tests/test_live_coordinator.py tests/test_live_provider_bundle.py \
  tests/test_live_service_runtime.py tests/test_live_auth.py \
  tests/test_live_api.py tests/test_live_portal.py \
  tests/test_live_helper_failure.py tests/test_live_pipeline_seams.py
```

Stress/repeat:

- at least 100 finalization lifecycle race cycles;
- multi-session queue at configured bound plus one over-bound refusal;
- stop/disconnect/reconnect during each state;
- process shutdown/cancellation at each chunk boundary;
- TTL-zero reaping before/during/after lease;
- active finalizer plus fresh live session latency;
- two deterministic corpus reruns per case;
- tape absent, disabled, degraded, truncated, gapped, corrupt index, budget exhausted,
  hostile store, and embedder exception controls;
- adversarial padding and no-golden-path controls.

Full gates:

```bash
swift test --package-path macos/MOSSCapture
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q -p no:cacheprovider
git diff --check
```

Acceptance: all Stage-0 accuracy/resource gates repeat on the product path; L2-off
fallback matches baseline; existing Swift/Python floors do not decrease.

#### B6. Keeper, deployment, and evidence

1. Merge only through the repository keeper at stage boundaries.
2. Push, then synchronize server and m4mbp to the exact merge SHA.
3. Finalize hash-covered manifest while preserving existing deployed identity
   constants unless Stage 0 separately authorized a change.
4. Deploy L2 default-off; verify descriptor SHA, canary, services, zero restarts, TCC,
   and tape-root posture.
5. Run paired L2-off/on measurements, finalization SLOs, accuracy, negative controls,
   and contention stress.
6. Archive raw durable evidence with a SHA-256 manifest. No final proof may exist only
   under `/tmp`.
7. Independent reviewer checks code, raw evidence, exact host SHA, and every gate.
8. Enabling L2 is a separate operator decision after review.

## 5. Commit and rollback structure

Campaign A commits:

1. Ralph/corpus guardrails;
2. corrected corpus manifests and L1 reproduction;
3. lifecycle/resource prototypes;
4. candidate comparison and sealed holdout;
5. verdict/evidence docs.

Campaign B commits:

1. ranged read/lease/span read model;
2. finalization state/coordinator;
3. measured refiner and optional shared revision publisher;
4. config/events/integration;
5. evidence/doc updates.

Each commit must be independently testable and revertible. Default-off is a safety
property, not a substitute for passing tests. Never mix algorithm tuning with
lifecycle, deployment, or evidence changes.

## 6. Stop conditions and remaining decisions

Stop and return to the operator if:

- tape candidate fails to beat both L1 and ledger-only control;
- any holdout case regresses beyond 0.5 pp;
- golden/reference access reaches runtime candidate code;
- deployment CPU misses the bound after the single preregistered optimization pass;
- `finalizing` cannot preserve viewer/tape safety without weakening auth/retention;
- the winner requires a new diarization model or GPU scheduling;
- implementation reveals a material interface not predicted by Stage 0;
- any request expands into crash/resume, Lane B, or full batch unification.

Operator decisions before Campaign B:

1. accept `finalizing` as a temporary visible state, if A3 passes;
2. state tape TTL/cap/root for deployment;
3. keep one-person-per-lane explicit opt-in or omit it;
4. authorize Campaign B;
5. separately authorize any future full `MeetingIdentityEngine` review after Lane B
   and batch are real consumers.

## 7. Definition of done

R1 is not "done" when a wrapper class exists. This plan is done when:

- Stage 0 returns a hash-pinned, independently reviewed verdict;
- every product seam is justified by a real caller and deletion test;
- authorized Campaign B, if any, passes focused/full/stress/negative/deployment gates;
- exact-SHA durable evidence proves the behavior;
- remaining full-engine and checkpoint decisions stay explicitly deferred.
