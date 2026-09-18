# WP34 — fresh-context ten-row spot-check

Run only in a fresh `/new` session, after preparation commit. First cd:
`/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp34-ledger-refresh`.
Modify nothing outside this checkout. Other worktrees read-only. No push, merge,
rebase, deployment, GPU, provider, GitHub or peer messages. Commit result locally.

Read in order COMMON.md then WP34-ledger-refresh.md under
`/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/`;
then local AGENTS.md, this file, evidence/mvpfix/wp34/NOTES.md and five deliverables.
Read required prototype skill; existing census is sufficient, no new algorithm.

1. Record current CODEX_THREAD_ID, worktree, branch, initial HEAD and clean status.
   An expected untracked `evidence/mvpfix/wp34/context-transition.json` may be
   created by the own-pane transition after preparation commit; record it separately.
   Compare thread to drafting `01a0b3c1-9ac9-7290-94f7-e0e7902007ed`. A different
   shell alone is not fresh context; transition record alone does not prove it.
   Failure detects wrong context/checkout; stop that claim and report truthfully.

   ```sh
   pwd
   git status --short --branch
   git rev-parse HEAD
   printenv CODEX_THREAD_ID
   ```

2. Independently inspect exactly **10 new rows: WP23–WP32 inclusive**. Read their
   pinned objects using source-index.json's tip/base/path, not just the copied
   reports. For each, run these with the actual values substituted:

   ```sh
   git log --reverse --format='%h %s' <base>..<tip>
   git diff --name-only <base> <tip>
   git show <tip>:docs/verify/wp<N>/VERIFY-RESULT.md
   git rev-parse <branch>
   ```

   WP25/WP30 show must fail because no committed result existed at their pins;
   this is expected absence, never passing verification. Compare WP25 committed
   long summary and workspace_row_4/demo_lanes logs, and WP30 committed NOTES/smoke.
   WP25 incomplete working-tree report retained in sources is explicitly provisional;
   do not promote it to a completed fresh run. If branch advanced, record drift
   separately and keep the frozen snapshot, unless the row was factually wrong at pin.
   Match question/verdict, SHAs, commit/file inventories, exact fresh counts,
   historical failed attempts, key numbers and unmeasured scope. Discrepancy falsifies
   the row: fix docs, record before/after and recheck only affected claims.

3. Verify five numerical/semantic groups from original reports/objects:
   - N1: WP12 Stop 3.788534/7.490138/16.964282 s; WP22 101.697916 s /1800 s,
     capture RSS 932.4375/981/973.25 MiB versus post-final 1148.953125; WP29
     +25.6875 MiB is one second-session stub increment, owner unknown.
   - N2: WP28 resolver 93.031965 s /15 windows, serial 320.838881; fixture equality
     and fresh 1929/2/37 with 2 real fixtures executed.
   - N3: WP25 distinct long workspace 11/106 and standalone 9/106 system final;
     mic immediate 11/53 against bars .095074/.166655. Capacity 0/4 under
     contention, before terminal starts, four voiced system lanes, not eight.
   - N4: WP31 base rollback 8/8 reads, 0/8 lanes, 32/40 exports; integrated 40/40.
     WP32 F1–F5 still open at a625d1a1; WP33 tip=base and zero package commits.
   - N5: lead integrated ladder JSON: 8 cases, 5 overlap cases, 37/37 +32/32
     witnesses, n=1. Open external source from brief; compare retained bytes.
     Check 28 first-parent package merges (WP4 via WP7); the reported full-suite
     sequence is absent from merge/build messages and must stay brief-attributed.
   These detect conflated scope/numbers; correct only claims contradicted by evidence.

4. Check document coherence and packaging: 34 package headings, 31 ticket snapshot
   states (16 OPEN/15 CLOSED), all local Markdown links in the five edited docs
   resolve; old WP1–WP22 rows explicitly historical. Attended plan links WP24 pack
   and covers WP27 setup states, distinguishes open ended-track issue. Required
   summaries/hidden tab/physical G7/visual/host acceptance remain unclaimed.
   Inspect diff against a625d1a1: only docs/ and evidence/mvpfix/wp34/ allowed.

   ```sh
   bash scripts/check_verify_layout.sh
   git diff --check
   git diff --name-only a625d1a1
   ```

   Read retained preparation suite logs/statuses: 1945 Python passed/5 skipped/
   37 subtests, frontend 265/28 files, both exit 0. **Do not rerun suites or live
   benches for this docs-only spot-check**; COMMON full gates already preceded
   VERIFY.md. If prose is corrected, check affected source and document links.

5. Write docs/verify/wp34/VERIFY-RESULT.md and
   evidence/mvpfix/wp34/fresh-spot-check.md: actual context identity, per-row sources,
   pass/fail denominator, all corrections, branch drift and limits. Update NOTES
   and WP34 ledger row from pending to actual outcome; keep preparation versus fresh
   execution distinct. Normalize only new log whitespace if needed, leave source
   snapshots exact. Check staged whitespace, commit locally, verify clean status.
   Any inherited source-snapshot whitespace must be identified, not falsified as a
   product failure. No servers should have been started. Report <=60 lines in this pane:
   branch + final SHA, prototype verdict, changed files, exact counts/measurements,
   remaining failures/unknowns and deviations. Do not call passing documentation
   verification product acceptance. No peer dispatch needed.
