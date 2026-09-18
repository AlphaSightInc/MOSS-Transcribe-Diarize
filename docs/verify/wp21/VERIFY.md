# WP21 fresh-context verification

This is the requested `/new` session in MOSS:3.2. Do NOT run `/new` again.
First cd `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp21-qualify-bundle`.
Modify nothing outside this worktree. No push/merge/rebase/deploy/GitHub or shared services.
Read AGENTS.md, then COMMON.md and WP21-qualify-bundle.md under
`/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/`, in that order.
Read tools/qualify/README.md, tools/qualify/NOTES.md and evidence/mvpfix/wp21/NOTES.md.

User explicitly authorized this fresh bounded live rerun. Own vLLM tunnel 18121 only;
owned app 17867/accounting forward 18122; maximum 300 decoder calls, two in flight.
Do not retry a busy/unavailable decoder or a failing live bench. Record every outcome.
No agent delegation. Existing frontend/node_modules symlink is prepared; do not install.

Run once, literally from this worktree:
```sh
git status --short --branch
git rev-parse HEAD
bash scripts/mvpfix-qualify.sh --compare evidence/qualify/5ae9566f017e-20260918T064038829598Z/summary.json > .wp21runtime/fresh-run.console 2>&1
```
Expected command exit 1: failures and unsupported benches are information, not waived passes.
Poll the console/bundle safely; give concise progress updates at least every 60 seconds.
The command includes full Python/frontend suites and all supported real workflow benches.
Do not read transcript-bearing raw logs into reports. Use bundle JSON and count projections.

Baseline completed dry run: tested 5ae9566f017e5b888d3676e9a3ccb0a007d5917d, 705.520 s;
1879 Python collected/reported, 1877 passed/executed, 2 skipped, 37 passed subtests;
frontend 244/244, helpers 6/6, assets 17/17 equal, typecheck/layout/stack/teardown PASS.
Workspace 10 PASS / 3 FAIL (4/5/10) / 1 SKIP (9) out of 14; lane cases 0/2;
lifecycle 7/7, reshare 6/6, identity 1/3 (gap/alternating interrupted after cap);
ladder 0/6 emitted after cap. Browser all 16, WP16 six-minute 1 and failures 5 UNRUNNABLE.
Long files (3) and capacity (4 sessions) SKIP by default. 300 requests, peak 1, active 0.
267 contention samples, no errors, shared running maximum 1/waiting maximum 0.

Current helper tests expect 7/7. After dry run, missing-reference-voice rejection was
strengthened and budget metadata added. Retained identity observations re-score identically
(3/3). Exact source SHA changes also include evidence/docs. Report this openly: even zero
gate-status deltas are NOT strict same-code determinism. The requested comparison still
must run and all actual deltas must be recorded. Do not manufacture a matching outcome.
The product baseline is c2e45867, not integration's later WP20 merge 5094206d; no sync allowed.

After completion, inspect the new summary.json (BUNDLE path in fresh-run.console), including
identity, gate denominators, decoder totals, teardown and determinism.deltas. Falsifiers:
missing gate; invented pass; source import outside own checkout; decoder >300 or peak >2;
content-bearing retained artifact; unreported failed check; treating budget-limited cases
as acoustic rejection; claiming full candidate qualification despite UNRUNNABLE gates.
Check only these final containment/scope failures (do not rerun GPU work):
```sh
git diff --exit-code c2e458676cf27b9e4da69bea20a1612152f1516a -- moss_transcribe_diarize frontend tests prototypes
bash scripts/check_verify_layout.sh
git diff --check
lsof -nP -iTCP:17867 -iTCP:18121 -iTCP:18122 -sTCP:LISTEN
```
Expected no product diff; layout/diff checks exit 0; no listeners (lsof exit 1). Do not kill
new listeners belonging to another process. Original benches remain unchanged.

Write docs/verify/wp21/VERIFY-RESULT.md: fresh context, tested SHA, exact gate counts,
all status deltas, actual runtime/requests/peak, scope and limitations/deviations.
Write evidence/mvpfix/wp21/fresh-summary.json with both bundle paths and comparison.
Commit only own scripts/tools/docs/evidence/ignore changes locally; never add runtime scratch.
Final report in this pane <=60 lines: branch/final SHA; prototype verdict; changed paths;
dry and fresh gate table; counts/runtime/request totals; UNRUNNABLE and budget limits;
pre-WP20 baseline, same-code determinism limitation, no production changes, clean teardown.
The task is prep + dry run + fresh comparison; do not try to fix unrelated product failures.

Memory was used only for the distinction between local evidence and deployed acceptance.
Append this citation block to the final report (included in the 60-line limit):
<oai-mem-citation>
<citation_entries>
MEMORY.md:719-720|note=[local qualification remains distinct from deployment]
</citation_entries>
<rollout_ids>
01a0909a-eddb-7030-ba15-453fe80dee63
</rollout_ids>
</oai-mem-citation>
