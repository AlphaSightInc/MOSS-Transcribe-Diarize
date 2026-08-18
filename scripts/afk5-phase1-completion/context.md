# context — afk5-phase1-completion

Living working memory. Update it every iteration so it matches reality. History goes in progress.txt.

## Verified state (2026-08-18, dev @ merge of y6 + y7)

- Latest root-suite probe (iteration 2): pytest **1 failed / 1065 passed / 4 skipped / 488
  subtests**; the sole failure is the permanent l15 product-tree pin. This does **not** reproduce
  the PRD-protected **2 failed / 1066 passed / 396 subtests** baseline: the environment-sensitive
  l2-stage0 case passed and the denominator changed. **Never "fix" either baseline guard**; W4
  must reconcile the changed result before G10 can be refreshed. Frontend remains **113/113** in
  prior full evidence, with typecheck clean.
- Gates certified: G1, G2, G7, G8, G10. G6 has its local real-browser bar met (y6: 19/19 assertions,
  all 19 falsified against corrupted observations).
- Job routes are guarded server-side and proven over real TLS. W1 source now keeps the bearer in
  `App` memory, passes it to both panels, and sends it on file create/poll/segments requests; it
  is not written to browser storage or a URL. Focused 11/11 and full frontend 113/113, typecheck,
  and production build passed. **It is not yet product-landed:** the build changes tracked
  `ProjectResources/Frontend/{app.js,app.js.map}`, but this ticket's preflight forbids those paths;
  the generated bundle was reverted rather than bypass the guard.
- W5 source now names every browser download
  `transcript-<session_id>-<iso8601>.<ext>`: `TranscriptPane` reads the live `sessionId`, requires
  it before enabling export, and supplies one click-time `Date` to the serializer. Focused export
  and pane coverage is **8/8** and typecheck is clean. The contract is source-certified only: W1's
  served-bundle blocker also prevents this filename behavior from reaching the current browser.
- Export caveat lands in md, txt and json, only when a turn is non-final. 4 tests.
- **No provider manifest exists in this repo**, so `--live` cannot start locally. W0 blocks G3, G4
  and G5 simultaneously. The local environment also has no `MOSS_VLLM_BASE_URL`; the read-only
  deployed descriptor returned 200 but lacks the full provisional manifest's asset/package records,
  so it cannot be safely synthesized or copied into this checkout.
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

1. **W4 — UNBLOCKED.** Reconcile `docs/phase1-gate-status.md` with iteration 2's two measured facts:
   G9 now has source-tested export naming and bearer propagation but neither is in the served bundle;
   G10's latest root suite is `1 failed / 1065 passed / 4 skipped / 488 subtests`, not its protected
   denominator. Cite the focused source evidence and state exactly what cannot be certified.
2. **W1 (blocked)** obtain ownership or a permitted release path for the tracked served bundle, then
   rebuild it from the already-tested source. Do not bypass `afk-guardrails`.
3. **W0 (blocked)** finalize a local manifest and wire it into the G3 recipe when the operator
   provides the full provisional manifest and a reachable `MOSS_VLLM_BASE_URL`.
4. **W3 (waiting on operator)** inspect `evidence/phase1/g3-attended/` for a raw attended-session
   log; certify only if the charter's frame, cadence, fetch, and RMS checks are all present.
5. **W2 (blocked)** G4/G5 certification — needs W0 and a reachable `MOSS_VLLM_BASE_URL`.

## Blockers

- `MOSS_VLLM_BASE_URL` is unset. Until `curl -sSk "$MOSS_VLLM_BASE_URL/models"` returns 200, W2
  cannot run and W0 cannot be proven. Do not fabricate a model.
- W0 additionally needs an operator-supplied full provisional manifest: the read-only descriptor
  supplies public geometry/provenance only, while finalization validates package and asset paths and
  hashes. Do not copy the remote `source_revision` into a local manifest.
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
