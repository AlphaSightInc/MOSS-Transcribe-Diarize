# WP17 literal fresh-context verification

Work ONLY in:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp17-lane-quality-voiceprint`
Branch `mvpfix/wp17-lane-quality-voiceprint`; base current integration at 41cfebb9.
Production fix 7870eb2c; reference fixture fix 685319f4. This session follows the
user-requested `/new` in MOSS:3.2 / %26. Do not run /new again.
No push/merge/deploy/GitHub, other-checkout source writes, peer messages or new
vLLM calls. No threshold, policy, quality-bound, protocol or lifecycle changes.

Read AGENTS.md, then the two briefs in order:
1. `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/COMMON.md`
2. `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/WP17-lane-quality-voiceprint.md`
The worktree already exists: do not recreate it or switch branches.
Read evidence/mvpfix/wp17/{NOTES.md,COMMANDS.md,reference-adjudication.md}, then inspect
the two fix commits. Do not use the prior conversation to infer a passing result.

## Literal commands

These controls detect wrong-tree imports, code/test regressions, stale assets,
inconsistent evidence and leaked owned processes. If a check fails, investigate
that failure in this worktree; retain the failed output. Do not relax assertions.

```sh
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp17-lane-quality-voiceprint
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/runs/wp17/tmp"
WP17_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
git branch --show-current
git rev-parse HEAD
git status --short
"$WP17_PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
"$WP17_PY" evidence/mvpfix/wp17/audit.py > evidence/mvpfix/wp17/fresh-audit.json
"$WP17_PY" -m pytest -q -ra -p no:cacheprovider -p evidence.mvpfix.wp17.local_scratch --basetemp=runs/wp17/pytest-fresh tests > evidence/mvpfix/wp17/fresh-python.txt 2>&1
npm --prefix frontend test -- --run --configLoader native --cache=false > evidence/mvpfix/wp17/fresh-frontend.txt 2>&1
npm --prefix frontend run typecheck > evidence/mvpfix/wp17/fresh-typecheck.txt 2>&1
npm --prefix frontend run build -- --configLoader native > evidence/mvpfix/wp17/fresh-build.txt 2>&1
git restore -- evidence/mvpfix/wp2/production-390.png evidence/mvpfix/wp2/production-400.png evidence/mvpfix/wp2/production-1280.png
git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets
git diff --check
lsof -nP -iTCP:17877 -iTCP:18117 -sTCP:LISTEN
```

Expected: evidence audit PASS (product acceptance FAIL), Python 1869 passed,
2 skipped (unprovisioned operator corpora), 37 subtests passed. Frontend 242 passed
in 27 files, typecheck/build pass; assets identical. lsof: no output, exit 1.
The optional screenshot restores undo only fixture-generated historical images.
Do not touch any other preexisting user change. Full initial suite already passed.

## Independent evidence assessment

- F1: microphone original 10/48 additions on both saved/reopened cases. Exact same
  25-second PCM decoded alone at gain .03 gives the same ten additions. Five are
  an omitted source sentence tail. Source PCM comparison 400000/400000 exact at
  longer-recording seconds 115–140. Dedicated fixture adds ONLY those five words.
  Remaining fillers/repetition are still errors, not silently normalized away.
- Before/after decoder reruns: final alternation system 9/106=8.49057%, mic
  10/48=20.8333% -> 5/53=9.43396%; overlap system 13/106=12.26415%, same mic
  improvement. Attribution 2->0 each; duplicates 2->0 alternating, 1->0 overlap.
  Immediate after alternation system 15/106, mic 11/53; overlap system 33/106,
  mic 6/53. Both acceptance cases STILL FAIL. Read the JSON, do not round into pass.
- F2: commit consumed pending embeddings before recognition publication. Fake
  encoder before: prepared 2 -> committed 0, album 2, embeddings 2. Two failing
  tests before fix; 70 focused tests pass after. No threshold or extra embeddings.
  WP7 case 3 baseline: no live recognition during 12-second capture, but a name
  can appear at terminal album publication. After: all four enrollment/recognition
  lane combinations 3.526–3.528 seconds at API; saved names correct. Browser DOM
  recognition latency remains unmeasured. Profile deletion removes historical
  links, so current DB counts are explicitly distinguished from recognition time.
- 12/12 duration probes cover 24/48 seconds × alternation/overlap × paired/system
  alone/microphone alone. duration-diffs.json compares eight lane cases by
  canonical/rolling/terminal producer and saved text. All 8 saved lane comparisons and all 8 terminal windows match; 3 matched
  rolling windows differ. Differential edit distance
  is NOT independent ground truth or quality acceptance; differing windows are
  explicitly unmatched. Inspect anomalies rather than merely accepting counts.
- Decoder budget: 427 decoder-requests.jsonl + 4 alone-requests.jsonl =431/600. Server
  ledger request indices restart by process; line count is the total. Two-request
  semaphore enforced by stack recipe. Owned service/tunnel were stopped.

Write VERIFY-RESULT.md with tested SHA, independent pass/fail, exact counts,
retained-evidence assessment and residual limits. Append result to NOTES.md.
Commit local verification records. Then final <=60-line report in THIS pane:
branch + final SHA; prototype verdict; changed files; exact tests; before/after
lane quality, recognition latency; residual acceptance FAIL and deviations.
Do not call this deployment, browser acceptance, or whole-product qualification.
