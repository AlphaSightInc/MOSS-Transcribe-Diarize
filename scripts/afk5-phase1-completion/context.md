# context — afk5-phase1-completion

Living working memory. Update it every iteration so it matches reality. History goes in progress.txt.

## Verified state (2026-08-18, dev @ merge of y6 + y7)

- G10's certified `dev` bar is **2 failed / 1066 passed / 2 skipped / 396 subtests**. Iteration 3
  preserved this worktree's raw, non-certifying result at
  `evidence/phase1/g10-ledger-reconciliation/iteration-3-root-pytest.txt`: **1 failed / 1065 passed /
  4 skipped / 488 subtests**. The valid local l2 corpus accounts for +92 subtests; two
  operator-owned real-corpus tests skip here. **Never "fix" either baseline guard or replace the
  certified bar with this worktree's denominator.** The source frontend suite is **115/115** across
  16 files at `evidence/phase1/g9-ledger-reconciliation/iteration-3-frontend-source-tests.txt`.
- Gates certified: G1, G2, G7, G8, G10. G6 has its local real-browser bar met (y6: 19/19 assertions,
  all 19 falsified against corrupted observations).
- Job routes are guarded server-side and proven over real TLS. W1 source now keeps the bearer in
  `App` memory, passes it to both panels, and sends it on file create/poll/segments requests; it
  is not written to browser storage or a URL. Focused 11/11 and full frontend 115/115, typecheck,
  and production build passed. **It is not yet product-landed:** the build changes tracked
  `ProjectResources/Frontend/{app.js,app.js.map}`, but this ticket's preflight forbids those paths;
  the generated bundle was reverted rather than bypass the guard.
- W5 source now names every browser download
  `transcript-<session_id>-<iso8601>.<ext>`: `TranscriptPane` reads the live `sessionId`, requires
  it before enabling export, and supplies one click-time `Date` to the serializer. Focused export
  and pane coverage is **8/8** and typecheck is clean. The contract is source-certified only: W1's
  served-bundle blocker also prevents this filename behavior from reaching the current browser. The
  re-runnable G9 audit pins the current served `app.js` by byte size and Git blob, then records both
  current source and legacy bundle behavior at
  `evidence/phase1/g9-ledger-reconciliation/iteration-5-served-bundle-audit.txt`.
- Export caveat lands in md, txt and json, only when a turn is non-final. 4 tests.
- **W0 local launch PASS:** the recovered real CPU bundle is materialized at the host-local live-data
  path; its manifest was re-finalized for `e1741f904fee942a5eef34e0d40a4d4f848b363d`. Its production
  preflight passes with `onnxruntime==1.23.2`, cached `webrtcvad-wheels==2.0.14`, and the real golden
  WAV. With the G1/G2-proven local HF snapshot, `scripts/g3-attended-session.sh` started TLS only on
  `127.0.0.1:7861`; local descriptor fetch and bearer-authorized session create/abort passed. Raw
  evidence: `evidence/phase1/w0-local-live/iteration-6-local-hf-launch.txt`. The helper uses vLLM
  only when a configured endpoint returns 200; otherwise it requires `MOSS_HF_MODEL` and records HF.
  **MONITOR 17:40 — that fallback is now FORBIDDEN and must be deleted; see the endpoint section below.**
  This is CPU/WebRTC launch evidence, not a G3 attended run or GPU G4/G5 evidence. Re-finalize before
  using a checkout whose source revision changes.
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

1. **W0 safety constraint** remove the G3 helper's forbidden HF fallback before any further G3/G4/G5
   run. It must hard-fail when the vLLM tunnel is absent or non-200, naming
   `./scripts/moss-vllm-tunnel.sh`; add focused coverage that no local-model path can be selected.
2. **W1/W5 release (now authorized)** first invert `verify_g9_served_bundle.py` so green means the
   bearer and filename contracts are present, then rebuild the tracked served bundle and validate the
   verifier against it. Keep the verifier and generated bundle in the same commit; do not weaken it to
   accept the stale bundle.
3. **W2 vLLM-only measurement** after the safety fix, make a newly preregistered tunnel-backed runner
   record pre/post endpoint probes, `/v1/audio/transcriptions` inference, and the mandatory transit/shared
   GPU limits. The CPU/HF contract and iteration-10 result cannot be reused as gate evidence.
4. **Issue #5 criterion 7 (operator ruled)** replace the current client developer string at silent-mic
   preflight with the exact server-authored remedy wording from `live_capture_status.py:41-44`, sourced
   once, and add a focused test.
5. **W3 (blocked externally)** an operator must add a raw attended-session log; iteration 7 confirms
   the directory contains only the fixture. Then validate the charter's frame, cadence, fetch, and RMS
   requirements.

## Blockers

- ~~`MOSS_VLLM_BASE_URL` is unset~~ **SUPERSEDED 17:40: the endpoint is LIVE at
  `http://127.0.0.1:18000/v1` via `./scripts/moss-vllm-tunnel.sh`, monitor-verified including a real
  transcription. A local HF run may NOT establish any G4/G5 portion — the local runner is off limits by
  operator ruling. Run G4/G5 against the tunnel.** Still unobtainable and not to be fabricated: GPU
  OOM/errors, GPU memory/utilisation, vLLM active/queued counts (the tunnel carries inference, not host
  telemetry; the host stays read-only).
- W1/W5's generated-bundle release is now authorized by the operator, but the mandatory order is
  verifier polarity first, then rebuild, then one commit. The current served bundle remains stale until
  the released-bundle verifier passes; never bypass `afk-guardrails` to mask that fact.
- Issue #5 criterion 7 is no longer a Lane-B decision: the operator selected the app-side preflight
  remedy. Keep its wording in one source (the existing `live_capture_status.py:41-44` sentence), do not
  create a session for a silent mic, and test the exact displayed wording.


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
- G9's audited proof is now refutable: its literal command and unedited output make 12 assertions against
  the HEAD-pinned 77,166-byte served bundle (blob `8121e270...f9c0d9c`). All pass, preserving the
  source-certified-only conclusion rather than treating source behavior as released browser behavior.

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

## `verify_g9_served_bundle.py` polarity flaw (monitor, 2026-08-18 16:55)

Re-ran it: 12/12 PASS, bundle pinned 77166 bytes / blob `8121e2703ce2cb7e6d5b4c805aaf9ad26f9c0d9c` matching
HEAD, every needle printed. Falsifiable — debt cleared. **But** two assertions expect ABSENT
(`bearerToken`, ``filename:`transcript-``), so **green means the defect still exists**. On release it goes FAIL
and the tempting repair is flipping expectations, which deletes the check. Invert now: assert the bundle
CONTAINS the new bearer and filename contracts → green = shipped, red = stale, and it becomes the W1/W5
release gate.

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
the selected 600-second soak, which the eventual verdict must state. Still open from 16:55: invert
`verify_g9_served_bundle.py` polarity.

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

## FIX BEFORE ANY GATE RUN: silent-substitution trap in the G3 helper

`scripts/g3-attended-session.sh:23-41` falls back to `MOSS_HF_MODEL` when the vLLM probe fails. A tunnel blip
would silently produce evidence with the now-forbidden local runner, announced by one easily-missed line.
**Remove the fallback:** if `MOSS_VLLM_BASE_URL` is unset or its probe is not 200, fail hard naming
`./scripts/moss-vllm-tunnel.sh`. No hf path at all.

## W2 — GO. Keep the frozen contract, widen the honesty.

Do not touch gate values or the matrix (`run_started` still false; the contract is good). Add to
`does_not_establish` and state in the verdict: latency includes **SSH tunnel + tailnet transit**; the GPU is
**shared with mineru-api at 0.5 utilisation, ~800 MiB free**, so this is not an isolated-GPU bound; the decode
path is `/v1/audio/transcriptions`. Honest scope, and better evidence than a CPU number.

**Probe the endpoint before AND after the run and record both** — the tunnel is a local process that can die,
and a mid-run death otherwise reads as a slow model. A run whose closing probe fails is not a passing run.

For #1 criterion 9: the tunnel carries inference, **not host telemetry**. GPU memory/utilisation remain
unobtainable; the host stays read-only. Do not claim them.

## Issue #5 criterion 7 — OPERATOR HAS RULED. Implement it.

Ship the remedy message **in the app, at preflight, when a silent microphone is detected**. Rationale to
preserve: the app already authors this moment badly, surfacing the developer string `both capture lanes must
have non-zero signal before session creation` (`captureClient.ts:491-493`), so this replaces bad client copy
with good client copy rather than adding a new client-authored-copy violation. No new endpoint; my option (a)
is dropped. Keep the **exact** wording from `live_capture_status.py:41-44`, sourced from one place rather than
forked, and add a test asserting it appears at preflight on a silent mic. Then #5 is closeable.

## Bundle release — RULED. The order is mandatory.

Charter T-09 already designs for a committed bundle ("the built bundle is committed, so the deploy host needs
no Node toolchain"), so this is the intended workflow, not an exceptional release act.
1. **Invert `verify_g9_served_bundle.py` first** — assert the new bearer and filename contracts are PRESENT,
   so green = shipped, red = stale.
2. Rebuild: `npm --prefix frontend run build`.
3. Commit the inverted verifier and the rebuilt bundle **together**, so the verifier gates the artifact.

**Do not flip expectations to make a stale bundle pass.**
