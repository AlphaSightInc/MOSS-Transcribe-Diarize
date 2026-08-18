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
  committed served-bundle proof records both current source and legacy bundle behavior.
- Export caveat lands in md, txt and json, only when a turn is non-final. 4 tests.
- **No provider manifest is committed in this repo**, but a hash-verified, host-matching CPU provider
  bundle is recovered locally (details below). W0 can now materialize stable assets and re-finalize a
  local manifest; it must use this checkout's `HEAD`, never the deployed host revision. The local
  environment still has no `MOSS_VLLM_BASE_URL`, so G4/G5's GPU-bound evidence remains blocked.
- `scripts/g3-attended-session.sh` exists and generates TLS + a shared token, but needs both a
  finalized local manifest passed to `--live-provider-manifest` and a reachable model endpoint.
- Two-speaker fixture ready: `evidence/phase1/g3-attended/two-speaker-fixture-90s.wav`
  (90 s, mono, 16 kHz, RMS 1031).

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

1. **W0 — UNBLOCKED.** Materialize the recovered real CPU assets to a durable repo-approved path,
   re-finalize the manifest for this `HEAD`, and falsify it against the recorded golden output before
   attempting the local-live recipe. Do not use the fabricated unit-test fixture.
2. **W1 (blocked)** obtain ownership or a permitted release path for the tracked served bundle, then
   rebuild it from the already-tested source. Do not bypass `afk-guardrails`.
3. **W3 (waiting on operator)** inspect `evidence/phase1/g3-attended/` for a raw attended-session
   log; certify only if the charter's frame, cadence, fetch, and RMS checks are all present.
4. **W2 (blocked)** G4/G5 certification — needs W0 and a reachable `MOSS_VLLM_BASE_URL`.

## Blockers

- `MOSS_VLLM_BASE_URL` is unset. Until `curl -sSk "$MOSS_VLLM_BASE_URL/models"` returns 200, G4/G5
  cannot run against the ticket-3 GPU bar. Do not fabricate a model. The recovered CPU bundle may
  prove local-live behavior but cannot establish GPU latency, GPU memory, or the deployed bound.
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


## W0 IS UNBLOCKED — monitor recovered the real provider bundle (2026-08-18 16:24)

The claim "no manifest exists" is true of the repo and false of this machine. Verified by shasum
against `evidence/phase1/t1/iteration-10-real-model-browser.json`:

```
scratchpad/w0-recovered/        (copied from /Users/gao/.Trash/moss-t1-iteration10.cBpN4M/, Trash is volatile)
  voxceleb_resnet152_LM.onnx   sha256 5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8
                               == artifact provider.identity_asset_sha256   MATCH
  golden.wav                   sha256 d101dd44a5976c466d254df218f4e28b60091aba00b1ce2e9110a677ac0e60aa
                               == artifact provider.golden_input_sha256     MATCH
  local-manifest-arm64.json    finalized, provider_name moss-rtx-webrtc-wespeaker, real bounds
```
Full path: `/private/tmp/claude-501/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/87bdb628-7234-4c4a-b2e7-6da5d8241d82/scratchpad/w0-recovered/`
Also reproducible from `~/.cache/huggingface/hub/models--Wespeaker--wespeaker-voxceleb-resnet152-LM`.

**Recipe:** re-point `assets[0].path` and `golden.input.path` (they reference the vanished
`/tmp/moss-t1-iteration10.cBpN4M/`), then `ops/finalize-live-provider-manifest.py --source-revision
$(git rev-parse HEAD)` with the arg list proven in
`evidence/phase1/t4/iteration-06-provider-manifest-finalization.txt` (`--hard-cap-samples 40000
--max-retained-samples 960000 --frame-samples 8000 --min-match-score 0.35 --min-match-margin 0.1
--album-admission-seconds 2.0 --birth-min-seconds 1.0`). Charter §8: re-finalize for this repo HEAD;
the recovered manifest's `source_revision a6b67870...` is a local revision, not the deployed
`fb83ba5e...`. **Falsifiable acceptance check:** the bundle must reproduce
`golden.expected_output_sha256 c0c36de90d8e8ea5176e905a5d16e8a1c465bfba84bf0c4ee098380c0bfe9311`.

**Never** source a manifest from `tests/test_live_manifest_finalizer.py::_write_provisional` — its
`_provisional_payload()` fabricates `sha256: "a"*64` / `"c"*64` / `"d"*64`. That is the stub evidence
prd.md forbids.

**Scope limit to state in any certification:** this bundle is cpu / `webrtc-cpu`. It unblocks a local
live service, the G3 recipe, and the model half of W2. A CPU G4 p95 is a CPU bound, not the deployed
ticket-3 bound, and produces no GPU memory/utilisation. Port 8000 is still needed for a GPU number.
