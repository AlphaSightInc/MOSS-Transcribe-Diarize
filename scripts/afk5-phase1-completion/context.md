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
  This is CPU/WebRTC launch evidence, not a G3 attended run or GPU G4/G5 evidence. Re-finalize before
  using a checkout whose source revision changes.
- Two-speaker fixture ready: `evidence/phase1/g3-attended/two-speaker-fixture-90s.wav`
  (90 s, mono, 16 kHz, RMS 1031).
- **W3 remains operator-blocked:** iteration 7's reproducible inventory at
  `evidence/phase1/g3-attended/iteration-7-operator-evidence-inventory.txt` found only that
  fixture and no raw attended-session log. A fixture cannot establish the charter §7
  fresh-gesture two-lane display-capture bar.
- **W2 CPU/HF-local measurement is re-frozen, not run:**
  `cpu_hf_local_preregistration.json` SHA-256 is
  `955a2883ada6cef99be007d1eb3c9838d6be9e227dc1408e06b6f8617fdb9d6c`. It records 120-second
  screens at 1/2/4/8 sessions and one 600-second largest-passing soak, using real decoder/speech,
  descriptor-derived geometry, p95 `<=10.0 s`, local RSS-growth `<=4 GiB`, zero OOM, skew `<=1`,
  retryable session-local v2 429, overload marker isolation, and observer reconnect. Iteration 9's
  harness writes frame/observer/RSS arrays and canonical dispatch events incrementally at
  `run_cpu_hf_local_measurement.py`; input preflight and its asynchronous event-writer smoke passed at
  `evidence/phase1/w2-local-concurrency/iteration-9-runner-and-refreeze.txt`. The result must use
  **CPU HF local decode, not the deployed GPU bound** and cannot claim deployed GPU p95, GPU OOM,
  GPU memory/utilisation, vLLM active/queued counts, or deployed real-time factor.

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

1. **W2 (runner and preflight ready; not measured)** run the hash-pinned local CPU/HF
   deployed-geometry measurement: screens 1/2/4/8, then soak its largest passing bound and retain
   raw state. It can establish local G4/G5 portions only; deployed p95, GPU, vLLM, and deployed-RTF
   figures remain external.
2. **W1 (blocked externally)** obtain ownership or a permitted release path for the tracked served
   bundle, then rebuild it from the already-tested source. Do not bypass `afk-guardrails`.
3. **W3 (blocked externally)** an operator must add a raw attended-session log; iteration 7 confirms
   the directory contains only the fixture. Then validate the charter's frame, cadence, fetch, and RMS
   requirements.

## Blockers

- `MOSS_VLLM_BASE_URL` is unset. A completed local HF run can establish only CPU-local G4/G5 portions
  at matching geometry; it cannot establish deployed p95 lag, GPU OOM/errors, GPU memory/utilisation,
  vLLM active/queued counts, or deployed real-time factor. Do not fabricate them.
- `scripts/afk-guardrails/preflight.py afk5-phase1-completion` rejects changes to the tracked served
  bundle under `ProjectResources/Frontend/`. W1 needs an operator-granted ownership change or a
  permitted release owner; source tests alone do not update the browser the Python service serves,
  including W5's export filenames.
- **Issue #5 criterion 7 is a Lane-B contract question — do NOT build it.** The silent-mic-at-preflight
  remedy line is unreachable by construction: the copy exists (`live_capture_status.py:41-44`) but
  rides the authenticated heartbeat, and `captureClient.ts:491-493` refuses `createSession()` before
  a session can exist, per charter §4. `browser_microphone_silent` is a non-terminal degraded code,
  not one of the three `PreSessionCaptureFailure` codes (`captureClient.ts:116-122`). The monitor has
  escalated it on issue #5 with two options; the operator rules. Do not invent a fourth pre-session
  code with client-authored copy (violates criterion 3 / C11) and do not create a session on a silent
  mic (violates charter §4).


## W0 evidence and limits

- The real assets' hashes are `5b734353...330262a8` (ONNX) and `d101dd44...ac0e60aa` (golden WAV),
  matching `evidence/phase1/t1/iteration-10-real-model-browser.json`. They were not sourced from the
  fabricated test fixture.
- The finalized manifest's golden check passes through the production `LiveProviderBundleConfig`
  readers, with zero failures and manifest hash `84600e8...0599c178`; raw command and output are in
  `evidence/phase1/w0-local-live/iteration-4-provider-preflight.txt`.
- Iteration 6 closed W0 with a local HF service, descriptor fetch, and authenticated session lifecycle.
  The absent vLLM endpoint now blocks only G4/G5's GPU evidence.
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
