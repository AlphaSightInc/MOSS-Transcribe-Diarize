# Handoff — walk the operator through user testing of the `auto-mvp-0911` candidate

Written 2026-09-12 21:15 EDT by the orchestrating session (Claude, tmux `MOSS:1.1`). The next agent's job is
**not** engineering: implementation is complete. It is to (1) read round 17's result, (2) guide the operator,
step by step and one step at a time, through the attended preadmission and the demo rehearsal, and (3) triage
anything that goes wrong without weakening a gate or changing policy.

## Where things stand (verify, do not assume)

- **Branch / deliverable:** `private/auto-mvp-0911` (never `dev`/`main`, never force-push). Head at writing:
  `5d21f59c` (staging fix) on top of qualified candidate **`e47ab229`**; differences since `e47ab229` are
  tests, docs and the staging script only. Draft PR (unmerged, on purpose):
  https://github.com/aiSight-us/MOSS-Transcribe-Diarize/pull/32 — do not merge; the operator decides on a
  history squash first (see the PR's "History note").
- **Round 16 (`e47ab229`) passed every product predicate**: deterministic 18/18, deployed 18/19,
  pre-admission 16/17, the single rejection being `quality_corpus` with exactly the three pre-approved
  exceptions (DER, reference-speech DER, matched-speaker accuracy — all inside the 5 % band; everything else
  strict). 48/48 sessions finalized, both load gates passed, backpressure proven. Full record and every
  earlier round: issue #10 (https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/10), latest
  comments first.
- **Round 17 is running** (started ~21:10 EDT, ~2 h 15 min) purely to produce a clean cutover record: the host
  profile's `cutover_rehearsal.candidate_manifest` still pointed at a deleted runtime and the rehearsal check
  failed the record even though all product predicates passed; `5d21f59c` makes staging repoint every manifest
  field and refuse stale ones. **First action for the next agent:** read `tmux capture-pane -t MOSS:2.1 -p -S -400`
  for the "Round 17" report (or `/tmp/moss-round17-stage/result/report.md` on this MacStudio). Expected:
  restored, no rehearsal error, only the three quality exceptions → "handoff condition met". If anything else
  fails, follow the triage rules below before guiding the operator.
- **Host (Alienware, WSL Ubuntu):** healthy. Phase-1 serving at https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861;
  vLLM PID 324, zero restarts; vhdx moved to `D:\wsl\Ubuntu` (C: ≈613 GB free); durable `/etc/hosts` prerequisite
  unit installed; pre-flight disk guards active; both MinerU scheduled tasks enabled.

## GitHub identity (confirmed by the operator 21:35 EDT 2026-09-12)

The deliverable repo is **https://github.com/aiSight-us/MOSS-Transcribe-Diarize** (private; branches:
https://github.com/aiSight-us/MOSS-Transcribe-Diarize/branches/active), remote name `private`. It is reachable only as the
GitHub account **`yugao-aisight`**, not `AlphaSightInc` (a second login on this Mac that owns the public fork `origin`).
The git credential helper is `gh`, so whichever account is *active* in `gh` is what `git push` uses. If a push or `gh api`
returns 404 "Repository not found", run `gh auth switch --user yugao-aisight` and retry — that is exactly what happened at
21:20 EDT (active account had flipped to AlphaSightInc; switched back, push succeeded). **Never** push to `origin`
(`AlphaSightInc/MOSS-Transcribe-Diarize`, a public fork). The host holds the staged round-17 runtime, so preadmission does
not depend on GitHub anyway.

## Operator documents (all on the branch — read them before guiding)

| doc | use it for |
|---|---|
| `docs/handoffs/auto-mvp-0911-handback.md` | the master handback: gate state (§2), what changed, verified checklist, latency, known limitations, content-boundary/history note |
| `docs/handoffs/g7-preadmission-runbook.md` | the attended preadmission procedure, host-verified: display options (WSLg is **disabled** on the host), exact CLI, journal phases, the four Enter prompts, rollback, host disk hygiene, the two MinerU restart tasks |
| `docs/handoffs/demo-script.md` | the 10-minute presenter flow with exact UI labels, timings, recoveries, "do not do" list |
| `docs/handoffs/e2e-smoke-for-operator.md` + `tests/e2e/verify_workspace.py` | post-preadmission smoke test against the production origin (`--base https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861 --rows ...`) |
| `scripts/demo-precheck.sh <FULL_SHA>` | go/no-go before a demo (TLS, candidate SHA, relay models, both LLM upstreams) |
| `ops/windows/wsl-maintenance.ps1` + `ops/windows/README.md` | only if WSL maintenance is ever needed (dry-run validated on Windows; disables both MinerU tasks, re-enables in `finally`) |
| `docs/evidence/round-reports/` | sanitized copies of the round reports cited above |

## The walkthrough to run with the operator (one step at a time; confirm each before the next)

1. **Confirm round 17** (above). Tell the operator the qualified SHA to stage (`e47ab229` unless round 17
   qualified a later head — use the SHA in round 17's report).
2. **Display for the canary.** The attended G7 canary needs a headed Chrome on the host. WSLg is disabled
   (`guiApplications=false`). Options and consequences are in the runbook: an X server on Windows (none was found
   installed) or enabling WSLg followed by `wsl --shutdown` — which restarts vLLM/Phase-1 and **must happen before
   an attempt, never during**, with both MinerU tasks disabled for the shutdown (the maintenance script does this).
3. **Attended preadmission** from an interactive WSL terminal on the Alienware (not detached): the runbook's
   exact `mtd-phase2-cutover run --profile … --attempt … --terminal preadmission` command; ~60–75 min of
   re-qualification, then Chrome opens; share a **tab with audio**, enable the microphone, speak until both
   lane meters move and two speakers appear, Enter; then **entire screen**; four Enter confirmations total. On
   PASS the candidate keeps serving on :7861 (that is the demo state). Any failure auto-restores Phase-1.
4. **Smoke + pre-check:** `scripts/demo-precheck.sh <FULL_SHA>` from the MacBook; then the operator smoke rows
   per `e2e-smoke-for-operator.md`.
5. **Demo prep:** open the workspace from the MacBook, enrol the presenter in the private voice bank (≥3 s of
   speech, name the speaker); Browser AI settings should show the server relay with
   `qwen/qwen3.6-35b-a3b · macstudio` default and `qwen38-27b-mtp · rtx4090` fallback — both servers must be up
   (`http://127.0.0.1:1234` on MacStudio, `http://ga0-rtx4090.tailnet.aisight.us:1235`).
6. **Rehearse the demo script** once end to end.

## Triage rules if something fails (inherited mandate — do not cross these)

- Never edit `QUALITY_BOUNDS`, the identity policy (`birth_min_seconds 1.0`, `album_admission_seconds 2.0`,
  `min_match_score 0.35`, `min_match_margin 0.1`), or an evaluator expectation to make a gate pass. The only two
  evaluator changes ever made are documented in `docs/audits/overload-duration-expectation-20260912.md`.
- Quality metrics within 5 % relative of a bound are pre-approved exceptions; anything worse blocks preadmission
  and goes to the operator as a decision.
- `moss-vllm` must not be restarted during an attempt; MinerU must not be changed (report only).
- Codex agents are standing by in tmux `MOSS:1.2`, `MOSS:2.1` (host owner — the only pane with the host SSH/WSL
  wrapper `/tmp/moss-8720503-stage/remote.py`), `MOSS:2.2`. They accept plain-English task messages via
  `tmux send-keys`. Build candidates only from a fresh clone of a pushed SHA, never from a shared worktree.
- Every host round so far has been `--terminal restored`; preadmission is attended and cannot be run detached.

## Known limitations to say out loud to the operator

Full list with numbers: handback "Known limitations". Headlines: new (un-enrolled) voices get a label only after
~2 s of contiguous speech and short fragments stay unlabeled by design; eight concurrent sessions degrade to ~20 s
latency without failing (four is the supported capacity); MinerU shares the GPU with vLLM (~13.7/16.4 GB
resident) — pause it during demos if latency matters; the branch history still contains 402 removed evidence
files (squash before merging if required).

## Memory for the next session

Read `~/.claude/projects/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/memory/auto-mvp-0911-progress.md`
(round-by-round state, last lines are current) and `auto-mvp-0911-mandate.md` (authorities and decisions).

## Suggested skills

- `tmux-peer` — to read the codex panes' reports (`MOSS:2.1` for round 17 first).
- `diagnose` — only if the attended run or a smoke row fails and the cause is not in the retained evidence.
- `claude-in-chrome` — optional, if the operator wants the smoke rows driven from MacStudio's Chrome instead of Playwright.
