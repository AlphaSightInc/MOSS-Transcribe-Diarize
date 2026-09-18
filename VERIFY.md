# WP6 fresh-context verification

Worktree ONLY: /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp6-capacity-baseline
Branch: mvpfix/wp6-capacity-baseline. Base: 37979e539f04d4ea740a1a94d021cd3bb894a0e2.

This file is for a NEW conversation entered through `/new` in MOSS:3.3 (%21).
Do not call current-context checks fresh. Confirm this is a new conversation.

## Scope / remaining block

User requested WP6 completely but also explicitly forbade touching shared services
beyond read-only metrics. Decoder load needs clarification. No answer was received
in the implementing context; no decoder calls/tunnels/servers were started.
**Do not run the live ladder without new explicit user authorization.**
Part 0 is fixed. Prototype is prepared, not live-verified. No capacity verdict or
campaign-driven production fix exists. This is a partial/blocked delivery.
No push/merge/deploy/GitHub, writes outside this worktree, or peer messages.

Read AGENTS.md, evidence/mvpfix/wp6/PART0.md, and prototypes/capacity-campaign/NOTES.md.
Read the original briefs if needed (read-only):
/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/COMMON.md
/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/WP6-capacity-baseline.md

## Execute literally

Set cwd to the worktree before each command. Use:

```sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=.
export TMPDIR="$PWD/.wp6-tmp"
WP6_PYTHON=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
mkdir -p "$TMPDIR"
"$WP6_PYTHON" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
git branch --show-current
git rev-parse HEAD
git status --short
"$WP6_PYTHON" evidence/mvpfix/wp6/check_part0.py
"$WP6_PYTHON" prototypes/capacity-campaign/run.py --sessions 1 --seconds 120 --prepare-only
"$WP6_PYTHON" prototypes/capacity-campaign/run.py --sessions 2 --seconds 300 --prepare-only
"$WP6_PYTHON" prototypes/capacity-campaign/run.py --sessions 4 --seconds 600 --prepare-only
"$WP6_PYTHON" prototypes/capacity-campaign/run.py --sessions 8 --seconds 120 --prepare-only
"$WP6_PYTHON" -c 'from pathlib import Path; paths=list(Path("prototypes/capacity-campaign").glob("*.py")); [compile(p.read_text(),str(p),"exec") for p in paths]; print(len(paths), "files compile")'
git diff 37979e53 -- moss_transcribe_diarize
```

Checks / falsifiers:
- Import must resolve inside assigned worktree; otherwise stop, fix command cwd/env.
- Ordered subset: 443 passed + 19 subtests; reverse: 443 + 19; runtime-pin suite: 15.
  Any failure falsifies Part 0 fix. One existing Starlette warning expected per run.
- Four preparation commands must succeed, with N distinct clip descriptors and
  nonempty reference rows. This verifies input preparation only, no capacity.
- Two prototype files compile; no production diff. Never relax production pin.
- Inspect fixture change: common tests ancestor; application restricted to phase2.
- Inspect runner vs NOTES; report material defects instead of declaring unrun
  behavior verified. Do not repair production based on an unrun campaign.

## Finish

Write VERIFY-RESULT.md with new conversation identity if available, tested SHA,
exact counts, pass/fail separately for Part 0 and prototype preparation, and
BLOCKED/NOT MEASURED for the real ladder. Do not invent capacity results.
Commit VERIFY-RESULT.md and any refreshed evidence locally on this branch.
Report <=60 lines in this pane: branch/final SHA, question/verdict, files, exact
counts, measurements (decoder calls 0), blockers and deviations. State plainly
WP6 is incomplete until authorized real decoder ladder and consequent fixes.

Known deviation: first base pytest run used default system temp directory; all
subsequent runs use .wp6-tmp. Do not delete outside-worktree temporary paths.
No production modification, threshold change, other checkout edit, shared service
mutation, or deployment occurred.
