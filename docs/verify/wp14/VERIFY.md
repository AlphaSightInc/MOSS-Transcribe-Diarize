# WP14 — literal fresh-context verification

Work ONLY in `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp14-integrated-e2e`.
Branch: `mvpfix/wp14-integrated-e2e`; code commits 1b1fc692 (lease explanation) and
4b1d3401 (harness). Base 8068afce. This verification follows the user-requested
`/new` in MOSS:3.2 / %26. Do not run /new again. No prior-context reasoning needed.
No push, merge, deploy, GitHub or other-worktree writes. No peer messages.

Read AGENTS.md, then the briefs in order:
1. `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/COMMON.md`
2. `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/WP14-integrated-e2e.md`
Then read evidence/mvpfix/wp14/{NOTES.md,COMMANDS.md,verdict.json} and the WP14 section
of prototypes/browser-stress/NOTES.md. Do not reopen unrelated historical evidence.

**No further live decoder run:** 400/400 requests already consumed. Owned ports
17874/18114 stopped. A new process must not reset the per-WP budget. Hidden-tab and
reshare limitations are reportable outcomes, not authority to exceed the budget.

## Run literally

These controls detect wrong checkout, code regression, stale served assets, leaked
owned processes or inaccurate evidence. New failure: diagnose/fix only this WP's
scope; preserve quality bounds/identity policy/protocol/readiness/lifecycle/sentinel.

```sh
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp14-integrated-e2e
source evidence/mvpfix/wp14/environment.sh
git branch --show-current
git rev-parse HEAD
git status --short
"$WP14_PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
"$WP14_PY" -m pytest -q -ra -p no:cacheprovider -p evidence.mvpfix.wp14.local_scratch --basetemp=runs/wp14/pytest-fresh tests > evidence/mvpfix/wp14/fresh-python.txt 2>&1
npm --prefix frontend test -- --run --configLoader native --cache=false > evidence/mvpfix/wp14/fresh-frontend.txt 2>&1
npm --prefix frontend run typecheck > evidence/mvpfix/wp14/fresh-typecheck.txt 2>&1
npm --prefix frontend run build -- --configLoader native > evidence/mvpfix/wp14/fresh-build.txt 2>&1
git restore -- evidence/mvpfix/wp2/production-390.png evidence/mvpfix/wp2/production-400.png evidence/mvpfix/wp2/production-1280.png
git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets
git diff --check
lsof -nP -iTCP:17874 -iTCP:18114 -sTCP:LISTEN
```
Expected Python **1849 passed, 2 skipped, 37 subtests passed**; frontend **242 passed,
27 files**; typecheck/build 0; asset diff empty. `lsof` has no output, exit 1.
Geometry tests rewrite their three historical screenshots; restore only those.
If skip reasons differ from ordinary environment exclusions, explain rather than
silently accepting the same count. No new decoder calls necessary for these suites.

## Verify the measured evidence, independently of the prose

Read the JSON/logs, derive the denominators and check the following. Do not call
retained measurement a new live replication. No raw transcript/audio is needed.

- `workspace-final/results.json`: 14 rows, 11 PASS, 2 FAIL (4,10), 1 SKIP (9).
  Row 4 first text 3.323115s, Stop -> saved 8.094547s. Row 2/3 WER 10/115 each.
  Row 6 all five formats match 6/6 turns, JSON lane=true. Row 14 3/3 complete.
  Row 13 both 3s/20s variants pass and preserve both frame sequences.
- `lanes-initial.json` and row 4 controlled_lane_cases: both semantic cases FAIL;
  final/reopened WER alt(system,mic)=(9/106,10/48), overlap=(13/106,10/48).
  Initial overlap expected_failure=true is the OLD faulty harness; final false.
  `overlap-falsifier.txt`: restored old comparator fails the new assertion.
- `workspace-final/row-10.json`: bank_contains_name=true, recognition_seconds=null;
  `voiceprint-finding.json`: zero durable links. Root cause not isolated, WP12 owns.
- `browser-corrected/campaign-results.json` case15: both native attempts hidden=false;
  UNMEASURED, never claim 60s background acceptance.
- `browser-lease-rerun/campaign-results.json`: 25s PASS, 3/3 commits unchanged,
  27 before words, 26 retained in saved wording, 1 removed/revised; Stop 76.9516s.
- `browser-ui-final/campaign-results.json`: 35s PASS, readable reset instruction,
  interrupted, 30/30 words + 3/3 commits retained, new capture completed same page.
- `lifecycle.txt`: 7/7. `reshare.txt`: 3/6, BUDGET_BLOCKED at the 400-call ceiling;
  not a product defect adjudication and not a passing acceptance result.
- `decoder-requests.jsonl`: exactly 400 starts, sequential request indices 1..400;
  stack recipe semaphore=2. GPU samples show no waiting requests. No new calls.
- Review source diff from 8068afce: UI message only in product source, regenerated
  assets; harness/bench/test/evidence changes. No quality/identity policy changes.

Missing/inconsistent data falsifies the report. Product acceptance remains **FAIL /
INCOMPLETE** even if all verification controls pass. Preserve these deviations:
scripted prototype; first suite interrupted after 352 pass to redirect hardcoded
/tmp sockets (outside-tree byte-for-byte isolation not established); tooling errors
retained; identity post-fix failure not rerun substantively; reshare cap blocked.

Write VERIFY-RESULT.md with fresh-context confirmation, tested SHA, exact counts,
skip reasons, evidence-consistency verdict, acceptance failures/coverage limits and
cleanup. Commit fresh results/logs locally. Then give the <=60-line report in this
pane: branch/final SHA; prototype verdict; changes; 14-row table; tests; 400/400;
lease measurements; unmeasured/budget-blocked items and deviations. No permission
request, no external message, and no claim that local tests equal product acceptance.
