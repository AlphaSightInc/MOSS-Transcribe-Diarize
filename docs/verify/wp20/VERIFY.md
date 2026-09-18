# WP20 literal fresh-context verification

This is the user-requested `/new` verification in MOSS:3.2 / pane %26.
Do NOT run /new again. First cd to the only writable worktree:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp20-lane-endpointing`.
Branch mvpfix/wp20-lane-endpointing; measured production base de35ef365724caad47c407bd41c34e21182d20c7.
Do not change branches, touch other worktrees, push/merge/deploy/GitHub, message
peers, or start any service/tunnel/decoder request. Historical budget390/500;
fresh verification is offline. All owned measurement processes are stopped.

Read this tree's AGENTS.md, then in order:
1. /Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/COMMON.md
2. /Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/WP20-lane-endpointing.md
Then prototypes/streaming-diarization/wp20/NOTES.md and
 evidence/mvpfix/wp20/{NOTES.md,COMMANDS.md}. Inspect the branch diff from base.
This is a negative prototype result: no production fix. Assess the evidence
independently; do not convert evidence consistency PASS into quality acceptance.
No word-level reference timestamps exist for partial 24/48-second/per-span WER.

## Literal execution

Purpose: detect wrong-tree imports, stale/manually altered evidence, changed
geometry or policies, test regressions, stale assets, and leaked owned listeners.
If any check fails, retain output, diagnose here, and correct only a justified
local failure; never waive assertions. No new live requalification needed.

```sh
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp20-lane-endpointing
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/runs/wp20/tmp"
WP20_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
git branch --show-current
git rev-parse HEAD
git status --short
"$WP20_PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
"$WP20_PY" evidence/mvpfix/wp20/audit.py > evidence/mvpfix/wp20/fresh-audit.json
"$WP20_PY" -m pytest -q -ra -p no:cacheprovider -p evidence.mvpfix.wp17.local_scratch --basetemp=runs/wp20/pytest-fresh tests > evidence/mvpfix/wp20/fresh-python.txt 2>&1
npm --prefix frontend test -- --run --configLoader native --cache=false > evidence/mvpfix/wp20/fresh-frontend.txt 2>&1
npm --prefix frontend run typecheck > evidence/mvpfix/wp20/fresh-typecheck.txt 2>&1
npm --prefix frontend run build -- --configLoader native > evidence/mvpfix/wp20/fresh-build.txt 2>&1
git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets
git diff --check
lsof -nP -iTCP:17880 -iTCP:18120 -sTCP:LISTEN
```

Expected: audit evidence PASS, prototype REJECTED_NO_OVERLAP_WIN, product FAIL;
Python1874 passed, 2 skipped, 37 subtests passed; frontend244 tests/27 files;
typecheck/build pass, assets unchanged. Listener check no output/exit1.
Python uses the previously committed WP17 scratch-path fixture plugin to prevent
hardcoded test temporary paths escaping this worktree. It changes no assertions
or product code; its runs/wp17 paths also reside inside this worktree. Dependencies
are symlinked read-only; native/cache=false avoids writing through that symlink.
Initial Python1874/2/37 in149.29s; frontend244/27 in2.71s passed BEFORE this recipe.

## Independent assessment targets

F1: full-reference overlap system12/mic10 nonzero mixed/local intervals equal,
canonical all WER18/106 and9/53 unchanged. Hard cap40000, no production policy edit.
F2: immediate system16/106 alternating versus24/106 overlapping; canonical pre
18 vs26 errors, canonical-all18 both. Extra8 omissions are unfinished tail at
pre-Stop: accepted28.5s/committed27.5s for29s speech. Rolling improves each by2.
Mic immediate11/53 vs6/53; local alternation canonical11->9/53, still above bar.
F3: same-boundary replay137/137 canonical,30/30 rolling,11/12 terminal exact;
alternating system terminal varies. Final alternate9/106, overlap13/106; mic5/53
both. Reopened equal. Padding controls share464000 samples, append400000 zeros;
pair trials9/13 and11/13 errors. Identical speech alone reproduces final gap.
F4: all6 captures complete/final. 24/48s partial controls' exact WER UNMEASURED;
differential output counts are not truth. Local scheduler/latency also UNMEASURED:
explicit no-overlap-win falsifier stopped promotion before production integration.
Baseline Stop24s5.411/11.389s,48s10.501/18.697s alternate/overlap; sampled pending
work1/2/2/2, not continuous queue high-water. WP12 separate candidate isn't matched.
Budget390=179 baseline+179 standalone+28 new local nonzero+4 padding. No retries
hidden. Variant reuses154 exact-PCM/reason answers across191 local partitions,
56 of which are zero. Raw public traces/PCM remain ignored under runs/wp20;
audit re-derives committed counts from them. Never commit audio, TLS, cookies.

Write docs/verify/wp20/VERIFY-RESULT.md with tested SHA, fresh counts, independent
verdict, limitations/deviations. Append short fresh result to both NOTES.md files.
Normalize only trailing whitespace in retained test logs (originals in runs/wp20)
before git diff --check; never alter counts/errors. Commit verification records
locally. Report <=60 lines in THIS pane: final branch/SHA, negative prototype,
files, exact tests, stage WER numbers, no production change, outstanding quality/
measurement limits and deviations. Do not claim deployment or browser acceptance.
