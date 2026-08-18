# context — afk5-phase1-completion

Living working memory. Update it every iteration so it matches reality. History goes in progress.txt.

## Verified state (2026-08-18, dev @ merge of y6 + y7)

- Baseline: pytest **2 failed / 1066 passed / 2 skipped / 396 subtests**; frontend **110/110**,
  typecheck clean. The 2 failures are permanent Phase 1 baselines (l15 pin, l2-stage0 untracked
  corpus). **Never "fix" them** — the l15 pin correctly refuses to run when the product tree moved.
- Gates certified: G1, G2, G7, G8, G10. G6 has its local real-browser bar met (y6: 19/19 assertions,
  all 19 falsified against corrupted observations).
- Job routes are guarded server-side and proven over real TLS. The frontend cannot yet send the
  bearer in file mode — that is W1.
- Export caveat lands in md, txt and json, only when a turn is non-final. 4 tests.
- **No provider manifest exists in this repo**, so `--live` cannot start locally. That is W0 and it
  blocks G3, G4 and G5 simultaneously.
- `scripts/g3-attended-session.sh` exists and generates TLS + a shared token, but will fail until W0
  supplies a manifest.
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

1. **W0** finalize a provider manifest for this host so `--live` starts. Everything else waits.
2. **W1** lift the capture bearer above `App` so file mode can send it (memory only).
3. **W2** G4/G5 certification — needs W0 and a reachable `MOSS_VLLM_BASE_URL`.
4. **W3** verify the operator's G3 artifacts once they appear.
5. **W4** reconcile the ledger to measured reality.

## Blockers

- `MOSS_VLLM_BASE_URL` — operator is publishing port 8000 on the tailnet. Until
  `curl -sSk "$MOSS_VLLM_BASE_URL/models"` returns 200, W2 cannot run and W0 cannot be fully proven.
  Record the blocker and move on; do not fabricate a model.
