# context — afk5-phase1-completion

Living working memory. Update it every iteration so it matches reality. History goes in progress.txt.

## Verified state (2026-08-18, dev @ merge of y6 + y7)

- G10's certified `dev` bar is **2 failed / 1066 passed / 2 skipped / 396 subtests**. Iteration 3
  preserved this worktree's raw, non-certifying result at
  `evidence/phase1/g10-ledger-reconciliation/iteration-3-root-pytest.txt`: **1 failed / 1065 passed /
  4 skipped / 488 subtests**. The valid local l2 corpus accounts for +92 subtests; two
  operator-owned real-corpus tests skip here. **Never "fix" either baseline guard or replace the
  certified bar with this worktree's denominator.** The current source frontend suite is **122/122** across
  16 files at `evidence/phase1/g3-attended/iteration-19-poller-flat-cursor-watchdog.txt`.
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

1. **Defect B replication (operator input, P1)**: iteration 20 measured a 15.377 dB RMS disparity but
   rejected peer-RMS matching (WER +3.468 pp, six more missing words). The sole aligned capture has the
   same lexical playback in both lanes, so it cannot set a general mixer policy or a warning threshold.
   Need multiple synchronized recordings with distinct audited per-lane references before re-testing any
   normalisation/AGC/offset proposal.
2. **Defect C (P2, blocked on B replication)**: do not source warning copy or choose a threshold from the
   one same-playback fixture.
3. **W2 integrity-oracle repair (P1):** iteration 28 repaired the fairness evidence rule; do not touch the
   scheduler unless a v2 lifecycle run measures a real violation. Before re-running, make every normal and
   overload session marker unique, reject non-unique-marker isolation claims, and evaluate text isolation plus
   observer reconnect in overload. Keep all gate values and the 1/2/4/8 + selected-600s matrix unchanged.
   The CPU/HF result remains diagnostic, not G4/G5 evidence.
4. **W3 (blocked externally)**: an operator must add the raw attended-session log before the charter
   frame/cadence/fetch/RMS validation can run.
5. **W4 ledger reconciliation (after W2 repair/replay)**: `docs/phase1-gate-status.md` still says no
   reachable vLLM endpoint; reconcile it only with a valid W2 replay and its explicit limits, never with the
   current unsound G5 oracle.
6. **Issue #8 criterion 2 (blocked externally)**: needs the lifecycle vocabulary ruling; do not invent
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
  selected 600-second one-session bound. Iteration 28 corrected the fairness observer: the old skew cannot
  establish a scheduler failure, and the next run must use v2 lifecycle records plus unique markers and an
  overload isolation/reconnect evaluator.
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
1. Run the preregistered W2 matrix using the live-preflighted remote-vLLM runner from a fresh output directory;
   do not alter frozen gates or use the CPU/HF runner as G4/G5 evidence.
2. Preserve its after-run endpoint probe and all non-GPU limits when evaluating the raw matrix.
3. W3 stays blocked until an operator adds a raw attended-session log; Issue #8 remains blocked on the
   criterion-2 lifecycle ruling; Defect B needs new audited recordings before Defect C.

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
