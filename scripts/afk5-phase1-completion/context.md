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

1. **W2 (partly actionable)** pre-register CPU/HF-local thresholds and run the local ≥10-minute
   deployed-geometry sustain/reconnect measurement. It can establish G5 and all non-GPU portions of G4;
   deployed p95 lag and GPU memory/utilisation still need the reachable GPU endpoint.
2. **W1 (blocked externally)** obtain ownership or a permitted release path for the tracked served
   bundle, then rebuild it from the already-tested source. Do not bypass `afk-guardrails`.
3. **W3 (blocked externally)** an operator must add a raw attended-session log; iteration 7 confirms
   the directory contains only the fixture. Then validate the charter's frame, cadence, fetch, and RMS
   requirements.

## Blockers

- `MOSS_VLLM_BASE_URL` is unset. The local HF path can now measure G5 and the non-GPU G4 behaviours at
  the matching deployed geometry, but it cannot establish deployed p95 lag, GPU memory, or GPU
  utilisation. Do not fabricate those GPU-only figures.
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
