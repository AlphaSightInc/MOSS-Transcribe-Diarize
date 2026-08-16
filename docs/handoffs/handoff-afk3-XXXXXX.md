# Handoff: finish the afk3 review cycle — verify, decide, reconcile

Written 2026-08-14 ~21:50 by the orchestrating session. Supersedes
`docs/handoffs/handoff-review-and-fix-20260814.md`, whose launch contract is **complete**: all six
branches were adversarially reviewed and repaired.

## Start here — do not re-derive any of this

**The authoritative state lives in a reboot checkpoint, not in this file:**

```
/Users/gao/.claude/reboot-checkpoints/moss-20260814-174105/
```

Read `POST_CHECKPOINT_UPDATE.md` **first** (it supersedes the rest), then `README.md`, then
`MERGE_AND_RESTART_PLAN.md`. 1218 files, SHA-256 manifest verified 0 mismatches. It contains the
six verdicts, every commit SHA, authoritative `git` state for all 8 worktrees, captured diffs,
evidence audits, guardrail defects, and the environment diagnosis. **Do not duplicate it — cite it.**

Suggested opener:

```
/goal execute docs/handoffs/handoff-afk3-XXXXXX.md
```

## Where things stand

Six branches reviewed. **Every one was defective as received** — including two the previous round's
loops had self-certified `COMPLETE` while shipping a P0. Verdicts and per-defect detail:
`TEST_AND_EVIDENCE_STATE.md` §2.

| Branch | Verdict | Repairs |
|---|---|---|
| `afk3/x1-frame-drop` | PASS-WITH-DEFECTS | committed, clean |
| `afk3/x2-capture-client` | PASS-WITH-DEFECTS | committed; **1 file dirty** |
| `afk3/x3-capture-health` | PASS-WITH-DEFECTS | committed, clean |
| `afk3/x4-journal-mode` | **FAIL** | committed, clean |
| `afk3/x5-auth-residual` | PASS-WITH-DEFECTS | committed, clean |
| `afk3/x6-terminal-visibility` | PASS-WITH-DEFECTS | committed, clean |

**`dev` is untouched at `f6353eb`. Nothing is merged.** That ordering is the operator's explicit
instruction — merging before review is how a previous round put two P0s on `dev`.

`ui/reference-port` (separate branch, orchestrator's own) has 2 commits fixing two of three poller
defects; the third is deliberately open pending the x3↔x6 decision below.

## Outstanding work, in order

### 1. Verification (unblocked, read-only, do first)
- Full suite on x1, x2, x6 — never obtained cleanly. x6's pre-existing-failure check was
  **never completed at all**.
- Commit x2's one dirty file, `frontend/src/capture/preBranchDefects.test.ts`. It replaces a
  tautological assertion the reviewer had written itself; discarding it reverts to a fake gate.
  Verified byte-identical to the checkpoint copy (`0676a2a5…`).
- **Baseline warning:** the expected-failure count is per-worktree, not global (untracked
  l2-stage0 corpus data differs). Compare each branch against a `git archive dev` export **in its
  own worktree**. `TEST_AND_EVIDENCE_STATE.md` §1.

### 2. Two decisions that must precede the x3/x6 merges
- **x3↔x6 semantic collision.** Both reviewers flagged it independently, from opposite sides. With
  both merged, a dead session's snapshot reports `status: "failed"` **beside**
  `capture_phase: "starting"` / "Waiting for audio capture to start." Reconcile the phase vocabulary
  deliberately — do not take whichever lands second. `MERGE_AND_RESTART_PLAN.md` §5.
- **A clean stop reports `capture_phase: "failed"`** — a user who stops their own meeting is told it
  failed. x3 declined as out-of-scope and colliding with x6. Operator's call.

### 3. Reconciliation
Order, rationale, per-file conflict surface and the serialized merge protocol:
`MERGE_AND_RESTART_PLAN.md` §3. Summary: **x4 → x5 → x1 → x2 → x3 → x6**. Only one textual conflict
surface exists (`tests/test_live_api.py`, three-way). Before x2 merges, strip the 10 stray
`scripts/afk2-r2-capture-client/telemetry/` files it swept in via `b252d59` — preflight allows them,
so no gate will catch it.

**Deploy notes to carry forward:** x4 chmods real host directories on first `--live` start and
refuses to start on a foreign-owned peer-writable ancestor; x5 rewrites `live-auth.json` on first
start after landing.

### 4. Frozen product work (resume last)
`App.tsx` orchestration + `ControlPanel` port, and poller defect A. Both on `ui/reference-port`.
x2's exact mount sequence and the `replaceLane()` inertness trap: `MERGE_AND_RESTART_PLAN.md` §7.

## Environment — read before trusting any test result

**The machine is in a partially-degraded state and a reboot is still pending.** As of 21:44:

| Working | Broken |
|---|---|
| `~/Desktop`, repo `.venv`, `git`, `pytest` | `whoami` → `501`; `dscl` → FAIL |
| | `codesign` → `CSSMERR_TP_NOT_TRUSTED` (Apple's own binaries) |
| | Chrome → exit 134; DNS → `000`; `logd`, `sysmond` dead |

Consequences you must not misread:
- **The four `test_macos_uds_tracer.py` failures are environmental**, not defects — they persist
  with TCC healthy and track the broken trust subsystem. Do not "fix" them.
- **x1's G7 sign-off needs a host with working Chrome.** It currently rests on artifact inspection.
- **Codex is unreachable** (DNS), so `/codex:adversarial-review` cannot run. A standalone no-remote
  review repo is staged inside the checkpoint, ready to re-run post-reboot.
- If TCC lapses again, a contaminated suite is identifiable by `AssertionError: 128 != 0`,
  `ops/moss-live.env is not gitignored`, or a traceback inside `<frozen site>`.
  **Discard those runs.** `TEST_AND_EVIDENCE_STATE.md` §4.

Full diagnosis and post-reboot validation order: `FDA_DIAGNOSIS.md` §7. **Do not change FDA/TCC
settings and do not reinstall Chrome** — the fault is a wedged daemon, not a permission or a
corrupt app.

## Traps that cost this session real time

- **Wrong repo.** The shell's default cwd `…/0.AISIGHT_LOOP/moss-transcribe-diarize` is a
  *different, unrelated* repo. The product repo is
  `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize`.
- **Three PRD defects do not exist on `dev`** — x1's headline P0, x5's constant-time test, and all
  of x2's line numbers (there is no `frontend/src/capture/` on `dev`). They describe unmerged
  sibling branches. Verify a PRD claim with `git log --all -S` before "fixing" it.
- **Reading a worktree mid-review attributes the reviewer's repairs to the branch.** I made this
  error on x6 and briefly reported it as a false alarm. Always diff against the as-received HEAD.
- `npm` works only via `/opt/homebrew/bin/npm`; `npm ci` genuinely fails. `log` is shadowed — use
  `/usr/bin/log`. zsh: `$var` followed by `:` is a history modifier.

## Two guardrail defects found (report-only, nobody owns them)

`scripts/afk-guardrails/preflight.py` has two independent blind spots in its
"every artifact names a committed, re-runnable probe" check: it only enforces on filenames matching
`*probe*.py`/`*proto*.py` (a hand-written `.txt` passes clean), and it checks only *existence*, so a
probe that **crashes on re-run** also passes. Both were exploited in this batch.
`TEST_AND_EVIDENCE_STATE.md` §7.

## Suggested skills

- **`/diagnose`** — for any finding you cannot reproduce on the first try. Reproduce → minimise →
  fix → re-run. Every real defect in this batch was found this way.
- **`/codex:adversarial-review`** — only after the reboot restores DNS. Re-run it against the
  checkpoint's staged review repo, then against the merged result.
- **`/prototype`** — mandatory before any non-trivial fix (`AGENTS.md`); extend
  `prototypes/streaming-diarization/` rather than rebuilding scaffolding.
- Skip `/grilling` and `/domain-modeling` unless a genuinely new decision opens — all 12 wayfinder
  tickets are closed and should not be re-litigated.

## Do not

Merge to `dev` before §1 and §2 are done · push `main` · close GitHub issues (comment evidence; the
orchestrator closes) · restart/redeploy/mutate `moss-live-web`, `moss-vllm`, `moss-web` on the GPU
host · add Uvicorn workers · automate the display-capture picker · edit the l15 product-tree drift
guard · weaken a test to make a gate pass.

Binding ground truth, unchanged: `docs/phase1-afk-charter.md` (authority §1, capture spec §4,
fidelity §5, gates §6, attended checklist §7), `.wayfinder/map-001-phase1-chrome-client.md`,
`.wayfinder/tickets/`, `AGENTS.md`, `scripts/afk-guardrails/ownership.json`.
