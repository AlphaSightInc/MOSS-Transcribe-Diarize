# Handoff — walk the operator through user testing of the `auto-mvp-0911` candidate

Written 2026-09-12 21:15 EDT by the orchestrating session (Claude, tmux `MOSS:1.1`). The next agent's job is
**not** engineering: implementation is complete. It is to (1) read round 17's result, (2) guide the operator,
step by step and one step at a time, through the attended preadmission and the demo rehearsal, and (3) triage
anything that goes wrong without weakening a gate or changing policy.

## Where things stand (verify, do not assume)

- **Branch / deliverable:** `private/auto-mvp-0911` (never `dev`/`main`, never force-push). **Attend against
  `b9aedebd6de27e289530856c14af49c9b160467f`**, staged inert on the host and independently verified
  (manifest SHA matches, all three `candidate_manifest` refs repoint, profiles `0600`, vLLM untouched at
  PID 369, `account-current` absent). `e47ab229` and `13c780e8` are both **superseded**; do not attend
  against either. Draft PR (unmerged, on purpose):
  https://github.com/aiSight-us/MOSS-Transcribe-Diarize/pull/32 — do not merge; the operator decides on a
  history squash first (see the PR's "History note").
- **Round 16 (`e47ab229`) passed every product predicate**: deterministic 18/18, deployed 18/19,
  pre-admission 16/17, the single rejection being `quality_corpus` with exactly the three pre-approved
  exceptions (DER, reference-speech DER, matched-speaker accuracy — all inside the 5 % band; everything else
  strict). 48/48 sessions finalized, both load gates passed, backpressure proven. Full record and every
  earlier round: issue #10 (https://github.com/aiSight-us/MOSS-Transcribe-Diarize/issues/10), latest
  comments first.
- **Round 17 FAILED on a host incident — not a product regression** (2026-09-12). vLLM died mid-round at
  21:52:41 EDT with `torch.AcceleratorError: CUDA error: unknown error` → `EngineDeadError` → exit. The cutover
  detected the broken invariant and terminated `SAFE_STOPPED` / `CutoverUnsafe` ("vLLM process changed during
  cutover or restore"), `g7: UNCLAIMED`, `admitted: false`; it quarantined candidate `5d21f59c` and restored
  Phase-1. The one product failure in that round (`ServiceReplayIdentityCommitFailure`, deployed quality session
  10) landed the same minute the decoder died — collateral. **Round 16 (`e47ab229`) therefore remains the last
  good product evidence** and the rehearsal/manifest fix is still unconfirmed by a clean record.
  Cause NOT established: zero nvlddmkm/TDR/WHEA events, GPU cold and idle afterwards. Windows logged "low
  virtual memory" 30 s prior, but that warning fires chronically (14+ times Sep 11–12, including 21:29:40 in this
  same round with no crash). Host has 31.7 GB RAM with WSL capped at 22 GB — a standing demo risk.
- **Host recovered 2026-09-12 ~22:55 EDT.** Operator rebooted (boot 22:20:43); new vLLM baseline **PID 369**,
  moss-web 1534, moss-live-web 378, model endpoint 200, canonical `/etc/hosts` loopback restored automatically,
  693 G free. **Trap:** `SAFE_STOPPED` deliberately verifies the Phase-1 quiesce marker is PRESENT and the web
  units STOPPED (`phase2_cutover.py:1496-1505`). The reboot restarted the units but left the marker, so Phase-1
  served while `quiesced` — refusing all new work. Lifted with the supported CLI on the Phase-1 checkout
  `/mnt/d/Coding/MOSS-Transcribe-Diarize`; note the module has **no `__main__` guard**, so `python -m ...` prints
  nothing and exits 0 — call `main()` directly:
  `venv/bin/python -c "import sys;sys.argv=['q','disable'];from moss_transcribe_diarize.app.phase1_quiesce_cli import main;main()"`.
  Marker state is read live per request (`os.stat`), so no restart is needed. Both views now `open`, zero work.
- **TLS trap:** the production origin serves a **self-signed** certificate (subject == issuer, valid to
  2028-10-20). The MacBook trusts it; MacStudio does not (`curl` exit 60). A `000` from MacStudio is **not**
  evidence the host is down — use `-k` from MacStudio, never from the operator machine.
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

1. **Staging and insurance are already done — do not repeat them.** `b9aedebd` is staged inert and verified,
   and the deterministic tests covering the changed boundary ran from that staged runtime: **128 passed**. The
   operator decided against another full `--terminal restored` round. That decision is well founded: 1.2 measured
   round 16 at **130.1 min of recorded commands**, dominated by two ~63.9 min collectors (quality is 24 serial
   sessions ≈43 min; capacity ≈22.9 min; overload ≈7.2 min; G9 runs a second capacity campaign), and the
   acceptance CLI has **no predicate selector** — waves are cumulative and `measure_layer` enumerates every
   requirement. So the round cannot be shortened without editing the runner or shrinking measurement windows, and
   shrinking a window that still runs would weaken the gate. `--terminal preadmission` performs the full
   qualification itself before G7, so that coverage is not lost — it is deferred into the attended run.
   **Not covered, state it aloud:** GPU stability under sustained 4/8-session load is not re-proven, and round
   17's crash shows that risk is real. If load insurance is wanted, the only honest form is the full round at
   full cost.
2. **Display for the canary — solved; use Option C.** The server has **no usable microphone**: every physical jack
   reports UNPLUGGED and the only ACTIVE capture endpoints are `Stereo Mix` (Realtek loopback) plus Virtual Desktop
   and Oculus virtuals. macOS RDP supplies no microphone redirection either, so a host-local canary was a dead end.
   The candidate now accepts an optional `measurements.pre_admission.chrome_cdp_endpoint`: when set, the canary
   attaches over DevTools to a Chrome **on the operator's own MacBook** (real mic, real share picker, real screen)
   instead of launching one on the host. The cutover, its qualification and the four Enter prompts stay on the
   Alienware over an SSH TTY. Loopback-only, reached through `ssh -R`; **the transport was verified end to end on
   2026-09-12** (a forwarded loopback port answered from Windows *and* from inside WSL). No WSLg, no
   `wsl --shutdown`, no vLLM PID change. Full procedure: runbook "Option C". Options A and B remain documented but
   both need capture hardware the server does not have.
3. **Attended preadmission.** With Option C, first do the runbook's four setup steps on the MacBook (dedicated
   Chrome with `--remote-debugging-port` and its own `--user-data-dir`, sign into MOSS in it, `ssh -R` the port,
   declare `chrome_cdp_endpoint` in the host profile — and re-verify the forward from inside Ubuntu). Then run the
   runbook's exact `mtd-phase2-cutover run --profile … --attempt … --terminal preadmission` command from an
   interactive WSL terminal (an SSH TTY satisfies the attendance check; do **not** detach or pipe stdin). Budget
   an hour or more of re-qualification, then two tabs open **in your own Chrome**: share a **tab with audio**,
   enable the microphone, speak until both lane meters move and two speakers appear, Enter; then **entire
   screen**; four Enter confirmations total, all answered in the SSH terminal. On PASS the candidate keeps serving
   on :7861 (that is the demo state). Any failure auto-restores Phase-1; `SAFE_STOPPED` needs the engineer — and
   note it intends the web units to stay stopped, so do not "fix" it with a reboot (see the quiesce trap above).
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
