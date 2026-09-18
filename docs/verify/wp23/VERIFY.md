# WP23 — fresh-context ten-row documentation spot-check

First cd `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp23-closure-docs`.
This is the fresh task after the user-required `/new` in MOSS:3.4 (%27).
Do NOT issue another /new. Read AGENTS.md, COMMON.md then WP23-closure-docs.md at
`/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/`.
Read evidence/mvpfix/wp23/NOTES.md and the six delivered docs. Writes only here;
other worktrees read-only. No product/test changes, GPU/network requests, services,
push/merge/rebase/deploy/GitHub writes or peer messages. Commit final result locally.

Question: does the closure ledger agree with independently opened source revisions?
Primitives: branch revision, scoped result, measurement, remaining boundary.
Falsifier: wrong SHA/commit range/test count/verdict; absent evidence relabelled pass;
source branch acceptance confused with c609d7f3 integration/host acceptance.
Each following check catches one of those failures; correct docs and retain the
mismatch if found. No full suite rerun is requested for this docs-only spot-check:
COMMON full-suite gate was completed before this file (1901 Python passed/2 skipped/
37 subtests, frontend 249/28 files). New product changes would require separate scope.

## Execute

1. `git status --short --branch`, `git rev-parse HEAD`; confirm owned branch and
   inspect any unexpected changes without overwriting them. Source pin stays
   c609d7f3 even if integration branch advances; do not silently repin this ledger.
2. Exactly TEN primary rows: **WP1, WP3, WP6, WP8, WP9, WP12, WP15, WP17, WP19, WP20**.
   Use source-index.json for each worktree/branch/base/tip/result path. For each,
   read `git -C <source-worktree> log --reverse --format='%h %s' <base>..<tip>` and
   `git -C <source-worktree> show <tip>:<verify-result-path>`. These pinned reads
   avoid concurrent branch drift. Compare the ledger's question/verdict, every
   test count and key numerical claim with the actual report; read its named NOTES/
   evidence where needed. Check listed changed files with `git diff --name-only
   <base> <tip>`. Do not merely trust WP23's prototype output or search for numbers
   without reading their scope. Ten matching SHA strings alone is insufficient.
   Retain a compact table in evidence/mvpfix/wp23/fresh-spot-check.md:
   WP, source tip, result path, exact suite counts, key measurement/limit, verdict.
3. Additional bounded checks: WP21 has no VERIFY-RESULT at 33112b07; its copied
   partial dry run is not fresh verification. WP22 at 8938cb2c has no commits since
   its branch base; inherited ancestry does not mean WP22 was merged. Read actual
   first-parent history at c609d7f3: WP4 arrives via WP7; final recorded frontend
   count 230/230 at a92bb4aa; focused export 22/22 at 79467f08; no final full-Python
   count in those messages. Confirm WP19 tip 16460396 is merged and WP12 tip a2ee97eb
   is not. Do not claim current branch tips unchanged if they have advanced.
4. Check the six deliverables are internally consistent:
   - ledger 22 rows; contract 31 ticket rows with original states unchanged;
   - PR draft pin c609d7f3, no launch/attended/capacity/summary claim;
   - attended estimate 120 min, trusted target TLS, physical MacBook mic/Chrome,
     six echo conditions, G7 x2 (headphones and speakers+AEC, BOTH source scenarios
     each), phrase 7/8 ordered, visual sizes, real summary key, VP7/17 cases,
     P3/P4/D3/D5 decisions; no host action granted by prose;
   - smoke uses actual supported lane/browser commands and conditional WP21 command;
   - limitations preserve WP17/WP20 quality failure, quiet additions, WP12 isolated
     before/after limits, 332.007926 s/15 windows, WP15 RSS and WP22 pending.
   - WP19 File enrollment MP3 exception is narrow; saved naming no longer active-only.
   - all local Markdown links exist; no private content or secrets introduced.
5. Run `bash scripts/check_verify_layout.sh` and `git diff --check`. Inspect changed
   paths since c609d7f3; only docs and evidence/mvpfix/wp23 may differ. No runtime
   benchmark started by WP23, no process/tunnel to stop. Do not run more product tests
   merely to reproduce the already retained full-suite pass.

## Finish

Write docs/verify/wp23/VERIFY-RESULT.md: actual fresh-context provenance (do not claim
witnessed reset from a queued-command file alone), tested docs SHA, 10/10 outcomes
or exact failures, additional checks, corrections and remaining boundaries. Update
NOTES.md pending status with the true result. Record exact full-suite numbers as
PREPARATION counts, not newly executed tests. Commit docs/evidence locally; clean tree.
Then <=60-line final report in THIS pane: branch/final SHA; census question/verdict;
six deliverables; 10-row fresh result; 1901/2/37 Python and 249 frontend scope;
key limitations; deviations; no push/merge/deploy/GitHub. Link ledger/result.

Preparation used memory only for evidence/qualification boundaries. Carry this
citation at the very end of the final report (not in any PR description):
<oai-mem-citation>
<citation_entries>
MEMORY.md:744-755|note=[evidence scope and local verification versus release acceptance]
</citation_entries>
<rollout_ids>
01a09220-a1e7-75a3-9881-6416f9e300f4
</rollout_ids>
</oai-mem-citation>
