# Retained-resume fix verification result

**PASS (current executor context).** No decoder, provider, external-network, or
tunnel calls were made. A separate fresh-context agent was not launched.

- RED receipt before production edits: `8 failed / 8` with `--runxfail`; normal
  run `8 xfailed / 0 failed`.
- Lead-review RED receipt: `6 failed / 2 passed` with `--runxfail`; normal run
  `2 passed / 6 xfailed`.
- Lead-review final controls: `8 passed`; retained-resume regression group:
  `49 passed`.
- Focused final controls: `14 passed`.
- Focused lifecycle regression gate: `67 passed`.
- Full backend: `2221 passed / 0 failed / 5 skipped / 2 expected xfailed / 37 subtests`.
- Frontend: `312/312`; TypeScript clean.
- `_assert_no_active_meetings`: AST-identical to `0de56e1a`.
- Product scope: only `phase2.py`, `phase2_file.py`, and
  `windowed_transcription.py`; secret scan empty.
- Mix-bound end-to-end result: crash after windows 0–1; restart dispatched
  exactly windows 2–3; final transcript equaled uninterrupted windows 0–3.

## Lead fresh-context verification (2026-09-21T22:34:00Z)

**FAIL.** Checks 1 and 3–8 pass. Check 2 fails two literal requirements. No
product or test repair was made. Decoder / provider / external-network / tunnel
calls: **0 / 0 / 0 / 0**.

- **Check 1 — PASS (scope).** Exact clean input was
  `round4/fix-i3i4@78b49eb3940f73891d483025ee97a337a427126b`, base
  `85aec9787b817fbd413c623fc550a6395a91591b`. Product diff is exactly
  `phase2.py` (+10/-0), `phase2_file.py` (+309/-67), and
  `windowed_transcription.py` (+17/-6). `_assert_no_active_meetings`, `accept`,
  `accept_url`, and `_retain_new_directory` are AST-identical to the base. No
  existing top-level constant changed; new internal constants are validation
  concurrency `4`, attempts `3`, exponential-backoff base `0.5 s` (sleeps
  `0.5 s`, `1.0 s`). No added `xfail`/`skip` marker under `tests/`.
- **Check 2 — FAIL (violating-control custody and base RED).** Current HEAD:
  all named F1/F2, T1–T4, S1/S3, and R1×5 controls pass, **13/13**. AST
  comparison with decorators removed: F1/F2, S3, and R1×5 are unchanged;
  Claude T1–T4 and S1 are changed beyond marker removal. Original frozen
  controls replayed on isolated `85aec978` with `--runxfail`: **11 failed,
  2 passed**. F1/F2, T1–T4, S1/S3, and R1 empty-multi/mix-bound/input-bound
  failed. R1 single-window unbound and digital-silence controls passed, so the
  requested 13/13 RED on `85aec978` is false. This agrees with the brief: R1
  was introduced by `9de2d9fc`, while those two paths were correct at the base.
- **Check 3 — PASS (fixture versus production).** Production
  `_transcribe_from_one_mix` with real `WindowedRunner`/`_CheckpointStore`
  crashed after committed windows 0–1. On-disk manifest and retained
  `transcription-mix.wav` SHA-256 both equal
  `b078637aee75bc5b8bf9501d36a6350323be93a8009a3b75b83e580b9f9923e4`.
  `n=4`, `k=2`; real lifespan restart decoded exactly `[2, 3]` = `n-k=2`,
  completed, matched uninterrupted transcript, then removed the owner dir.
- **Check 4 — PASS (R1).** Five production-path controls prove: unbound
  single-window restart prepares/decodes/publishes the mix and equals fresh;
  digital silence makes zero decoder calls; empty multi-window equals fresh;
  mix-bound skips prepare, decodes/publishes retained mix; input-bound skips
  prepare, decodes retained input, and leaves audio unavailable.
- **Check 5 — PASS (validation).** Before/after recursive listings and bytes
  were identical for empty (`2/2` entries), missing (`1/1`), partial (`5/5`),
  and valid (`8/8`) checkpoints. Injected `OSError` returned `error`, not
  `refused`. Real-lifespan retry trace was attempts 1/2/3 with sleeps
  `0.5/1.0`, then audio reconciliation, durable `failed/resume_failed` with
  reason `Retained File restart could not finish.`, then directory removal.
- **Check 6 — PASS (reservations/isolation).** During held validation,
  operator interrupt and account revoke both returned true, showed
  `validating`, settled once, kept the directory until the validation thread
  returned, then removed it. Six-owner probe measured max validation
  concurrency exactly `4`; stalled owner 1 stayed `validating` while owners
  2–6 all resumed. Owner 1's two failed durable outcome writes did not prevent
  owner 2 from resuming. A forced reclaim request left a reserved owner dir
  intact; lifespan additionally filters claimed owners before the post-fallback
  sweep (`phase2.py:2090-2099`).
- **Check 7 — PASS (full gates).** Prescribed runtime and real SQLite:
  **2,221 passed / 0 failed / 5 skipped / exactly 2 xfailed / 37 subtests** in
  214.00 s. Frontend **312/312**. `tsc --noEmit` clean.
- **Check 8 — PASS (secrets).** Repo-wide key-shaped `git grep -nE` returned
  no output.
