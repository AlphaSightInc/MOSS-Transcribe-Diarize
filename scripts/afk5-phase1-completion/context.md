# context — afk5-phase1-completion

Living working memory. Update it every iteration so it matches reality. History goes in progress.txt.

## Verified state (2026-08-18, dev @ merge of y6 + y7)

- Baseline: pytest **2 failed / 1066 passed / 2 skipped / 396 subtests**; frontend **113/113**,
  typecheck clean. The 2 failures are permanent Phase 1 baselines (l15 pin, l2-stage0 untracked
  corpus). **Never "fix" them** — the l15 pin correctly refuses to run when the product tree moved.
- Gates certified: G1, G2, G7, G8, G10. G6 has its local real-browser bar met (y6: 19/19 assertions,
  all 19 falsified against corrupted observations).
- Job routes are guarded server-side and proven over real TLS. W1 now keeps the bearer in `App`
  memory, passes it to both panels, and sends it on file create/poll/segments requests; it is not
  written to browser storage or a URL. Focused 11/11 and full frontend 113/113, typecheck, and
  production build passed.
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

1. **W0 (blocked)** finalize a local manifest and wire it into the G3 recipe when the operator
   provides the full provisional manifest and a reachable `MOSS_VLLM_BASE_URL`.
2. **W3 (waiting on operator)** inspect `evidence/phase1/g3-attended/` for a raw attended-session
   log; certify only if the charter's frame, cadence, fetch, and RMS checks are all present.
3. **W4** reconcile the ledger after the next measured gate result; include W1's 113/113 evidence
   but do not imply a real-model or attended-capture result.
4. **W2 (blocked)** G4/G5 certification — needs W0 and a reachable `MOSS_VLLM_BASE_URL`.

## Blockers

- `MOSS_VLLM_BASE_URL` is unset. Until `curl -sSk "$MOSS_VLLM_BASE_URL/models"` returns 200, W2
  cannot run and W0 cannot be proven. Do not fabricate a model.
- W0 additionally needs an operator-supplied full provisional manifest: the read-only descriptor
  supplies public geometry/provenance only, while finalization validates package and asset paths and
  hashes. Do not copy the remote `source_revision` into a local manifest.
