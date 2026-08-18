# context — afk5-phase1-completion

Living working memory. Update it every iteration so it matches reality. History goes in progress.txt.

## Verified state (2026-08-18, dev @ merge of y6 + y7)

- G10's certified `dev` bar is **2 failed / 1066 passed / 2 skipped / 396 subtests**. Iteration 3
  preserved this worktree's raw, non-certifying result at
  `evidence/phase1/g10-ledger-reconciliation/iteration-3-root-pytest.txt`: **1 failed / 1065 passed /
  4 skipped / 488 subtests**. The valid local l2 corpus accounts for +92 subtests; two
  operator-owned real-corpus tests skip here. **Never "fix" either baseline guard or replace the
  certified bar with this worktree's denominator.** The current source frontend suite is **117/117** across
  16 files at `evidence/phase1/g9-ledger-reconciliation/iteration-13-silent-mic-source-tests.txt`.
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

1. **Defect A residual latch (P0)**: add the monitor-specified failing flat-ingress replay before changing
   the poller. A bounded no-progress watchdog must reset a stale snapshot cursor once when neither cursor
   moves, then observe the terminal snapshot. Retain the existing ingress-advance fast path.
2. **Defect B (P1)**: prototype and measure the two input lanes' real-fixture RMS and transcription effect
   before choosing any mixer normalization/AGC/offset policy. Pre-register the success measure; no
   hand-tuned gain constant.
3. **Defect C (P2)**: only after B establishes a measured disparity threshold, source the warning copy
   from the server and add the client gate.
4. **W2 vLLM-only measurement prerequisites**: iteration 16 compacted the committed CPU/HF diagnostic
   `run-state.json` from 59,992,997 to 288,007 bytes without raw PCM. Bring audited tunnel launcher
   `affeaea` from `dev`, then use only the preregistered tunnel-backed runner. The CPU/HF result remains
   diagnostic, not G4/G5 evidence.
5. **W3 (blocked externally)**: an operator must add the raw attended-session log before the charter
   frame/cadence/fetch/RMS validation can run.
6. **Issue #8 criterion 2 (blocked externally)**: needs the lifecycle vocabulary ruling; do not invent
   nonexistent `starting`/`recording`/`completed` values.

## Blockers

- ~~`MOSS_VLLM_BASE_URL` is unset~~ **SUPERSEDED 17:40: the endpoint is LIVE at
  `http://127.0.0.1:18000/v1` via `./scripts/moss-vllm-tunnel.sh`, monitor-verified including a real
  transcription. A local HF run may NOT establish any G4/G5 portion — the local runner is off limits by
  operator ruling. Run G4/G5 against the tunnel.** Still unobtainable and not to be fabricated: GPU
  OOM/errors, GPU memory/utilisation, vLLM active/queued counts (the tunnel carries inference, not host
  telemetry; the host stays read-only).
- The monitored tunnel endpoint remains live, but its launcher is absent from this worktree: `affeaea`
  added `scripts/moss-vllm-tunnel.sh` on `dev`, and `git merge-base --is-ancestor affeaea HEAD` returns
  false. Iteration 11 fails closed rather than silently selecting HF; W2 cannot be run from this checkout
  until the reviewed launcher is brought in.
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

## Priority order
1. Trim the already-committed 60 MB CPU/HF diagnostic artifact in a new commit, preserving predicate-bearing
   arrays and recording original `a28f57e5b5266c429bb1df106417ee6448fed58fb94180c207788e5b4d8986dd` / 59,992,997-byte provenance.
2. Bring the reviewed tunnel launcher into this branch, then run W2 against
   `http://127.0.0.1:18000/v1`.
3. W3 stays blocked until an operator adds a raw attended-session log.
4. Issue #8 remains blocked only on the criterion-2 lifecycle ruling.

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

## Defect A: fixed for mid-capture, RESIDUAL latch at stop (monitor, 2026-08-18 18:45)

`168db85` is a real root-cause fix — recovery keyed on an independent signal (cumulative
`v2_session.lanes[*].accepted_samples`), trigger `deferralIndex !== -1 || (!snapshot && ingressAdvanced)`,
defensive parse, and the test strengthened to four assertions carrying the operator's real numbers.
Frontend 16 files / **119 pass**.

**Residual, same shape, and it is the operator's Stop symptom:** recovery requires ingress to ADVANCE. After
capture stops, `accepted_samples` is flat → `ingressAdvanced` false; no `identity_finalized` → `deferralIndex
=== -1`; so no re-baseline at `:303`. Terminal detection at `:306` needs a **changed** snapshot the stale
cursor never produces, and `recoverOwnerTerminal` (`:139`) is reachable only from the 401/403 branch (`:325`).
A strand beginning at/after the last frame ⇒ "Finalizing…" forever.

**Fix:** bounded no-progress watchdog — N consecutive rounds with no movement in *either* cursor while not
known-terminal ⇒ re-baseline `snapshotVersion = 0` once, reset counter. Subsumes the heuristic, no new server
field. **Test with FLAT ingress** (constant `accepted_samples`, stale cursor `unchanged`, server terminal) and
assert `onTerminal` fires; it must fail before the watchdog exists — if it passes, my reading is wrong, record
that instead. Keep the ingress signal as the fast path; the watchdog is the floor.

### Resolved iteration 18 — terminal 409 envelope and rendering

All four former bare terminal-409 branches now return a `failure` envelope. When the runtime has a terminal
record, its exact `code`, `message`, and detail are reused; clean mono/v2 terminal states receive the stable
`live_session_terminal`/`v2_session_terminal` code. The capture client uses a nonempty server `detail` (or
the failure message) for every otherwise-unhandled 409, so it reports the server-authored line instead of
`frame POST failed: HTTP 409`. The route replay creates a real `canonical_decode_failed` failure from a
decoder seam and proves its OSError detail reaches the 409; the full live API suite and the 120-test frontend
suite pass. Evidence: `evidence/phase1/g3-attended/iteration-18-terminal-409-envelope.txt`.

Next: **Defect A residual latch**, then **B** (measure per-lane RMS first, no hand-tuned constant) → **C**.
