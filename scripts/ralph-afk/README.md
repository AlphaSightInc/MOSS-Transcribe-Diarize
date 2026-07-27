# Ralph AFK loop — MOSS live meeting transcription MVP

Executes the `moss-live-meeting-v1` contract from revision 6 or later of
`/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/docs/live-capture-gap-and-execution-plan-20260727.md`.
`prd.md` is the acceptance contract, `context.md` is living working memory, `progress.txt` is the
append-only journal, `prompt.md` is the per-iteration procedure.

## Run it

```bash
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize
./scripts/ralph-afk/launch.sh 30          # recommended first run
RALPH_DRY_RUN=1 ./scripts/ralph-afk/launch.sh 1     # validate config, preview prompt, no work
RALPH_AGENT=codex ./scripts/ralph-afk/launch.sh 30  # or ./scripts/ralph-afk/ralph-afk-codex.sh 30
```

Always launch through `launch.sh`. It resolves pyenv Python 3.12 (a bare `python3` can be 3.9 in a
non-interactive shell), pins the model, and sets the fences below. `ralph-afk-codex.sh` routes
through it too, so the fences cannot be bypassed by choosing the other agent.

```bash
touch scripts/ralph-afk/.stop                        # graceful stop after the current iteration
tail -f scripts/ralph-afk/telemetry/run-*/iter-*.log # watch
./scripts/ralph-afk/preflight.sh                     # self-resolves pyenv; names a failed check
```

## Launch fences

All are fail-closed. `launch.sh` sets them; the engine and `preflight.sh` enforce them.

| Fence | Enforced by | Why |
|---|---|---|
| branch is `ralph/live-meeting-mvp` | engine (`RALPH_EXPECTED_BRANCH`) | product work never lands directly on `main` |
| HEAD descends from `af3ac36` | engine (`RALPH_REQUIRED_ANCESTOR`) | refuses an unrelated or rewritten history |
| working tree clean | engine (`RALPH_ALLOW_DIRTY=0`) | no stray edit contaminates a checkpoint |
| preflight mandatory | `RALPH_PREFLIGHT_REQUIRED=1` | a broken interpreter or missing ref stops the run instead of producing garbage |
| plan revision ≥ `RALPH_PLAN_MIN_REVISION` | `preflight.sh` | refuses a stale plan without blocking compatible editorial revisions |
| plan contract exactly `RALPH_PLAN_CONTRACT` | `preflight.sh` | refuses a newer but execution-incompatible plan until this bundle is reconciled |
| authoritative server metadata exactly `RALPH_SERVER_HOST` | `preflight.sh` | refuses a retargeted plan; historical mentions cannot satisfy the fence |
| governed loop still halted | `preflight.sh` | one writer per repo; the `aisight-coding-loop` sentinel must stay |

## Exit codes (this instance)

The engine here is **extended** relative to the template pack, so these differ from the template
README. Read the last `[loop <run-id>]` marker in `progress.txt` for the reason.

| Code | Meaning |
|---:|---|
| 0 | acceptance bar met (`<promise>COMPLETE</promise>`) or graceful `.stop` |
| 1 | error, or budget exhausted with an unresolved agent failure |
| 2 | `<promise>BLOCKED</promise>` (needs input the loop cannot obtain), **or** no-progress cutoff, **or** budget exhausted without completion |

Exit 2 is the expected outcome when the run reaches the macOS TCC clicks: they are
SIP-protected and cannot be scripted. The journal will name the exact clicks.

## Local scripts

| Script | Purpose |
|---|---|
| `launch.sh` | the only supported entry point; resolves Python, pins model, sets fences |
| `preflight.sh` | per-iteration environment facts only — never code style or work-in-progress state, because a cosmetic failure would halt an unattended run |
| `validate-phase-a-locality.sh` | Phase A only: fails if changes leave IDEA-044's registered thirteen product/doc paths. Later phases intentionally widen scope, so stop using it after the Phase A checkpoint |
| `merge-keeper.sh` | the single reviewed `main` merge, performed in a temporary worktree so the primary worktree stays on the feature branch. Builds both Swift executable products as explicit gates before Swift/Python testing |

## Manual recovery paths

- **`merge-keeper.sh` fails after committing the merge.** `main` has already advanced, so the
  script's `expected_main` fence will refuse a re-run. Inspect `git log main`, understand why the
  post-commit assertion failed, and only then re-run with
  `RALPH_MERGE_MAIN_BEFORE=<current main sha>`. Do not delete or reset `main`.
- **Preflight blocks the launch.** Run it directly; it names the failing check.
- **A later plan revision lands.** A compatible revision keeps the same Ralph contract and
  passes the minimum. An execution-contract change must change the marker in the plan; reconcile
  this bundle, then update `RALPH_PLAN_CONTRACT` in `launch.sh`.

## Maintainer warning

`ralph-afk.sh`, `prompt.md`, and `ralph-afk-codex.sh` are **modified** from the
`ralph-loop-afk` template pack (branch/ancestor/clean-tree fences, the `BLOCKED` token and its
exit code, phase-gate and remote-action rules, launcher routing). Re-running
`setup-ralph-afk.sh` with `RALPH_OVERWRITE=1` would silently discard all of it.
