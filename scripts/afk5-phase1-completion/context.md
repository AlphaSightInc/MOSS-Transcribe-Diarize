# context — afk5-phase1-completion

Living working memory. Update it every iteration so it matches reality. History goes in progress.txt.

## Verified state (2026-08-18, dev @ merge of y6 + y7)

- G10's certified `dev` bar is **2 failed / 1066 passed / 2 skipped / 396 subtests**. Iteration 3
  preserved this worktree's raw, non-certifying result at
  `evidence/phase1/g10-ledger-reconciliation/iteration-3-root-pytest.txt`: **1 failed / 1065 passed /
  4 skipped / 488 subtests**. The valid local l2 corpus accounts for +92 subtests; two
  operator-owned real-corpus tests skip here. **Never "fix" either baseline guard or replace the
  certified bar with this worktree's denominator.** The current source frontend suite is **126/126** across
  16 files (iteration 34); the earlier 122/122 artifact remains historical evidence.
- Gates certified: G1, G2, G7, G8, G10. G6 has its local real-browser bar met (y6: 19/19 assertions,
  all 19 falsified against corrupted observations).
- W1/W5 are now released in `ProjectResources/Frontend/{app.js,app.js.map}`. The app keeps the
  bearer in `App` memory, passes it to both panels, and sends it on file create/poll/segments
  requests; it is not written to browser storage or a URL. Export names are
  `transcript-<session_id>-<iso8601>.<ext>`. Focused bearer/export coverage (11/11 and 8/8), full
  frontend 115/115, and typecheck passed before the release; iteration 12 rebuilt the served bundle
  (77,879 bytes, worktree blob `4ad30bf...a488cb`). The release verifier now fails on legacy upload
  and static filename signatures, requires `bearerToken`, and regex-checks dynamic session/timestamp
  interpolation in the generated bundle. It passes only when the generated artifact is committed at
  `HEAD`. The scope is declared narrowly in `scripts/afk-guardrails/ownership.json` for these two
  generated artifacts, following the operator-authorized release rather than bypassing preflight.
- Export caveat lands in md, txt and json, only when a turn is non-final. 4 tests.
- **Issue #5 criterion 7 is now closeable (iteration 13):** the descriptor's existing request carries the
  exact server-owned `BROWSER_MICROPHONE_SILENT_STATUS_LINE`; the production literal remains only in
  `live_capture_status.py`. `CaptureClient` renders that line on sustained pre-session microphone silence
  and refuses session creation while the condition persists. Focused frontend coverage (33 assertions),
  live API coverage (49 tests), and the full 16-file frontend suite (117 tests) passed. The rebuilt
  `ProjectResources/Frontend/{app.js,app.js.map}` is pending this iteration's commit, so the HEAD-pinned
  served-bundle verifier correctly remains red until then.
- **W0 local launch PASS:** the recovered real CPU bundle is materialized at the host-local live-data
  path; its manifest was re-finalized for `e1741f904fee942a5eef34e0d40a4d4f848b363d`. Its production
  preflight passes with `onnxruntime==1.23.2`, cached `webrtcvad-wheels==2.0.14`, and the real golden
  WAV. With the G1/G2-proven local HF snapshot, `scripts/g3-attended-session.sh` started TLS only on
  `127.0.0.1:7861`; local descriptor fetch and bearer-authorized session create/abort passed. Raw
  evidence: `evidence/phase1/w0-local-live/iteration-6-local-hf-launch.txt`. Iteration 11 makes the
  helper vLLM-only: an unset or non-200 endpoint now fails before certificates or model startup and names
  `./scripts/moss-vllm-tunnel.sh`; `tests/test_g3_attended_session.py` proves both paths with a usable HF
  directory present (3 passed). The historical CPU/HF launch remains SERVICE-STARTUP evidence only, never
  G3/G4/G5 evidence. Re-finalize before using a checkout whose source revision changes.
- Two-speaker fixture ready: `evidence/phase1/g3-attended/two-speaker-fixture-90s.wav`
  (90 s, mono, 16 kHz, RMS 1031).
- **W3 remains operator-blocked:** iteration 7's reproducible inventory at
  `evidence/phase1/g3-attended/iteration-7-operator-evidence-inventory.txt` found only that
  fixture and no raw attended-session log. A fixture cannot establish the charter §7
  fresh-gesture two-lane display-capture bar.
- **W2 CPU/HF-local measurement ran once before the 17:40 operator ruling, and is diagnostic only:**
  `cpu_hf_local_preregistration.json` SHA-256 is
  `955a2883ada6cef99be007d1eb3c9838d6be9e227dc1408e06b6f8617fdb9d6c`. It records 120-second
  screens at 1/2/4/8 sessions and one 600-second largest-passing soak, using real decoder/speech,
  descriptor-derived geometry, p95 `<=10.0 s`, local RSS-growth `<=4 GiB`, zero OOM, skew `<=1`,
  retryable session-local v2 429, overload marker isolation, and observer reconnect. Iteration 9's
  harness writes frame/observer/RSS arrays and canonical dispatch events incrementally at
  `run_cpu_hf_local_measurement.py`; input preflight and its asynchronous event-writer smoke passed at
  `evidence/phase1/w2-local-concurrency/iteration-9-runner-and-refreeze.txt`. Iteration 10 completed the
  full 1/2/4/8 matrix at `evidence/phase1/w2-local-concurrency/run-20260818T213600/`: no normal row
  passed, so no 600-second soak was selected. Screen 1 had p95 `4.95967215 s` but RSS growth
  `4300292096` bytes (>4 GiB) and an unclosed stop; screens 2/4/8 had p95 `50.0133405` /
  `79.1572325` / `101.8289666 s`, skew `8` / `4` / `2`, and unclosed stops. The overload row did
  observe session-local retryable 429, peer acceptance, and eventual retry success, but both stops did
  not close. The endpoint/operator ruling arrived after this run: **do not use this CPU/HF result for
  any G4/G5 portion or inference claim**; retain it solely as raw harness/host diagnostic evidence.
- **W2 remote-vLLM contract revised (iteration 28):**
  `remote_vllm_tunnel_preregistration.json` SHA-256
  `0961e7ad863db419c3f2e4ee4e35da6e3a0065418ec9f8c049dc32beae5b1083` preserves the
  1/2/4/8 + selected-600-second matrix and every gate value. It now requires ordered
  `canonical_queued` -> `canonical_started` -> `canonical_processed` evidence and evaluates pairwise
  skew only while both sessions remain queued; incomplete lifecycle evidence fails closed. It still requires
  a run-owned manifest re-finalized to the exact captured `HEAD`, descriptor-derived geometry, and endpoint
  `/health` plus selected-model `/models` probes before *and* after the run. Tunnel-inclusive latency may
  be measured, but isolated GPU latency, GPU memory/utilisation/OOM, and vLLM active/queued counts remain
  unclaimed. The focused lifecycle regression is at
  `evidence/phase1/w2-local-concurrency/iteration-28-fairness-lifecycle.xml`; the contract validator also
  passed with this SHA.
- **W2 eight-marker source inventory (iteration 29):** the read-only endpoint recognized eight distinct
  markers from separately bounded clips of the exact hash-pinned W2 source, and every marker was absent
  from the other seven direct transcripts. The full clips, output, and fixture/manifest hashes are in
  `evidence/phase1/w2-local-concurrency/iteration-29-unique-marker-inventory.json`. At that time it
  established fixture capacity only; iteration 31 absorbs it into the runner below. G4/G5 remain uncertified.
- **W2 integrity oracle is ready (iteration 31):** the fixture now declares those eight audited clips, and
  `proto_unique_marker_inventory.py` reads that shared configuration rather than duplicating its values.
  The read-only endpoint re-proved the exact new fixture manifest (`d8932485...e8bb9aee`): 8/8 expected
  markers appeared only in their own real-speech clip at
  `evidence/phase1/w2-local-concurrency/iteration-31-unique-marker-fixture.json`. The runner assigns one
  distinct clip per session and fails closed before capture if any normal or overload phase is undersupplied
  or duplicated. Its v2 canonical log now associates submitted spans with their rendered transcript (never
  PCM); overload replays the peer's whole clip and requires both rendered/canonical marker isolation plus
  isolated reconnect snapshot and replayed-event evidence. Focused route/runner validation is 10/10 at
  `evidence/phase1/w2-local-concurrency/iteration-31-integrity-oracle.xml`. This is harness/fixture
  readiness, not a G4/G5 result; the unchanged fresh matrix is still required.
- **W2 remote-vLLM runner first live attempt (iteration 25), fail-closed before capture:**
  `run_remote_vllm_tunnel_measurement.py` uses the production local-route/`VllmRunner` seam with one
  loopback process, a fresh evidence-owned finalized manifest bound to the captured HEAD, descriptor
  equivalence checks, and background helper heartbeats at explicit lease/4 cadence. It fails before
  service startup if `/health`, selected-model `/models`, fixture/provisional inputs, endpoint URL, or
  deployed descriptor checks fail; it records canonical model-catalog identity before and after a run,
  and a failed closing probe makes the verdict non-qualifying. Its first real preflight passed against
  the live tunnel and read-only deployed descriptor at
  `evidence/phase1/w2-local-concurrency/iteration-24-remote-vllm-runner-preflight/preflight.json`
  (frozen contract `53de...7504`, catalog hash `8467...c2e7`, deployed bounds match the required shape).
  The first actual run, in
  `evidence/phase1/w2-local-concurrency/run-20260818T200016-iteration25/`, correctly failed before
  any session or inference: its fresh run-owned manifest retained relative `identity-state` and
  `golden-input` paths, which then resolved beside the evidence output rather than the provisioned
  asset directory. The production preflight recorded both assets absent in `bundle-preflight.json`.
  Endpoint health and selected model probes were 200 before and after; this is harness failure evidence
  only, not G4/G5 evidence.
- **W2 run-owned-manifest locality repair (iteration 26):** to preserve the frozen run-owned manifest
  contract without adding the 79,158,228-byte ONNX to repository evidence, the runner now finalizes an
  ephemeral execution bundle outside the repo, materializes relative assets only there, runs the production
  bundle preflight before route startup, and copies only the finalized manifest plus small hash records to
  `--output`. The focused runner test calls the real `LiveProviderBundleConfig.preflight()` before and after
  materialization: the counterfactual requires both `identity-state` and `golden-input` absence failures;
  the repaired state requires neither. It passed **5/5** at
  `evidence/phase1/w2-local-concurrency/iteration-26-ephemeral-execution-manifest.txt`. This is harness
  locality evidence only: no route, remote inference, or G4/G5 phase ran.
- **W2 first remote-vLLM matrix (iteration 27):** the real frozen 1/2/4/8 run completed at
  `evidence/phase1/w2-local-concurrency/run-20260819T000000-iteration27/` against the read-only tunnel
  (before/after health and selected-model probes 200; captured HEAD `037b633...`; prior contract
  `53de815...`). Screen 1 and its 600-second soak passed (p95 1.5023 s, local RSS growth 206,815,232 bytes,
  zero locally observable accelerator/OOM errors, closed stop); overload passed its retryable session-local
  429, peer-acceptance, retry, and stop checks. Its reported screen-2/4/8 skew 30/33/13 is **unmeasurable**, not
  scheduler evidence: the v1 log has only `canonical_processed` entries, so it cannot reconstruct which sessions
  were continuously ready and must not select a bound. The normal marker oracle is also degenerate at 4/8 because
  only two markers repeat, and overload does not evaluate required text isolation or observer reconnect. Latency is
  SSH-tunnel/tailnet inclusive; GPU memory/utilisation/OOM and vLLM queue counts remain unmeasured. G4/G5 remain
  uncertified; do not infer a scheduler defect or a bound from this run.

## Environment facts that cost previous cycles real time

- `npm` works only via `/opt/homebrew/bin/npm`. `npm ci` genuinely fails on this host.
- Playwright lives in **pyenv 3.12.12**, not `.venv`. Use
  `PYENV_VERSION=3.12.12 pyenv exec python`.
- `log` is shadowed by a shell builtin — use `/usr/bin/log`.
- zsh: `$var` followed by `:` is a history modifier; quote it.
- A `gh issue list` with no `--repo` hits the **upstream fork parent** `OpenMOSS/...`, not our
  tracker. Always pass `--repo aiSight-us/MOSS-Transcribe-Diarize`.
- The GPU host advertises `provider_name: moss-rtx-webrtc-wespeaker` and
  `source_revision: fb83ba5ee60c...`, which is **not a commit in this repo**. Do not copy its
  revision onto ours.

## Candidates (ranked — re-rank as you learn)

1. **W2 run-32 lifecycle re-score and stop-classification repair (P1):** iteration 35 added a bounded,
   writer-owned drain barrier before every normal/overload lifecycle read, so first inspect the already-durable
   run-32 log's counts and re-score it without another matrix if complete. Then separate drain completeness
   from fairness and report no-contention fairness as `not_applicable`. Do not change frozen gate values or
   scheduler behavior. The run-32 four-session soak is already a true G4 failure (p95 84.378 s); do not rerun
   a matrix merely to seek a higher bound.
2. **W2 overload rendered-marker timing probe/repair (P2):** canonical marker evidence is present but the
   rendered marker was checked before reconnect. Test a bounded wait for rendered ownership before reconnect;
   keep a real timeout as a failure, not a pass. This can clarify G5 integrity evidence but cannot make the
   failed G4 soak pass.
3. **Defect B replication (operator input, P3)**: iteration 20 measured a 15.377 dB RMS disparity but
   rejected peer-RMS matching (WER +3.468 pp, six more missing words). The sole aligned capture has the
   same lexical playback in both lanes, so it cannot set a general mixer policy or a warning threshold.
   Need multiple synchronized recordings with distinct audited per-lane references before re-testing any
   normalisation/AGC/offset proposal.
4. **Defect C (P4, blocked on B replication)**: do not source warning copy or choose a threshold from the
   one same-playback fixture.
5. **W3 (blocked externally)**: an operator must add the raw attended-session log before the charter
   frame/cadence/fetch/RMS validation can run.
6. **W4 ledger reconciliation (after W2 repair):** `docs/phase1-gate-status.md` is stale about
   the reachable vLLM endpoint. Reconcile it only with the run-32 result and explicit limits: G4 is not met,
   while G5 has no cross-session leakage observed but remains not certified.
7. **Issue #8 criterion 2 (blocked externally)**: needs the lifecycle vocabulary ruling; do not invent
   nonexistent `starting`/`recording`/`completed` values.

## Blockers

- ~~`MOSS_VLLM_BASE_URL` is unset~~ **SUPERSEDED 17:40: the endpoint is LIVE at
  `http://127.0.0.1:18000/v1` via `./scripts/moss-vllm-tunnel.sh`, monitor-verified including a real
  transcription. A local HF run may NOT establish any G4/G5 portion — the local runner is off limits by
  operator ruling. Run G4/G5 against the tunnel.** Still unobtainable and not to be fabricated: GPU
  OOM/errors, GPU memory/utilisation, vLLM active/queued counts (the tunnel carries inference, not host
  telemetry; the host stays read-only).
- The tunnel launcher is now present at `scripts/moss-vllm-tunnel.sh`, exact-content matched to reviewed
  `affeaea`; iteration 21 also observed its pre-existing local endpoint return `/v1/models` 200. The
  route-probe support now exists at `production_route_server.py` and its real seam artifact is iteration
  22; iteration 26 closed the relative-asset locality blocker with an ephemeral execution bundle outside the
  repo. Iteration 27 proved tunnel reachability, real decoder wiring, run-owned manifest admission, and the
  selected 600-second one-session bound. Iteration 28 corrected the fairness observer, iteration 29 proved
  eight source markers, iteration 30 superseded the old machine-readable G4/G5 claim, and iteration 31
  wired unique markers plus overload isolation/reconnect into the runner. Next is one unchanged fresh v2
  lifecycle matrix; it alone can decide the W2 result.
- Issue #8 criterion 2 needs an operator ruling: the demanded `starting`/`recording`/`completed` values do
  not exist in the product's `SessionLifecycle`, and queued/running both presently map to `active`.


## W0 evidence and limits

- The real assets' hashes are `5b734353...330262a8` (ONNX) and `d101dd44...ac0e60aa` (golden WAV),
  matching `evidence/phase1/t1/iteration-10-real-model-browser.json`. They were not sourced from the
  fabricated test fixture.
- The finalized manifest's golden check passes through the production `LiveProviderBundleConfig`
  readers, with zero failures and manifest hash `84600e8...0599c178`; raw command and output are in
  `evidence/phase1/w0-local-live/iteration-4-provider-preflight.txt`.
- Iteration 6 closed W0 with a local service, descriptor fetch, and authenticated session lifecycle.
  **It is SERVICE-STARTUP evidence only — never cite it for inference; the local HF runner is off limits.**
  The vLLM endpoint is now live via the tunnel, so G4/G5 are unblocked.
- Iteration 12 replaces G9's stale-bundle proof with a release gate: all legacy signatures must be absent,
  bearer propagation must be present, and the generated bundle must dynamically interpolate session ID and
  ISO-8601 export time. Its final `HEAD` pin is part of the same verification; no source-only result may
  stand in for a released artifact.

## Deployed bounds == local bounds (monitor, 2026-08-18 16:55) — W2 is mostly unblocked

Probed `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/api/live/descriptor` and diffed against the
local manifest. Identical: `hard_cap_samples 40000`, `max_events 1000`, `max_frame_samples 16000`,
`max_identity_speakers 16`, `max_queue_depth 16`, `max_retained_samples 960000`,
`stop_drain_deadline_seconds 5.0`, `frame_samples 8000`, `sample_rate 16000`.
(`hard_cap_samples 4000` / `max_queue_depth 64` / `max_identity_speakers 2` is the G7 artifact's `api-fake`
provider — not the deployed host. Never cite those as deployed.)

**Split G4/G5 accordingly:**
- **Local, at the real deployed bound, no GPU:** queue-depth behaviour, per-session vs global 429, round-robin
  fairness, marker isolation under overload, reconnect, no OOM, the ≥10-minute sustain.
- **GPU host only:** p95 transcript lag as a deployed figure, GPU memory/utilisation (also issue #1's last
  unmet criterion).

Iteration 9 re-froze the contract before measurement: screens are 1/2/4/8, the selected bound alone
soaks for 600 seconds, the final contract records why both safety ceilings are wide, and the harness
records CPU-local decode RTF, per-session queue depth, and writer overhead.

## Resolved iteration 12 — G9 served-bundle release gate

The old audit green-lit the stale bundle. The release verifier now makes the inverse claim: a stale bundle
fails six behavior assertions; a rebuilt bundle must remove all four legacy paths, include bearer options,
and dynamically form `transcript-<session_id>-<iso8601>.<ext>`. It also compares the served artifact to
`HEAD`, so a local rebuild cannot be cited as released until committed.

## W2 threshold basis + run shape (monitor, 2026-08-18 17:05; resolved in iteration 9)

Resolved: SHA `955a2883ada6cef99be007d1eb3c9838d6be9e227dc1408e06b6f8617fdb9d6c` records the 10-second and 4-GiB
bases without moving a gate, requires a comparison to prior 0.248-second p95, and retains raw data every tick.

## W2 matrix widening (monitor, 2026-08-18 17:12; resolved in iteration 9)

Issue #3 criterion 2 requires concurrency **1, 2 and 4**; criterion 3 requires recording for **1, 2, 4 and 8**
simultaneous meetings. Your frozen matrix is `screening_session_counts [2, 4]`. **A perfect run as specified
cannot close #3.** Add 1 and 8 and re-freeze while `run_started` is still `false` — a legitimate
pre-measurement amendment; note that the monitor requested it and why.

- **1** is the serialized baseline every other number is judged against. Cheapest row, biggest loss if omitted.
- **8** may be infeasible on CPU. That is an acceptable *result*: "8 sessions: gate exceeded at p95 X s,
  sustained ingress not maintainable on CPU HF" satisfies the criterion. An omitted row does not.
- Keep the 600 s soak on the chosen bound only — the extra cost is two short screening rows.

Name in `does_not_establish` exactly what stays external: **GPU OOM/errors** and **vLLM active/queued request
counts** (need :8000), and deployed real-time factor. Everything else #3 asks for is locally establishable at
the matched deployed geometry.

## W2 instrumentation perturbation (monitor, 2026-08-18 17:22; resolved in iteration 9)

`prototypes/browser-capture-feasibility/production_route_server.py:120-139`: `measured_record_event` performs
`open` + `write` + `flush` + **`os.fsync`** *inside* the shared `measurement_lock`, on the canonical
publication path, for every `canonical_processed` event across all sessions. At 8 sessions / 0.5 s ingress
that is ~16 fsyncs/s, 1-10 ms each on APFS, serialized through one lock held during disk I/O.

Latency impact against a 10 s gate: immaterial. **Ordering impact: material** — the tight gates are
`fairness.maximum_dispatch_count_skew...: 1` and per-session queue depth, and lock-held disk I/O on the
dispatch path reorders dispatch and inflates queue depth. That measures the harness, not the system.

Fix while keeping incremental persistence: build the record inside the lock, **append outside it** with one
long-lived handle, drop the per-event fsync (fsync at run end, on interruption, or on a ~5 s interval), and
record the instrumentation overhead in the artifact. If you keep per-event fsync, you must measure its cost
and argue the fairness figure survives it.

Verified good, no action: preregistration amendment moved no gate value and the validator was tightened to
enforce the new matrix and the basis text. Fixture `leading-030s.wav` sha256 `a42507d9…` matches, 90.0 s real
speech, two markers make isolation falsifiable. **Note in the artifact that a 600 s soak repeats the 90 s
source**, since repeated audio can make decode timing unrepresentative.

The issue is resolved: canonical records are constructed while holding only the short publication lock,
then serialized/enqueued after it. A dedicated writer owns one long-lived handle and performs its first
durability sync after five seconds, then at five-second intervals and shutdown; it records enqueue/write/
sync/pending-record overhead with every phase. The real-source fixture is 90 seconds and repeats during
the selected 600-second soak, which the eventual verdict must state.

## MODEL ENDPOINT IS LIVE — verified by the monitor, 2026-08-18 17:40

```
MOSS_VLLM_BASE_URL=http://127.0.0.1:18000/v1     # SSH tunnel, start via ./scripts/moss-vllm-tunnel.sh
```
Liveness has been misreported three times, so I checked the thing that actually matters:

| check | result |
|---|---|
| `GET /v1/models` (x2) | 200 · `OpenMOSS-Team/MOSS-Transcribe-Diarize` · `max_model_len 16384` |
| `GET /health` | 200 |
| `POST /v1/audio/transcriptions` with real audio | **200 · `{"text":"[humming]","usage":{"type":"duration","seconds":3}}` in 0.42 s** |

The engine decodes — `/models` answering would not have proved that, and the earlier failure was an engine
GPU-memory crash. Route shape matches the product: `vllm_runner.py:143-147` builds
`<base>/audio/transcriptions` from a `/v1` base. This server exposes **only** `/health`, `/v1/models`,
`/v1/audio/transcriptions`, `/v1/audio/translations` — no chat/completions (both 404). Pass `.../v1`, nothing else.

## Resolved iteration 11 — G3 helper cannot substitute a local model

`scripts/g3-attended-session.sh` contains only the vLLM backend. If `MOSS_VLLM_BASE_URL` is unset or
`/models` is non-200, it exits before TLS/model startup and names `./scripts/moss-vllm-tunnel.sh`.
`tests/test_g3_attended_session.py` runs both failures while `MOSS_HF_MODEL/config.json` exists, proves
the helper never reaches certificate generation, and asserts no HF backend remains in the script.

## W2 — GO. Keep the frozen contract, widen the honesty.

Do not touch gate values or the matrix (`run_started` still false; the contract is good). Add to
`does_not_establish` and state in the verdict: latency includes **SSH tunnel + tailnet transit**; the GPU is
**shared with mineru-api at 0.5 utilisation, ~800 MiB free**, so this is not an isolated-GPU bound; the decode
path is `/v1/audio/transcriptions`. Honest scope, and better evidence than a CPU number.

**Probe the endpoint before AND after the run and record both** — the tunnel is a local process that can die,
and a mid-run death otherwise reads as a slow model. A run whose closing probe fails is not a passing run.

For #1 criterion 9: the tunnel carries inference, **not host telemetry**. GPU memory/utilisation remain
unobtainable; the host stays read-only. Do not claim them.

## Resolved iteration 13 — Issue #5 silent-microphone preflight remedy

No endpoint was added: the existing descriptor response exposes `preflight_status_lines` from the sole
`BROWSER_MICROPHONE_SILENT_STATUS_LINE` constant in `live_capture_status.py`. Sustained pre-session microphone
silence updates the ControlPanel status line with that exact string; a stale-ready state cannot create a
session until microphone signal recovers. `captureClient.test.ts` and `ControlPanel.test.tsx` cover both facts.

## 60 MB run-state.json — runner fixed; committed diagnostic needs trim

`evidence/phase1/w2-local-concurrency/run-20260818T213600/run-state.json` = 59,992,997 bytes. Traced:
`phases` 51.41 MB (screen-2 5.16, screen-4 16.1, screen-8 30.12); within screen-8,
**`unexpected_frame_results` alone is 30.08 MB** while every other key in that phase is < 0.05 MB. Each entry
embeds the full frame payload **including `pcm_base64`**. Repo precedent: largest committed evidence file is
2.88 MB, largest JSON 1.1 MB. Gzip only reaches 26.9 MB.

The base64 PCM is not diagnostic — status, error, lane, sequence, device_epoch are; and the audio is already
pinned by `fixture_sha256`. **Runner repair, completed in iteration 15 before the vLLM run:**
1. Never record `pcm_base64` in a result — record `pcm_len` (+ short sha256 prefix if identity matters).
2. Aggregate `unexpected_frame_results` by `(http_status, error_code, lane)` with counts, keeping ~3 verbatim
   exemplars per bucket first and last, so the raw shape stays auditable.
3. **Keep** the predicate-bearing arrays — latency samples, dispatch order, RSS samples, queue depth, 429
   outcomes. Those are small and they make the verdict falsifiable. Do not prune them.
4. `canonical-processed.jsonl` (197 KB), `verdict.json`, `service.log`, `preflight.json` and the manifest
   records are fine as-is. Trim only the committed `run-state.json` in the next, separate change.

Verified good, no action: the CPU/HF verdict is a clean negative — `screening_passes: []`,
`qualifies_local_g4_g5_portions: false`, `chosen_normal_session_bound: null` — and it corroborates the operator
ruling, since local CPU could not sustain two sessions. Cleanup confirmed: nothing on 8899/7861, no model
process alive.

## Next feasible sequence
1. Repair the W2 writer/evaluator drain boundary and classify stop drain separately from fairness; do not
   alter the frozen gates or reinterpret the failed four-session soak.
2. Probe the bounded rendered-marker wait before overload reconnect; preserve a timeout as a failure.
3. Reconcile the ledger after those W2 repairs. W3 stays blocked until an operator adds a raw attended-session
   log; Issue #8 remains blocked on the criterion-2 lifecycle ruling; Defect B needs new audited recordings
   before Defect C.

## Resolved iteration 12 — Issue #8 `/studio` continuation documented

The G9 ledger now records the ruled no-bridge design: file jobs write to the shared `runs_dir`; `/studio`
lists and edits those same job routes. It cites existing app-route coverage and explicitly excludes a new
browser-hop or real-model claim.

## Verified this cycle, no action needed

- **Fail-closed G3 helper (iteration 11):** behaviourally tested, not just read. No `MOSS_HF_MODEL` /
  `--backend hf` left; unset endpoint → exit 1, bad endpoint → exit 1 ("probe returned '000'"), nothing starts,
  nothing left on 7861. Only listener is the SSH tunnel on 18000.
- **Served-bundle verifier (iteration 14):** its 16 assertions pass against `HEAD`: bearer ownership and
  propagation, XHR upload plus byte progress, explicit no-resume copy, removal of legacy upload/static-export
  signatures, and the dynamic session/timestamp export filename. The shipped frontend suite is 118/118.
- **W2 unexpected-frame evidence (iteration 15):** the runner stores total counts and the first/last three
  diagnostic exemplars per `(http_status, error_code, lane)` bucket. It retains safe frame metadata, `pcm_len`,
  and a 16-character PCM SHA-256 prefix, never raw PCM. Focused regression and afk5 preflight pass; the historic
  oversized artifact remains deliberately unmodified for the next, separate trim.

## The 60 MB artifact: my note was 2 minutes late, it is already committed

`run-state.json` (59,992,997 B) landed in `227e8ba` at 17:43:42. Iteration 15 completed (a): the runner never
persists `pcm_base64`, aggregates `unexpected_frame_results` by `(http_status, error_code, lane)` with three
first/last exemplars, and retains predicate-bearing arrays. Still do (b): **trim the committed artifact in a new
commit** — your own artifact, so in scope — preserving every array the
verdict's predicates used, and recording the original sha256 + byte size so the trim is auditable.
**No history rewriting** (no amend/rebase/force-push). `dev` uses true merge commits, so the history question is
the operator's call, not yours.

## Issue #8 — C4 met; C2 is the only remaining blocker

I audited all nine criteria after the release. Bundle verified: verifier `OVERALL=PASS`,
`served_bundle_matches_HEAD` true, 77,879 B pinned to HEAD; the **committed** bundle (checked via
`git show HEAD:...app.js`) carries `bearerToken`, the `transcript-${…sessionId}-${…toISOString()}` filename form,
and **#9's caveat** — previously all 0. Frontend 115/115. Ownership grant correctly narrow (two file paths).
`/studio` doc is real and its citation checks out (`tests/test_app_api.py` exercises jobs create/list,
`PUT …/segments`, `…/download?kind=srt`, `GET /studio`).

**C4 MET (iteration 14):** `submitJob` uses native multipart `XMLHttpRequest`; it retains the shared bearer,
reports length-computable `{loaded,total}` through `upload.onprogress`, and `FilePanel` drives the existing bar
plus its status line from those bytes. Poll retries now explicitly say they are checking transcription. The UI
permanently says failed uploads restart from the beginning and resume is unavailable in Phase 1. Focused 11/11,
full frontend 118/118, typecheck, production build, and the 16-assertion HEAD-pinned served-bundle verifier
pass; see `evidence/phase1/g9-ledger-reconciliation/iteration-14-file-upload-progress.txt`.

**C2 needs an operator RULING — do not silently decide:** criterion names `queued→starting, running→recording,
done→completed`, but `api/types.ts:3` has `SessionLifecycle = idle|active|closing|closed|failed|aborted`.
`starting`/`recording` are `capture_phase` vocabulary; `completed` exists nowhere. `lifecycleForJobStatus`
sends everything non-terminal → `active`, so **queued and running are indistinguishable** and the bar reads 0%
for both. Write a `docs/rulings/` memo with both readings + your recommendation and queue it for the operator.

Other seven PASS: C1, C3, C5 (507 "Insufficient storage for upload." surfaced, no silent queueing — literal
"server busy" wording not used), C6, C7, C8, C9.

## ATTENDED-RUN DEFECTS — this is the work now (monitor, 2026-08-18 18:25)

Two attended runs happened. **G3 capture + decode is proven end to end** (transcript, two speaker ids, real
browser). Four defects came out. Verified against the code by me. Order: **A → 409 → B → C**.

### A (P0) poller cursor latch — one root cause, both frozen symptoms
Server healthy (294 frames, 0×429, stop 200, final version=332, pending_work=0). Client pinned at
snapshot `since_version=153` / events `since_seq=210`, 200s forever.
`frontend/src/api/mossPoller.ts`:
```js
const deferralIndex = snapshot ? -1 : newEvents.findIndex(e => eventNeedsSnapshot(e.kind));  // ~:220
eventSequence = consumedSequence;                                                            // ~:289
if (deferralIndex !== -1) { snapshotVersion = 0; }                                            //  :291
function eventNeedsSnapshot(kind) { return kind === "identity_finalized"; }
```
**The re-baseline fires only when a null snapshot coincides with a pending `identity_finalized`.** All other
null-snapshot rounds pin `snapshotVersion` with no recovery. `parseSnapshot` nulls on
`snapshot === null || unchanged === true`. With `newEvents` empty, `consumedSequence` collapses to the current
`eventSequence` — event cursor pinned too. The `:216` comment ("a deferral always resolves instead of
latching") is false for every kind but one. Stop never resolves because the terminal branch needs a *changed*
snapshot. **Write the failing test first**: serve `unchanged: true` at a stale cursor while the server version
advances; assert re-baseline and terminal observation. Do not just widen `eventNeedsSnapshot`.

**Resolved in iteration 17 (source and served bundle):** the test first failed with the exact terminal
callback missing. The poller now retains the server-owned cumulative v2 accepted-sample total and resets only
an `unchanged` snapshot cursor whose ingress total advanced. The replay requires requests `0 → 153 → 0`, a
fresh version-332 closed snapshot, and `onTerminal("Session closed.")`; it passes with full frontend 119/119,
two real-route terminal-contract tests, typecheck, and a rebuilt bundle. Evidence:
`evidence/phase1/g3-attended/iteration-17-poller-cursor-recovery.txt`. This removes the reproduced latch but
does not substitute for a fresh attended run or certify G3/G4/G5.

### 409 (P1, cheap, independent) terminal 409 has no `failure.code`
Browser showed "frame POST failed: HTTP 409" while the server held `canonical_decode_failed`. G6 violation —
a bare status code is not a status line; same class as the VIEWABLE_SESSION_STATUSES gap y3 fixed.
**Already-correct pattern lives in the same file**: `live_transport.py:316`, `:475`
(`{"detail":…, "failure": exc.failure.to_dict(), "snapshot":…}`) and `:455` (`{"failure":{"code":…}}`).
Bare sites to fix: **`:307`, `:308`, `:462`, `:463`**. Client: `captureClient.ts:809`/`:820` handle only
`frame_work_exceeds_queue_capacity` and `v2_out_of_order_frame`; `:828` synthesises a raw-status Error —
render the server line for any unhandled 409. Test for a human-readable UI line, not a status code.

### B (P1, worst real impact) lanes summed with identical gain
`live_mixer.py:256` `mixed = (system * _HEADROOM_GAIN) + (microphone * _HEADROOM_GAIN)`, `_HEADROOM_GAIN =
10**(-6/20)` (`:16`). No level matching, so a quiet mic is buried: shared audio gave full sentences while the
operator's mic gave only "A", "I", "image. Yeah" over 73 s. Charter T-06 is **silent** on inter-lane level
matching — unruled ground. **Prototype and measure first (AGENTS.md, operator instruction). Do not hand-tune a
constant.** Measure per-lane RMS on the real fixture, pre-register what "better" means, then evaluate
normalisation / slow AGC / measured offset against accuracy on a two-speaker fixture. `silent_samples` /
`overlap_samples` in that file is where per-lane level telemetry belongs.

### C (P2) no warning on lane level disparity
Preflight gates only `level >= SILENCE_RMS` (`captureClient.ts:171,739`, `SILENCE_RMS = 1e-4`), so a lane
20+ dB below its peer passes. Do it **after B**, using B's measurement for a defensible threshold, and source
user-facing copy from the server exactly as the silent-mic remedy does.

## Defect A: full cursor-latch repair (iterations 17 and 19)

`168db85` is a real root-cause fix — recovery keyed on an independent signal (cumulative
`v2_session.lanes[*].accepted_samples`), trigger `deferralIndex !== -1 || (!snapshot && ingressAdvanced)`,
defensive parse, and the test strengthened to four assertions carrying the operator's real numbers.
Frontend 16 files / **119 pass**.

**Stop-time residual closed in iteration 19:** when capture has stopped, ingress is flat and the original
fast path cannot trigger. The new red replay held `accepted_samples` and events constant, answered stale
`since_version=153` as `unchanged`, and made only the uncursored reread return closed version 332; before
the repair it kept requesting 153 and never called `onTerminal`. A preregistered state trace selected exactly
two flat rounds: 6 s maximum terminal observation at the 2 s closing cadence, one forced refresh per three
healthy quiescent reads, and no refresh while event delivery advances. The poller resets its counter after the
forced reread and retains the faster ingress-advance route. Focused 14/14, full frontend 122/122, typecheck,
rebuilt bundle, diff check, and preflight pass. Evidence:
`evidence/phase1/g3-attended/iteration-19-poller-flat-cursor-watchdog.txt`. It repairs the source/released
bundle path but does not replace a fresh attended run.

### Resolved iteration 18 — terminal 409 envelope and rendering

All four former bare terminal-409 branches now return a `failure` envelope. When the runtime has a terminal
record, its exact `code`, `message`, and detail are reused; clean mono/v2 terminal states receive the stable
`live_session_terminal`/`v2_session_terminal` code. The capture client uses a nonempty server `detail` (or
the failure message) for every otherwise-unhandled 409, so it reports the server-authored line instead of
`frame POST failed: HTTP 409`. The route replay creates a real `canonical_decode_failed` failure from a
decoder seam and proves its OSError detail reaches the 409; the full live API suite and the 120-test frontend
suite pass. Evidence: `evidence/phase1/g3-attended/iteration-18-terminal-409-envelope.txt`.

## Resolved iteration 20 — Defect B lane-level measurement

The correctly aligned system/mic pair was pre-registered and committed in `756ade4` before the
live vLLM run. The production mixer measured system -19.577 dBFS, microphone -34.954 dBFS
(15.377 dB gap). Peer-RMS matching derived 5.87275×, but one pre-mix sample clipped and it
worsened quiet-lane WER from 0.28324 to 0.31792 (+3.468 pp), with missing words 42→48. No
output limiter samples occurred. The result is an explicit **NO_POLICY_SELECTED**, not a basis
for Defect C: the one 59.584 s capture's lane references are identical playback, so it cannot
attribute transcript recovery to a lane or establish a general threshold. Evidence:
`evidence/phase1/g3-attended/iteration-20-lane-level-aligned-prototype.json`.

## Resolved iteration 21 — W2 tunnel launcher import

`scripts/moss-vllm-tunnel.sh` now exactly matches reviewed `affeaea` (source SHA-256
`5b71bc679c0ef6751017e990dbd7346a3225acd534bd8c0fbf34f585f8d42a92`), passes `bash -n`, and reused an
existing local tunnel whose `/v1/models` returned 200. It never alters the GPU host. This proves only
launcher availability/reachability; W2 still requires a dedicated remote-vLLM runner and its before/after
endpoint probes. Evidence: `evidence/phase1/w2-local-concurrency/iteration-21-tunnel-launcher-import.txt`.

## Verified this cycle, no action

`43d1034` flat-ingress watchdog: hypothesis confirmed by red replay (4th request stuck at `since_version=153`);
counter scoped to `!snapshot && snapshotVersion > 0 && !eventCursorAdvanced`, resets on progress and after
re-baseline; **negative test** added ("does not re-baseline while the event cursor advances", cursors stay
`{153, 4}`). Frontend **122/122**. Bound 2 chosen by a committed, re-runnable prototype
(`proto_poller_cursor_watchdog.py`, sweep 1/2/3, rule fixed in advance) — I re-ran it: `chosen_bound: [2]`.

## Defect B is BLOCKED ON A FIXTURE — do not attempt a policy (monitor, 2026-08-18 19:45)

Measured and verified: system **−19.577 dBFS** vs microphone **−34.954 dBFS** = **15.377 dB** apart — the
disparity is real. Peer-RMS matching made it **worse** (WER 0.28324 → 0.31792, missing words 42 → 48) and was
correctly rejected against the frozen rule. `live_mixer.py` untouched across `43d1034..HEAD` — correct.

**The blocker is the fixture, not the method.** Its two lanes carry identical lexical references
(`system_reference_tokens: 173` / `microphone_reference_tokens: 173`, and both reference scores return the same
137 tokens / 130 LCS / 43 missing / WER 0.289). Identical scores ⇒ per-lane WER cannot attribute a word to a
lane ⇒ no mixing policy is justifiable from it. Re-running cannot fix this.

**Needs an attended capture where the two lanes carry DIFFERENT speech**, separately referenced — the way W2's
fixture uses distinct markers ("New York" / "payments"). Escalated to the operator. Until it exists: attempt no
policy, and set no Defect C threshold (C's number depends on B's authorization). If you ever synthesize a
fixture by overdubbing, record that it is synthetic and what that costs.

Correct next work while B/C are blocked: repair the W2 runner's run-owned relative-asset locality, with a
falsifiable production-preflight test, then start a new tunnel-backed matrix run. The contract remains frozen:
`run_started: false`, sha `53de815d…c857504`, matrix `[1,2,4,8]`, latency label names SSH tunnel + tailnet
transit, `does_not_establish` lists isolated-GPU bound, GPU memory/utilisation, GPU OOM, vLLM queue counts,
attended capture.

## DO NOT materialize assets into evidence/ (monitor, 2026-08-18 19:53) — read before committing iteration 26

Diagnosis verified: `bundle-preflight.json` → `available: false`,
`["asset is not preinstalled: identity-state", "asset is not preinstalled: golden-input"]`; the run-owned
manifest's **relative** paths resolve beside itself, inside the evidence dir. Failing closed was correct.

**But "run-owned asset materialization" copies a 79,158,228-byte ONNX + the golden WAV into `evidence/` per
run** — same class as the `pcm_base64` blob just compacted 59,992,997 → 288,007 bytes. Repo's largest
committed evidence file is 2.88 MB. Do not trade one bloat for another.

**Do this instead** — assets already sit adjacent to a manifest in
`/Users/gao/.local/share/moss-transcribe-diarize/live/`:
1. Re-finalize the manifest **in place there** for the current HEAD (`--source-revision $(git rev-parse HEAD)`).
   Charter §8 needs per-HEAD finalization and HEAD moves each iteration; it is idempotent and free. The
   relative-path invariant then holds because the assets really are adjacent.
2. Point the runner at that manifest path.
3. Copy **only** the resulting manifest JSON (3,320 B) + `manifest-finalization.txt` into the run's evidence
   dir. The manifest carries the asset sha256s, so auditability is preserved without duplicating bytes.
4. **Keep the fail-closed test**, asserting the two failure strings above so it cannot pass vacuously.

If isolation truly requires a run-owned copy, materialize to a **temp dir outside the repo** and record its
path + asset sha256s — never into `evidence/`.

Housekeeping: that durable dir has accumulated `live-provider-manifest.json.backup-*` files; prune or stop
writing them if re-finalization adds one per run.

## Monitor corrections + resolved artifact fix (2026-08-18 20:45; updated iteration 30)

**Correction to my 20:35 note:** the strict `gates.fairness.evidence` wording (lifecycle order, reject
incomplete evidence, continuously-ready intervals) **did not exist during run 27** — at run time it read only
"full canonical_processed dispatch order and per-session counts", which the evaluator did provide. You added the
strict wording in `e5a59c4`. So this was **under-specification, not a contract violation**; the gate's *name*
always said `..._for_continuously_ready_sessions`. Conclusion unchanged: fairness unmeasurable from run 27,
bound not established as 1.

**Checked for goalpost-moving: none.** The contract diff is a pure tightening; gate values untouched (skew 1,
p95 10.0 s, matrix [1,2,4,8], soak 600 s) and `run_started` back to false. Recorded so a later reviewer needn't wonder.

**Resolved iteration 30:** `run-20260819T000000-iteration27/verdict.json` now sets
`"qualifies_local_g4_g5_portions": false` and has `superseded_by: "e5a59c4"` plus an `evaluator_defect`.
The correction keeps `chosen_normal_session_bound: 1` as the measured serialized result and leaves raw state,
latency, RTF, OOM, RSS, and the closing probe untouched. It explicitly says fairness is unmeasurable under the
tightened continuously-ready evaluator and isolation is undetermined above two sessions; G4/G5 remain uncertified.

**Remaining before the next matrix run:** unique per-session markers, and the overload phase actually executing
its isolation + reconnect checks (your own flagged omission). Then re-run the frozen matrix unchanged.

## Marker problem SOLVED without a new capture (monitor, 2026-08-18 20:55)

`5dcf223` derives **eight** distinct markers from the existing hash-pinned fixture (`a42507d9…016b6eea`) —
"New York", "payments team", "huge thanks", "show notes", "investment advice", "entertainment purposes",
"feels appropriate", "dressed up" — each proved through the **live vLLM endpoint**, with
`marker_absent_from_other_candidates` **computed** (`proto_unique_marker_inventory.py:127-129`), not asserted:
8/8 exclusive, 8/8 present, probe committed. That covers the whole `[1,2,4,8]` matrix, so the isolation oracle
is no longer false-by-construction. **The operator fixture request now stands only for Defect B** (two lanes,
different speech).

`bcab94d` corrected the verdict properly: `qualifies_local_g4_g5_portions: false`, `superseded_by: e5a59c4`,
accurate `evaluator_defect` wording ("then-under-specified"), new commit, no history rewrite, all sound numbers
retained.

**Resolved in iteration 31:** the runner now assigns the eight markers one-per-session and executes overload
isolation plus reconnect assertions. Re-run the frozen matrix unchanged next. Expect the bound may exceed 1:
sessions 2 and 4 previously failed **only** on the unsound fairness metric.

## Classify the "queued item remained at stop" finding correctly (monitor, 2026-08-18 21:15)

Oracle hardening verified: `_select_marker_clips` fails closed on too-few clips, missing id/marker, or ANY
repeated identifier/marker; `validate_fixture_phase_capacities()` rejects a matrix that would repeat a marker in
any phase — upfront, not six phases deep. Tests 7/7, including
`test_lifecycle_fairness_excludes_an_idle_peer_but_rejects_ready_peer_starvation` (both directions).

**When the verdict lands, classify the stop finding before writing it up:**
- Descriptor declares `stop_drain_deadline_seconds: 5.0`. Queued **inside** that window and drained before the
  deadline ⇒ declared behaviour, not a defect. Say so plainly.
- Survived the deadline, or a clean stop reported while work remained unprocessed ⇒ **stop-contract / G6**
  finding about losing committed work at stop — **not** a G4 fairness/concurrency finding. Report it separately.
- Either way record: the queued item's session id, its queued/started/processed timestamps, and the measured
  stop→drain interval. Without those three the classification is not checkable by anyone who was not here.
- Do not let it silently downgrade a row: if every gate otherwise passes at a concurrency, that row passes and
  the stop finding stands as its own item.

## Run 32: stop finding is on the WRONG GATE — fix before the verdict (monitor, 2026-08-18 21:25)

**Good news first: screen-2 and screen-4 PASS** (p95 2.03 s, 2.60 s vs 10 s). Run 27's "bound = 1" was an
artifact of the broken fairness metric. screen-8 fails on genuine latency (47.66 s). Honest bound looks like **4**.

**Problem:** `screen-1` reports `passes: False` on one thing only —
`canonical_lifecycle_fairness.errors: ['run ended with queued canonical items for 21b7ce43…']` — while
`maximum_session_p95_passes: True` (3.39 s), OOM 0, `stops_closed: True`, `helper_presence_passes: True`, all
marker checks good, RSS 242 MB vs 4 GiB. And that row records **`contended_pair_dispatch_observations: 0`** — at
concurrency 1 fairness is not evaluable. A **stop-contract** condition was folded into the **fairness** predicate.

**Fix before writing the verdict:**
1. Give the drain condition its own predicate (`stop_drain_complete`), reported separately — G6/stop-contract,
   not G4 concurrency.
2. `contended_pair_dispatch_observations == 0` ⇒ fairness **not_applicable**, never failed. You already applied
   that principle to run 27; apply it here.
3. Classify against declared `stop_drain_deadline_seconds: 5.0`. Record session id `21b7ce43…`, queued/started/
   processed timestamps, and the stop→drain interval. **`stops_closed: True` with queued items outstanding is
   itself the finding** if it survives the deadline.
4. Re-derive the verdict from corrected predicates. No gate-value edits, no contract changes, no retro-fitting
   row outcomes — move the misfiled predicate and re-evaluate.

If screen-1 still fails on a correctly-classified stop predicate, report it as a failing row **and** a separate
G6 finding, stating plainly that latency, memory, isolation and fairness were satisfied or inapplicable there.

## W2 remote-vLLM matrix result (iteration 32, not qualifying)

- The fresh frozen v2 matrix completed against the read-only tunnel at
  `evidence/phase1/w2-local-concurrency/run-20260819T011500-iteration32/`; its separate immutable-input
  preflight is `iteration-32-remote-vllm-preflight/preflight.json`. The endpoint's health and selected-model
  catalog probes were HTTP 200 both before and after. Contract SHA-256 remains
  `0961e7ad863db419c3f2e4ee4e35da6e3a0065418ec9f8c049dc32beae5b1083`; no gate value changed.
- Screens 2 and 4 passed their recorded v2 predicates (p95 2.035 s and 2.602 s; fairness skew 0 and 1;
  all unique-marker checks true; zero locally observable accelerator/OOM errors). Screen 8 failed genuine
  latency (p95 47.664 s > 10 s). Screen 1's recorded fairness failure is an evidence-writer race, not a
  product finding: it evaluated 59 queued / 58 started entries before the asynchronous writer flushed; the
  completed log has 61/61 and a direct post-writer re-score passes with no errors and zero contention.
- The selected four-session 600-second soak fails independently of that race: p95 84.378 s, three sessions
  retain queued canonical work, lifecycle skew reaches 11, and three stop requests return 429. Its raw stop
  outcome must be classified against the descriptor's 5-second drain contract; it is not evidence of a
  scheduler change request. The matrix therefore does not establish a sustained G4 bound.
- Overload observed retryable v2 429, peer acceptance, retry success, clean overload stops, and reconnect
  isolation evidence, but it fails integrity: the `payments` peer never produced its own required marker
  before reconnect or in rendered/canonical text. Thus it does not establish G5 across overload/reconnect.
  `verdict.json` correctly remains `qualifies_local_g4_g5_portions: false`.

## W2 writer/evaluator boundary prototype (iteration 33)

- `proto_writer_evaluator_boundary.py` exercised the production `_CanonicalEventLogWriter` and
  `_canonical_lifecycle_fairness` evaluator without a service or scheduler. In **3/3** trials, after writer
  activity had begun, an immediate read saw **0/48** complete fair-lifecycle records and failed closed; after
  the writer's existing `close()` barrier it saw **48/48** and passed at maximum skew **1**. Raw artifact:
  `evidence/phase1/w2-local-concurrency/iteration-33-writer-evaluator-boundary.json` (SHA-256
  `31fe21ec4c1eeab9711ccfc8d9a83ee6e7794f021c46464fcade73fe6934e975`).
- Verdict: a writer-owned drain barrier is required before evaluating lifecycle evidence. This is an
  observation-boundary finding only: it does not establish a scheduler defect, stop-drain result, G4, or G5;
  no gate value changed. Next W2 change, after Defect D, is the narrow barrier plus separate
  `not_applicable` fairness and stop-drain predicates.

## Run 32 audited — G4 not met, G5 close, two real defects (monitor, 2026-08-18 21:35)

Verdict is honest: `qualifies_local_g4_g5_portions: false`, `screening_passes: [2,4]`, `soak_passes: false`,
`overload_passes: false`.

**Correcting my 21:25 note:** the bound is **not** 4. Concurrency 4 passes the 120 s screen (p95 2.60 s) then
collapses over the 600 s soak — **p95 84.378 s** vs a 10 s gate (~32×), `stops_closed: False`, queued canonical
items outstanding for multiple sessions. **Lead with this: concurrency 4 is not sustainable; G4 not met.** A
two-minute screen alone would have shipped a bound the product cannot hold.

**Defect (separate):** `stops_closed: False` in the soak — sessions did not close cleanly after a sustained run.
Own predicate, own write-up; do not fold it into the latency story.

**G5 is closer than `overload_passes: false` implies.** Passing in overload: `retryable_v2_429_observed`,
`peer_accepted_while_saturated`, `refused_frame_retried_successfully`, `canonical_foreign_markers_absent`,
`reconnect_replayed_canonical_foreign_markers_absent`, `observer_reconnected`, both stops closed. **Only**
`rendered_markers_observed_before_reconnect: False` fails — while `canonical_own_marker_present: True`. Text
reached canonical and hadn't rendered before the harness reconnected: **likely a harness race**. Test it — wait
(bounded, with timeout) for the rendered marker before reconnecting. If it always succeeds, the predicate was
racy; if it times out with canonical present and rendered absent, that is a real render-path defect.
For the board: `retryable_v2_429_observed` + `peer_accepted_while_saturated` + `refused_frame_retried_successfully`
is the **first genuine evidence for issue #3's per-client 429 criterion**.

**Still not applied (from 21:25):** screen-1 fails only on the drain error inside `canonical_lifecycle_fairness`
while reporting `contended_pair_dispatch_observations: 0`. Fairness must be **not_applicable** at concurrency 1;
move the drain condition to its own `stop_drain_complete` predicate.

**Isolation held everywhere:** with the eight unique markers, every session in screen-1, the 4-session soak and
overload reports `canonical_foreign_markers_absent: True` **and** `rendered_foreign_markers_absent: True`,
including on reconnect replay. No cross-session leakage anywhere — meaningful only because the oracle was fixed first.

## Resolved iteration 34 — Defect D empty-text poller contract

The server deliberately emits `transcript=""` for silence spans; the client now accepts empty **string** text
only for canonical commits and provisional tails. The two red public-poller cases initially failed with
`Malformed MOSS canonical commit transcript.` and `Malformed MOSS provisional transcript.`; they now dispatch
their snapshot rounds without `onError`. Matching `null` cases still fail with the same field-specific errors.
`snapshot.session_id`, runtime-event `session_id`/`kind`, and numeric fields still use their original strict
validators. Frontend validation: focused poller **18/18**, full suite **126/126**, typecheck, and production
bundle rebuild passed.

`revised_transcript` remains intentionally optional. Server audit proves it cannot validly be `""`:
`LiveSession._revised_span` requires a nonempty label track and equal parsed-segment count, then returns
`render_segments(...)` only after at least one applied label change; that renderer emits one nonempty grammar
record per segment. Empty text has no segment/track and is refused, so there is no server path that publishes
an empty revision. No blanket parser relaxation was made.

## Defect B: echo cancellation EXCLUDED (monitor, 2026-08-18 21:40)
Operator ran Speakers and Headphones with identical poor mic transcription in the same sequence ⇒ echo
cancellation is not the cause. Strengthens the level/mixing diagnosis at `live_mixer.py:256` and the measured
15.377 dB disparity. Rejection of peer-RMS matching still stands; no hand-tuned constant. B still blocked on a
fixture with different speech per lane.

Transient "capture … expired" on stop = capture request deadline path in `captureClient.ts`; appeared and
resolved. Cosmetic ordering unless it recurs — do not spend an iteration on it.

## Run 32 findings split by provenance (monitor, 2026-08-18 21:45)

Iteration 33 proved a writer/evaluator race 3/3 (immediate read 0/48; flushed read 48/48, `passes: true`,
skew 1, `errors: []`). **Partly my fault** — my 21:15 steer moved the fsync off the dispatch path into a
background writer; correct for fidelity, but it needs a read barrier.

**SURVIVES (not from the event log):**
- `stops_closed = all(stop["status"] == 200 …)` (`run_cpu_hf_local_measurement.py:1071`) ⇒ soak
  `stops_closed: False` is a **real defect**.
- `maximum_session_p95_seconds` from latency samples ⇒ soak collapse **p95 2.60 s @120 s → 84.378 s @600 s**
  (~32×) is **real**. Headline stands: concurrency 4 not sustainable, **G4 not met**. screen-8 47.66 s real.
- `marker_checks` (text comparisons) clean everywhere.

**SUSPECT (event-log derived, no barrier):** every `'run ended with queued canonical items …'` error — including
the sole reason screen-1 failed — and all fairness verdicts / `contended_pair_dispatch_observations`.
`_CanonicalEventLogWriter.close()` exists (`production_route_server.py:185-190`, sentinel + `join()`) but the
runner never calls it before evaluating. **The fix is a barrier, not a redesign.**

**Order:** (1) **Defect D first** — P0, blocks every clean G3 artifact, independent of this. (2) Add the barrier:
close/join before reading, **fail closed** on barrier timeout, plus the regression test from your own probe.
(3) Re-evaluate — if run 32's lifecycle events are complete on disk (check `line_count` vs expected), re-score
fairness **without** re-running; if short, the data is gone. (4) Only then re-run the frozen matrix. No gate or
contract edits.

**Name the pattern in the write-up:** this is the **third** degenerate oracle here — repeated-marker oracle,
unscoped fairness counter, writer/evaluator race. All three produced confident numbers that meant nothing.

## W2 writer-owned lifecycle drain barrier (iteration 35)

- The local route's `_CanonicalEventLogWriter` now accepts an ordered, non-closing drain marker. It flushes and
  fsyncs all records preceding that marker, then acknowledges it; later phases continue using the same writer.
  The measurement runner requests that bounded boundary before every normal or overload lifecycle read and
  refuses partial evaluation when it does not receive a `200`/`drained: true` acknowledgement inside its existing
  stop deadline. No scheduler behavior, frozen gate value, or contract changed.
- Focused coverage is **5 passed**: it exercises the loopback drain route and proves the runner fails closed on
  a rejected barrier. The production writer/evaluator prototype ran **3/3**: each immediate read saw **0/48**
  records and failed closed, while each acknowledged drain exposed **48/48** complete records and passed the
  fairness evaluator (maximum skew 1). Raw artifact:
  `evidence/phase1/w2-local-concurrency/iteration-35-writer-evaluator-drain.json`, SHA-256
  `c1fa5697a7f5d36eece0fb568e7a6eae5bf75dfa830f1c206c1ad50209429bba`.
- This repairs only the observation boundary. Run-32's p95 and HTTP stop outcomes remain independently valid;
  lifecycle/fairness and queued-item results require the next evidence-only re-score before any classification.
