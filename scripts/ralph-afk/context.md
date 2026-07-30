# Context - MOSS live meeting transcription MVP

> **Compaction log — eight passes, every one archived VERBATIM to progress.txt, nothing deleted.**
> Grep progress.txt for `ARCHIVE OF context.md` to read any pass in full. **This log is the ONLY
> record of a pass** — the per-pass bullets that used to duplicate it in "Where the loop stands" went
> to progress.txt with the seventh.
>
> | pass | run / iteration | before → after | what went |
> | --- | --- | --- | --- |
> | 1st | `20260728-181020` it. 10 | 339 018 → 129 832 B | every per-iteration gate transcript, contract block, redeploy record and closed-phase candidate list |
> | 2nd | `20260728-181020` it. 30 | 257 135 → 183 529 B (−28.6 %) | 20 blocks: K5d, the F1/F3 diagnoses, the Phase L/M mechanism narrative, the three D-c measurements, the merge and redeploy records |
> | 3rd | `20260729-025318` it. 14 | 245 562 → 148 157 B (−39.7 %) | 26 blocks, including **11 ranges of the Validation fence** (closed phases' per-node recipes, spent one-time host recipes) and the Phase L/M/P candidate lists |
> | 4th | `20260729-094359` it. 2 | 263 219 → 199 877 B (−24.1 %) | 8 ranges: the Phase-N landing narrative and its 12 per-step blocks, the superseded `N1`-`N5` list, 22 closed rows of the gates index, candidate 60's full block, F1-on-`42abc5a`, the test-totals chain |
> | 5th | `20260729-094359` it. 8 | 249 137 → 210 671 B (−15.4 %) | 14 ranges: the four compaction narratives themselves, the two retired-evidence index tables (merged into one), the standing summary's it. 3–7 bullets, the F1/F2/F3 certification narratives, Phase N's spent gate/merge/redeploy rows, the port-publish race, and the superseded layers of candidates 55/60/65 and decision 19 |
> | 6th | `20260729-094359` it. 11 | 227 379 → 215 772 B (−5.1 %) | **the Validation fence, as the fifth pass planned**: 16 ranges — the C1/K3/H-blocker/J5d/F4a/M6c narrow recipes, the four Phase-N red-before revert ladders, candidate 65's five-probe cause chain, the spent keeper-merge notes, and three stale duplicates |
> | 7th | `20260729-094359` it. 14 | 231 932 → 218 689 B (−5.7 %) | **the Candidates section, as the sixth pass named it**: 9 ranges — candidate 55's six re-pricings, 65's four-iteration cause chain, 60's four, 63's `[open]` history, 67's pre-fix description, the five-iteration 55/60/65 chain in the standing summary, the four compaction bullets that duplicated this log, two spent probe-instrument recipes, and the six compaction narratives' prose. **27 747 B of ranges out, 9 539 B of distilled pointers in (net −18 208), and this pass's own record +4 965 B back.** Plus **six staleness repairs**: three assertions of a claim iterations 7 and 12 falsified, candidate 65's title re-filed as iteration 12 instructed and no iteration had applied, F1's and F3's `[…]` tags still naming superseded runs, and two broken block pointers — see rule (1) below |
> | 8th | `20260729-094359` it. 19 | 241 160 → 233 281 B (−3.3 %) | **"Read before any certification run", as the seventh pass named it**: 4 ranges — **the four overlapping sweep blocks merged into one** (session-end it. 7, at-F2's-fragmentation it. 9, cadence it. 12, probe-reduction it. 13 → one block with three tables and four numbered instrument rules), the "three certification runs have one home now" pointer, the Phase P/M landing bullets plus the "Phase M proven on the real hosts" bullet that duplicated the retired-evidence index, and the "eighth authorization landed" bullet that restated prd.md a third time. **20 114 B of ranges out, 11 161 B of distilled pointers in (net −8 953), and this pass's own record put 1 074 B back.** Plus **four staleness repairs and nine cross-reference retargets onto one anchor** — see rule (1) |
>
> **The trigger to watch is the `Read` tool's 256 KB HARD CAP, not a `Read` count.** At 263 219 B the
> fourth pass opened with `File content (257KB) exceeds maximum allowed size` and context.md had to be
> paged blind by offset before any work could start. Measured drift is **~5-10 KB per iteration**, so
> a pass is due roughly every ten. *Honest limit, unchanged since the second pass:* the `Read` tool's
> binding limit is **tokens** (25 000 tokens is 51-61 KB of this prose), so **one `Read` is not
> reachable** without cutting something load-bearing; three to four is the working target.
> **How to run one:** archive the ranges **verbatim** under a banner in progress.txt, then verify by
> script that each body appears byte-for-byte there **and is absent here**, and that the surviving
> fence still passes `bash -n`.
> ***The `bash -n` half of that recipe was WRONG, and iteration 22 found it while adding to the
> fence.*** Run on the whole section the fence has been **failing since at least the M6c entry**,
> and iteration 21's bench block added a second failure - not because a command is malformed but
> because bash parses **prose**: a backtick in a comment opens a command substitution once an
> earlier odd apostrophe has closed the quote that was hiding it, so `` `simulate(birth_floor=)` ``
> and `` `rollback: mv <backup> <output>` `` both abort the parse. The check to run is
> **commands-only**, which is what a fence actually promises:
> `awk '/^## Validation/,/^## Candidates/' context.md | grep -v '^#' | bash -n` — **93 command
> lines, rc=0, at HEAD and after.** *A check that has never failed is not necessarily a check that
> passes; this one had stopped reading the thing it named.* New evidence goes in as *the conclusion plus the numbers that justify
> it* - the transcript belongs in progress.txt when it is written, not later.
>
> ***Two rules the seven passes produced, and rule (1) is why a pass is worth an iteration even when
> the file is not yet at the cap.***
> **(1) A SIZE PASS CATCHES STALENESS, because a claim no iteration re-reads is exactly the claim
> that goes stale.** The fourth caught seven "not deployed" rows for code that was deployed; the
> fifth caught nine sentences iteration 7 had already falsified; the sixth caught four stale values
> **inside executable recipes**, the worst being F4a's restore line reading `git checkout 317df4d` -
> the **second of eight** merges - which, followed literally in an emergency, would have rolled the
> server back six merges and left it there. **The seventh caught the same falsified claim surviving
> in the two worst places of all:** a numbered *"recorded here so they are not re-argued"* decision
> (18) and the sequencing premise of **the one open item the loop can start without the operator**
> (N-batch). Both still said *"neither half of step 3 publishes a correction on the deployed
> system"* after iteration 7 measured 19 corrections and iteration 12 measured three more.
> *A stale sentence misleads a reader; a stale command misleads a host; a stale premise misleads a
> DECISION, and that is the one that costs a phase.*
> ***And a corollary the seventh pass paid for twice:*** **the scoreboard row and the candidate entry
> for the same clause drift apart, because only one of them is re-read after a run.** F1's entry
> still read `[GREEN]` off a superseded `42abc5a` run while the scoreboard above it carried the RED,
> and F3's still pointed at iteration 9's `42abc5a` soak after iteration 12 re-ran it on `7a4f59c`.
> **After any certification run, correct BOTH.** Likewise a title: iteration 12 wrote *"re-file 65"*
> and no iteration did it for two passes, so the falsified headline kept being cited.
> ***The eighth pass extended that corollary one level up, and this is the cheapest staleness there
> is to prevent:*** **A HEADER IS RE-READ LESS OFTEN THAN THE TABLE IT INTRODUCES.** The PRD
> scoreboard's own header still read *"the two certification rows are RED-and-stale … F1 and F3 have
> never run against Phase M"* — true when `77e0014` was the newest deploy, and left standing through
> **two merges, one redeploy and three certification runs on `7a4f59c`**, while every row underneath
> it was corrected each time. The rows were maintained precisely because they are what an iteration
> reads; the sentence above them was not. *Its sibling in the same pass:* the standing summary still
> told a reader that **"what now stands in front of Phase N is candidate 60"** after Phase N had been
> written, gated, merged, deployed and certified. **When a row moves, re-read the sentence that
> introduces it.**
> **(2) A SHA inside a recipe is not a fact, it is a cache, and every redeploy invalidates it** - the
> Validation fence says so at each site that holds one.
>
> **Section sizes RE-MEASURED at the eighth pass, naming the NINTH's target without argument.**
> Candidates **74.6 KB (33 %)** — the largest again, and the seventh pass's "63.6 KB" is not
> comparable because Phase N grew 11 KB after it — Validation fence **39.5 KB** (490 lines, `bash -n`
> clean, untouched here), "Read before any certification run" **33.4 KB** (was 40.3 before this pass),
> "Where the loop stands" **26.7 KB**, "Deployed reality" 16.3 KB, shipped contracts 13.6 KB, gates
> index 10.8 KB, compaction log 7.8 KB. **The ninth pass's target is the Phase N section (38.4 KB
> inside Candidates), specifically the two N-batch probe narratives** that iterations 17 and 18 added
> (~7 KB between them): they are the baseline and the counterfactual for **step 4, which the loop is
> authorized to write and forbidden to merge**, so they can become one table of two engines and three
> findings the moment a ninth merge is authorized or step 4 is closed. Second target: "Open diagnostic
> candidates" at 26.2 KB. *Re-measure with the `## heading` script rather than trusting this line —
> it has been wrong once already, when a section grew under a stale figure.*
> **Headroom: NONE — the file passed the 256 KB cap during iteration 22 and now reads 271 KB.**
> (The eighth pass wrote "~22 KB below"; it. 20 +2.7 KB, it. 21 +26.5 KB — Q1's landing was five
> times a normal iteration — and it. 22 +9.8 KB spent it.) **The ninth pass is DUE NOW, not in
> five.** Its target is unchanged and named below: Phase N's two N-batch probe narratives, then
> "Open diagnostic candidates". Nothing is blocked — since iteration 16 the `Read` tool pages this
> file rather than refusing it — so the cost is pages per iteration, not a stalled start.
> **One new fact about the trigger, from iteration 16:** the `Read` tool now **pages** this file
> instead of refusing it — it returned lines 1-537 of 2293 with `showing … cap 25000 tokens` and a
> pointer to `offset=538`. So the 256 KB cap is no longer a wall that stops work; the **token** cap
> is what binds, and the cost of drift is now *more pages per iteration*, not a blocked start.
> Weigh the eighth pass on that basis rather than on the fourth pass's hard-failure story.

## Ground

- Repo: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize` — branch
  `ralph/live-meeting-mvp` (cut from `main af3ac36`). Keep all client and server implementation
  on this branch; merge **once** only after Phase A, production-client, server-reliability, and
  tracked deployment/install-artifact gates are all green.
- Orchestrator host: MacStudio. `python3` = pyenv 3.12.10 (pytest 9.0.2); `swift` 6.3.2.
  Do **not** use `/usr/bin/python3` (3.9.6).
- Read before editing:
  - `/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/docs/live-capture-gap-and-execution-plan-20260727.md`
    — current controlling revision, the design rationale and decisions D1-D14. Authoritative.
  - `CONTEXT.md` (repo glossary — lane, mixer, v2 contract, portal, helper terms)
  - `docs/adr/0001-live-v2-json-http-contract.md`
  - `docs/adr/0002-two-tier-diarization-fingerprint-album.md` + `docs/design-streaming-diarization.md`
    — the authoritative live-identity design (Phase N); `docs/adr/0003-live-session-audio-retention.md`
    — the retention bound step 2 must implement
  - `LOCAL_DEPLOYMENT.md` (server layout; Phase C updates it)
- **Ignore `scripts/aisight-coding-loop/`** — an inert older loop bundle with identically named
  `prd.md`/`context.md`/`prompt.md`/`progress.txt`. This loop lives only in `scripts/ralph-afk/`.
- Key code paths:
  - `moss_transcribe_diarize/app/live_auth.py` — view/capture authority, peer allowlist, pairing
  - `moss_transcribe_diarize/app/live_transport.py` — the live HTTP routes
  - `moss_transcribe_diarize/app/live_coordinator.py` — PCM → endpoint → decode → publish
  - `moss_transcribe_diarize/app/live_mixer.py` — lane mixdown and resampling
  - `moss_transcribe_diarize/app/live_ingest.py`, `live_lane_contract.py` — v2 lane ingress, replay
  - `moss_transcribe_diarize/app/live_provider_bundle.py` — manifest admission and config hashes
  - `moss_transcribe_diarize/app/live_portal.py` — the `/live` page
  - `moss_transcribe_diarize/app/web_cli.py` — `--live` flags, TLS wiring, runner proxy
  - `macos/MOSSCapture/Sources/MOSSCaptureCore/*` — capture, transport, security, native lanes
  - `ops/` — env, start scripts, systemd units, Windows networking

## Where the loop stands

**Branch and freeze.** Branch `ralph/live-meeting-mvp`, cut from `main af3ac36`. Fourteen phases have
landed on it (A-E client/server/deploy/install, then six operator-authorized post-merge fix cycles
G, H, J, K, M, P, and Phase N). **Eight keeper merges have been made and all eight are spent** —
`f9285d6` (C4), `317df4d` (G5), `b817871` (H4), `6a540fe` (J5b), `fc7097d` (K5b), `77e0014` (M6),
`42abc5a` (P7), **`7a4f59c` (N8, run `20260729-025318` iteration 28)** — and `merge-keeper.sh`'s
`expected_main` guard now refuses a **ninth** (rehearsed non-vacuously immediately after the eighth:
`main moved from expected pre-merge SHA 42abc5a…`, rc=1). **Phase N steps 1-3 are MERGED, PUBLISHED
AND DEPLOYED (iteration 29, gate step (c)): four checkouts at `7a4f59c`, the album running at the
calibrated 0.35/0.1.** Every tracked product change since `f9285d6` was made
under a named amendment. Per-phase detail is in the closed-phase index below and in full in the progress.txt
archive.
**The push spent the merge's own rollback.** `git update-ref refs/heads/main 42abc5a` was a complete
undo until iteration 29; `origin/main` is now published at `7a4f59c` and force-push is forbidden, so
undoing the eighth merge means a **revert commit**, which is a new merge and needs its own
authorization. What remains available is host-local: checkout + restart, and the manifest copy-back.
**One non-Ralph commit is on the branch.** `00620ab` *"docs: streaming diarization design +
ADR-0002 (two-tier, fingerprint album)"* was authored by **AlphaSightInc** at 03:23:50Z on
2026-07-29 — i.e. the operator committed to the feature branch **while iteration 5 was running**, and
the branch tip moved under the loop. It adds two files under `docs/` and **no product source, no
test and no `ops/`**, so it changes nothing this loop has measured and nothing the service reads. It
is why, between iterations 5 and 14, `git diff --name-only 42abc5a HEAD -- ':!scripts/ralph-afk'`
listed `docs/adr/0002-two-tier-diarization-fingerprint-album.md` and
`docs/design-streaming-diarization.md` instead of being empty. (Both files reached `main` with the
eighth merge, so that diff is empty again against the deployed `7a4f59c`.) **Do not revert it** and do not treat it as loop drift; do re-check the tip
before any future merge, because the freeze's "only Ralph evidence changes on this branch" premise no
longer holds by itself.
**IT HAPPENED AGAIN IN ITERATION 6, and it is now a standing hazard, not an anecdote.** `128eae4`
*"docs: prototype gates A/B/C passed - ADR-0002 accepted"* was committed by the operator at 23:48:25,
**35 seconds before** this loop's own iteration-6 commit — the second concurrent operator commit in
two iterations, both `docs/`-only. Nothing was lost this time (`git show <my sha> -- docs/` is empty,
because the operator committed their own work first), but the near-miss is the point: **`git add -A`
on this branch can stage an operator's uncommitted work-in-progress and publish it under a `ralph:`
commit message.** *The durable rule:* stage this loop's evidence **explicitly** —
`git add scripts/ralph-afk/` — or, when a product change is in play, stage the reviewed payload by
path. Never `git add -A` here again. And check `git log --format='%h %an %ad %s' --date=iso -5`
before any merge: the tip may have moved twice since the iteration began.
**A THIRD TIME, AND THIS ONE CARRIED AN AUTHORIZATION.** `0456177` *"ralph: supersede Phase N with
ADR-0002"* was committed by the operator at 01:36:54 — **2.5 minutes after** iteration 14's own
commit — and it edits **prd.md and context.md**, i.e. the loop's own working memory and its
contract. *The durable consequence, which cost this iteration a near-miss:* iteration 14 recorded
"prd.md is unchanged at seven amendments, so everything is frozen", and that sentence was **false
within three minutes of being written**. **Re-read prd.md's tail and `git log --oneline -3 --
scripts/ralph-afk/prd.md` at the START of every iteration, and never trust a previous iteration's
report that no authorization exists.** An iteration that had believed its predecessor here would
have compacted context.md a fourth time while an authorized phase sat open.

**PRD acceptance scoreboard. Every row below is CURRENT against the deployed `7a4f59c`** — F1, F2
and F3 have each been re-run on it (iterations 30, 1 and 12), so a RED here is RED-and-current, never
RED-and-stale. *Repaired in the eighth compaction, which is the shape rule (1) predicts:* this header
still said *"the two certification rows are RED-and-stale … F1 and F3 have never run against Phase M"*
— written when `77e0014` was the newest deploy and left unread through two merges and three
certification runs, while the rows underneath it were maintained every time. **A header is re-read
less often than the table it introduces; correct it with the rows.**

| clause | state |
| --- | --- |
| IDEA-044 compatibility checkpoint | GREEN, frozen at `1ede498` (10/10 and 16/16, 11 commands, 0 Darwin skips) |
| Production client gate | GREEN (B6 `3fb5567`, re-gated G4 `23dc163`, K5a `cd7faf9`) |
| Server meeting-reliability gate | GREEN at `f400d426`, clause→node map recorded |
| One reviewed keeper merge (+ 7 authorized follow-ups) | GREEN, eight merges, each reviewed against its amendment's scope |
| One exact SHA everywhere | **GREEN — 4/4 at `7a4f59c3ca023b5ac7b9df814b92645c10d204dd`** (iteration 29, gate step (c)). Local `main` == `origin/main` == server == m4mbp, and **both host checkouts report tree `16de7f6264deca…`**, the merge's own tree — so the deployed *content* is proven identical to the reviewed one by hash, not by SHA alone. |
| Live service answering | GREEN — `/live` and `/api/live/descriptor` 200 over the pinned leaf from MacStudio **and from m4mbp** |
| Batch service unharmed | GREEN — `http://192.168.68.38:7860/` and `/api/jobs` 200; batch MainPIDs never restarted |
| Signed app installed | GREEN — and "DR unchanged across a rebuild" proven *across an actual rebuild* in K5c |
| Permissions granted | **GREEN** — both TCC grants `auth_value=2`; `mtd-capture status` reported both lanes `capturing` through a 672-frame meeting (K5d) |
| Rollback rehearsed and recorded | GREEN (F4a) |
| 60 s canary (F1) | **RED ON THE DEPLOYED `7a4f59c`, AND SINCE ITERATION 22 THE RED IS ONE CLAUSE, NOT TWO.** The run is unchanged (iteration 30, Phase N gate step (d) first half, rc=3); what changed is the **reducer**, which now answers the RTF clause by Q2's derived definition. Re-reduced: **seven GREEN and ONE RED** — decoder p95 RTF **0.580** over 49 spans >= 0.13 s (3 excluded, their RTF 2.365–3.599, printed in the verdict sentence) plus a new **aggregate RTF 0.203** over all 52 spans with nothing excluded, both GREEN; the surviving RED is user-visible p95 **4150.8 ms** (miss by 150.8 ms, 3.8 %). **The RTF number that stood here was 2.365, carried entirely by 3 spans shorter than 0.1 s — candidate 70 records why that is a measurement of the decoder's fixed per-request cost and not of the decoder.** F1 is still re-run as Phase Q's gate; this is a re-reduction of existing evidence, not a new run. See the **F1 on Phase N** row in the gates index (the narrative block is retired to progress.txt with the fifth compaction). *Superseded, kept for one reason:* F1 was **GREEN on `42abc5a`** (iteration 6, rc=0) at p95 **3909.3 ms** and RTF **0.911**, 329 published == 329 accepted, and that is the **only** run in this loop's history where the user-visible clause passed at the 4000 ms gate. **One half is NOT certified in either run:** "two speakers" were both on the *system* lane (candidate 51's measured microphone limit). **ITERATION 15 PRICED THE LATENCY RED: the plan's own second ordered remedy (0.5 s poll) subtracts exactly 500.0 ms, taking it to 3650.8 ms — GREEN with +349.2 ms margin — and touches no domain-contract value.** The RTF RED is untouched by it — and is **now answered separately** by Q2's definition (candidate 70), so **the latency miss is the only thing standing between F1 and green**. **ITERATION 23 APPLIED THAT REMEDY ON THE BRANCH (Q3, candidate 71) — both halves at 0.5 s, with an enforcing node in each language.** The −500 ms is **arithmetic on a report, not yet a measurement**: this row stays RED until Phase Q's own F1 re-run measures it on a redeployed build. See the latency-remedy block and candidates 71 and 68. |
| 300 s certification (F2) | **GREEN ON THE DEPLOYED `7a4f59c`** (run `20260729-094359` iteration 1, `live-canary-clauses.py --user-visible-gate-ms 6000 --interrupt-report` rc=0): six GREEN, no RED, no UNDECIDED. user-visible p95 **4078.6 ms** ≤ 6000 **and qualified**, decoder p95 RTF **0.577** < 1, **1261 published == 1261 POST /frames, and every one of the session's 4766 logged requests answered 200**, a **5.090 s** interruption seen by the client and survived, outbox 0 → **5** → 0. (Was GREEN on `42abc5a` in iteration 11 of the previous run: 3859.6 ms, RTF 0.670, 1257 == 1257 — that block is archived in progress.txt.) **One half is NOT certified and was deliberately not attempted:** the separate mic-granted / system-audio-denied run, which would spend a TCC grant. See the **F2 on Phase N** row in the gates index (the narrative block is retired to progress.txt with the fifth compaction) |
| 16-minute soak (F3) | **RE-RUN ON THE DEPLOYED `7a4f59c` (run `20260729-094359` iteration 12) — 5 GREEN, 1 RED, rc=3, and it is now the current F3 evidence.** 17/17 full minutes, 648 spans, 381/381 portal polls 200, view authority 200 at age **903.6 s and 1023.0 s**, user-visible p95 **4106.5 ms** ≤ 6000 **qualified and `timelineIntact` true**, decoder p95 RTF **0.568**, **no lane fault at all**, clean drain `retained=0`. The RED is **candidate 60**, unchanged and expected — the Mac client never calls `POST …/stop`, so the post-stop view check answered 200. **ITERATION 24 FIXED IT ON THE BRANCH (Q4, candidate 72): the client now calls the route after its final drain.** The row stays RED until Phase Q's own F3 re-run measures it — and that re-run needs the **m4mbp rebuild+reinstall**, because the app that answers `stop` is the one in `/Applications`, not the one in this checkout. **The run also falsified candidate 65's headline: the CADENCE sweep published three corrections mid-meeting.** See the **F3 on Phase N** row in the gates index and the deployed-sweep block below (§1). (The prior `42abc5a` run — iteration 9 of run `20260729-025318`, same 5/1 shape — is superseded as evidence; its row is kept in the gates index for the before/after deltas.) |
| Secret hygiene | static half green; run-time half green in F1, F2 and F3 as far as those runs went. **The *browser storage* half is now MEASURED ON THE DEPLOYED PAGE — iteration 10, `portal-storage-probe.py` rc=0, five clauses GREEN, six negative controls all detected.** It had never been measured at all: `leak-scan.sh` never scans the portal (iteration 7), the tracked static assertion (`tests/test_live_portal.py:217-219`) reads a **locally rendered** page, and the harness's `storageWrites` recorder (`:618,657,737,812,841`) has **no assertion anywhere in the suite** — dead instrumentation a runtime write would pass. See the portal-storage block below. **What is still open is the tracked *regression*, not the evidence — candidate 66** |
| Final close (F4b) | open |

**What stands between the loop and the bar (rewritten in the eighth compaction, iteration 19; the
Phase M/P landing narratives it used to carry are in progress.txt under that pass's banner).**
- **PHASES M AND P ARE CLOSED, LANDED, DEPLOYED AND PROVEN ON THE REAL HOSTS, and their landing
  narratives are retired to progress.txt with the eighth compaction.** What a future iteration needs:
  Phase P (candidate 56, the wall-clock duration) reached (a) gate `5bc4f7f` → (b) merge `42abc5a` →
  (c) deployed 4/4 → (d) F1 and F3 run to completion; Phase M (53/48/49/D-a/D-b/D-c) reached (a)
  `21a73ea` → (b) `77e0014` → (c) deployed → (d). **Both are proven fixed on the hosts, not merely
  merged** — candidate 53's minute-14.6 death has not recurred in any run since, candidate 56 did not
  fire in a 17-minute soak while the host clock was measured still stepping, and D-c took the
  committed p95 from 8343–9148 ms to **2567/2592 ms**. Their surviving homes are the **Duration vs
  timestamp** row in Shipped contracts, the Phases L/M and Phase P section stubs, candidate 56's
  entry, and the retired-evidence index — all of which say it without this bullet.
- **A SOAK DRIVER SURVIVES THE ITERATION THAT STARTED IT, and one iteration nearly threw 17 minutes
  away by not knowing.** Iteration 8 of run `20260729-025318` launched the F3 soak and then died with
  no record and no commit; iteration 9 found the driver still running at minute 6 and let it finish,
  which is the only reason that F3 evidence exists. The driver is `nohup`'d on m4mbp **by design** —
  before concluding a host is idle, `ps -eo pid,etime,command | grep live-soak`.
- **Candidate 55 — identity capacity saturates in the first minute — IS FIXED ON THE BRANCH AND NOT
  YET ANYWHERE ELSE** `[iteration 21, Phase Q item Q1]`. The diagnosis stands unchanged (16-speaker
  bound reached at t+45.5 s / t+51.8 s / t+65.6 s; 9 of 16 slots minted by one-word `Hi.` fragments
  of microphone ambient noise; degrades quality without ending a session, so no gate saw it). What
  changed is that the fix is written, measured and covered: **canonical speakers 16 -> 2-7 across
  eight fixture meetings, live accuracy 93.4 % -> 99.1 %, and 3.56 -> 3.00 with accuracy untouched
  on nine real interview clips.** Read candidate 69 for the rule, the seam and every number; it is
  the only place they live. **Not merged, not deployed** — F2's and F3's 16-canonical measurements
  still describe the running service.
- **Phase N's sequencing question is CLOSED by the operator, not by the loop** (`0456177`,
  iteration 15): *"Phase N remains authorized. Take it in ADR-0002's shape, not the sixth
  amendment's."* The evidence had already emptied the gate's reason — the sixth amendment sequenced
  N after M because "identity quality cannot be certified on a meeting that dies at minute 14.6",
  and F3 ran 17 minutes with a degraded lane — but the call was the operator's and they made it.
  Candidate 60 is a **stop-time** authority-revocation defect and cannot touch an identity
  measurement taken during a meeting.
- **THE EIGHTH AUTHORIZATION LANDED, AND ITS CONTENT IS NOT RESTATED HERE.** prd.md gained *"Phase N
  is SUPERSEDED by ADR-0002"* in operator commit `0456177`. It creates no new fix cycle, **re-shapes
  the already-authorized Phase N**, and ends its sequencing question with *"Phase N remains
  authorized. Take it in ADR-0002's shape."* The parameters, the four-step scope, the >= 90-95 %
  acceptance bar, the deliberate retention change and ADR-0002 §7's clean-read-speech caveat are
  stated in the **Phase N section** and in prd.md itself; this bullet restated them a third time and
  is retired to progress.txt with the eighth compaction. **Read the Phase N section, not a summary
  of it.**
- **PHASE N STEPS 1-3 ARE LANDED, GATED, MERGED (`7a4f59c`), DEPLOYED 4/4 AND CERTIFIED BY F1 AND
  F2.** The fourteen per-step narratives that used to sit here (album, recalibration, retention ADR,
  tape writer, wiring, declaration, sweep engine, convergence, sweep wiring, revision, session-end
  sweep, gate (a), merge (b), redeploy (c), F1, F2) are **retired to progress.txt under the
  fourth-compaction banner**. What a future iteration needs is in three places instead: the **Phase N
  step index** and the **decisions that outlive the steps** in the Phase N candidate section; the
  gates index rows (`Phase N gate step (a)`, `N8 merge #8`, `N8c redeploy`, `F1 on Phase N`, `F2 on
  Phase N`), which since the fifth compaction are the **only** home of F1's and F2's numbers.
  **Gate step (d) is
  complete in both halves:** F1 rc=3 (5 GREEN / 2 RED - user-visible p95 **4150.8 ms** vs the 4000 ms
  gate and decoder p95 RTF **2.365**, causes named as candidate 64 and the plan's latency remedies,
  neither a Phase N regression) and F2 rc=0 (6 GREEN - p95 **4078.6 ms** <= 6000, RTF **0.577**,
  1261 published == 1261 accepted, every one of 4766 logged requests 200).
- **THE FIVE-ITERATION CHAIN ON CANDIDATES 55 / 60 / 65 IS SETTLED, AND ITS STEP-BY-STEP RECORD IS
  RETIRED** (iterations 3-9; the full bullet, with what each step measured, corrected or falsified, is
  in progress.txt under the seventh-compaction banner). *Do not re-argue any of it from the record;
  the record was wrong twice and is now corrected.* **The surviving conclusions live in exactly two
  places and nowhere else** - the numbered entries for candidates 55, 60 and 65, and Phase N decisions
  19 and 20. Read those, never a summary of them.
- **F1's LATENCY RED IS PRICED, AND THE PLAN'S OWN SECOND REMEDY CLOSES IT** `[iteration 15]`. The
  gated number is `committedP95 + portalCycleMS + snapshotP95 + eventsP95`, verified to **0.000000000
  ms residual** on F3's real report, so the **portal poll is a whole 1000.0 ms (24.4 %)** of it and
  halving it subtracts **exactly 500.0 ms** — F1 **4150.8 → 3650.8** against the 4000 gate, **3.3×**
  the 150.8 ms miss. Remedy 1 (2.0 s span cap) moves a **domain-contract** value and remedy 2 does
  not, so the plan lists them contract-expensive first. The remedy carries its own defect, filed as
  **candidate 68**: the 1000 ms lives in two constants in two languages with **nothing tying them**,
  so moving the Swift one alone would improve a PRD number by 500 ms with no change to what a human
  sees. See the latency-remedy block below. **The authorization request is now current** and carries
  this as item (d), candidate 66 as (e), and the cost order to grant partially.
  **ITERATION 16 MEASURED THE ONE TERM THE PRICING LEFT UNMEASURED, AND THE HONEST LIMIT TURNED OUT
  TO BE WRONG RATHER THAN INCOMPLETE.** The stated cost — *"a fetch p95 rising under twice the request
  rate (F3: 381 polls → ~760)"* — named the **soak driver's** stream. The gated fetch p95s come from
  the **app probe's own** fetches at a fixed **0.25 s** (4001 samples over F3's 1019.724 s), a cadence
  neither constant touches, so the −500 ms has **no offsetting term** in the runs that measure it.
  What replaces the limit is narrower and points the other way: halving the portal's poll doubles a
  **real browser's** rate, and F1/F2/F3 open no browser, so a re-run **under-counts the cost** rather
  than over-counting the benefit. Candidate 68 gets *stronger*: the two constants are causally
  disconnected **in both directions**, so either one moved alone is wrong in its own direction.
- **PHASE N STEP 4 IS NO LONGER AN ORDERING ITEM — THE ENGINE IT REPLACES IS MEASURED, AND THE CHEAP
  VERSION OF THE FIX IS RULED OUT** `[iteration 17]`. The batch identity engine had never been scored
  on anything, so step 4 could not be told from tidying. Driven through production
  `IdentityResolver.resolve` on the **same eight meetings** and scored by **the album's own scorer**:
  **80.07 % mean / 63.33 % min** against the album's 93.44 / 92.18 — *the product's file mode is worse
  than its live mode on identical audio*, and that batch number is an **upper bound** (Tier A was
  handed a perfect local diarization). The decisive half is the second: **batch Tier B moves the score
  by exactly 0.0000000000 pp on every meeting**, and it still does at the album's 0.35/0.1 and at
  k=10, because `_tier_b_evidence:726` offers it only **singleton** components — 36 of 71 — and
  `cannot_link_conflict` refuses **195 of 310** proposals. **Retuning `IdentityResolverConfig` to the
  album's parameters is measured to buy nothing; step 4 must replace the linking structure.** See the
  N-batch block.
  **ITERATION 18 SUPPLIED THE COUNTERFACTUAL, AND IT IS +19.93 pp.** The **production live identity
  engine** over the **identical** batch input (the same `build_case`, imported rather than
  re-derived) scores **100.00 % mean / min** against 80.07 / 63.33 — **one canonical per true speaker,
  30 births for 30 voices** — with the whole gain at k >= 3. It wins at **batch's own 0.70/0.20** too
  (+19.90), so with iteration 17's zero the ruling closes **in both directions: step 4 is not a
  recalibration either way.** ***The 100 % is a CEILING and the probe measures why:*** a 150 s window
  carries 20-61 s per speaker, where the worst same-vs-cross cosine gap is **+0.190** — so what is
  proven is the **cause** (losing ~20 pp on a task this separable is structural, not perceptual),
  never the production number. Tier A adds **zero** once the album is present, at its most favourable.
  **The work is authorized; the ninth MERGE is not** — step 4 is now §4(f) of the request document.
  **ITERATION 20 REMOVED THE CEILING AND ONE OF STEP 4's TWO READINGS DIED UNDER IT.** Both
  iterations above measured a **perfect** local diarization, which is why `album_only` and
  `tier_a_album` both read 100.00 % and the choice between ADR-0002's two readings looked free.
  `degraded-causal-pass-probe.py` (rc=0, offline, 6 s) degrades the causal pass and hands the
  **identical** labels to both engines through one monkeypatched `build_case`; the `none` control
  reproduces 80.0667 / 63.3330 / 100.0000 / 100.0000 exactly. Under **over-segmentation**
  *"the album replaces both tiers"* is **worse than the engine it replaces** — **30.50 %** vs batch's
  57.84 (**−27.34 pp**) at @0.30, −24.99 at @0.60, still −13.04 after the sweep — while
  *"the album replaces Tier B only"* wins at every condition (**79.34 %**, **+21.50 pp**). **Step 4
  must keep Tier A, and this is the only measurement that says so.** The mechanism is counted:
  44 extra nodes produce **6** extra births, so **38 cut halves were matched onto an EXISTING
  canonical** — `assign_speakers` is one-to-one *within a span*, and **a window is not a span**, so
  the live path's one-to-one rule is false on the batch path and pushes the second half of a cut
  turn onto another speaker, poisoning that speaker's centroid as well. See the degraded-causal-pass
  block below.
- **THE ROUTING RULE - REWRITTEN IN ITERATION 20, BECAUSE THE NINTH AMENDMENT LANDED WHILE THAT
  ITERATION WAS RUNNING AND MOVED HALF OF IT.** `6e3e4fe` *"ralph: authorize the birth floor, the
  stop, the RTF gate and the cadence (Phase Q)"* was committed by the operator at 10:14:08, **eight
  minutes after** iteration 20 began, and it **grants candidates 55, 60, 64 and the cadence fix
  (68's enforcing node)** and **withdraws candidate 65 outright**. The list below was correct when
  iteration 19 wrote it and was false eight minutes into iteration 20 — the fourth time the operator
  has committed to this branch mid-iteration and the second time with an authorization inside it.
  **Read prd.md's tail and `git log -3` at the START of every iteration; never trust this bullet
  without re-deriving it.**
  **A FIFTH TIME, IN ITERATION 21, AND IT MOVED prd.md AGAIN.** `bb8daad` *"ralph: record the
  operator's real-audio bench evidence as binding"* landed at 10:21:37 while iteration 21 was
  running and added the ninth amendment's **item (e)**: the bench's real conversational audio
  **outranks the LibriSpeech fixtures wherever the two disagree**, the calibrated matcher is
  confirmed (not changed) at 0.35 / 0.1, and the F-certification distinct-voice harness takes the
  real corpora alongside TTS. Nothing was clobbered - the operator's own section and this loop's
  edits are both in the tree - but the near-miss is now routine enough to be a procedure: **stage by
  path, re-read prd.md's tail before writing the journal, and check the tip again before any
  merge.** Five commits, two of them carrying authorizations, one carrying a binding evidence rule.
  **AUTHORIZED AND OPEN — this is the loop's next work, and it needs no further permission:**
  Phase Q's four items (candidates 69-72 in the Phase Q section: the birth floor at 1.0 s of
  embedded speech, the RTF gate *definition*, the cadence fix with its enforcing node, and the Mac
  client's `stop`), their coverage gap, their gate (full Swift/Python → F1 and F3 → **one** merge →
  push → redeploy). **Q1 (candidate 69) LANDED ON THE BRANCH IN ITERATION 21** — measured, covered
  by nine red-before nodes, Python green at 809. **Q2 (candidate 70) LANDED IN ITERATION 22** —
  loop tooling only, so it re-opens neither suite. **Q3 (candidate 71) LANDED IN ITERATION 23** —
  both cadence halves at 0.5 s, an enforcing node in each language, Python **810** and Swift
  **159** green. **Q4 (candidate 72) LANDED IN ITERATION 24** — the Mac client's clean stop now
  reaches the server, five Swift nodes, six red-before directions, Swift **164** and Python **810**
  green. **ALL FOUR PHASE Q ITEMS ARE ON THE BRANCH; what is left is Q5's GATE** — the accuracy
  harness's canonical-count number, **F1 and F3**, one merge, push, redeploy **including the m4mbp
  rebuild+reinstall** (Q3 and Q4 both changed `macos/`, so the installed app is not what this
  checkout describes and F1 would measure the cadence remedy at 0.0 ms and F3 the stop at 200).
  **STILL needs an authorization:** candidates **58**, **66**, and **Phase N step 4** — which prd.md
  now names *"out of scope"* for Phase Q in as many words, *"worth its own authorization later"*, so
  the split iteration 18 recorded is now the operator's own wording. **Candidate 65 is WITHDRAWN**,
  not deferred: both sweeps publish on the deployed service and the two *"it never runs"* readings
  were this loop's own blind instruments.
  *Everything below this line is unchanged and still true:* the F2 system-audio-denied variant (producing it
  means taking a TCC grant away from `com.alphasight.moss.capture`, i.e. spending the one input this
  loop is forbidden to ask for again); F1/F2's "two speakers" half (blocked by candidate 51's
  **measured** hardware limit - m4mbp's built-in microphone cannot hear a second voice across the
  room, five runs now say so); and F4b, which closes only when everything else has evidence.
  **Does NOT need one:** **candidate 67**
  (done, iteration 13), **re-running any certification run**
  (F1/F2/F3 are the PRD's own clauses driven by loop-owned tooling against the deployed service and
  the installed bundle - iteration 12 re-ran F3 on this basis, spending no operator input and no TCC
  click), and this loop's own tooling and working memory.
  **SPLIT SINCE ITERATION 18, because the old wording was a premise a decision would lean on:**
  Phase N **step 4** used to be listed above as needing nothing. Half of that is right — prd.md's
  *"Phase N remains authorized. Take it in ADR-0002's shape"* authorizes the **work** — but
  `merge-keeper.sh`'s `expected_main` guard refuses a **ninth merge**, so the product change could be
  written and **could not be landed**, and it would break the offline-probe-speaks-for-the-deployed-
  service invariant for every iteration until it was. ***Authorized to write is not authorized to
  merge; say which one you mean.*** *Re-derive this whole list from prd.md's tail every iteration
  rather than from this line:* the operator has committed to this branch mid-iteration three times,
  once with an authorization inside it.
- **STEP 2's RETENTION IS CODE-COMPLETE AND OFF ON THE HOST.** `ops/moss-live.env` is host-local and
  untracked and the tracked template ships all three `MOSS_LIVE_RETENTION_*` keys **commented out**,
  so the deployed `7a4f59c` retains **no audio** and the PRD's *"no raw audio is persisted"* clause
  holds unchanged at every observable boundary. ADR-0003's two-form hygiene test is what to run at
  the moment an operator edits that host file.
- **Candidate 57 — the clause reducer called a passing latency number RED** `[done — iteration 29]`.
  Loop tooling, no authorization; fixed and proved on four real evidence directories. See "The
  reducer stopped calling a passing number RED" in progress.txt.
- **Candidate 52 - the seven compaction passes** `[third: run `20260729-025318` it. 14; fourth,
  fifth, sixth, seventh: this run's it. 2, 8, 11, 14]`. The four per-pass bullets that stood here
  **duplicated the compaction log at the top of this file**, which is the one place a pass is
  recorded; they are retired to progress.txt with the seventh compaction. **Read the log, not a
  bullet about the log.** What it carries that nothing else does: the 256 KB `Read` cap is the
  trigger, ~5-10 KB is the measured per-iteration drift, and every pass since the fourth has caught
  something **stale** as well as something large.
- **F3 IS NO LONGER STALE, AND THE RE-RUN FOUND MORE THAN IT WENT LOOKING FOR** `[iteration 12]`.
  The 16-minute soak was the last PRD clause whose evidence spoke for superseded code (`42abc5a`,
  i.e. **before** the album, tape and sweep). Re-run on the deployed `7a4f59c`: **rc=3, 5 GREEN /
  1 RED**, same shape as before, and every measured number moved the right way or held — user-visible
  p95 **4557.2 → 4106.5 ms** and this time `timelineIntact` is **true**, D-c capped **67 of 443 → 1
  of 648**, and the t+474 s lane degradation **did not recur** (no lane fault of any kind). The RED
  is candidate 60, unchanged. **The unplanned finding is the one that matters:** the **cadence** sweep
  published three corrections mid-meeting, which candidate 65 said never happens — see the
  deployed-sweep block below (§1). It also exposed candidate **67**, an instrument that reads the revision
  version off a surface that does not carry it. No product change, no authorization, no TCC click,
  no new device row (`pair` reuses the stored id), all three server MainPIDs and both TCC grants
  unchanged, batch 200/200.
- **THE INSTRUMENT EVERY SWEEP QUESTION IS ASKED THROUGH CAN NOW SEE THE ANSWER** `[iteration 13]`.
  Candidate 67 is **done** — `live-pipeline-probe.py`'s sweep reduction reads the revision version off
  `canonical_processed` rather than off a committed item that never carried it, an absent field is
  `null` rather than a silent 0, and the session-end half names its refusal. **It carried a second
  defect out with it:** `since_seq` is inclusive, so every poll re-delivered the previous poll's
  highest event and the probe counted it again — which is why three reports say `session_created: 2`
  and why iteration 9's fragmented run reported 62 spans for a 61-span meeting and RTF p95 0.190
  where the deduped stream gives 0.212. Red-before by semantic revert (17 failures), green after
  (`--self-test`, 0), and iteration 12's F3 histogram reproduced from its raw `events.tsv`. No
  product source, no host, no session. See the deployed-sweep block below (§5).
- **THE SECRET-HYGIENE CLAUSE'S LAST UNMEASURED HALF IS ANSWERED** `[iteration 10]`. The browser-
  storage half had **no** measurement of any kind — the tracked static check reads a locally
  rendered page, `leak-scan.sh` never opens the portal, and the suite's own `storageWrites` recorder
  has no assertion behind it. `scripts/ralph-afk/portal-storage-probe.py` measures the **deployed**
  page: rc=0, five clauses GREEN, six negative controls all detected, and the served script proven
  **byte-identical** to this checkout's render — the first time the deployed portal has been tied to
  a reviewed revision by hash. Loop tooling and one unauthenticated `GET`; no authorization needed
  and none available. What it does **not** buy is a regression: that is **candidate 66**, two
  asserts and one accessor in a tracked test, and the cheapest authorization on the list.
Candidates 55 and 56 are tracked product source under the post-merge freeze. **Candidate 54 is ANSWERED**
(iteration 11) and **candidate 51 is DONE** (iteration 12), neither spending an authorization: the
409 is `LiveV2SessionTerminalError` — `"v2 system lane is failed."` — armed by the client's *own*
heartbeat, **not** the `v2_out_of_order_frame` that was on record as likeliest; and the two lanes
now carry different content, which took no product change at all. See those two blocks and Phase M.

**E3 was the blocker for four runs; the clicks were necessary and not sufficient.** Both grants are
recorded and survive a bundle replacement. **Never ask the operator for those clicks again.**

**Test totals on the branch. Python re-measured whole at iteration 24 (Q4): 810 passed / 2 skipped /
368 subtests in ~73 s** (801 -> 809 at Q1: five preparer nodes and three provider nodes for the
birth floor, the accuracy harness's five candidate-55 nodes re-stated rather than added; 809 -> 810
at Q3: the Python half of the cadence-enforcing node; **unchanged at Q4, which touches only
`macos/`**). **Swift re-measured at iteration 24 — 164 passed / 0 failed, 0 warnings on a fresh
scratch** (158 -> 159: the Swift half of the cadence node; 159 -> 164: Q4's clean stop - two
controller nodes, two HTTP-adapter nodes and the portal-timings tie, with the production-wiring
node extended rather than duplicated). The two skips are the
pre-existing `tests/test_large_upload.py:155,175` Python-3.10 compatibility contract and are
**never** Darwin skips. The growth chain (604 -> 801 across Phase P and Phase N steps 1-3) and the
per-file node counts are retired to progress.txt with the fourth compaction - regenerate them with
the gate command in the Validation fence rather than trusting a copy. The dominant term is the
accuracy harness (**17.49 s** measured alone), then the tape suite (3.6 s); the sweep's own nodes
total 0.1 s of `call` time.

## Read before any certification run or client fix

**Retired evidence — ONE index (the second and third compactions' two tables, merged in the
fifth).** Thirty blocks that diagnosed, decided or recorded Phases K/L/M/P, the spent host recipes and
the four loop-tooling fixes were moved to progress.txt **verbatim**. Nothing was deleted: grep
progress.txt for any title below, e.g. `grep -n "The decode is bounded" scripts/ralph-afk/progress.txt`.
**Any cross-reference elsewhere in this file of the form "see <title> above/below" resolves through
this table.** The banners are `ARCHIVE OF context.md SUPERSEDED BLOCKS — RUN 20260728-181020
ITERATION 30` (the first twenty) and `… RUN 20260729-025318 ITERATION 14` (the last ten).
*The retirement trigger for all of them is met:* every defect they diagnose is fixed, merged,
deployed and proven on the real hosts — Phase M by iteration 26's two F1 re-runs (no lane fault,
**165 × 200** heartbeats through a permanently failing publish, committed p95 **2567/2592 ms** where
these blocks measured 8343–9148 ms), Phase P by the probe that ran its full plan on `42abc5a` where
it had died at t+31.5 s on `77e0014`.

| retired block (grep this title) | what it settled |
| --- | --- |
| **K5d — the re-read, and the answer** (it. 7) | both lanes failed `macos_buffer_overrun`, and the cause was a client-side wedge in `CaptureController.start` — not TCC, pinning, schema or duplicate helpers |
| **F1 — the 60 s canary, RED** (it. 8) | user-visible p95 10426 ms and 0.5 s of lane loss; the tail is **two** runaway spans, not a floor — which refuted candidate 43's premise |
| **F3 — the 16-minute soak, RED at minute 14.6** (it. 9) | 14 healthy minutes, then a throwing publish skipped `emitHealth` and the 30 s lease ended the meeting |
| **The three Phase M decisions, taken and binding** (it. 13) | D-a / D-b / D-c with the reasoning the amendment required in writing before the patch |
| **The heartbeat is uncoupled from the publish** (it. 14) | 53 + 48 as one shape, three red-before/green-after nodes |
| **D-a is landed** (it. 15) | overrun → degradation, two enums, the mailbox fence removed, the mailbox overflow given its own code |
| **The decode is bounded** (it. 16) | the `68 + ceil(87 × duration_sec)` cap and **how the tokens were counted** |
| **The failed lane is in the suite** (it. 17) | the Phase M coverage gap closed, both nodes red-proved by semantic revert |
| **The Phase M gate is green / the ORDER is settled by precedent** (it. 18) | gate (a) green at `21a73ea`; the certification order |
| **The sixth merge is made — `77e0014`** (it. 19) | both fences satisfied, payload 10 files / +983/−51, the guard now refuses a **seventh** |
| **M6c is deployed** (it. 20) | 4/4 at `77e0014`, deployment proven by a witness with a control word rather than by SHA |
| **F1's re-run is blocked on a sleeping Mac** (it. 21) | m4mbp off the tailnet; `live-canary-clauses.py` built and validated on three real directories |
| **F3 has a repo driver now** (it. 22) | `live-soak.sh`, the pruned snapshot body, and the reducer that had been passing two red runs |
| **D-c is MEASURED on the deployed service** (it. 23) | 58/58 spans carry the product's own cap; `capped_count` 0, so it was live-but-unexercised |
| **D-c's latency effect is MEASURED** (it. 24) | 8.129 s → 1.074 s, **7.571×**, on the deployed engine, reproducing F1's runaways within 4 % |
| **D-c's OTHER half is settled** (it. 25) | a capped span commits 18 segments; 9062 cut points, **0** terminal; F1's runaways held zero words |
| **The F3 driver would have aborted at minute 1** (it. 26) | the soak driver's abort glob matched every healthy poll — 85/90 wrong, then 90/90 |
| **Candidate 49's mechanism was wrong in the record** (it. 13) | the watermark, not the projection |
| **The lanes are separated** (it. 12) | muting separates the lanes, and the echo was **not** what made 16 canonical speakers |
| **The 409 is NAMED, and the meeting was survivable** (it. 11) | `LiveV2SessionTerminalError` → `"v2 system lane is failed."`; the peer lane and a later heartbeat both 200 |
| **F1 RAN TWICE AGAINST `77e0014`** (run `20260729-025318` it. 6 archive banner) | both runs cut at one instant with three simultaneous symptoms; the eliminations that ruled out lanes, heartbeat, host load and decode |
| **PHASE P IS DEPLOYED AND CANDIDATE 56 IS DEAD ON THE REAL SERVER - P5(c)** | the deployed `42abc5a` ran the identical probe that died at t+31.5 s on `77e0014` — 300/300 ticks, 0 non-200s — and gave the project its first trustworthy RTF (p95 **0.18**) |
| **CANDIDATE 56 IS ANSWERED, AND THE CAUSE IS THE HOST'S WALL CLOCK** | the failure record, the mechanism (`vllm_runner.py:111` wall clock → negative `elapsed_sec` → non-retryable `LiveProviderError`), and the host clock stepping −1.5 s every 32.3 s |
| **Candidate 56 did NOT reproduce under continuous two-lane audio** | the eliminations: heartbeat/lease, drift, span density, identity — none of them |
| **The reducer stopped calling a passing number RED - candidate 57** | `live-canary-clauses.py` splits *missed the gate* from *cannot answer it* |
| **THE REDUCER STOPPED ASKING A CERTIFICATION THE SOAK'S QUESTIONS - candidate 62** | a soak is a directory that declares `VIEW_CLAUSE_AGE` in `times.env`, not one that has `view-checks.tsv` |
| **TCC-verification contract / E3 command surface / Prompt order is fixed by the source** | how the grants are read read-only and how the operator's two clicks were spent |
| **Rollback rehearsal - the PRD clause is GREEN (F4a)** | disable → revert → prove batch → restore, and the four facts that make it safe |
| **Validation fence — G1/G2/G3, B1-B4/C3c/C2/C3a/C3b/B5, E1/E2b/E3, H3/H1/J1-J4, H blocker 4, token accounting, decode-cap, D1/K5c/J5c/H4c/E2a/D3, the superseded F1 driver** (11 archived ranges) | the narrow per-node and one-time host recipes of the closed phases |
| **Phase L and Phase M candidate lists (48-55, D-a/D-b/D-c)** | the diagnosis and the landed record of the fifth amendment's cycle |
| **Phase P candidate list (P1-P5, the sweep table, the per-half red-before table)** | the seventh amendment's cycle, landed and merged at `42abc5a` |

**What survives those blocks, because nothing else in this file says it.**
- ***An offline probe speaks for the deployed service only while
  `git diff --name-only <deployed sha> HEAD -- ':!scripts/ralph-afk'` is empty*** — compare against
  the **deployed** SHA, never against `main`, because between a merge and its redeploy those differ.
  **AS OF ITERATION 21 THE INVARIANT IS BROKEN, DELIBERATELY, AND STAYS BROKEN UNTIL PHASE Q's
  REDEPLOY.** Q1 put `moss_transcribe_diarize/app/live_identity.py` and `live_provider_bundle.py` on
  the branch, **iteration 23's Q3 added `live_portal.py` and `CaptureLatencyProbe.swift`, so the
  installed `.app` is now stale as well as the server**, and **iteration 24's Q4 added four more
  files under `macos/`**, so
  `git diff --name-only 7a4f59c HEAD -- ':!scripts/ralph-afk'` lists product source
  and **no offline probe speaks for the deployed service any more** — exactly the state Phase N
  steps 1-3 held from iteration 15 to iteration 28. A measurement about the *running* service must
  come from the running service until gate step (c) of Phase Q lands. (Iteration 20's reading, now
  superseded: the diff listed nine paths — `AGENTS.md`, `docs/design-streaming-diarization.md` and
  seven under `prototypes/streaming-diarization/` from the operator's `44ed003` and `b6b6c5c` — none
  of them product source, a test or `ops/`, so the rule held as written; it was never about docs and
  it is not about a bench either.) **Re-run the diff rather than trusting this sentence.**
  It was **empty** from run `20260729-025318` iteration 29 until iteration 20 of this run. It was false from iteration 15 (when Phase N steps 1-3
  put tracked product source on the branch) to iteration 28 — and note that **the merge alone did
  not restore it**: merging moves `main`, while the rule compares against the **deployed** SHA, which
  only moved at gate step (c). (It was true from iteration 5 to iteration 14,
  when the only diffs were the operator's two `docs/` files from `00620ab`, which no runtime reads —
  read the rule as *no product source, no test, no `ops/`*; it was never about docs.)
- **The certification order, decided once and binding:** gate → merge → publish + redeploy
  (+ Mac rebuild) → F1 and F3. An amendment that lists the runs *before* the merge is physically
  unreachable — the runs exercise the **deployed** server and the **installed** bundle — and H4, J5
  and K5 all resolved the identical wording the same way. The merge buys the ability to measure,
  never the verdict, and a red run is answered by the next amendment.
- **Re-classifying a fact means auditing everything that treated it as final.** D-a's overrun fence
  (`isTerminalOverrun`) was justified by "nothing after this matters"; it outlived the classification
  that justified it and would have silenced a still-producing lane for the rest of a meeting.
- **A driver aborts only on a session that genuinely cannot continue** — client `running:false`,
  `snapshot.terminal_failure` non-null, `v2_session.status != "active"`, or three consecutive refused
  polls. A **lane fault is recorded and never aborts**: it is the evidence 53/48/49/D-a exist to
  produce. And `jq -r '.x // empty'` **swallows `false`** — use `try (if .x == false then …)`.
- **A probe that greps the working tree is not asking about the source — use `git grep`**
  `[iteration 16]`. `grep -rn portalCycleSeconds macos` returns **37** hits where `git grep` returns
  **3**: 34 of them are the string baked into `macos/MOSSCapture/.build` test binaries and the lab
  bundle, and the same shape adds a `__pycache__/*.pyc` hit under `moss_transcribe_diarize/`. It cost
  one FAIL on a correct claim, and the dangerous direction is the other one — every *"nothing
  references this"* check in a probe is one stale build artifact away from a **false RED**, and a
  probe that has never been wrong is exactly the one nobody re-checks.
- **macOS host procedure.** There is no `timeout(1)`: use
  `perl -e "alarm shift; exec @ARGV" <sec> <cmd>…`. `pair` **reuses** the stored
  `capture-device-id`, so it mints no new device row. **Do not read an empty `log show` as an absent
  log line** — widen the window and drop `--style` before concluding anything.

***Four readings out of the retired candidate-56 blocks that nothing else in this file states.***
1. **`165 × 200` heartbeats is NOT evidence a session is alive.** `LiveHelperFailureCoordinator.
   observe` returns early on `session_id in self._terminal_sessions` and the route still answers
   **200**. Never use heartbeat status as a liveness signal.
2. **The answer to "why was this frame refused" is on the wire and the app throws it away.** A
   terminal `LiveServiceError` on `POST /frames` returns 409 with `failure.to_dict()` **and** the
   snapshot's `terminal_failure` (`live_transport.py:267-272`). The probe keeps that body; the client
   does not — the fix is scoped out of every amendment so far and needs its own.
3. **An events poller is structurally blind at the instant that matters:** `_fail` appends the
   `terminal_failure` event under the same lock that makes the next view request 401.
4. **`ops/live-pair.sh` prints `payload: <PAYLOAD>`** — extract with `sed -n 's/^payload: //p'`;
   `tail -1` hands the probe a 122-byte string and the server answers 401 `pairing payload is
   invalid.`. **The payload itself is 113 characters — 122 is the whole LINE, prefix included**, and
   iteration 29 lost a pairing code to a sanity guard written from the 122 (it rejected a *correct*
   payload). Guard on `>= 110`, or on the 401, never on 122.
   And `live-pipeline-probe.py --lane-audio continuous` tiles each lane so no frame is
   silent (`alternating` stays the default so earlier runs stay comparable).
5. **A `grep` that matches nothing kills a remote `set -euo pipefail` script**, and every check after
   it silently never runs — the same shape M6c recorded for `ls`. On a script whose job is to
   *report*, drop `set -e` or tail every grep with `|| true`: a script that exited early looks
   exactly like one whose later checks all passed.

***How to read any `live-canary-clauses.py` verdict, out of the retired candidate-57 block.***
Three disqualifiers make the latency clause **UNDECIDED** rather than RED — `userVisibleMS` null,
`mixerOriginResolved` false, `sufficientSamples` false — and only a qualified report is compared to
the gate. `timelineIntact` false is deliberately **not** a disqualifier; the caveat is appended to
the verdict string instead, because the surviving samples are real but cover a **prefix**. A missing
`latency-final.json` is UNDECIDED, never silence. *The rule behind all of it, now paid for four
times:* **a verdict word must name the thing it decides.**
***And since iteration 22 the RTF clause reads the same way — candidate 70.*** The p95 is taken
over spans at or above the derived **0.13 s** meaningfulness floor; the excluded **count, share and
RTF range live inside the verdict sentence**, so a verdict quoted anywhere carries its own
exclusion; the unfiltered p95 is still printed above it "for the record"; a span from an older
event schema with no `frozen_span_duration_sec` is **counted, never excluded**; and a new
**aggregate RTF** clause — total decode seconds over total audio seconds across *every* span — is
gated beside it, so no floor can hide a backlog. Two conditions make it UNDECIDED rather than
green: every span below the floor, or fewer than **20** spans above it (below 20 a nearest-rank
p95 *is* the maximum wearing a percentile's name). `--rtf-floor-sec` exists for sensitivity work
only — **`--rtf-floor-sec 0` reproduces the pre-Q2 verdict exactly**, which is how the change was
red-proved. *The fifth payment of the same rule:* the 5 % exclusion-share cap written first would
have called F1 it.30 UNDECIDED on 49 perfectly measurable spans.

**WHAT THE GATED LATENCY NUMBER IS MADE OF, AND WHAT THE PLAN'S SECOND ORDERED REMEDY IS WORTH —
run `20260729-094359` iteration 15. READ THIS BEFORE RE-RUNNING F1 OR ARGUING ABOUT ITS LATENCY
RED.** `scripts/ralph-afk/latency-remedy-probe.py`, rc=0, offline: one real
`latency-final.json` (iteration 12's F3) plus two tracked source constants. No host, no session.
**THE REMEDY IS APPLIED AS OF ITERATION 23 (Q3, candidate 71) — both halves at 0.5 s — so the probe
now asserts the TIE where it used to assert that nothing tied them, and section 1's
`portalCycleMS == 1000` is labelled PRE-remedy because it reads F3's real report, which was measured
before and does not change retroactively.** The −500 ms below is still arithmetic on that report;
what turns it into a measurement is Phase Q's F1 re-run on a redeployed build.

`userVisibleMS = committedP95 + portalCycleMS + snapshotFetchP95 + eventsFetchP95` — **residual
0.000000000 ms** on F3's real report (2674.0095 + 1000 + 241.501792 + 191.003041 = 4106.514333).
So the **portal cycle is a whole 1000.0 ms, 24.4 %** of the gated number, additive, and independent
of the two measured fetch p95s. Halving the poll subtracts **exactly 500.0 ms**:

| run | measured | at a 0.5 s poll | gate | now → then |
| --- | --- | --- | --- | --- |
| **F1** on `7a4f59c` | **4150.8** | **3650.8** | 4000 | **RED → GREEN**, margin **+349.2 ms** |
| F2 on `7a4f59c` | 4078.6 | 3578.6 | 6000 | GREEN → GREEN (+2421.4) |
| F3 on `7a4f59c` | 4106.5 | 3606.5 | 6000 | GREEN → GREEN (+2393.5) |

F1 missed by 150.8 ms; the remedy is worth **3.3×** the miss.
1. **The plan lists its two remedies contract-expensive first.** Remedy 1 (2.0 s span cap) moves
   `hard_cap_samples` 40000, which **prd.md's own Constraints declare a domain-contract value**, so
   the loop cannot touch it under any reading. Remedy 2's portal poll appears **nowhere** in that
   list — checked term by term, and note *"pump interval 0.5 s"* in that list is the **client's frame
   tick** (`frameQuantisationMS` 500), a different quantity that happens to share the number.
2. **The remedy's own trap is candidate 68:** the 1000 ms lives in `live_portal.py:146`
   (`pollDelayMs`) *and* `CaptureLatencyProbe.swift:18` (`portalCycleSeconds`), and nothing ties them,
   so moving the Swift one alone would take 500 ms off a PRD number with no change to what a human
   sees. **Both move together or neither moves.** *Closed in iteration 23:* both moved, and two
   enforcing nodes — one per language, each reading the other's source — now fail on either half
   moving alone. See candidate 71 for the four red-before directions.
3. **WHOSE REQUEST RATE EACH CONSTANT CHANGES — measured in iteration 16 (probe section 5), and it
   CORRECTS the honest limit this line used to carry.** The two constants are causally disconnected
   **in both directions**: `portalCycleSeconds` has three tracked sites (declaration, report default,
   the `renderBound` sum) and reaches **no scheduling site**, so moving it moves the *number* and no
   request rate; `pollDelayMs` has two (the constant and `schedulePoll(pollDelayMs)`) and **0 hits
   under `macos/`**, so moving it moves what a *browser* waits and the gated number by **0.0 ms**.
   The gated fetch p95s are the **app probe's own** fetches at `CaptureLatencyContract.pollInterval`
   **0.25 s** — `main.swift` builds `RepeatingCaptureSchedulerAdapter(interval:)` from that constant
   — proven on F3's real report: **4001** snapshot and 4001 events fetches over **1019.724 s**, an
   implied **0.2549 s**, +1.9 %.
   ***The old limit named the wrong stream:*** *"a fetch p95 rising under twice the request rate
   (F3: 381 polls → ~760)"* was the **soak driver's** view-poll stream (381 rows at 2.68 s), which
   the gated number never measures. **The real limit is the opposite one:** halving `pollDelayMs`
   doubles a **real browser's** rate, F1/F2/F3 open **no browser at all**, so a re-run records the
   full −500 ms and leaves the viewer load unpriced — the gate **under-counts the cost**, it does not
   over-count the benefit. Re-run F1 to confirm the −500 ms; never read it as proof about a viewer.
4. *Deliberately untouched:* the committed half is **2674 / 2680 ms** of the ~4.1 s and is what
   remedy 1 attacks. This buys the 4000 ms gate back and no more.

**F1 was GREEN on `42abc5a` as well (run `20260729-025318` iteration 6, rc=0)** - user-visible p95
**3909.3 ms** <= 4000 and qualified (`sufficientSamples` true, n=44), decoder p95 RTF **0.911**,
329 published == 329 accepted, 370/370 view polls 200, 165/165 heartbeats 200, no lane fault,
0 tracebacks. Superseded as evidence by the F1-on-Phase-N run (gates index) and **retired verbatim to
progress.txt** with the fourth compaction; it is kept in one line because it is the **only** run in
this loop's history where the user-visible clause passed at the **4000 ms** gate, which is the
baseline candidate 64 and the plan's ordered latency remedies are argued against. Not certified by
it: the "two speakers" half - both voices were on the system lane.

**THE THREE CERTIFICATION RUNS HAVE ONE HOME AND IT IS THE GATES INDEX.** The rows **F1 on Phase N**,
**F2 on Phase N** and **F3 on Phase N** carry every clause verdict, every measured number and the
identity half of each; the narrative blocks went to progress.txt with the fifth compaction and this
pointer's own retirement paragraph with the eighth. *What those runs measured about identity is in the
deployed-sweep block below, not here.* **Not certified by any of the three, unchanged:** the "two
speakers" half — every run put both voices on the **system** lane, candidate 51's measured microphone
limit, five runs now — and F2's separate mic-granted / system-audio-denied variant, deliberately not
attempted because producing it would spend a TCC grant.

**THE F2 INSTRUMENT — READ THIS BEFORE RE-RUNNING F2 (built iteration 10, corrected by the green run
in iteration 11; full block retired to progress.txt).** Three files, one logical instrument:
`live-cert.sh` (m4mbp, the 300 s locked program), `live-cert-interrupt.sh` (the server, in WSL, the
interruption) and `live-canary-clauses.py --interrupt-report` (section 10). No product source.
- **The mechanism, chosen against three rejected alternatives** (dropping the tailnet strands the
  ssh path; restarting `moss-live-web` destroys the session; `kill -STOP/-CONT` makes "dropped" and
  "delivered late" indistinguishable): `iptables -I INPUT ! -i lo -p tcp --dport 7861 -j DROP` for
  5 s. `! -i lo` keeps `ops/live-pair.sh` working; `--dport 7861` cannot reach batch 7860. It
  self-deletes from a detached `setsid` child in a loop. **Rollback if it ever survives:**
  `sudo iptables -D INPUT ! -i lo -p tcp --dport 7861 -j DROP`, then `-S INPUT` must print exactly
  `-P INPUT ACCEPT`.
- **Arm the server job BEFORE launching the driver, and use `--delay 240`, not 215.** The window must
  land inside the driver's `[T_START+200, T_START+260]` phase; with `Δ = T_ARM → T_START` that needs
  `Δ ∈ [D-255, D-200]`, so `D=215` tolerates only 15 s of setup and `D=240` tolerates 40 s. Measured
  `Δ` on the green run was 2.0 s and the drop landed at `T_START+226.7 s`.
- **The instrument measures itself on CLOCK_MONOTONIC on purpose** — this host's wall clock steps
  ~1.5 s backwards every ~32.3 s, so `t_drop_begin_wall` in the report is **not** trustworthy for
  locating the window (it read 10.8 s off on the green run). *The client-side signal is the reliable
  one:* `publishedFrameCount` freezes and `outboxRetainedFrames` rises.
- **The reducer's positive control:** section 10 credits survival **only** if the client itself
  refused at least one poll inside the window; otherwise **UNDECIDED**. And section 1 excludes those
  self-inflicted refusals *by printing them*, never by subtracting them silently.
- *Host access facts this cost a probe each to learn:* `$OUT` on the server is root-owned;
  `wsl.exe -d Ubuntu -- bash -lc "echo <base64>|base64 -d|bash"` fails with "The command line is too
  long" for a 6 KB script — pipe the file on **stdin**; and the WSL user is **`devcontainers`**,
  reached as `ssh gyauo@ga0-alienware-rtx4070ti.local` then `wsl.exe -d Ubuntu`.

**THE DEPLOYED SWEEP, MEASURED — ONE BLOCK, FOUR RUNS (iterations 7, 9, 12, 13). Cited everywhere
else in this file as *the deployed-sweep block*, by §; the four separate blocks it replaces are
retired verbatim to progress.txt with the eighth compaction. READ THIS BEFORE ANY 55/60/65
AUTHORIZATION AND BEFORE TRUSTING ANY "0 sightings" LINE ANYWHERE IN THIS FILE.** All of it is
measured against the deployed `7a4f59c` over the pinned leaf from MacStudio — no Mac, no TCC, no
operator, no product change, `git diff --name-only 7a4f59c HEAD -- ':!scripts/ralph-afk'` empty before
and after each. Reports `/tmp/i7-probe.json`, `/tmp/i7b-probe.json`, `/tmp/i7c-probe.json`,
`/tmp/i9-frag-probe.json`, `/tmp/i9b-cont-probe.json`, plus iteration 12's F3 soak evidence. Each
probe meeting cost one pairing code, one device and one session; **every probe device was revoked**.

***1. BOTH HALVES PUBLISH, so the categorical "a sweep never publishes" claim is dead on both paths.***

| half | measured |
| --- | --- |
| **session-end** (it. 7, three 150 s probe meetings) | `stop` **200** on all three, and `_finalize_identity_locked` runs *before* `session.stop`, so a raise would have failed the stop. **19 of 31 committed items carry a `revised_transcript`**, **19/19 change the label** (18 × `S00 → S01`, 1 × `S00 → S01,S00`), **0** byte-identical rewrites, **words byte-identical in all 19** (decision 10 on the wire). Live `{S00:25, S01:5, S02:1}` → final `{S01:24, S00:7, S02:1}` |
| **cadence** (it. 12, inside F3's 1020 s / 648-span soak, ~17 deadlines) | **three revisions.** `canonical_processed.identity_revision_version` histogram **`{0:130, 1:122, 2:173, 3:223}`** — first non-zero **t+209.7 s** (span 130), v2 **t+368.5 s**, v3 **t+604.6 s**; `session.label_revision_version` climbs 0 → 3. Spans **48, 208, 382** carry a `revised_transcript` in snapshots at **t+236.4 / 397.1 / 643.3 s** — mid-meeting, so a polling reader saw them. 3/3 `S00 → S01`, words byte-identical |
| **why F2 measured zero** | it was **real**, not a broken sweep: F2's own evidence on the authoritative surface is `{0: 171}` with 0 revised items, F1's is 0 on all 52 spans. What separates the runs is meeting **length** — 5 crossed deadlines against ~17 |

***2. THE CONFOUND-FREE FACT, and it is the sharpest thing the loop knows about the sweep.*** Across
**four** deployed swept meetings — it. 7's 19, it. 9's 7 and 20, it. 12's 3 — **49 published
corrections, every one a fill-in of a MISSING label, and not one a reassignment.** *So no cadence, no
`stop` wiring and no amount of sweeping repairs a minted junk label*, which is what repairing
candidate 55 would require.

***3. AT F2's OWN FRAGMENTATION THE SWEEP IS NOT AMBIGUOUS, IT IS UNINFORMED*** (it. 9, two 150 s
runs, same instrument and length, **61 committed spans each**, 0 non-200s, `stop` 200, view
**401/revoked** after both).

| | **fragmented** | **continuous** (control) |
| --- | --- | --- |
| canonical speakers minted | **16** | 4 |
| labels appearing on ≤ 2 spans | **15** | 3 |
| dominant label's span count | `S02` on **52/61** | `S01` on 26/61 |
| `speaker_capacity_exceeded` abstains | 7 | 0 |
| session-end sweep revisions | **7 (11.5 %)** | **20 (32.8 %)** |
| …of the abstained spans | **7 of 8 (87.5 %)** | 20 of 34 (58.8 %) |
| reassignments / words moved | **0 / 0** | **0 / 0** |
| decoder p95 RTF (deduped, §5.3) | 0.212 | 0.172 |

**Candidate 55 is reproducible on demand in 150 s with no Mac and no TCC** — `live-pipeline-probe.py
--lane-audio fragmented` mints 16 canonicals for **one** embeddable voice, 14 on exactly one span
each, F2's shape hit exactly. **And iteration 5's predicted mechanism is CORRECTED, not confirmed:**
the deployed sweep does not *refuse* those units, it **never receives** them — a speaker born below
the evidence floor has no embedded unit, hence no ledger entry, hence nothing to re-match (decision
20's site, read from the sweep's side). Its *conditional* repair rate on the fragmented meeting is
**higher** than the control's; what fragmentation destroys is the **supply** of repairable spans,
because a span that would have abstained instead carries a confident junk label.
***Honest limit, because the contrast is not single-variable:*** the runs differ in fragmentation
**and** in embeddable-voice count, so **11.5 % vs 32.8 % is not a controlled rate**; findings 1-2 do
not depend on the contrast. The single-variable run that would close it is a fragmented run whose peer
lane carries **two** voices, which the probe cannot build today (one voice per lane).

***4. WHAT A CLIENT CAN AND CANNOT READ, and it invalidates a whole class of past readings.***
`POST …/stop` is reachable by **both** authorities (`CAPTURE_ACTIONS` and `VIEW_ACTIONS` both hold
`stop`), the `/live` portal's Stop button calls it, this loop's F0 probe has called it since Phase F,
and a stop through it **revokes view authority immediately** — `snapshot_status` **401**,
`revoked: true`, three runs for three. The PRD soak clause's *immediately* is therefore satisfied **by
the route**, and candidate 60 is exactly and only that the **Mac client** does not call it. But
`identity_finalized` is **unreadable by every client**: post-stop events answer **401** with the view
token and **403 `session is not owned by this device.`** with the capture token, and `_record_event`
writes to an in-memory list and **never to the journal** — so every *"0 sightings in the journal"*
reading in this file's history is **uninformative, not negative**, and even the session-end sweep's
own counts reach no reader.

***5. THE INSTRUMENT'S FOUR RULES, out of candidate 67 `[done — it. 13]`.*** Loop tooling only, all in
`scripts/ralph-afk/live-pipeline-probe.py`, checkable with `--self-test` (**PASS, 0 failures**, six
cases, needs no host); red-before was a semantic revert on a copy → **FAIL, 17 failures**.
1. **Read the revision version off `canonical_processed`, never off a committed item.** The field
   lives in two places under two names — `canonical_processed.identity_revision_version`
   (`live_service_runtime.py:615,800`) and a committed item's `identity_snapshot_version`
   (`live_session.py:165,814`), a different quantity. The old read returned `None` on **every span of
   every run** and an `isinstance(…, int)` filter made that a silent `[]`, so it would have reported
   "no revision" on the very soak that measured three.
2. **An absent field is `null`, never `0`/`[]`.** Third time in this loop a missing field read as a
   negative measurement (`identity_finalized`, `storageWrites`, this). "Measured zero revisions" and
   "measured nothing" are opposite facts.
3. **`since_seq` is inclusive server-side** (`event.seq >= since_seq`), so every poll re-delivers the
   previous poll's highest event; dedupe by `seq` as the portal does (`live_portal.py:474`) and
   **print** the duplicates, never subtract them silently. *This corrected numbers already in the
   record:* it. 9's fragmented run reported **62 spans for a 61-span meeting** and RTF p95 0.190,
   which is **0.212** deduped (+11.6 %); the control moves 0.167 → 0.172; every earlier report counted
   `session_created` **twice**; and it. 12's F3 `events.tsv` holds **380 duplicates over 381 polls**.
4. **`sweep.session_end` names its refusal** (`"…drain returned 403"`) rather than reporting a zero.
***Honest limit:*** the chain was proven in two halves — the reduction replayed on real deployed
payloads, the collection keys checked against `live_service_runtime.py:800` — never in one live run.
On a 150 s meeting expect `{"0": N}` and `max_version` 0, now *measured zero* rather than *unmeasured*.

***6. WHAT SURVIVES OF CANDIDATE 65:*** the **rate** and the **diagnosability** half. Three revisions
repaired **3 of F3's 122 abstained spans (2.5 %)**, so ~14 of ~17 deadlines produced nothing — and
produced it silently, because `sweep_now` sets `_unconsumed` and logs **only when the revision is
non-empty**. "Swept and proposed nothing" is still indistinguishable from "never swept", and
`identity_revision_refusals` is the only sweep-refusal surface a client can read, covering the
**cadence** half alone — a session-end sweep's refusals ride the unreadable `identity_finalized`.

**THE PORTAL WRITES NOTHING TO BROWSER STORAGE, MEASURED ON THE DEPLOYED PAGE — run
`20260729-094359` iteration 10, `scripts/ralph-afk/portal-storage-probe.py --report
/tmp/i10-portal-deployed.json`, rc=0, ~4 s.** One unauthenticated `GET /live` over the pinned leaf;
no pairing code, no device, no session, no token, no product change. Five clauses, all GREEN:

| clause | measured |
| --- | --- |
| the deployed page **is this checkout's page** | served script sha256 `7682008cc7b7…` (17 992 B) **byte-identical** to this checkout's render. *Nothing had ever proven this* — `/api/live/descriptor`'s `source_revision` is a manifest field stamped when the finalizer last ran, not the running code's revision |
| no storage identifier in the served page | **7** scanned (`localstorage`, `sessionstorage`, `document.cookie`, `indexeddb`, `window.name`, `navigator.storage`, `caches.open`), **none present** — the tracked suite's 3 plus the four surfaces it never named, and on the *deployed* page rather than a local render |
| nothing is written to browser storage at runtime | `storageWrites` **empty** on both harness scenarios that return it (`happy`, `retry`), 9 requests driven |
| the view token reaches no URL and no rendered text | absent from every request URL and every rendered node; carried **only** as `Authorization: Bearer`, **9/9** headers |
| the recorder catches a deliberate write | **6/6** controls detected |

*How it reaches the surfaces the tracked harness cannot see, without editing the tracked suite:* a
prologue is prepended to a **copy** of the served script that routes `document.cookie`,
`window.name`, `indexedDB` and `caches` writes **into the harness's own `localStorage` Proxy**, so
one recorder answers for every surface and the probe's assertion is exactly the one-liner a future
tracked node would make — `storageWrites == []`. The harness's fake `document` has no `cookie`
accessor, so without that prologue a cookie write is **invisible**, not absent.
*Why the controls are not decoration:* a recorder nobody has ever seen fire may not work, and this
one had never fired in the loop's history. Each control splices one deliberate write
(`localStorage`, `sessionStorage`, `document.cookie`, `window.name`, `indexedDB`, `caches`) into a
copy of the served script and **must** be caught; an undetected control makes the run UNDECIDED
(rc=5), never green.
***Honest limits, three.*** (1) The two scenarios drive connect → poll → events → stop → abort and
a reconnect; a write on a path neither reaches is unmeasured. (2) The controls fire at eval time,
not mid-poll — they prove the recorder is live, not that every code path is instrumented. (3) This
is **evidence, not a regression**: nothing in the tracked suite asserts it, so the next portal edit
can reintroduce a write and the whole gate stays green. That is candidate 66.

**THE MARKER IS MATCHED PHONETICALLY — candidate 59 `[done — iteration 13]`. READ THIS BEFORE
READING ANY `live-canary-analyze.py` MARKER LINE** (full block, with the six-directory measurement
that chose the design, retired to progress.txt). The decoder rewrites a rare noun, so
`marker.lower() in transcript.lower()` scored `cardamom` **absent** in three runs whose marker
demonstrably landed — `Cockamom, cockamom, cockamom.` (F1 span 15), `Pardon me, pardon me, pardon
me.` (F2 span 29), `Cardinal.` (F3 span 4).
- **Three tiers, and every marker line names which one answered:** **VERBATIM** (proof by itself) →
  **REWRITTEN** (a fragment inside a phase that *declares* this marker, whose whole text is one token
  n-gram repeated — the driver's isolated-and-repeated delivery — within **0.60** consonant-skeleton
  similarity; decisive) → **CORROBORATING** (any near-match ≥ **0.80** in a declared phase; printed,
  never decisive).
- ***Score alone cannot work in either direction, and that is measured over 637 spans:*** at 0.60 the
  score also admits `we return` and `continuous` inside F1's own marker phase; at 0.80 the room
  marker `obsidian` sits two hundredths above the program's own word `system`. The **delivery shape**
  is the discriminator — a pure repetition occurs exactly four times in the corpus, at 0.29, 0.60,
  0.80 and 1.00 — so the rule is **score ∧ shape ∧ position**.
- **Any future marker check must be phonetic**, and coverage is reported whether or not the marker
  was found (a verdict that turns positive must not stop saying what it did not measure).

**WHERE `live-canary-analyze.py` READS SPANS — candidate 61 `[done — iteration 12]`** (full block
retired to progress.txt). `live-cert.sh`/`live-soak.sh` prune `snapshot.tsv` rows to `span_id`, so
the analyzer takes three sources in order and always names which one answered: the last 200
`snapshot.tsv` row is authoritative for the run's **end** (final version and span count); the span
**bodies** come from the newest readable `snap-full-*.json`; and `descriptor.bounds` is resolved with
them, because pruning nulls it. A full snapshot every 30 polls means the bodies are a **prefix**, so
an absence is judged against **coverage** — undecided only when **no** delivery phase of that marker
is covered (the strict "any uncovered phase" reading fires on every pruned run and decides nothing).
An unreadable layout is a named **rc=6** refusal, never a traceback.

**Feasibility — settled, do not re-litigate.**
- Warm 12-run decode p95: 7.5 s span → **0.241 s**; 2.5 s → **0.162 s**. One pre-warm
  2.5 s request took 3.851 s, so certification must warm the resident engine before timing.
  Output already carries `[t][S01]` speaker labels.
- Live decode reuses the **already-resident** vLLM engine (`web_cli.py:87-98`) → **no extra
  VRAM**. GPU free 1328 MiB of 16376 after the probe is not a blocker.
- Latest m4mbp → 4070Ti tailnet probe: ping avg **72 ms**, max **146 ms**. Treat callback cadence
  and tailnet latency as variable; no fixed request-rate assumption is valid.
- Uplink: 48 kHz lanes = 2.05 Mbit/s of base64 JSON; 16 kHz lanes = 0.68 Mbit/s.

**A hung `mtd-capture` is not a dead app (M36's surviving half).** `UnixDomainControlServer.serve()`
is a **serial** accept loop (`CaptureSecurity.swift:897-902`) and `UnixDomainControlClient` sets no
`SO_RCVTIMEO`, so anything blocking inside `start` blocks every other command — `status` included —
with no timeout. Diagnose with `pgrep -x MOSSCaptureApp` and `sample`, never by killing the app.
(The system-tap prompt itself is spent: `AudioHardwareCreateProcessTap` has returned promptly on
m4mbp in every run since E3 closed.)

## Deployed reality — all four checkouts at `7a4f59c`

> **Iteration 29 published and deployed the eighth merge.** `origin/main`, the server checkout and
> the m4mbp checkout all moved `42abc5a` → **`7a4f59c`**, both host trees `16de7f62…`. The one
> host-state fact that moved with them is the **live provider manifest**, regenerated at the
> calibrated 0.35/0.1 — every hash below that starts `61d97ffe` is superseded by `0cb775da`.

**Server (`ga0-alienware-rtx4070ti`, WSL Ubuntu, checkout `/mnt/d/Coding/MOSS-Transcribe-Diarize`).**
Detached at **`7a4f59c`** since N8c (run `20260729-025318` iteration 29), **MainPID 365632**,
`NRestarts=0`; before that `42abc5a` (P5c, MainPID 355607), `77e0014` (M6c), `fc7097d` (K5c),
`6a540fe` (J5c), `b817871` (H4c), `317df4d` (G5), `f9285d6` (D1). The checkout's own `main` ref is
still **`163e969`**, so `git -C /mnt/d/Coding/MOSS-Transcribe-Diarize checkout 163e969` is a complete
one-command rollback that moves nothing but `HEAD` — rehearsed for real and undone in F4a.
- **THE THREE MOSS UNITS ARE `systemctl --user` UNITS, and a bare `systemctl` LIES ABOUT THEM
  (found iteration 11, cost four probes).** `systemctl show moss-live-web -p MainPID` prints
  `MainPID=0 / LoadState=not-found / ActiveState=inactive` — which reads exactly like *the live
  service is dead* — and `sudo systemctl` is wrong for the same reason. The unit files are at
  `/home/devcontainers/.config/systemd/user/{moss-live-web,moss-web,moss-vllm}.service`, all three
  `enabled`. **The only correct probe is `systemctl --user show …`.** Cross-check with
  `ps -eo pid,etime,args | grep mtd-subtitle-web`, which shows the real MainPIDs regardless.
- **The venv is an editable install pointing at the checkout** (measured in M6c:
  `live_adapters.__file__` is under `/mnt/d/Coding/…`), which is why a restart picks up a checkout
  and why `git checkout` + `systemctl restart` is the whole redeploy.
- `moss-live-web.service`: installed (byte-identical to `ops/systemd/`), enabled, active, TLS on
  `0.0.0.0:7861`, **MainPID 365632** (was 355607 before N8c), `NRestarts=0`. `/live` answers 200
  ~8-11 s after a restart — **poll for 200, never sample once**; a single early probe returns `000`
  and reads like a failure.
- **The host's wall clock steps ~1.5 s BACKWARDS every ~32.3 s and this is a permanent host fact.**
  Re-measured after the P5(c) restart, 100 s at 20 ms, 4768 samples: **−1.464 / −1.437 / −1.466 s at
  t 14.076 / 46.370 / 78.661 s**, i.e. intervals of 32.29 s and 32.29 s — the same shape iteration 28
  measured (−1.523/−1.504/−1.503 at 32.25/32.28 s) on a host whose `timedatectl` still says
  synchronized. It is WSL2 resynchronising, nothing in this repo fixes it, and **nothing needs to**:
  Phase P made the live decode measure itself monotonically, so the step can no longer reach any
  duration. Treat any future `time.time()`-derived duration on this host as a live defect, not a
  theoretical one — this is the one host where that bug is guaranteed to fire.
- Batch, never restarted by any step of this loop: `moss-web` **MainPID 301112**, `moss-vllm`
  **MainPID 322117**, both `NRestarts=0`. Those two values are what every later probe must still show.
  The running batch process is still the `163e969` *image* (`INDEX_HTML`/`FAVICON_SVG` are
  module-level constants), so "batch unharmed" is proven by the derived-argv check, not by a restart.
- Live state lives **outside** the repo on ext4 at `~/.local/share/moss-transcribe-diarize/live/`:
  `live.crt` (0644) / `live.key` (0600) with all four SANs, `live-provider-manifest.json` (generated),
  the untouched `.provisional.json`, `golden.wav`, and the pre-rotation `*.backup-20260728T044132Z`
  pair that is D2's recorded rollback. `live-auth.json` (0600) is the device store.
- **The live pin is `a35ca9fc4a0f5b32bf7da6dc2e03c1fa5b4ac60992f0ee49b6d5677d22b680ff`** (was
  `2c88836b…` before D2's rotation). That is what every pairing payload carries and every Mac stores.
  Rotating it invalidates every stored pin — never pass `--rotate` again without a name change.
- **`provider_manifest_hash 0cb775da…`** since iteration 29 (was `61d97ffe…`), with
  `identity_config_hash 4b7c94ed…`, `combined_config_hash 431efb3f…`, `bounds_config_hash
  bb7e098d…`. That movement **is** the recalibration's signature: the manifest now carries
  `identity_config {max_speakers 16, min_match_score 0.35, min_match_margin 0.1}` where it carried
  `0.5 / 0.05`. Read back through the runtime's own readers, no domain-contract value moved
  (endpoint == bounds hard cap 40000, min_silence 8000, max_retained 960000, frame 8000, rate 16000,
  16 speakers, no `session_hard_cap_samples`).
  `/api/live/descriptor` now reports `source_revision 7a4f59c…` — it was stale at `f9285d69…` for six
  merges, because it is a **manifest field stamped when the finalizer last ran, not the running
  code's revision**. It is honest for *this* deploy and goes stale again the moment a redeploy skips
  the regeneration, so it is still never the deployed-SHA check. Use the four-way `git rev-parse`
  plus venv introspection.
- `live-auth.json` holds one **unrevoked** device, m4mbp's
  `AB600574-FD93-4321-967E-652AB064A70B`, plus several revoked probe devices from F0/H2/J5d. Device
  *count* is not a signal; count unrevoked devices — **14 devices / 1 unrevoked** after N8c
  (13/1 after P5(c); iteration 29's probe device was minted and revoked in the same iteration).
  Baseline copy: `live-auth.json.ralph-f0-backup-20260728T091927Z`, sha256 `9d306766…`.
  **Two traps, both of which cost iteration 5 a wrong answer before they were read out of the
  source.** (1) The revoke route is **`DELETE /api/live/devices/{device_id}`**
  (`live_transport.py:460`) — a `POST …/revoke` returns **404 for route-not-found**, which reads
  exactly like "device already gone" and would leave a probe device live. Assert the 200 **and** its
  `{"device_id": …}` body. (2) The persisted device record's keys are
  `paired_at / revoked / revoked_at / token_digest` — **the device id is the dict KEY, not a field**,
  so `x.get("device_id")` prints `None` for every row and a filter written on it silently matches
  nothing.
- Windows host: portproxy `0.0.0.0:7861 → 172.30.115.123:7861` beside the untouched 7860 and 5100
  rows; firewall rule `MOSS-Transcribe-Diarize-Live` (Inbound/Allow/**Private** only); the sign-in
  scheduled task argument list ends `-RefreshOnly -IncludeLive`. `webrtcvad-wheels 2.0.14` and
  `onnxruntime 1.23.2` installed; WeSpeaker ONNX staged and hash-verified.
- **Remote-shell quoting.** Nested quoting through Windows conhost → `wsl.exe` → bash mangles inline
  scripts. Ship the script on **stdin** (`printf '%s\n' … | ssh … "wsl.exe -d Ubuntu -- bash -s"`).

**m4mbp (the capture Mac).** macOS 26.5.2, Xcode 26.5, Swift 6.3.3. Checkout
`/Users/ga0/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize`, reachable as `ga0@m4mbp`
with `BatchMode=yes`, **detached at `7a4f59c`** (tree `16de7f62…`, the merge's own tree), clean.
- **`origin` is not the same repository on every host.** Here `origin` is the AlphaSight fork;
  **on m4mbp `origin` is OpenMOSS and the fork is `alphasight`**. `git fetch origin main` there
  fetches upstream and the checkout then fails `fatal: unable to read tree`, which reads like
  corruption and is really "never fetched". **Resolve the remote by URL, never by the name `origin`.**
  Its `main` ref is deliberately untouched at upstream `40cf854`, so `git checkout main` is the
  complete rollback. The fork is fetchable anonymously; no credential lives on that host.
- **Topology:** m4mbp is on `192.168.1.240` and **cannot reach the batch LAN** `192.168.68.38` (100 %
  loss). The two hosts meet only on the tailnet, `100.64.0.4 → 100.64.0.8` — which is exactly the
  path the PRD's live clause names. The batch clause is measured from MacStudio.
- `/Applications/MOSSCapture.app` + `~/.local/bin/mtd-capture` installed from **`77e0014`** (M6c,
  iteration 20): bundle digest `c7c12ce2…`, CLI sha256 `450c20bf…`, inode `212080356`,
  mtime `2026-07-28T18:22:32Z`. **The checkout is `7a4f59c` but the INSTALL is still the `77e0014`
  product, and that is correct, not drift:** P7's **and** N8's payloads touched **0** files under
  `macos/`, so all three SHAs build a byte-identical client. Re-measured after both P5(c)'s and
  N8c's checkouts — inode `212080356`, mtime unchanged, and
  CLI sha256 `450c20bf…` **unchanged**, which is the positive proof no rebuild happened and therefore
  that the TCC grants were never at risk.
  ***THAT STREAK ENDS WITH PHASE Q, AND ITERATION 23 IS WHERE IT ENDED.*** Q3 changed
  `macos/MOSSCapture/Sources/MOSSCaptureCore/CaptureLatencyProbe.swift`, so Phase Q's payload is the
  **first since M6c to touch `macos/`** and the installed client is now genuinely stale rather than
  correctly-identical. **Iteration 24's Q4 doubled the reason** — `CaptureController.swift`,
  `CaptureHTTPTransport.swift`, `FakeCaptureAdapters.swift` and `MOSSCaptureApp/main.swift` — so
  without the rebuild F1 measures the cadence remedy at 0.0 ms **and** F3's post-stop view check
  still answers 200. **Phase Q's redeploy therefore needs an m4mbp rebuild + reinstall, which the
  last five did not** — the third amendment's housekeeping note (*"no rebuild or reinstall is needed
  unless `macos/` changes"*) now applies in its other branch. Recheck both TCC grants after it (the
  DR is byte-identical across rebuilds, which is why they survive, but *measure* rather than assume),
  and **F1 cannot measure the −500 ms until that reinstall happens** — the analytic render bound is
  computed inside the app. *One measurement trap:* `212080356` is the **bundle
  directory's** inode; the Mach-O at `Contents/MacOS/MOSSCaptureApp` is `212080361` and the CLI is
  `212080364`. Compare like with like or a healthy install reads as replaced. (K5c's `fc7097d` install was digest `267ada93…`, CLI `c11e89ff…`,
  inode `211995344`.) Both verify
  `codesign --verify --strict`; the bundle satisfies its DR. The **designated requirement is
  `identifier "com.alphasight.moss.capture" and certificate leaf =
  H"e118d874377746c4bd25beb8252bb84302b73e72"`** and is byte-identical across rebuilds even though
  SwiftPM is **not** byte-reproducible here — which is why the TCC grants survive a rebuild (they key
  on the DR, measured directly in TCC's own `csreq` blob). Pass that requirement to
  `codesign --verify -R=` **without** the `designated => ` prefix or it fails `unexpected token`.
  Embedded entitlements are exactly `{com.apple.security.device.audio-input: true}` — B5's
  `keychain-access-groups` drop fires on this host. `LSUIElement` is true: a launched app shows no
  window and no Dock icon; observe it with `pgrep -x MOSSCaptureApp`.
- Bundle backups, the **only** copy of those bytes: `…backup-20260728T222244Z` (**pre-M6c**, i.e.
  the `fc7097d` product — carries K1-K4 but not 53/48/49/D-a), `…backup-20260728T191937Z` (pre-K5c,
  carries G1+G2+G3 but not K1/K2/K4) and `…backup-20260728T085551Z` (pre-G6, no ATS key, CDHash
  `026836…`), each with a matching `mtd-capture.backup-<utc>`. Never delete these — SwiftPM is not
  byte-reproducible here, so a rebuild cannot recreate them.
- `~/Library/Application Support/MOSSCapture/secrets.json` exists, 0600 in a 0700 directory, holding
  `capture-bearer`, `capture-certificate-pin`, `capture-device-id`, `capture-server-url`,
  `capture-session-id`, `capture-view-token`, `local-control-secret`. A bare `start` therefore
  resolves a configuration — **always `pair` first** so the session id and bearer are this run's.
- Signing: `~/Library/Keychains/moss-signing.keychain-db` holds `MOSS Capture Local Signing`
  (RSA 2048, `CA:FALSE`, EKU `codeSigning`, 2026-07-28 → 2036-07-25), password in
  `~/.config/moss-capture/signing-keychain.password` (0600 in a 0700 dir), fourth in the search list;
  the default keychain is still `login.keychain-db`. `leaf_sha256 ef8fa542…`, leaf SHA-1
  `e118d874…`. **The identity is not reproducible** — a re-created one has a different leaf, so the DR
  changes and the human's TCC grants die with it. Never `security delete-keychain` now that grants
  exist. A fresh SSH session finds the keychain locked (`errSecInternalComponent`); `build-app.sh`
  unlocks itself, an ad-hoc `codesign` must unlock first. Never gate on
  `security find-identity -v -p codesigning` — it reports 0 valid identities for a self-signed leaf
  that `codesign` accepts.
- `~/.local/bin` is **not** on the non-interactive SSH `PATH`; over SSH always call
  `/Users/ga0/.local/bin/mtd-capture` by absolute path.

**MacStudio (this host, the orchestrator).** `python3` = pyenv 3.12.10 (pytest 9.0.2), `swift` 6.3.2.
Never `/usr/bin/python3` (3.9.6). It carries **no** `MOSSCapture` install, no signing keychain and no
`~/Library/Application Support/MOSSCapture` — B6 left it clean and later gates re-proved it.

**TCC is verified read-only, and the grants are DONE.** `~/Library/Application Support/com.apple.TCC/
TCC.db` on m4mbp is `-rw-r--r-- ga0:staff` and opens over plain SSH **without** Full Disk Access.
Microphone = `kTCCServiceMicrophone`, System Audio Recording = `kTCCServiceAudioCapture`;
`auth_value` 2 = allowed. Both hold **2** for `com.alphasight.moss.capture` and have survived four
bundle replacements, because each row's `FADE0C00` blob decodes (via `sqlite3 … writefile()` +
`csreq -r <file> -t`) to the app's **designated requirement**, not its cdhash. **Never ask the
operator for those clicks again, and never write TCC.**

**The `mtd-capture` surface, and the three facts that make it work over SSH.** Full surface:
`pair --server <https-url> | start [--label <name>] | stop | status | handoff | latency`; anything
else is `rc=64`. (1) **The pairing payload goes on stdin, never argv** (`input.readAll()`; empty
stdin is `rc=65`); a Return before Ctrl-D has been harmless since G2. (2) **The CLI cannot launch the
app** unless `MOSS_CAPTURE_APP_URL` is set and the control socket is absent — start it from the GUI
session (`open -a`), never `…/Contents/MacOS/MOSSCaptureApp` from a shell, which would attribute TCC
to the terminal. Socket is `/tmp/moss-capture-501/control.sock`. (3) **`LSUIElement` is true**, so a
running app shows nothing; observe it with `pgrep -x MOSSCaptureApp`.

**Rollback rehearsal — the PRD clause is GREEN (F4a, iteration 8; full block retired to
progress.txt).** Disabled → reverted to `163e969` → batch proved 200 → restored, on the real server,
batch never restarted. Four facts make it repeatable: (1) **order is forced by `ExecStart`** — the
live unit runs `ops/start-web.sh` *from the checkout*, and at `163e969` that script would bring up a
**batch** server, so `disable --now` before the checkout moves and restore the checkout before
`enable --now`; use `disable`, not `stop`. (2) **A correct restore reads as broken for ~10 s** — poll
for 200, never sample once. (3) **A rolled-back tree reports `?? ops/moss-live.env`** because
`163e969`'s `.gitignore` predates it; only `git clean` would destroy the profile the restore depends
on. (4) **Nothing a paired Mac hashes moves** — the TLS pair, manifest and device store live outside
the repo on ext4 and kept inode and sha256 across the whole cycle, which is why this is safe against
already-paired devices. The stop condition for any future run is the **pin changing**.

**Gotcha — file modes are unenforceable inside the host checkout (found by D3).** `/mnt/d` is a 9p
`drvfs` mount **without** the `metadata` option, so every file under
`/mnt/d/Coding/MOSS-Transcribe-Diarize` reads `777` and `chmod` is a silent no-op (the tracked
`ops/moss-live.env.example` reads 777 too — this predates the loop). That is safe for
`ops/moss-live.env` because the profile carries only paths and scalars, no secret. It is *not* safe
for anything holding a secret: `MOSS_LIVE_AUTH_STATE`, `live.key` and the manifest all live under
`~/.local/share/moss-transcribe-diarize/live` on **ext4**, mode 0700, where the modes are real.
Never move live secret state onto the Windows drive, and never write a doc line that promises a
mode inside the checkout.

**Open defect (found by D2, iteration 18) — the finalizer needs the deployment venv, and the
tracked doc says otherwise.** `ops/finalize-live-provider-manifest.py` inserts the repo root on
`sys.path` and imports `moss_transcribe_diarize.app.live_manifest_finalizer`, which first executes
the package `__init__.py` → `configuration_moss_transcribe_diarize.py` → `from transformers import
PretrainedConfig`. The host's system `python3` (3.12.3) has no `transformers`, so the exact command
`LOCAL_DEPLOYMENT.md:666` prescribes — `python3 ops/finalize-live-provider-manifest.py …` — dies
with `ModuleNotFoundError` before printing a single `plan:` line. The finalizer module itself needs
nothing from `transformers`; only the package `__init__` chain does. **Workaround used by D2, and
the invocation D3 and any re-run must use:**
`$HOME/.local/share/moss-transcribe-diarize/venv/bin/python3 ops/finalize-live-provider-manifest.py …`
— the deployment venv (3.12.13, `transformers 5.14.1`) already resolves
`moss_transcribe_diarize` **from this same checkout**, so the reviewed revision is still what
generates the file, and it is the interpreter the live service itself will use to read the manifest.
The durable fix is to load the finalizer module by file path (`importlib.util.spec_from_file_
location`) instead of importing it through the package, which would make the tool stdlib-only and
match its own docstring. That is a **tracked-source** change and the merge freeze forbids it on this
branch: it needs a new branch and a decision, not a second keeper merge. Nothing in D3–F4 is blocked
by it — only the doc's copy-paste line is wrong.

## Shipped contracts — index

Each line is the rule and its anchor. The **full** block, with its node lists and its rehearsal
evidence, is in the progress.txt archive under the same title.

| contract | the rule, in one line |
| --- | --- |
| **Lab bundle** (it. 4) | The tracer's one fixed path `/tmp/moss-capture-lab/MOSSCapture.app` is built, bundled and ad-hoc-signed from the real products; a deleted bundle is re-created, so "no bundle → paired app" is proven cold. |
| **Secret store** (it. 5 / B1) | `CaptureSecretStoreSelection.makeDefault()` returns the **file** store (0600 in a 0700 dir); Keychain is dormant with no access group. Construction has no side effects. |
| **Outbox** (it. 6 / B2) | `CaptureFrameOutbox` retains every drained frame until the server **acks** it; 15 s per lane; overflow is a typed degraded state, never silent loss. |
| **Wire format** (it. 7 / B3) | Both lanes leave the Mac 16 kHz mono in exact 8000-sample frames; `capture_timestamp_ns` is **converted** nanoseconds re-derived per buffer, never raw host ticks. Conversion never happens on the realtime callback. |
| **Transport pump** (it. 8 / B4) | Lanes publish concurrently with **one request in flight per lane**, no overlapping pass, one pinned `URLSession` per pin; a late tick skips instead of piling on. |
| **Packaging tools** (it. 9 / B5) | `macos/scripts/{bootstrap-signing-identity,build-app,install-app}.sh`; the signing entitlements are derived from the tracked file with `keychain-access-groups` **dropped**, and the build refuses to finish if it reappears in the signature. |
| **Signing mechanics** (it. 9) | `codesign --keychain <kc> --sign <name>`; verify by `codesign`, never by `find-identity`; unlock the keychain first from a fresh session. |
| **View authority** (it. 11 / C1) | View authority is **derived** from the live session lifecycle — active session only, 12 h absolute cap, immediate terminal/device/operator revoke. The 900 s fixed expiry is gone (`VIEW_TTL_SECONDS` does not exist). |
| **Manifest bounds** (it. 12 / C2) | The deployed manifest's bounds are **generated** by `ops/finalize-live-provider-manifest.py`, hash-covered, and admitted by the runtime's own readers. |
| **Live-credential tools** (it. 13 / C3a) | `ops/generate-live-tls.sh` + `ops/live-pair.sh` share one library; the payload is minted once, on the host, on stdout, never redirected to a file. |
| **Two-service deployment** (it. 14 / C3b) | The live service is a **second** systemd unit over one adapter: `ops/moss.env` (batch) + `ops/moss-live.env` (live profile, gitignored). One deployment root, one `start-web.sh`. |
| **Latency probe** (it. 15 / C3c) | The Phase F number is measured **inside the app**: single-clock committed latency + analytic render bound, separate components, default-off, typed unavailable, stops with the session, and the CLI never receives the view token. |
| **Handoff** (it. 3 / A2) | View authority is app-only. `MOSSCaptureApp/main.swift` is the only composition root that reads `capture-view-token` and writes the pasteboard; the CLI relays `{ok, sessionID, portalURL, viewAuthority}` verbatim. |
| **Lane admission** (it. 2 / A3) | `.granted` → admit inline, `.denied` → typed lane failure, `.undetermined` → one `requestAccess` and lane `pending`. `start` never waits on a user decision; system audio's recording start *is* its request. |
| **ATS** (G1) | `Info.plist` declares `NSAppTransportSecurity = {NSAllowsArbitraryLoads: true}` and **nothing else** — any sibling key makes the OS ignore it. ATS applies only to a **bundle** talking to a **remote non-RFC-1918** peer, so **no single-host test can gate it**; never re-add a node that looks like an ATS gate but binds a local server. |
| **Pairing payload** (G2) | The payload is typed and **trimmed**: a Return pressed before Ctrl-D is harmless. The canonical wire form is exercised end to end by the tracer's second real pairing. |
| **Control-channel failure** (G3) | Typed failures keep their names and carry no detail; only an **unclassified** failure produces a log line, with a fixed vocabulary and its command. The app wires the log; the CLI does not. |
| **WebRTC VAD framing** (H3) | `WebRtcSpeechProvider` admits only `frame_samples ∈ {160,320,480}` and carries the voiced tail across frames; an unaligned mixed frame no longer raises `webrtcvad.Error`. |
| **Empty-span decode** (H1) | A span the decoder cannot parse **commits empty** (`empty_reason decoder_returned_no_transcript`) — never terminal. Accounting equality `accepted == accounted == committed` is what the design turns on. |
| **Span-cap authority** (H2) | **One** authority decides the span cap. `LiveSession` no longer partitions audio and takes no `hard_cap_samples`; `_require_one_span_cap` refuses a manifest whose endpoint and bounds caps disagree. |
| **Span bounds** (J1) | Decoder timestamps are **clamped** to the span, answered once in `live_span_bounds.py` and called from all three consumers. Measured: 6.1 % of hard-cap spans overshoot, by +0.01/+0.02 s; a fixed ε is a guess, a clamp cannot be exceeded. |
| **Unresolved identity** (J2) | A non-`prepared` preparation publishes the span's **words** under `S00` with no speaker attributed. Identity answers *who*, never *whether*. |
| **Transient decode** (J3) | A decoder that did not **answer** is not one that **failed**: `DECODE_ATTEMPTS_PER_SPAN` 2, `MAX_CONSECUTIVE_UNANSWERED_SPANS` 3, then degrade — not terminal. |
| **Named refusal** (J4) | Every refusal on the live path carries the word naming it out of the process, in the `canonical_processed` event and the failure detail. `CanonicalSubmission(submitted=False, refusal=None)` raises. |
| **Lane reporting** (K1) | One projection, two readers: `CaptureStatus.reportedLanes()` feeds both the heartbeat and `ControlChannelResponse.lanes` (lane / state / `failureCode`). Counts, states and typed codes only — never audio, never a token. |
| **Lane-failure log** (K2) | The app records a **typed** lane failure alongside G3's unclassified one, through `LaneFailureLoggingHealthAdapter`, with one `CaptureLaneStates` vocabulary. *Extended by D-a (it. 15):* a **degradation** is recorded the same way, once per lane per generation, and the line's verb comes from the state — so grep `capture lane ` , not `failed`. |
| **Terminal record** (K3) | The heartbeat that ends a session carries the failed lanes' typed codes into `LiveV2Session.expire`, `runtime.abort`, the `session_aborted` event and one host-journal line. |
| **Session refusal** (K4) | 401/403/404/410 → `CaptureStatus.sessionRefusal` / `ControlChannelResponse.sessionRefusal`, recorded from the tick **and** the stop drain, so `running: true` never stands alone while every request refuses. A new session id is a new question. |
| **Fingerprint album** (Phase N step 1, it. 15 of run `20260729-025318`; **DEPLOYED at `7a4f59c`**) | **Matching is not enrollment.** The evidence floor (`identity_provider.min_segment_samples`) does not move, so a short span is still *labelled*; enrollment needs ADR-0002's **1.0 s**. Per canonical speaker: up to **k=10** exemplars, matched against their **duration-weighted centroid**; plus **one** sub-admission stand-in used only while the bank is empty, discarded — never averaged — by the first real exemplar. Neither tier is recency-driven. Every refusal is a named disposition and nothing here raises. |
| **Manifest calibration** (Phase N step 1b, it. 17 of run `20260729-025318`; **DEPLOYED at `7a4f59c`, host manifest regenerated at 0.35/0.1**) | A **free** deployed parameter is stated by the deployment, never inherited. `finalize-live-provider-manifest.py` requires `--min-match-score` / `--min-match-margin`, writes them into `identity_config`, hash-covers them, names them in the plan and the evidence, and refuses a pair `live_provider_bundle._identity_config` rejects. The calibrated pair is named once, in `live_identity_album.py`, and the accuracy harness imports it — so the measured pair and the deployable pair cannot diverge. |
| **Session tape** (Phase N step 2, it. 19 of run `20260729-025318`; **DEPLOYED at `7a4f59c` but OFF - no host declares a root**) | **A tape is placed by capture timestamp and bounded by a declaration.** Three PCM16 tracks + an atomically republished `index.json`; the **gap manifest is the complement of coverage**, so a dropped frame is silence *and* a named gap and a late frame fills it. Retention is opt-in — no root, no tape, no behaviour change. `declared()` refuses a root inside the checkout, sharing a filesystem with a runs tree, or on a filesystem where `chmod` is a no-op. No frame ever raises: cap, write failure and inadmissible frame each stop taping with a typed degradation. The reaper is driven by session state + TTL, runs at startup, and skips what it cannot read as a tape. |
| **Taped live path** (Phase N step 2, it. 20 of run `20260729-025318`; **DEPLOYED at `7a4f59c` but inert - no host declares a root**) | **The recorder is the boundary, and `None` is a whole configuration.** The transport holds one `LiveSessionTapeRecorder`, constructed always and inert when no root is declared — so the untaped service is a state of the wiring, asserted by a route node, not an absence of it. Lane frames tee **after the ingress ack**; the mixed track tees at `admit_available`'s sealed commit, placed by the commit's own start timestamp. The tape is released wherever the **mixer** is, including the coordinator's lease-expiry teardown. Nothing in the recorder raises: a store failure is one WARNING naming the action, never a 500 on `POST /frames`. |
| **Retrospective sweep** (Phase N step 3, it. 22 of run `20260729-025318`; **DEPLOYED at `7a4f59c`; wired in it. 24, but candidate 65 says no cadence sweep has ever published a correction in production**) | **A sweep re-matches retained evidence against the album; it never re-hears audio, and it proposes — it does not apply.** One matcher for both paths (`live_identity.assign_speakers`), so a correction can never be a second implementation's second opinion. It may not invent a speaker, may not remove a label it cannot replace (unrepresentable: the correction's speaker is non-optional), and may not move a unit that fails the deployed margin. A merge at ≥ 0.70 needs an admitted bank on **both** sides, matches on the **union** of the exemplars, and leaves the id with the most admitted speech standing. Deterministic, and applying a revision leaves nothing for the next sweep to correct. The ledger is bounded at 20 000 units ≈ 22 MB and refuses new units rather than evicting old ones. |
| **Session end** (Phase N step 3, it. 26 of run `20260729-025318`; **DEPLOYED at `7a4f59c` and PROVEN TO RUN AND PUBLISH on the real service - iteration 7 measured 19 of 31 spans relabelled through a portal-reachable `stop`; the Mac client is the one client that does not call that route - candidate 60**) | **The meeting's last sweep is not a cadence, and it reconciles before it re-matches.** The cadence is paced by the *next* span's start, so the last interval of every meeting — and the whole of any meeting shorter than one interval — has nothing to trigger it, and the last span's evidence is retained unlabelled until something settles it. `finalize_identity` settles that span **then** sweeps once, unconditionally; reversed, the sweep "corrects" the last span to the label it already had. Asked for by name at all three layers, so a stack that cannot sweep is not an error. **`stop` calls it after the drain and before the close; `abort` deliberately does not** — a terminal session is not viewable and the correction would reach no reader. Nothing is terminal: a stack that raises is one named refusal (`identity_finalize_failed`) in the same map the session's own refusals use, and `identity_finalized` is recorded whether or not anything changed. |
| **Living document** (Phase N step 3, it. 25 of run `20260729-025318`; **DEPLOYED at `7a4f59c`; no revision has yet reached a real reader - candidates 60 and 65**) | **A correction is published beside the words, never onto them.** `transcript` and `prefix_hash` record what was *said*; `revised_transcript` is who is believed to have said it now, and a reader is shown `revised_transcript \|\| transcript`. A correction is addressed by `(span, local speaker)` — the session retains a label track, because an abstained span shows `S00` for every one of its speakers. A span is revised **only if it re-renders to itself byte for byte**, so a relabelling cannot cost a word; the span grammar therefore has exactly one writer (`live_span_bounds.render_segments`) beside its one reader. A span never puts two of its own locals on one identity (`UNATTRIBUTED_SPEAKER` exempt). Nothing raises: six named refusals reach `canonical_processed`. A **closed** session is still revisable — the session-end sweep arrives after the last span. |
| **Duration vs timestamp** (P1/P2, it. 1 of run `20260729-025318`) | A **duration** is measured on `time.monotonic()`; `time.time()` is a **timestamp** and may step. The live decode measures itself and never reads the runner's `elapsed_sec`. Timing metadata that cannot be trusted converts to `None` (`live_adapters.trustworthy_duration_sec`) — elapsed and RTF null on `canonical_processed`, span committed, one WARNING on `moss_transcribe_diarize.live.decode` — never terminal. |

**The one class all of Phase J, L1 and candidates 50/53/56 belong to:** *a condition the design
contemplates is handled everywhere except the one path that ends (or degrades) the meeting.* Four
blockers in Phase H/J were this shape; L1 and 53 were the same shape and were fixed as one in
iteration 14; 50 landed as Phase M's D-c; **56 was the fifth instance and is Phase P**; **55 is the
one still unfixed.** Suspect this class first — and note the tell it now has a name for: every
instance so far was a *non-fatal* condition wearing a *fatal* type.

## Gates, merges and redeploys — index

Full transcripts (build times, per-node counts, payload reviews, content-parity hashes) are in the
progress.txt archive under each title.

| record | outcome |
| --- | --- |
| **IDEA-044 attempt-2 checkpoint** | GREEN, frozen at **`1ede498`** — 10/10 and 16/16, all eleven registered commands, tracer 0 Darwin skips. **Do not try to reproduce 16/16 on the tip:** B1 deliberately superseded checks 09 and 15 (Keychain default), which now read 14/16, and `validate-phase-a-locality.sh` is historical from iteration 6 — verify it against `1ede498`, never the tip, and never add paths to it. |
| **Closed-phase gates, merges and redeploys** - Phase B, the server-reliability gate, C4/#1, G4+#2, H4+#3, J5a+#4, K5a+#5, the G5/H4c/J5c/K5c redeploys, the F0 probe chain, J5d, F4a, K5d, the it.8/it.9 REDs, F1 it.6, F2 it.11, Phase M (a)+M6/#6+M6c, Phase P (a)+P7/#7+P5(c) | All GREEN and all spent. **The twenty-two rows are retired verbatim to progress.txt** with the fourth compaction (`grep -n "ARCHIVE OF context.md SUPERSEDED BLOCKS - RUN 20260729-094359 ITERATION 2"`). The two things in them a future iteration still needs are hoisted into the next two rows. |
| **K5c - the redeploy shape to copy** | Rollbacks committed **before** any host is touched; manifest admission checked **after** the checkout, under the code about to start; content parity proven by hashing files whose **content differs** across the two SHAs (a file that is unchanged proves nothing); the deployed change **exercised**, never `hasattr`-ed; and the TCC grants **measured**, not assumed, to survive a bundle replacement (inode moved `211648186 -> 211995344`). **J5c is the same shape minus the Mac rebuild** and is what a *server-only* merge needs - which is what the last three merges have been. |
| **F3 soak, run `20260729-025318` it. 9 - SUPERSEDED as evidence, kept for the deltas** | **rc=3 - 5 GREEN, 1 RED** on `42abc5a`. 17/17 full minutes, 443 spans, 355/355 portal polls 200, view authority 200 at age **1024.1 s**, user-visible p95 **4557.2 ms** <= 6000 qualified, decoder p95 RTF **0.546**, one lane degraded at t+474 s and **kept capturing**, clean drain `retained=0`, hosts clean. RED: the clean stop did not revoke view authority - **candidate 60**. |
| **F3 on Phase N, run `20260729-094359` it. 12 - THE CURRENT F3 EVIDENCE** | **rc=3 - 5 GREEN, 1 RED** on the deployed `7a4f59c`; `live-canary-clauses.py <dir> --user-visible-gate-ms 6000`. Label `ralph-i12-f3-20260729T121319Z`, session `34a71d7a…`, 1019.7 s of capture, 17 utterances, `ABORT=none`. GREEN: **381/381** portal polls 200 over t+1.2 → t+1029.8; decoder p95 RTF **0.568** < 1 over **648** spans (p50 0.189, max 5.735, total decode 252.4 s, D-c capped **1 of 648** against `42abc5a`'s 67 of 443); user-visible p95 **4106.5 ms** ≤ 6000 **qualified with `timelineIntact` TRUE** (n=605, `mixerOriginResolved` true, 0 fetch failures; committed **2674.01** + render bound **1432.50**); **17 full minutes** each carrying 57.3–61.0 s of accepted audio and new spans; the same view authority 200/200/200 at age **903.6 s** *and* **1023.0 s**. RED: the post-stop check 0.2 s after a clean stop answered snapshot=200 events=200 — **candidate 60**, expected. **No lane fault of any kind** — lane health changed exactly twice (both capturing → both stopped at t+1025.2), `failure_code` None and `failed_samples` 0 on both lanes, so `42abc5a`'s t+474 s degradation did not recur. Clean drain `retained=0`, refusal None. Identity: **16 canonicals for 2 voices, saturated t+138.1 s**; 397 empty / 129 prepared / **122 abstain**; `live-canary-analyze.py --voices 2` rc=4 (system marker phonetically REWRITTEN as `carton of` ×3 at 0.80 in a MUTED run; room marker **not transcribed** — the **sixth** measurement of candidate 51's hardware limit, this time against two MacStudio deliveries at volume 70). |
| **Phase N gate (a) / N8 merge #8 / N8c redeploy** — all three spent and **retired verbatim to progress.txt** with the fifth compaction | **(a) GREEN at `1e1cf3f`** — Swift **158/0** with 0 warnings on a fresh scratch, Python **801 passed / 2 skipped / 368 subtests** in 75.67 s, tracer **4/0 skips**, discriminator 10/10, leak-scan clean, lane-refusal probe rc=0, guard rehearsed non-vacuously. Accuracy re-measured **on production code**, which is what ADR-0002 asks for rather than a suite result: album **93.44/92.18**, overwrite 72.02/55.68, swept **99.26/98.48** with **116** corrections, **0** merges and **`residual_corrections` 0** — both halves of ADR-0002's bar met on the code about to merge. Payload **44 files / +8172/−126**, **0 under `macos/`** → server-only; the product diff's 112 removals touch **no** domain-contract value and `live_identity.py`'s 83 are a **move**, not a deletion. **(b) merge `7a4f59c`** (parents `42abc5a` + feature tip `732e1f6`), join `96ba30e` proven content-free **before** running it, **merge tree == feature tree `16de7f62…`**, in-worktree gate digit-for-digit identical to (a)'s numbers, and the guard then refuses a **ninth** (rc=1, `main moved from expected pre-merge SHA 42abc5a…`). **(c) deployed 4/4 at `7a4f59c`**, server MainPID 355607 → 365632 with `NRestarts=0`, batch `301112`/`322117` untouched, **host manifest regenerated at the calibrated 0.35/0.1** (`provider_manifest_hash 61d97ffe… → 0cb775da…`, no domain-contract value moved), m4mbp **checkout only — no rebuild, no reinstall, no TCC exposure**, and the deployed change **exercised, not `hasattr`-ed** (2.0 s enrol `admitted`, 0.5 s fragment `rejected_below_admission`; `live-pipeline-probe.py` rc=0, 40/40 ticks, 0 non-200s, view **401/revoked** after a clean stop). |
| **F1 on Phase N, run `20260729-025318` it. 30** | **rc=3 - 5 GREEN, 2 RED** on the deployed `7a4f59c`. RED: user-visible p95 **4150.8 ms** vs the **4000 ms** gate (miss 150.8 ms, 3.8 %) and decoder p95 RTF **2.365** carried entirely by **3 spans shorter than 0.1 s** (candidate 64; p50 0.142, total decode 17.09 s over an 86 s meeting = aggregate 0.20). Identity half, the best measured on real hosts: **12** canonical speakers for 2 voices (was 16), capacity **never saturated** (was t+65.6 s), 36 prepared / 16 empty, **zero** abstains and zero refusals at the calibrated 0.35/0.1, and the system lane's program keeps **one** identity across the 28 s room window and back. `identity_finalized` **0** in 467 events — **uninformative, not negative**: no client can read that event (iteration 7). Narrative block retired to progress.txt with the fifth compaction. |
| **F2 on Phase N, run `20260729-094359` it. 1 - Phase N gate step (d) COMPLETE** | **GREEN, rc=0** - six GREEN, no RED, no UNDECIDED, on the deployed `7a4f59c`. user-visible p95 **4078.6 ms** <= 6000 qualified (`sufficientSamples` true, n=114; committed 2680.15 + render bound 1398.44), decoder p95 RTF **0.577** over 171 spans (max 2.529, total decode 58.3 s over 319 s, D-c capped 3), a **5.090 s** CLOCK_MONOTONIC interruption seen by the client and survived, outbox 0 -> **5** -> 0, **1261 published == 1261 `POST /frames`**, and **every one of the session's 4766 logged requests answered 200**. Identity: 16 canonicals for 2 voices, saturated at **t+127.1 s** (33 s later than `42abc5a`'s t+93.9 s), 105 prepared / 50 empty / 16 abstain (15 `speaker_capacity_exceeded`). Not certified by it: the system-audio-denied variant (deliberately not attempted - it would spend a TCC grant) and the "two speakers" half. Narrative block retired to progress.txt with the fifth compaction. |

**How the two fences are satisfied — the standing pre-merge procedure.** Established for the second
merge (run `20260728-072601` iteration 5) and re-run unchanged for the third (run `20260728-112922`
iteration 5); the SHAs below are the second merge's, and the third's are in its own block above.
1. *History join.* `git merge --no-ff main` on the feature branch → `502a49a` (third merge:
   `9f1552e`). Proven content-free **before** running it: `git merge-tree --write-tree main HEAD`
   returned HEAD's own tree `5963a2b0…` (third: `bbb84f24…`), and afterwards
   `git diff --stat <pre-join HEAD> HEAD -- .` and
   `git diff --name-only <gate SHA> HEAD -- ':!scripts/ralph-afk'` were both empty. Only then was
   `merge-base --is-ancestor main HEAD` honestly true. Do **not** loosen fence 2; join first.
2. *`expected_main` advanced in the script*, not by env override, with a comment citing the
   authorizing amendment — so the guard is still live and its reason reviewable. Rehearsed
   **non-vacuously after each merge**: the dry run then names the superseded SHA and exits 1, so the
   next merge is refused until another amendment advances the line again.
3. *Fence 2 speaks.* It was a bare command under `set -e` that exited 1 printing nothing; it is
   now `|| { echo ERROR …; exit 1; }` naming both SHAs and the fix. Rehearsed against a dangling
   `git commit-tree` object (no ref created): both lines print, rc=1.
*Order that matters:* advance `expected_main` and **commit** it before running the script — the real
run refuses a dirty tree, and the commit becomes the feature tip the merge captures.

**Run `merge-keeper.sh` in the BACKGROUND, never in a time-capped foreground shell (iteration 5).**
The first attempt was killed by a 10-minute foreground cap. The kill does not run the script's EXIT
trap, so it left a linked worktree with `main` checked out and the merge staged — and because a
branch can be checked out in only one worktree, the *retry* would have failed at
`git worktree add … main`. Recovery is `git -C <wt> merge --abort && git worktree remove --force <wt>`.
The stall itself is **unexplained**: the last build artifact was written 17 s in, then nothing for
10 min; re-running each stage by hand in that same worktree passed (139 / 537+2 / 4), and a fresh
full run of the script then completed in **~95 s**. Suspect a first-run macOS security assessment of
the freshly built binaries at a new path; nothing was proven, so if it recurs, `sample` the stuck
process *before* killing it — that is the evidence this iteration failed to collect.

**The port-publish race — retired to progress.txt with the fifth compaction; the standing lesson
stays.** The keeper script's own gate once returned `596 passed, 2 skipped, **2 errors**` on a tree
that had just passed clean in the primary worktree. Both errors were fixture setup: the `live_server`
fixture in `tests/test_live_deployment_credentials.py` treated the port file's **existence** as the
signal that the port was readable, and `write_text` creates the file **before** it holds anything
(measured over 4000 barrier-released rounds: **168/4000** torn reads, 4.2 %; staging file +
`os.replace` **0/4000**, which is the fix that shipped — not a tolerant reader, which would have left
the window open). **The standing lesson: an unexplained failure inside `merge-keeper.sh` that does not
reproduce in the primary worktree is a scheduling-sensitive test, not a bad merge.** Re-running the
merge until it passes would have hidden a 4 %-per-run flake under an authorized merge.

## Validation

```bash
# --- narrow: live server slice (~5 s) ------------------------------------
python3 -m pytest tests/test_live_auth.py tests/test_live_portal.py -q
python3 -m pytest tests/test_live_service_runtime.py tests/test_live_provider_bundle.py \
  tests/test_live_mixer.py tests/test_live_ingest.py -q

# --- C1 view-authority nodes (10) - the narrow recipe is RETIRED to progress.txt; the
#     server-reliability gate is GREEN at f400d426 and the full gate below runs them. --------

# --- N-gate: live speaker accuracy on production code, 27 nodes, ~20 s (iterations 16 + 23) ----
#     Fixture integrity + the two silence splits (16 parametrised), five measured live claims,
#     then N-convergence's six (ADR-0002 gate B: the sweep cadence, applied and scored).
python3 -m pytest tests/test_live_identity_accuracy.py -q
# The numbers themselves, any configuration, without pytest -- this is how a future run
# re-measures rather than re-derives. Configs are lru_cached, so each costs ~1.2 s once
# (~3 s once a sweep_interval is passed: the sweep re-scores every retained unit in Python).
# `sweep_interval` is meeting seconds and is only defined for policy='album'; passing it with
# 'overwrite' RAISES on purpose, so "the sweep did not help" can never mean "there was no album".
python3 -c "
import sys; sys.path.insert(0,'tests'); sys.path.insert(0,'.')
import live_identity_accuracy as H
for tag, kw in (('album',{}), ('overwrite',{'policy':'overwrite'}),
                ('swept',{'sweep_interval':60.0}), ('swept cap64',{'sweep_interval':60.0,'max_speakers':64})):
    r = H.replay_all(**{'policy':'album', **kw})
    print('%-12s final %.2f/%.2f  live %.2f  corr %d merges %d resid %d' % (
        tag, H.mean_accuracy(r)*100, H.min_accuracy(r)*100, H.mean_live_accuracy(r)*100,
        sum(x.corrections for x in r.values()), sum(x.merges for x in r.values()),
        sum(x.residual_corrections for x in r.values())))
"
# Expect SINCE ITERATION 21 (Q1's birth floor): album 99.13/97.37 · overwrite 72.0/55.7 ·
# swept 99.65/99.10 · swept cap64 99.65/99.10, merges 0 and residual 0 everywhere.
# `accuracy` is the transcript a reader ENDS with and `live_accuracy` the one they read DURING
# the meeting; without a sweep the two are equal. The 16-speaker cap NO LONGER BINDS, so
# cap64 == cap16 on every field -- before Q1 it was worth +4.5 pp and the pre-Q1 expectation
# was album 93.44/92.18 · swept 99.26/98.48.

# --- Q1 birth floor: the two semantic reverts that prove the nine nodes red-before. Each is a
#     pytest plugin in /tmp, run with `-p <name>`; neither touches the tree. -------------------
#   /tmp/redbefore_plugin.py   (6 red in accuracy + provider bundle)
#     from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider
#     del WeSpeakerLiveEvidenceProvider.birth_deferrals
#   /tmp/redbefore2_plugin.py  (3 red in test_live_identity)
#     from moss_transcribe_diarize.app.live_identity import BoundedCausalIdentityPreparer
#     BoundedCausalIdentityPreparer._deferred_births = lambda self, *, span, candidates: {}
PYTHONPATH=/tmp python3 -m pytest tests/test_live_identity_accuracy.py \
  tests/test_live_provider_bundle.py -q -p redbefore_plugin    # expect 6 failed, 60 passed
PYTHONPATH=/tmp python3 -m pytest tests/test_live_identity.py -q -p redbefore2_plugin
                                                               # expect 3 failed, 10 passed
# Two nodes stay GREEN under both on purpose: a short span is still LABELLED (matching is not
# enrollment) and a provider without the capability births exactly as before.

# --- Q1 on real conversational audio. The bench is a RE-IMPLEMENTATION sharing only the
#     production embedder, so the production change does NOT flow through it -- the floor is
#     `simulate(birth_floor=)`. Fully cached: ~0.5 s. Needs the bench's own venv and corpora
#     (see prototypes/streaming-diarization/README.md); models and data are local-only. --------
(cd prototypes/streaming-diarization && .venv/bin/python proto_real_replay.py)
# Expect the operator's own aggregate unchanged -- grid-best/album+sweep mean 95.2 / min 87.4 --
# and the Q1 block below it: canonical speakers 3.56 -> 3.00 mean, worst clip 5 -> 4, accuracy
# identical on every clip. That the accuracy does NOT move is the finding, not a null result.

# --- N-sweep: the retrospective sweep engine, 40 nodes, ~0.1 s (iteration 22). Pure; no host,
#     no server, no fixture. The matcher extraction is proved behaviour-preserving by the
#     accuracy numbers above staying at 93.4 / 72.0, not by these nodes. -------------------------
python3 -m pytest tests/test_live_identity_sweep.py -q
# Its ten red-before reverts (each naming DIFFERENT nodes) are RETIRED to progress.txt: the
# step is merged, deployed and certified, and red-before evidence only reads against the tree
# it was written for. Re-derive by reverting one line against a COPY of the module.

# --- N-revision: a sweep's correction reaching the reader, 9 nodes (iteration 25). The seam node
#     is the one that matters -- real coordinator + session + preparer + provider + album + sweeper,
#     five 2 s spans, only the ONNX forward pass and the GPU decode scripted. ~4 s for all four. ---
python3 -m pytest tests/test_live_session.py tests/test_live_pipeline_seams.py \
  tests/test_live_portal.py tests/test_live_identity_sweep.py -q          # expect 145 passed
# Its ten red-before reverts are RETIRED to progress.txt (same reason as N-sweep's).
# The portal node needs `node` on PATH (it drives the real page's JS); it is skipped without it.

# --- N-tape: the session tape recorder, 37 nodes, ~3.6 s (iterations 19 + 20). ADR-0002 gate C's
#     assembly cases + ADR-0003 D2-D6, then the recorder. Offline, no host, no server, tmp_path. ---
python3 -m pytest tests/test_live_tape.py -q
# Its three red-before reverts are RETIRED to progress.txt.
# --- N-tape-wiring: the tape teed onto the REAL routes, 4 nodes inside test_live_api.py (33) ------
python3 -m pytest tests/test_live_api.py tests/test_live_tape.py tests/test_live_helper_failure.py -q
# Its four reverts, and the `{"deadline": 5.0}` gotcha a stop in these nodes needs, are
# RETIRED to progress.txt.

# --- K3 terminal record (8 nodes) - RETIRED to progress.txt with its logging-config proof;
#     Phase K is closed, merged and deployed. The narrow command it named: ------------------
python3 -m pytest tests/test_live_helper_failure.py tests/test_live_session_v2.py \
  tests/test_live_pipeline_seams.py -q

# --- narrow: Mac client --------------------------------------------------
swift build --package-path macos/MOSSCapture --product mtd-capture
swift build --package-path macos/MOSSCapture --product MOSSCaptureApp
swift test --package-path macos/MOSSCapture
swift build --package-path macos/MOSSCapture --show-bin-path   # resolve real product dir

# --- real-process tracer (darwin; needs a live private-address TLS server)
# present since the iteration-1 graft. It builds/bundles/ad-hoc-signs the real products, so it
# needs both Swift products built first. Currently 4 passed, 0 skipped (~15 s). The fourth node
# needs a 100.64.0.0/10 address on this host and FAILS (never skips) without one.
python3 -m pytest tests/test_macos_uds_tracer.py -q

# --- G1/G2/G3 narrow recipes (ATS shape gates, pairing-payload trim, control-channel
#     classification + logging) are RETIRED to progress.txt; `swift test` covers all of them. ------
# Reproducing the failure itself needs a REMOTE non-exempt peer, i.e. m4mbp -> 100.64.0.8. The
# ad-hoc probe that measured the matrix is disposable; rebuild it in /tmp when needed, never in
# the repo. Bare binary vs the same binary inside an ad-hoc `.app` is the whole experiment.

# --- the lab-bundle reinstall line is RETIRED to progress.txt (Phase A is closed and the
#     checkpoint is frozen at 1ede498; the tracer re-creates the bundle itself). ------------
# --- Phase A discriminator (the A4 gate; run it before and after any Phase-A change) --------
PYTHONDONTWRITEBYTECODE=1 python3 \
  "/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/spikes/idea-044-attempt2-red-control/repro.py" \
  --target "$PWD"        # 10/10 since iteration 4; must stay 10/10
# The 16-check sibling is historical after B1 and reads 14/16 on the tip (09 and 15 assert the
# superseded Keychain default). Its frozen green is commit 1ede498, not the tip.

# --- The B1-B5 / C2 / C3a-c and E1 / E2b / E3 narrow recipes are RETIRED to progress.txt
#     (closed phases; the full gate below runs them all), AND SO IS the m4mbp
#     rebuild+reinstall recipe this line used to promise "is kept below" - see the M6c
#     pointer further down. Two warnings survive them: NEVER pass `--rotate` to
#     ops/generate-live-tls.sh again (it invalidates every pairing payload and every pin a
#     Mac has stored), and E3 is closed forever - the read-only TCC check that remains live
#     is in the Deployed-reality TCC block. -------------------------------------------------
# --- Phase A locality is historical from iteration 6: check the frozen checkpoint, not the tip
git diff --name-only af3ac3667393a0411616f52f76339eff01dc13e2 1ede498 --   # == the 13 allowed paths

# --- wide checkpoint -----------------------------------------------------
# Keep executable builds explicit because tests/test_live_integration.py and the A-034 tracer
# execute the real products and error when they are absent. Swift 6.3 currently builds both
# executables incidentally during `swift test`; the gate must not depend on that behavior.
swift build --package-path macos/MOSSCapture --product mtd-capture
swift build --package-path macos/MOSSCapture --product MOSSCaptureApp
python3 -m pytest -q

# --- server (read-only probe) -------------------------------------------
printf '%s\n' \
  'set -e' \
  'systemctl --user is-active moss-vllm.service moss-web.service' \
  'cd /mnt/d/Coding/MOSS-Transcribe-Diarize && git log --oneline -1' \
  'nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv' |
  ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local \
    "wsl.exe -d Ubuntu -- bash -s"

# --- service reachability ------------------------------------------------
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.68.38:7860/                 # batch, must stay 200
curl -sk -o /dev/null -w '%{http_code}\n' https://100.64.0.8:7861/live               # live, target 200
curl -sk https://100.64.0.8:7861/api/live/descriptor | head -c 200

# --- Mac (read-only probe) ----------------------------------------------
ssh -o BatchMode=yes ga0@m4mbp 'sw_vers -productVersion; ls -d /Applications/MOSSCapture.app; \
  codesign -dv /Applications/MOSSCapture.app 2>&1 | head -5; codesign -d -r- /Applications/MOSSCapture.app 2>&1 | tail -1'

# --- host manifest finalization. MUST use the deployment venv python, not `python3` - see the
#     open defect above. SINCE ITERATION 17 the two matcher thresholds are REQUIRED flags
#     (candidate 63): omitting them is an argparse rc=2 refusal, not silent inheritance of
#     whatever the untracked host provisional holds. Re-running with the SAME values prints
#     `unchanged:` and does not touch the inode; re-running with the ALBUM values on the
#     current host will REWRITE, print a `rollback: mv <backup> <output>` line first, and change
#     identity_config_hash, combined_config_hash and the provider manifest hash.
#     RUN FOR REAL IN ITERATION 29: the host carried the pre-album 0.5/**0.05** (not the 0.5/0.2 on
#     record) and now carries 0.35/0.1; provider_manifest_hash 61d97ffe… -> 0cb775da…. Re-running it
#     with the SAME values now prints `unchanged:`, so a rewrite from here is drift, not calibration.
printf '%s\n' \
  'set -euo pipefail' \
  'cd /mnt/d/Coding/MOSS-Transcribe-Diarize' \
  '"$HOME/.local/share/moss-transcribe-diarize/venv/bin/python3" ops/finalize-live-provider-manifest.py --input "$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.provisional.json" --output "$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json" --source-revision "$(git rev-parse HEAD)" --hard-cap-samples 40000 --max-retained-samples 960000 --frame-samples 8000 --min-match-score 0.35 --min-match-margin 0.1' |
  ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local \
    "wsl.exe -d Ubuntu -- bash -s"
# Run it --dry-run FIRST and read the two `plan: set identity_config.…` lines and the
# `evidence: identity_min_match_*` lines; they are what makes the calibration reviewable.

# --- a SECOND manifest-admission recipe stood here carrying the SUPERSEDED manifest_hash
#     61d97ffe… (the host has been 0cb775da… since iteration 29). RETIRED to progress.txt;
#     the live one is the pre-redeploy admission check further down. -----------------------

# --- the H3/H1/J1-J4 per-node counts and their semantic-revert red-prove recipes are RETIRED to
#     progress.txt. The file itself is still the live seam suite (60 nodes): ------------------------
python3 -m pytest tests/test_live_pipeline_seams.py -q
# --- H blockers 2 and 3: the seven offline `live-hardcap-repro.py` cases are RETIRED to
#     progress.txt - every one has been rc=0 since H2 (iteration 3) and Phase H is closed.
#     The script is still in the repo and still the hard-cap repro named by every amendment
#     gate: `python3 scripts/ralph-afk/live-hardcap-repro.py --frames 8` is the smoke case. --

# --- The probe's own instruments, offline, no server and no pairing code (iterations 26, 28) -----
#     Run BOTH before spending a host run on the driver they belong to: an instrument that has
#     never run is not evidence that it works, and both of these found a real defect on first run.
python3 scripts/ralph-afk/soak-abort-probe.py      # live-soak.sh's abort decision: 90/90, rc=0
python3 scripts/ralph-afk/view-reader-probe.py     # live-pipeline-probe.py's ConcurrentViewReader
python3 scripts/ralph-afk/live-pipeline-probe.py --self-test   # its sweep/event reductions: rc=0
# view-reader-probe.py caught `self._stop = threading.Event()` shadowing threading.Thread._stop,
# which threading.Thread.join() calls internally: every run would have died at reader.join().
# --self-test (candidate 67, iteration 13) guards the two reductions that read a field off a
# surface: the cadence version comes off `canonical_processed` and never off a committed item,
# an absent field is null and never 0, and a re-delivered event (`since_seq` is INCLUSIVE) is
# one measurement. Red-before is a semantic revert on a COPY - read `items` instead of
# `canonical_events` and drop the seq guard - which fails 17 of its checks.

# --- candidate 65/55's CAUSE chain: five offline instruments (identity-evidence-probe.py,
#     sweep-fixpoint-probe.py, album-bank-shape-probe.py, sweep-multiplicity-probe.py,
#     birth-floor-probe.py). All five are still in scripts/ralph-afk/ and re-runnable; their
#     invocations and every expected number are RETIRED to progress.txt, because iteration 6
#     closed the diagnostic chain ("no further probe of 65's cause is worth an iteration")
#     and iteration 9 then CORRECTED their offline mechanism on the deployed service. Read
#     Phase N decisions 19 and 20 and the deployed-sweep block (§3) for what they
#     settled; read the archive for how to re-run one. ---------------------------------------

# --- iteration 7: READ THE SESSION-END SWEEP ON THE DEPLOYED SERVICE. No Mac, no TCC, no operator,
#     no product change; ~3 min per run. Costs one pairing code, ONE DEVICE (REVOKE IT) and one
#     session, and restarts nothing. This is the only instrument in the loop that can answer
#     ADR-0002's second acceptance half against the running system. ------------------------------
# 1. parity first, or the run speaks for a service you are not testing:
#      git diff --name-only <deployed sha> HEAD -- ':!scripts/ralph-afk'      # must be EMPTY
# 2. mint on the host loopback; ops/live-pair.sh takes NO --device-id (the CLIENT names the device):
#      printf '%s\n' "cd /mnt/d/Coding/MOSS-Transcribe-Diarize && bash ops/live-pair.sh 2>&1" \
#        | ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local "wsl.exe -d Ubuntu -- bash -s" \
#        | sed -n 's/^payload: //p' | tr -d '\n' > /tmp/payload     # expect 113 chars, NOT 122
# 3. run under `bash -c` (the zsh trap) with the payload on STDIN, >= 75 s so the 60 s cadence
#    deadline is crossed and enough spans commit to see a revision:
#      cat /tmp/payload | python3 scripts/ralph-afk/live-pipeline-probe.py --host 100.64.0.8 \
#        --port 7861 --pin a35ca9fc… --device-id "ralph-<it>-<utc>" --seconds 75 --lead-seconds 1.0 \
#        --lane-audio continuous --lane-offset-ms system=137 --report /tmp/probe.json
# 4. READ THESE THREE FIELDS, which is the whole point and which no run before iteration 7 had:
#      .stop.status                     200 => `_finalize_identity_locked` COMPLETED (it runs before
#                                       session.stop, so a raise would have failed the stop)
#      .transcript.items[].revised_transcript   the corrections themselves. Compare against
#                                       .transcript[].transcript: the WORDS must be byte-identical
#                                       and only the [Sxx] tags may move (Phase N decision 10).
#      .event_kinds                     a histogram, not a count. `events_seen` alone cannot answer
#                                       "did the sweep run".
#    Iteration 7 measured 19 of 31 spans revised, 19/19 label-changing, 0 byte-identical rewrites,
#    words unchanged in all 19, {S00:25,S01:5,S02:1} -> {S01:24,S00:7,S02:1}, on 2 canonical
#    speakers for 2 real voices. A meeting at F2's 8.4 refs/voice is the run still not taken.
# 5. `.post_stop_events` is EXPECTED to be 403 `session is not owned by this device.` — a clean stop
#    releases the session from the access store, and it already revoked view authority (401). That
#    is the finding, not a probe failure: `identity_finalized` is unreadable by EVERY client and is
#    never journalled, so NEVER read "0 hits on identity_finalized" as evidence about the sweep.
# 6. THEN REVOKE THE DEVICE, in the same iteration (loopback, on the host). Assert the 200 AND its
#    {"device_id": …} body — a POST …/revoke 404s for route-not-found and reads like "already gone":
#      curl -sk -X DELETE 'https://127.0.0.1:7861/api/live/devices/<device-id>'
#    then confirm the store is back to ONE unrevoked device (m4mbp), and that HEAD, all three
#    MainPIDs, NRestarts=0, live-runs 0, /tmp/mtd-live-* and journal tracebacks are all unchanged.
# --- iteration 9: THE SAME PROBE AT CANDIDATE 55's FRAGMENTATION, plus its control. Two runs,
#     ~150 s each, two devices (REVOKE BOTH). This is the only way to produce 55 on demand. -------
#      ... --seconds 150 --lane-audio fragmented --fragment-lane microphone --fragment-interval 3.0
#      ... --seconds 150 --lane-audio continuous                       # the control, same length
#    Read `.fragmentation` (canonical_speakers / references_per_real_voice / capacity_abstains) and
#    `.sweep` (revised_items / label_changing / byte_identical_rewrites / words_moved). Iteration 9
#    measured 16 canonical vs 4 and 7/61 revisions vs 20/61 -- and, the finding that needs no
#    control, ZERO reassignments in either. The builder REFUSES a fragment line that renders at or
#    above the 0.5 s evidence floor, so a `say` voice change cannot silently turn this back into the
#    healthy regime; if it raises, shorten the line rather than lowering the floor.
#    KNOWN CONFOUND, unclosed: the fragmented run's peer lane carries ONE voice and the control's
#    two, so the revision RATES are not a single-variable contrast. Closing it needs a two-voice
#    peer track, which the probe cannot build (one voice per lane).

# --- H blocker 4's host probe and its boundary sweep are RETIRED to progress.txt (J1's clamp
#     superseded them; the surviving rule is the Span-bounds row in Shipped contracts). ------------
# --- J5d, the third amendment's gate (GREEN in iteration 16): its three-step recipe and the
#     build-span-sweep.py J1 check are RETIRED to progress.txt. What survives it is the
#     live-pipeline-probe.py report's `decode` section, which every probe run still reads: --
# 5. SINCE ITERATION 23 the report carries a `decode` section reducing D-c's own event fields:
#    spans_measured / cap_present_count / capped_count / capped_span_ids, elapsed_sec and rtf
#    quartiles, caps_observed, and cap_derivation_mismatches. `cap_expectation_source` says whether
#    the expected cap came from the PRODUCT function (imported) or the recorded literal - prefer
#    the former and treat a `recorded-literal` report as weaker evidence. Read the three states
#    apart, because they are NOT the same result:
#      cap_present_count == 0            -> D-c is NOT on this service (a pre-iteration-16 build)
#      cap_derivation_holds == false     -> it is there and DRIFTED; the mismatch names its span
#      capped_count == 0 with the above green -> deployed and UNEXERCISED. This is a pass on the
#        cap's SAFETY (nothing truncated) and says NOTHING about its latency effect.
#    ALWAYS discount span 0: the session's first decode is engine warm-up (measured iteration 23:
#    1.689 s for 0.763 s of audio, RTF 2.214, empty transcript, against <= 0.456 s for all 57
#    others). It is the `rtf.max` in an otherwise clean run and reads exactly like a runaway.

# --- the lane-refusal probe (iteration 11). Names the 409 that ends a meeting after one capture
#     overrun, and reproduces the rival sequence-gap hypothesis beside it. Offline and
#     deterministic: drives the REAL create_app in-process through fastapi.testclient, starts no
#     server, opens no socket, touches no deployed state, needs no GPU and no network (~3 s).
#     rc=0 every recorded expectation held, rc=3 the diagnosis is wrong, rc=2 it could not run.
#     Valid as evidence about the DEPLOYED service only while the branch carries no product source
#     and all four checkouts are one SHA - check that first, it is one command.
#     It has been SPENT twice and is VALID again: from iteration 16 until M6c redeployed, and from
#     Phase N step 1 until N8c redeployed. All four checkouts hold 7a4f59c.
#     THE DURABLE RULE, because this flipped twice: compare against the DEPLOYED SHA, never against
#     `main` — between a merge and its redeploy those are different commits, and branch-vs-main
#     parity then says nothing about the running service. **AND THE SHA IN THIS COMMAND IS ITSELF A
#     THING THAT GOES STALE**: it read 77e0014, two merges behind the deployed service, from
#     iteration 20 until iteration 11 of run 20260729-094359 found it. Update it at every redeploy.
git diff --name-only 7a4f59c HEAD -- ':!scripts/ralph-afk'   # DEPLOYED sha; non-empty == probe != service
git diff --name-only main    HEAD -- ':!scripts/ralph-afk'   # branch parity; NOT the same question
python3 scripts/ralph-afk/live-lane-refusal-probe.py --json /tmp/ralph-lane-refusal.json
# It imports tests/test_live_api.py BY FILE PATH (`tests/` is not a package, so
# `import tests.test_live_api` fails with ModuleNotFoundError) to reuse the tracked payload
# builders - restating them here would let the probe drift from the shapes the suite asserts.

# --- the /tokenize accounting recipe and the decode-cap latency probe are RETIRED to progress.txt.
#     D-c is landed, deployed and measured (7.571x on the deployed engine); the cap derivation is
#     re-checked on every run by `cap_derivation_holds` in live-pipeline-probe.py's report. --------
# --- secret-hygiene scan (lives with the tracer spike, not in scripts/ralph-afk) ----------
#     It scans macos/MOSSCapture/Sources, the tracer test and the tracer artifacts - NEVER the
#     portal. The clause's browser-storage half is the next command, not this one. ---------------
bash "/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/spikes/idea-044-real-uds-tracer/leak-scan.sh"

# --- the clause's BROWSER-STORAGE half (iteration 10). Read-only: one unauthenticated GET /live
#     over the pinned leaf, no pairing code, no device, no session. ~4 s. rc 0 green / 3 red /
#     5 a control went undetected / 6 named refusal. `--offline` measures this checkout's render
#     instead and makes the deployed-parity clause UNDECIDED (use it when the tailnet is down).
#     Needs `node` on PATH; it drives the TRACKED harness in tests/test_live_portal.py, so a change
#     to that harness changes what this measures - which is deliberate. -------------------------
python3 scripts/ralph-afk/portal-storage-probe.py --report /tmp/portal-storage.json
python3 scripts/ralph-afk/portal-storage-probe.py --offline   # no host contact

# --- Phase A compatibility checkpoint (historical; frozen at 1ede498) ----
# Run the exact eleven registered commands from:
# /Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/context/VALIDATION_COMMANDS.md
# section "IDEA-044 attempt-2 exact commands". `validate-phase-a-locality.sh` belongs to that
# checkpoint and now fails on the tip by design — see the locality note above.

# --- the pre-redeploy manifest admission check (read-only; run before ANY live restart from H2 on).
#     Both new refusals fail the service closed, so check them before bouncing the unit, not after.
#     Expect endpoint == bounds == 40000, speech_provider.frame_samples in {160,320,480}, and no
#     `session_hard_cap_samples` anywhere in the document. SINCE ITERATION 29 also expect
#     identity_config {max_speakers 16, min_match_score 0.35, min_match_margin 0.1} and
#     manifest_hash 0cb775da005a7698124b66c7e4432d83c4491ad0080088174c644f796599ca1f. Read it
#     through the RUNTIME'S OWN readers, not out of the JSON - `_preflight_payload(path)` returns a
#     DICT (`available`/`failures`/`manifest_hash`/`config_hashes`/`descriptor`), NOT an object, and
#     `_identity_config` / `_endpoint_config` / `_bounds` each take their own sub-mapping. ---------
printf '%s\n' 'python3 - <<PY
import json,pathlib
d=json.loads((pathlib.Path.home()/".local/share/moss-transcribe-diarize/live/live-provider-manifest.json").read_text())
print("caps equal =", d["endpoint_config"]["hard_cap_samples"]==d["bounds_config"]["hard_cap_samples"], d["endpoint_config"]["hard_cap_samples"])
print("vad frame_samples =", d["speech_provider"]["frame_samples"])
print("retired knob present =", "session_hard_cap_samples" in json.dumps(d))
PY' | ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local "wsl.exe -d Ubuntu -- bash -s"

# --- the full gate, run before every merge (iteration 4 of run 20260728-072601 re-ran it green at
#     23dc163; iteration 4 of run 20260728-112922 re-ran it green at 8b852f2; iteration 5 of run
#     20260728-181020 re-ran it green at cd7faf9 — 150 / 598+2 / tracer 4 / 10/10 / clean) --------
# The zero-warning claim needs a FRESH scratch each time: a second build into a warm scratch is a
# no-op and re-emits nothing, so grep `warning:` over a first build's log, not a rebuild's.
SCRATCH="$(mktemp -d /tmp/moss-gate-scratch.XXXXXX)"   # must be EMPTY; one dir, two invocations
swift build --package-path macos/MOSSCapture --scratch-path "$SCRATCH" --product mtd-capture
swift build --package-path macos/MOSSCapture --scratch-path "$SCRATCH" --product MOSSCaptureApp
swift build --package-path macos/MOSSCapture --product mtd-capture      # default .build: the tracer
swift build --package-path macos/MOSSCapture --product MOSSCaptureApp   # executes these two
swift test --package-path macos/MOSSCapture
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_large_upload.py -q -rs   # names the 2 skips
test -z "$(git status --porcelain)"

# --- the spent notes for keeper merges #1/#2/#6 are RETIRED to progress.txt. EIGHT merges
#     are spent (f9285d6 / 317df4d / b817871 / 6a540fe / fc7097d / 77e0014 / 42abc5a /
#     7a4f59c) and the guard refuses a NINTH. Both fences are satisfied the same way every
#     time - join first, then advance expected_main IN-SCRIPT and commit it. -----------------
RALPH_MERGE_DRY_RUN=1 bash scripts/ralph-afk/merge-keeper.sh   # expect rc=1, "main moved from …"
# To dry-run the guard while the tree is DIRTY (e.g. to check a proposed expected_main before
# committing it), the script needs BOTH flags — RALPH_MERGE_DRY_RUN=1 alone still refuses:
#   RALPH_MERGE_DRY_RUN=1 RALPH_MERGE_ALLOW_DIRTY=1 bash scripts/ralph-afk/merge-keeper.sh
# If a further merge is ever authorized, run the script in the BACKGROUND: a foreground timeout kill
# skips its EXIT trap and strands a worktree holding `main`, which then blocks the retry. Recover
# with: git -C <wt> merge --abort && git worktree remove --force <wt>

# --- M6c's publish+redeploy recipe AND the m4mbp rebuild+reinstall recipe are RETIRED to
#     progress.txt (grep "M6c: publish + redeploy the SIXTH merge"). N8c below is the kept
#     template; M6c is the strictly larger one and is what a merge touching `macos/` needs.
#     The four rules out of it that are not shape but law: PROVE the venv resolves the
#     package from the checkout (an editable install) rather than assuming it; EXERCISE the
#     deployed change instead of `hasattr`-ing it (and note `canonical_decode_token_cap` is
#     KEYWORD-ONLY - a positional call raises TypeError, which under 2>/dev/null looks
#     exactly like the symbol being absent); a `strings` witness needs a CONTROL WORD present
#     in BOTH binaries, or a 0 cannot be told from a broken grep; and two shapes report a
#     SKIPPED check as a passing one - `set -o pipefail` with a no-match `ls` glob, and
#     reading `live-runs/` from a path that does not exist. The bundle rollbacks are the
#     ONLY copies of those bytes and are named in Deployed reality; the current install is
#     the 77e0014 product with backup-20260728T222244Z beside it. ---------------------------
# --- N8c: publish + redeploy the EIGHTH merge (SPENT in iteration 29). The J5c shape - server
#     restart plus an m4mbp checkout with NO rebuild - plus ONE step no prior redeploy had. Order
#     matters and this is the order that worked:
#   1. pre-record the rollbacks in progress.txt and COMMIT, before any host is touched
#   2. git push origin main                       # 42abc5a..7a4f59c, verify --is-ancestor FIRST;
#                                                 # after this the merge has no rollback but a revert
#   3. server: cp -p the manifest to a DETERMINISTIC name (the finalizer's own backup name is minted
#      at run time, so it cannot be pre-recorded), then git fetch + checkout, then the finalizer
#      --dry-run, then for real, then the admission check - ALL BEFORE the restart
#   4. systemctl --user restart moss-live-web, then POLL /live for 200 (never sample once)
#   5. m4mbp: git fetch <fork URL> main && git checkout <sha>   # no build, no install
#   6. four-way `git rev-parse`, then `git diff --name-only <deployed sha> HEAD -- ':!scripts/
#      ralph-afk'` empty -> the offline probes speak for the deployed service again
#   THE ORDERING TRAP: the finalizer's REQUIRED --min-match-score/--min-match-margin flags only
#   exist at the NEW revision, so the checkout must precede the finalizer. Running it against the
#   old checkout is an argparse rc=2, which reads like a broken command rather than a wrong order.
# --- the J5c, K5c, D1 AND M6c publish/redeploy recipes are all RETIRED to progress.txt. N8c above
#     is the one kept in full (server restart + manifest regeneration + an m4mbp checkout); M6c is
#     the strictly larger one (it adds the Mac rebuild) and its four laws are in the pointer above. 
# --- m4mbp: `origin` IS NOT THE ALPHASIGHT FORK THERE. The names are INVERTED relative to this
#     host: on m4mbp `origin` = OpenMOSS upstream and the fork is `alphasight`. `git fetch origin`
#     there fetches the wrong repo and the checkout then fails `fatal: unable to read tree (<sha>)`,
#     which looks like corruption and means "never fetched". Resolve the remote by URL:
ssh -o BatchMode=yes ga0@m4mbp 'cd /Users/ga0/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize && \
  git remote -v | grep AlphaSightInc'
#   then: git fetch alphasight main --quiet && git checkout <sha>     # rollback: checkout 7a4f59c
#   (that rollback SHA is the DEPLOYED one and moves with every redeploy; it read a six-merges-stale
#    317df4d until iteration 11 of run 20260729-094359. m4mbp's own `main` ref is untouched upstream
#    40cf854, so `git checkout main` there is NOT a rollback to this project's main.)
#   The post-checkout inode check that stood here quoted K5c's inode 211995344; the install
#   has been 212080356 since M6c and the premise was already marked stale (the TCC grants key
#   on bundle id + signing identity, not the inode). RETIRED to progress.txt, with the
#   duplicated m4mbp-cannot-reach-the-batch-LAN topology note - both live in Deployed reality.
# --- F4a: the rollback rehearsal (SPENT in iteration 8; the PRD clause is GREEN). The full
#     recipe with its assertions is RETIRED to progress.txt, together with the rollback-
#     rehearsal block's four enabling facts. THE ORDER IS FORCED BY ExecStart - the live unit
#     runs ops/start-web.sh FROM THE CHECKOUT, and at 163e969 that script brings up a BATCH
#     server - so `disable --now` before the checkout moves and restore the checkout before
#     `enable --now`; use `disable`, not `stop`. NEVER `git clean` there: it would delete the
#     untracked ops/moss-live.env the restore depends on. The two mutations, each with its
#     rollback (the restore SHA is the DEPLOYED one and moved with every redeploy - it read a
#     six-merges-stale 317df4d until iteration 11 corrected it): ------------------------------
systemctl --user disable --now moss-live-web.service            # rollback: enable --now
git -C /mnt/d/Coding/MOSS-Transcribe-Diarize checkout 163e969    # rollback: checkout 7a4f59c
# Then POLL (~10 s) for https://127.0.0.1:7861/live -> 200; a single probe at 6 s returns 000.
# Stop condition: the served leaf must still hash to the D2 pin a35ca9fc…, else every paired
# Mac is broken - do not proceed, record a blocker.

# --- pinned live reachability from any client host (read-only; run from MacStudio or m4mbp) ----
# Pin first, then trust exactly that leaf — this is what the Mac client's full-certificate pin does.
#   PIN=a35ca9fc4a0f5b32bf7da6dc2e03c1fa5b4ac60992f0ee49b6d5677d22b680ff
#   echo | openssl s_client -connect 100.64.0.8:7861 \
#     -servername ga0-alienware-rtx4070ti.tailnet.aisight.us 2>/dev/null | openssl x509 > leaf.pem
#   openssl x509 -in leaf.pem -outform DER | shasum -a 256   # must equal $PIN before trusting it
#   curl -s --cacert leaf.pem \
#     --resolve ga0-alienware-rtx4070ti.tailnet.aisight.us:7861:100.64.0.8 \
#     -o /dev/null -w '%{http_code}\n' \
#     https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/live      # 200
# Plaintext on 7861 must stay dead: `curl -m 5 http://100.64.0.8:7861/live` -> 000.

# --- batch-restart safety probe (read-only; mutates and starts nothing) --------------------
# The running batch process serves module-level constants, so a checkout cannot change it; this is
# what proves the *next* restart is also unharmed. It rewrites only the final `exec` line of a
# /tmp copy and asserts the original last line first, so it can never launch the server.
#   last line must be: exec "${VENV_DIR}/bin/mtd-subtitle-web" "${web_args[@]}"
#   sed '$ s|.*|printf "argv:%s\\n" "${web_args[@]}"|' ops/start-web.sh > "$tmp/probe.sh"
#   set -a; . ops/moss.env; set +a; bash "$tmp/probe.sh"
# Expect exactly tests/test_live_service_deployment.py:52-62 with {state} and DEPLOYMENT_ROOT
# expanded, and no --live flag. Re-run it after D3 edits any env file.

# --- the pre-iteration-12 /tmp F1 canary driver is RETIRED to progress.txt; it put the SAME audio
#     on both lanes (candidate 51) and is superseded by the lane-separating canary below. ----------
# --- the LANE-SEPARATING canary (iteration 12). This supersedes the /tmp F1 driver above for any
#     NEW run: it is in the repo, it keeps the program out of the room, and it phases its evidence.
#     Same launch/mint/pair prelude as F1. ~3 min, no operator input. -------------------------
scp scripts/ralph-afk/live-canary.sh ga0@m4mbp:/tmp/ && ssh ga0@m4mbp \
  "MARKER_SYSTEM=umbrella MARKER_ROOM=elephant OUTPUT_MODE=muted ROOM_WINDOW_SECONDS=28 \
   bash /tmp/live-canary.sh ralph-c51-$(date -u +%Y%m%dT%H%M%SZ)"
# Run it from MacStudio with stdout redirected to a local log and WATCH THAT LOG: the driver
# announces `ROOM_WINDOW_OPEN` and then stays silent for ROOM_WINDOW_SECONDS, which is when an
# external sound source must supply the microphone lane. Nothing on the capture Mac can do this -
# by construction, since the whole point is that the room and the program are different sources.
# `OUTPUT_MODE=muted` is the mechanism: the process tap is UPSTREAM of the output mute (measured),
# so the program reaches the system lane and never the room. `OUTPUT_MODE=audible` reproduces the
# old confound on purpose. The driver mutes, and its EXIT/INT/TERM trap unmutes - it restores
# whatever it found, so never leave the mute to a follow-up command.
# Pull the whole directory (scp of a brace list does NOT expand remotely - use `scp -r`):
#   scp -r ga0@m4mbp:/tmp/ralph-canary/ /tmp/ralph-c51-evidence/
#   python3 scripts/ralph-afk/live-canary-analyze.py /tmp/ralph-c51-evidence/ralph-canary --voices 2
# RUN THE DRIVER nohup'd ON m4mbp AND POLL ITS LOG - never as a foreground ssh. The link dropped
# three times during iteration 21's setup alone, and a drop mid-meeting kills the driver, leaving
# the output muted and the session open:
#   ssh ga0@m4mbp "rm -rf /tmp/ralph-canary; nohup env MARKER_SYSTEM=cardamom MARKER_ROOM=obsidian \
#     OUTPUT_MODE=muted bash /tmp/live-canary.sh <label> > /tmp/ralph-canary-run.log 2>&1 &"
#   then poll: ssh ga0@m4mbp 'tail -5 /tmp/ralph-canary-run.log'
# live-canary-analyze.py READS PRUNED DIRECTORIES since iteration 12: a cert/soak snapshot.tsv keeps
# only span_id, so the span bodies come from the newest readable snap-full-*.json and cover a PREFIX
# - the header names the source and the coverage instant. rc: 0 both markers, 3/4/5 one/other/neither
# missing, 7 UNDECIDED (no delivery phase of that marker is covered - a run that died early reads
# this way too), 6 a named refusal (no readable spans anywhere), 2 nothing to read.
# AND IT MATCHES THE MARKER PHONETICALLY since iteration 13 (candidate 59) - VERBATIM, then
# REWRITTEN (a fragment inside a phase that DECLARES the marker, whose whole text is one n-gram
# repeated - the driver's isolated-and-repeated delivery - within 0.60 skeleton similarity), then
# printed-only CORROBORATING near-matches at >= 0.80. Every marker line names which tier answered,
# so "present" never hides "as a different word". Do NOT read a bare rc: the tier is the evidence.
# The CERTIFICATION-CLAUSE reduction is a SECOND reducer - live-canary-analyze.py answers lane
# separation, this one answers the PRD clauses (poll health + first non-200, growth, per-lane v2
# health, the accounting equality, decoder RTF + D-c's token cap and capped count, per-span commit
# lag from the event stream, the latency report's two components against the run's gate, and the
# lane-health timeline printed only where it CHANGES). rc=0 all green, 3 a clause red, 2 unreadable:
#   python3 scripts/ralph-afk/live-canary-clauses.py /tmp/ralph-c51-evidence/ralph-canary
#   python3 scripts/ralph-afk/live-canary-clauses.py <dir> --user-visible-gate-ms 6000   # F2/F3
# Q2's RTF DEFINITION and its two-sided fence (iteration 22, candidate 70). The floor lives once,
# as RTF_FLOOR_SEC in live-canary-clauses.py, and the probe IMPORTS it - so an edit to the constant
# fails here rather than drifting. Offline, ~3 s, reads five evidence directories on this host:
#   python3 scripts/ralph-afk/rtf-floor-probe.py                      # 9/9, rc=0
#   python3 scripts/ralph-afk/rtf-floor-probe.py --floor-sec 0        # 7/9, rc=1  (too small)
#   python3 scripts/ralph-afk/rtf-floor-probe.py --floor-sec 0.93     # 6/9, rc=1  (too large)
# The red-before for the reducer is a SEMANTIC REVERT with no edit, because the floor is a flag:
#   python3 scripts/ralph-afk/live-canary-clauses.py /tmp/i30-f1-evidence/ralph-canary \
#       --rtf-floor-sec 0    # reproduces the pre-Q2 verdict exactly: RED, p95 2.365 over 52 spans
# Both UNDECIDED paths, the second needing a fixture because both F1 runs hold exactly 26 spans at
# the 2.5 s hard cap and no floor can leave 1-19:
#   ... --rtf-floor-sec 3.0                      # every span below the floor (cap is 2.5 s)
#   a 25-span events.tsv with 20 at 0.05 s and 5 at 1.0 s   # gated 5 < RTF_MIN_GATED_SPANS
# The probe REFUSES below 3 directories / 300 spans: a floor derived from one run is a floor fitted
# to that run's noise - per-run Theil-Sen puts C/m between 0.590 s and 2.007 s.
# Q3's CADENCE TIE (iteration 23, candidate 71). Two nodes, one per language, each reading the
# other's source; the probe's section 3 asserts the tie and that BOTH halves read 0.5 s:
#   python3 -m pytest tests/test_live_portal.py -q -k poll_cadence      # 1 passed
#   swift test --package-path macos/MOSSCapture \
#     --filter testPortalCycleContractMatchesTheServedPortalCadence     # 1 test, 0 failures
#   python3 scripts/ralph-afk/latency-remedy-probe.py                   # rc=0, needs it.12's F3 dir
# Red-before is a TEMPORARY SEMANTIC REVERT of tracked source, so back both files up first and
# restore under a shell trap; four directions, each of which must go red:
#   portalCycleSeconds 0.5 -> 1.0 | pollDelayMs 500 -> 1000
#   schedulePoll(pollDelayMs) -> schedulePoll(500)          # declared but not scheduled
#   renderBoundMS = CaptureLatencyContract.portalCycleSeconds * 1_000 -> a literal
# The probe's section 1 reads F3's PRE-remedy report and must keep saying portalCycleMS == 1000.
# Q4's CLEAN STOP (iteration 24, candidate 72). Five Swift nodes, no Python:
#   swift test --package-path macos/MOSSCapture --scratch-path /tmp/i24-swift-scratch --filter \
#     'testCleanStopTellsTheServerTheMeetingIsOverAfterTheFinalDrain|testAStopTheServerCannotBeToldAboutStillStopsLocallyAndNamesTheRefusal|testStopContractMatchesTheServedPortalControlTimings|testProductionPumpTicksOncePerCanonicalWireFrameOnOneSharedPinnedProvider|testHTTPSessionStopPostsTheDrainDeadlineOnItsOwnBoundedRequest'
# Red-before is a TEMPORARY SEMANTIC REVERT of CaptureController.swift and MOSSCaptureApp/main.swift
# under a shell trap; six directions, each naming a DIFFERENT node:
#   A stopServerSession call deleted        B call moved BEFORE the final drain
#   C catch -> try? (refusal not recorded)  D main.swift not handed sessionStop:
#   E drainDeadlineSeconds 5.0 -> 3.0       F requestTimeoutSeconds 10.0 -> 60.0
# The server half needs NO new node: tests/test_live_api.py:503
# test_clean_stop_immediately_revokes_view_authority already drives capture-bearer -> /stop ->
# view 401. The seam nothing covers is "the BUILT app's stop reaches the DEPLOYED server", which is
# F3's post-stop view check -- i.e. Phase Q's own gate, after the m4mbp rebuild.
# Validated in iteration 21 against iteration 12's canary (reproduces committed p95 8342.697 ms and
# user-visible 9702.2 ms), against /tmp/ralph-f1-evidence (reproduces decoder p95 RTF 0.706 and
# prints the t+86.0 s system-lane failure), and it REFUSES the F3 soak layout by name.
# rc 0 both codewords reached the transcript / 3 not the system one / 4 not the room one / 5 neither.
# rc is NOT the whole answer: read section 1's prose, which separates "the mute killed the tap" from
# "the decoder rewrote the marker word" - those look identical in a marker-only check and mean
# opposite things. Since iteration 13 the rewrite is matched rather than left to the reader, and
# 3/4/5 deliberately carry no cause in the docstring any more.
# ALWAYS afterwards, exactly as F1: `pkill -x MOSSCaptureApp`, `rm -rf /tmp/ralph-canary
# /tmp/live-canary.sh`, both TCC grants re-checked (auth_value=2), mute and volume back.
# The operator uses m4mbp while the loop runs: volume moved 50 -> 64 -> 50 during iteration 12 and
# the pasteboard refilled after the driver cleared it. Read topology-before/after.txt, and do not
# read a post-run pasteboard as this run's leak.

# --- F3 soak on the real hosts (RUN in iteration 9 of run 20260728-181020; re-runnable, ~19 min,
#     costs no operator input). Same launch/mint/pair prelude as F1 above, then: -----------------
#   scp /tmp/ralph-f3-soak.sh ga0@m4mbp:/tmp/ && ssh ga0@m4mbp "bash /tmp/ralph-f3-soak.sh ralph-f3-$(date -u +%Y%m%dT%H%M%SZ)"
# SOAK_SECONDS (1020), UTTERANCE_INTERVAL (60), POLL_INTERVAL (2), STATUS_INTERVAL (10) are env
# knobs. It logs a compact jq projection per snapshot poll instead of the whole body (a 17-minute
# run at full bodies is ~40 MB), keeps one full snapshot per minute, and writes view-checks.tsv with
# an explicit t0 / post15 / post-stop exercise of the SAME token. Reduce with
# /tmp/ralph-f3-analyze.py <dir>, which prints the clause in its own terms.
# Run it in the BACKGROUND from MacStudio (Bash caps a foreground call at 10 min) and watch the log.
# ALWAYS afterwards, exactly as F1: volume back to 31, `pkill -x MOSSCaptureApp`, both TCC grants
# re-checked (auth_value=2), `pbpaste | wc -c` == 0.
# The three surfaces that must be read TOGETHER to diagnose a soak death, and their clock offsets:
#   m4mbp:  bash /tmp/f3-log.sh   # log show in a SCRIPT FILE - inline over ssh hits zsh's `log`
#                                 # builtin and prints nothing at all
#   server: journalctl --user -u moss-live-web.service --since "-40 min"   # ~40 min retention only
#   client: status.tsv transitions (10 s) + snapshot.tsv 200->401 (2 s)
```

## Candidates

Strictly ordered by phase. Mark outcomes inline (`[done <commit>]`, `[dead: <why>]`) and prune
only after the durable result is in progress.txt.

### Closed phases — index (full candidate lists in the progress.txt archive)

| phase | what it delivered | state |
| --- | --- | --- |
| **A** — preserve and close IDEA-044 | the A-034 graft, per-lane permission coordinator, app-owned handoff, the tracer rebuilt on the immutable lab bundle | closed, checkpoint frozen at `1ede498` |
| **B** — production Mac reliability | file secret store, retained-until-ACK outbox, 16 kHz/8000-sample wire format + converted timestamps, bounded concurrent transport, packaging/install tools, the B6 gate | closed at `3fb5567` |
| **C** — server meeting reliability, then one merge | session-bound view authority, retuned manifest bounds, TLS/pairing tools, the two-service deployment bundle, the app-owned latency probe, the C4 merge | closed at `f9285d6` |
| **D** — publish and enable the 4070Ti | published the merge, finalized the host manifest and rotated the TLS pair, installed and started the live service plus its Windows forward | closed |
| **E** — Mac install and human permission boundary | aligned the m4mbp checkout, created the signing identity, built/signed/installed the app; **E3 (the TCC grants) is CLOSED** | closed |
| **G** — first authorized fix cycle | ATS declaration, pairing-payload trim, control-channel classification + logging, gate, merge `317df4d`, redeploy, Mac rebuild | closed |
| **H** — server decode-seam cycle | H3 VAD framing, H1 empty-span decode, H2 span-cap authority, gate, merge `b817871`, redeploy; H4d then found blocker 4 | closed |
| **J** — the live path's terminal-failure policy | J1 span clamp, J2 unattributed publish, J3 transient decode, J4 named refusal, gate, merge `6a540fe`, redeploy, **and a green probe** | closed |
| **K** — lane observability | K1 lane state on the control channel, K2 typed lane-failure log, K3 server terminal record, K4 session refusal, gate, merge `fc7097d`, redeploy + Mac rebuild, K5d re-read | closed; fourth amendment spent |

Ruled out by measurement over Phases K/L/M: TCC (both granted), pinning and network (probes 200),
schema (five faithful heartbeat shapes 200), duplicate helper instances (exactly one app process),
and the **server**, which behaves correctly at every step of the client-side failure.

### Phase F — certification and rollback

23a. **F0 — server-side live pipeline probe (no Mac, no TCC)** `[done — iteration 9 of run
    20260728-072601]`: `scripts/ralph-afk/live-pipeline-probe.py` drove the deployed service through
    pairing → session → two-lane v2 ingress → endpointer → decode → snapshot from a real remote
    pinned-TLS peer. It retired a large block of server risk (see the F0 block in the iteration-10 archive for
    everything now proven, including "no raw audio is persisted" and the ~1280 ms render bound) and **found two
    blockers that would have destroyed F1 seconds after the operator's TCC clicks**. Off-list and
    justified in progress.txt: it is the only remaining work that could fail *downstream* of the one
    human step, and it needed no human. Re-runnable; the device revoke is mandatory after each run.
23b. **F0b — the offset probe run** `[done — iteration 10]`: one run with
    `--lane-offset-ms system=137 --lead-seconds 0` spent F0's open caveat and found blocker 3. The
    device was revoked, both batch units and the live unit kept their MainPIDs/NRestarts/timestamps,
    `live-runs/` is still 0 entries and no `/tmp/mtd-live-*` survives. See the H-diagnosis block.
24. **F1 — 60 s canary** per prd.md. `[CURRENT EVIDENCE IS RED — the re-run on the deployed
    `7a4f59c`, run 20260729-025318 iteration 30, rc=3, 5 GREEN / 2 RED (user-visible p95 4150.8 ms
    vs the 4000 ms gate; decoder p95 RTF 2.365, carried by 3 sub-0.1 s spans). Causes are candidates
    64 and the plan's ordered latency remedies, neither a Phase N regression; **both need the
    operator**. Tag corrected in iteration 14 — it had read `[GREEN]` off the superseded `42abc5a`
    run for eleven iterations while the scoreboard row above carried the RED.]`
    *Superseded, kept because it is the only run in this loop's history where the user-visible clause
    passed at the 4000 ms gate:* `[GREEN — run 20260729-025318 iteration 6, rc=0; see the
    F1-green block, retired to progress.txt with the fourth compaction. The RED history below is iteration 8's run and is kept only for what it
    diagnosed.]` See the F1
    block above. Green: continuously updating labelled transcript (42 spans, version 0 → 283),
    decoder p95 RTF **0.706**, zero double count (340 published == 340 accepted), run-time secret
    hygiene, no raw audio persisted. Red: **user-visible p95 10426 ms vs ≤ 4000 ms**, and **0.5 s of
    system-lane loss** to a mid-meeting `macos_buffer_overrun`. The diagnosis (candidate 50) is the
    part that matters; the label/marker clauses are confounded by the harness (candidate 51) and
    must be re-run, not re-argued. F1 is re-runnable end to end from
    `/tmp/ralph-f1-canary.sh` and costs no operator input.
25. **F2 — 300 s locked run** with 5 s interruption and the system-audio-denied variant.
    `[GREEN ON THE DEPLOYED 7a4f59c — run 20260729-094359 iteration 1, rc=0, six GREEN / no RED /
    no UNDECIDED; see the **F2 on Phase N** row in the gates index. This is Phase N gate step (d)'s second half and it
    COMPLETES that gate.]` user-visible p95 **4078.6 ms** ≤ 6000 qualified, decoder p95 RTF
    **0.577**, a **5.090 s** interruption seen and survived, **1261 published == 1261 accepted,
    every one of the session's 4766 logged requests 200**, outbox 0 → 5 → 0, clean drain.
    *Previously GREEN on `42abc5a` (iteration 11 of run `20260729-025318`): 3859.6 ms, RTF 0.670,
    1257 == 1257 — archived in progress.txt.* **The denied-lane half is still open
    and is NOT a scripting problem** — it is a separate
    run by the PRD's own wording and producing it means taking a TCC grant away from
    `com.alphasight.moss.capture`, i.e. spending the one input this loop is forbidden to ask for
    again. It needs its own recorded plan before anyone writes code for it.
26. **F3 — 16-minute active-view soak**: capture and `/live` polling stay active with periodic
    two-lane audio; same authority works after minute 15; clean stop immediately revokes it.
    `[CURRENT EVIDENCE IS THE RE-RUN ON THE DEPLOYED `7a4f59c` — 5 GREEN, 1 RED, rc=3, run
    20260729-094359 iteration 12; tag corrected in iteration 14, it still pointed at the superseded
    `42abc5a` run of 20260729-025318 iteration 9. See the **F3 on Phase N** row in the gates index
    and the scoreboard row above. The RED is candidate 60; the two soak halves this entry once called
    "unproven" are PROVEN — the same authority answered 200 at age 903.6 s and 1023.0 s. Only "clean
    stop immediately revokes it" fails, and it fails for a reason nothing to do with the soak.]*
    *The RED history below is the run 20260728-181020 iteration-9 attempt, kept only for what it
    diagnosed.* See "F3 — the 16-minute soak" (RETIRED, grep progress.txt). Green for 14 minutes:
    56–62 s of accepted audio every wall-clock minute, 412 committed spans, version 0 → 2647
    monotone, retained ≤ 25.8 % of its bound, 3430 published == 3430 accepted. Then at minute 14.1
    one `macos_buffer_overrun` wedged the publish path, the heartbeat stopped **because a throwing
    publish skips it** (`CaptureController.swift:413-417`), and the 30 s helper lease ended the
    meeting 29 s later. All three clause halves are therefore unproven, not merely failed: the
    token was accepted to 871.9 s, 25 s short of the 900 s the clause is aimed at. Re-runnable end
    to end from `/tmp/ralph-f3-soak.sh`, costs no operator input, and **will fail the same way until
    candidate 53 lands**.
**F4 was split by evidence in iteration 8**, the way iteration 20 split E2: its rollback rehearsal
needs no operator, closes a PRD acceptance clause on its own, and is *cheaper before* certification
than after (nothing in flight to disturb). Its close half still waits on everything else.
32a. **F4a — rehearse and record the rollback** `[done — iteration 8 of run 20260728-072601]`:
    live service disabled (clean `Result=success`, 7861 dead from the client on both addresses),
    checkout reverted to `163e969`, `http://192.168.68.38:7860/` + `/api/jobs` (141 jobs) +
    `/api/runtime` all 200 while rolled back and the pre-live `start-web.sh` still derives the exact
    contract `BATCH_ARGV`, then both mutations undone and the pinned live surface re-verified
    byte-identical. See the rollback-rehearsal block above. **The PRD's "Rollback rehearsed and
    recorded" clause is GREEN.**
32b. **F4b — close the loop** only when every other PRD acceptance item has evidence.
    `[blocked on E3 → F1–F3]`

### Phases L and M — CLOSED; the candidate lists are retired to progress.txt

The fifth amendment's cycle (48, 49, 50, 53, plus decisions D-a/D-b/D-c and the coverage-gap fix)
landed at `21a73ea`, merged as `77e0014`, deployed, and is **proven on the real hosts**: F2's green
run shows 53 keeping 622 heartbeats alive through the outage, D-a turning a `macos_buffer_overrun`
into a degradation that kept capturing, and D-c capping 4 of 161 spans with RTF p95 0.670. The two
lists — Phase L's diagnosis of 48/49 and Phase M's entries 50-55 — are in progress.txt under
**"Phase L and Phase M candidate lists (48-55, D-a/D-b/D-c)"**. Every cross-reference of the form
"see the Phase M list" resolves there.
**Only candidate 55 is still open**, and it has its own entry in the numbered list below.

### Open diagnostic candidates — the numbered ones, in one place

55. **AUTHORIZED 2026-07-29 AS PHASE Q ITEM (a) — see candidate 69.** The operator took **option 1**,
    the birth floor at the album's admission (**1.0 s of embedded speech**). Every *"needs its own
    authorization"* below is superseded; the diagnosis is not. **Identity capacity saturates in the
    first minute** (iteration 12). The 16-speaker bound is
    reached at t+45.5 s (t+51.8 s in F1), so a voice arriving later can never be labelled. Degrades
    quality without ending a session, so no gate sees it. Tracked product source; **needs its own
    authorization**. **PRICED IN ITERATION 16 and NOT subsumed by the album**: the accuracy harness
    reproduces it offline and deterministically — all eight fixture meetings exhaust 16 canonicals
    for 2–6 real voices *with the album on*, and lifting the bound to 32/64 moves the album from
    **93.4 % → 97.9 % / 98.7 %**. So it costs **4.5 pp of live speaker accuracy** and is the whole
    of the gap between production and ADR-0002's 98.5 %. The album was the hypothesis for its cause
    and the hypothesis is now measured wrong: births are unchanged by design, so the fragmentation
    survives the fix. It needs its own authorization and its own mechanism.
    **THE DIAGNOSIS IS CLOSED, and the six re-pricings between iteration 22 and iteration 9 are
    retired to progress.txt** with the seventh compaction. What they settled, and it is all a future
    iteration needs: **the site is `live_identity.py:129`**, which births a canonical speaker for
    every unmatched local speaker with **no duration condition of any kind**, while the evidence
    floor (`min_segment_samples`, applied per *segment*) and the album's 1.0 s admission both sit
    below it - so **14 of F2's 16 and 13 of F3's 16 canonical speakers hold no reference whatever**
    (born from `'...'`, `Hi.`, `Mm-hmm.`), and a birth floor on embedded seconds would leave **2 / 3**
    speakers, the fixture's own healthy 1.0-1.5 refs/voice regime. Phase N decision 20 carries the
    table and the counterfactual's honest bound.
    Three consequences, each a measurement rather than an argument: the sweep's **merge** repairs
    none of it (decision 7 needs an admitted bank on *both* sides and these speakers have none); the
    sweep does not *refuse* those units, it **never receives** them (no embedded unit => no ledger
    entry); and across **four** deployed swept meetings **all 49 published corrections are
    `S00 -> Sxx` and not one is a reassignment** - so no cadence, no `stop` wiring and no amount of
    sweeping moves a minted junk label. Offline the fixture prices 55 at **5.30 pp of live speaker
    accuracy** (93.44 vs 98.74) with the *final* transcript unharmed; on a real meeting nothing
    repairs it, so the loss is permanent rather than a latency of labelling.
    **Reproducible on demand in 150 s with no Mac and no TCC:** `live-pipeline-probe.py --lane-audio
    fragmented` mints 16 canonicals for one embeddable voice, 14 of them on exactly one span each -
    F2's shape hit exactly. **The request is written and on the table:**
    `scripts/ralph-afk/authorization-request-55-60-65.md`, whose item (a) - the birth floor - is the
    only one of its three that touches this. Raising `max_speakers` and lowering
    `min_segment_samples` are both measured wrong; decision 20 records why, so they are not
    re-proposed.
    **ITERATION 12 MEASURED 55 AT SOAK SCALE ON THE DEPLOYED CODE, AND THE 46 BECAME 49.** The F3
    re-run minted **16 canonicals for 2 real voices (inflation ×8.0), saturated at t+138.1 s of a
    1029 s meeting** — 11 s later than F2's t+127.1 s and still inside the first 14 %, so **~87 % of
    the meeting ran with no slot left for an arriving voice**. The fragmentation shape is F2's again:
    of 17 labels seen, `S00` 138 spans, `S05` 83, `S01` 35, and **twelve labels on exactly one span
    each**. 122 of 648 spans abstained. The cadence sweep repaired **3** of them, and all three are
    `S00 → Sxx` — so the confound-free fact now reads **49 corrections across four deployed swept
    meetings, zero reassignments**, and 55's cost survives the first cadence sweep ever observed to
    publish.
56. **A live session stops being viewable mid-meeting.** `[CLOSED — fixed run 20260729 it. 1,
    merged as 42abc5a it. 4, deployed and PROVEN ON THE SERVER it. 5]`. Cause: the server host's wall clock steps ~1.5 s
    backwards every ~32.3 s, `vllm_runner.py:111` measured `elapsed_sec` on it, and
    `live_adapters.py:344` turned a negative one into a non-retryable `LiveProviderError` that ended
    the meeting. Authorized as **Phase P** by the seventh amendment and implemented as P1-P4; the
    failure record, the clock measurement and what landed are in progress.txt under
    `CANDIDATE 56 IS ANSWERED…` and `Phase P candidate list…`.
    **It blocks nothing now:** the same probe invocation that reproduced it at
    t+31.5 s ran its full 150 s plan on the deployed `42abc5a` with zero non-200s, while the host
    clock was measured still stepping every 32.29 s. The hazard is permanent; the defect is gone.
57. **The reducer called a passing latency number RED.** `[done — iteration 29]`. See "The reducer
    stopped calling a passing number RED" in progress.txt, and the reducer-verdict rules in the
    third-compaction index. Loop tooling; no authorization was needed.
59. **The marker check calls a landed marker absent, because it matches the word exactly.**
    `[done — iteration 13; see "THE MARKER IS MATCHED PHONETICALLY" above. Three tiers,
    the middle one corroborated by the driver's own delivery shape; F1 and F2 both move rc 5 → 4
    with the system marker named, F3 stays rc=4 on its verbatim hit.]`
    *Originally:* `[open, new — run `20260729-025318` iteration 6; loop tooling, no authorization needed]`.
    `live-canary-analyze.py` scored `cardamom` **NOT FOUND** in a run whose transcript contains
    `Cockamom, cockamom, cockamom.` — isolated, repeated, three times, in the correct phase, on the
    correct lane. The decoder rewrites a rare noun **phonetically**, which is precisely why the
    driver was changed in iteration 12 to say the marker alone and slowly; the reducer never learned
    the same lesson, so `rc=5` was printed over a marker clause that holds. **Iteration 12 made this
    the cheapest remaining item and gave it a fifth measurement:** with candidate 61 fixed, F2's
    directory reduces to `rc=5` while carrying 121 labelled system-phase fragments and a marker that
    landed as *"Pardon me, pardon me, pardon me"* — i.e. the only thing between F2's evidence and a
    system-marker verdict is this exact-match comparison. *Shape of the fix, not a
    decision:* compare on a phonetic/edit-distance key rather than equality, and — the part that
    matters more — make the **verdict word name what it decides**, as candidate 57 had to: "the
    marker word was not transcribed verbatim" is not "nothing from this lane reached the transcript".
    Third instance of that class in this loop. Note the cheap negative control that already exists:
    the room marker was absent **and** its phase produced only one-word fragments, so absence of
    content and rewriting of a word look nothing alike in the evidence — only in the verdict.
60. **AUTHORIZED 2026-07-29 AS PHASE Q ITEM (d) — see candidate 72.** A transport call after the
    final drain, with the fifth amendment's rule that a stop which cannot reach the server must
    still stop locally. Every *"needs its own authorization"* below is superseded.
    **A clean stop never reaches the server, so it does not revoke view authority.** `[open, new —
    run `20260729-025318` iteration 9; **F3's one RED**]`. `CaptureController.stop` drains and
    returns; **no MAC-CLIENT code path** calls `POST /api/live/sessions/{id}/stop` (as filed this read
    "no client code path", which iteration 7 falsified - the portal and the F0 probe both call it),
    a route that exists at
    `live_transport.py:325` and is covered by `tests/test_live_api.py:502`. Measured: view authority
    answered 200 for **29.4 s** after a clean stop, until the 30 s helper lease expired. Bounded and
    self-healing, but it is the PRD clause's word *immediately*, and it was already visible in F1's
    "29 s after the run's own stop" line without being named. Tracked product source under `macos/`;
    **needs its own authorization**. The full block is retired to progress.txt with the fourth compaction; the one-line form is in the certification section.
    **THE FOUR RE-PRICINGS BETWEEN ITERATION 30 AND ITERATION 5 OF THIS RUN ARE RETIRED to
    progress.txt** - upwards twice, downwards twice, all four superseded by iteration 7's direct
    measurement below. The three facts from those runs that survive unaltered: F1, F2 and F3's server
    journals each hold **0** hits on `.../{sid}/stop` (because *their drivers* never called it), the
    terminal line is `helper_lease_expired` about **29 s** after a clean stop in both F2 and F3, and
    the deployed sweep has never published a reassignment - so wiring `stop` while 55 is open buys
    the `identity_finalized` event and few corrections. **Sequence 60 with or behind candidate 55.**
    **ITERATION 7 RE-SCOPED 60 BACK TO WHAT IT IS, AND DELETED ITS SECOND CLAUSE.** Measured on the
    deployed service: the route is reachable by **both** authorities, the `/live` portal's Stop
    button calls it, this loop's own F0 probe has called it since Phase F, and a stop through it
    **revokes view authority immediately (401)** *and* **ran the session-end sweep, which published
    19 corrections on 31 spans**. Candidate 60 is therefore a **client** defect and nothing more:
    `CaptureController.stop` does not call a route that works. Every sentence in this file of the
    form *"the session-end sweep never runs in a real meeting"* or *"ADR-0002's second acceptance
    half is unreachable in production"* is **withdrawn** — each was inferred from `identity_finalized`
    sightings, and that event is unreadable by every client (see the deployed-sweep block, §4). Two
    consequences: 60 buys neither convergence nor the `identity_finalized` event (it is worth having
    on its own merits — a Mac stop should behave like the portal's), and **the loop needs no
    authorization to measure the session-end sweep**, because the probe already can.
65. **WITHDRAWN BY THE OPERATOR 2026-07-29 IN THE NINTH AMENDMENT — not deferred, withdrawn.**
    *"Both the session-end sweep (19 corrections on 31 spans) and the cadence sweep publish on the
    deployed service, and the two 'it never runs' readings were the loop's own blind instruments."*
    Do not re-file it and do not carry the diagnosability half into another ask. The body below is
    kept because its measurements are cited elsewhere; its **ask** is closed.
    **An empty cadence sweep leaves no record to tell "found nothing" from "never ran".**
    `[open, new — run `20260729-094359` iteration 1; **RE-FILED under this title in iteration 14**,
    which is what iteration 12 instructed and no iteration had applied — the original title said
    *"Neither half of Phase N step 3 produces a correction on a real meeting"* and both halves have
    since been measured publishing on the deployed service]`. Filed from F2 on the deployed
    `7a4f59c`, a **319 s** meeting that minted **16 canonical speakers for 2 real voices**:
    `identity_revision_version` **0 on all 171 spans** (re-verified on the authoritative
    `canonical_processed` surface in iteration 12, so that zero is real), **0** `live identity sweep`
    lines in the server journal, `identity_finalized` **0**.
    `LiveIdentitySweeper.maybe_sweep` is called per scored span (`live_provider_bundle.py:570`) with
    `meeting_seconds = span.start_sample / 16000` at `SWEEP_INTERVAL_SECONDS` **60**, so **five**
    deadlines were crossed and produced nothing. *What separates F2's zero from F3's three is meeting
    **length**, not a broken sweep* — and neither run's ~14 silent deadlines said so anywhere.
    ***The diagnosability half is the part this loop can name today.*** `sweep_now` sets
    `_unconsumed` and logs **only when the revision is non-empty**, so an empty cadence sweep is
    indistinguishable on every surface from a sweep that never happened — the precise distinction
    Phase N decision 11 records `identity_finalized` **unconditionally** to preserve, granted to
    the session-end half and withheld from the cadence half. Sixth instance of "a verdict word must
    name the thing it decides" (57, 59, 61, 62, 64, now 65). *Shape of the fix, not a decision:* a
    counter or an event that says a sweep ran and proposed nothing, so the next run measures a cause
    instead of an absence. Tracked product source; **needs its own authorization** — and it should be
    weighed together with candidate 60, because a fix to 60 alone would light up the session-end half
    while leaving the cadence half exactly as unreadable as it is now.
    ***THE CAUSE HALF IS CLOSED AND ITS FOUR-ITERATION CHAIN IS RETIRED to progress.txt*** with the
    seventh compaction: iterations 3 and 4's two superseded explanations, iteration 5's decisive
    `sweep-multiplicity-probe.py` mechanism, iteration 6's birth site, and iteration 7's split. The
    conclusion, stated once: **an empty sweep is candidate 55's fragmentation, not a broken sweep** -
    at F2's shape the minted labels have no embedded unit, so the sweep never receives them. That is
    iteration 9's correction to iteration 5's model, which had *given* the sweep stand-in references
    and measured **84.1 % `kept_ambiguous`**; read that number as an upper bound on what a
    *repairable* fragmentation would cost, never as production's. Phase N decisions 19 and 20 carry
    both tables.
    ***The SESSION-END half is withdrawn outright.*** Iteration 7 measured it running and publishing
    **19 of 31 spans** on the deployed service, and every "0 sightings of `identity_finalized`"
    reading in this loop's history was uninformative rather than negative, because that event is
    written to an in-memory list no client can read. *What iteration 7 adds and nothing else says:*
    even the session-end sweep's **payload** - the counts `identity_finalized` carries - is
    unreachable by any client, so a reader can see *that* labels moved and never *what the sweep
    decided*. That is the same diagnosability defect and belongs in the same authorization.
    ***ITERATION 12 FALSIFIES THE HEADLINE AND LEAVES THE DIAGNOSABILITY HALF STANDING.*** The F3
    soak on the deployed `7a4f59c` crossed ~17 cadence deadlines and the cadence sweep **published
    three revisions**, mid-meeting and visible to a polling reader (spans 48/208/382, all
    `S00 → S01`, words byte-identical). F2's zero was **real** — re-read on the same surface it is
    still `{0: 171}` — so what separates the two runs is meeting **length**, not a broken sweep.
    **65's title is now wrong and its body is right:** the rate is 3 repairs of 122 abstained spans
    (2.5 %), ~14 deadlines produced nothing, and nothing anywhere says so. Re-file 65 as *the empty
    cadence sweep leaves no record*, which is item (b) of the authorization request and unchanged.
    See the deployed-sweep block above (§1).
67. **The probe reads the revision version off a surface that does not carry it.** `[DONE —
    iteration 13; loop tooling, no authorization spent. See the deployed-sweep block above, §5.]`
    The pre-fix description - `live-pipeline-probe.py` projecting `identity_revision_version` off a
    snapshot committed item that carries `identity_snapshot_version` instead, and the
    `isinstance(..., int)` filter turning the resulting `None` into a silent 0 - is retired to
    progress.txt with the seventh compaction. The deployed-sweep block above (§5) carries what landed.
    **Fixed in iteration 13, and it carried a second defect out with it** — the probe counted a
    re-delivered event as a second measurement. See the deployed-sweep block above (§5) for both, the red-before proof
    and the numbers the second one moves.
58. **The replay evaluator calls a declared absence an invalid measurement.** `[done — operator-
    directed P1 cycle, 2026-07-30]`. This was the same evaluator seam as the declared-null F4b
    blocker: a coherent pair with both timing keys present and null is now a visible
    `declared_unknown` measurement, excluded from p95 without being silently omitted. Half-null,
    missing, negative, and non-finite payloads remain corrupt and fail closed. The count and records
    travel through the summary, trace, and evaluator artifacts; adversarial coverage lives in
    `tests/test_live_service_replay.py`.
61. **`live-canary-analyze.py` crashes on any pruned evidence directory.** `[done — iteration 12;
    see "WHERE `live-canary-analyze.py` READS SPANS" above. Spans now come from the
    newest readable `snap-full-*.json`, an absence is judged against coverage, and an unreadable
    layout is a named `rc=6` refusal. F3 rc=4 with the system marker at span 5; F2 rc=5 on
    candidate 59.]` It raised
    `KeyError: 'transcript'` at `live-canary-analyze.py:142` on an F2 directory, because it reads
    spans out of `snapshot.tsv`, whose rows every current driver **prunes to `span_id` only**
    (`SNAP_PRUNE` in `live-cert.sh`/`live-soak.sh`). The transcript survives in the periodic
    `snap-full-*.json` files, which the analyzer never opens. *Shape of the fix, not a decision:*
    read spans from `snap-full-*.json` when the TSV projection has no `transcript`, and — the part
    that matters — **fail with a named refusal instead of a traceback**, the same rule
    `live-canary-clauses.py` already applies to a layout it cannot read. It cost this iteration
    nothing (the markers were extracted by hand in five lines) but it means the lane-separation
    verdict is unavailable for F2 and F3 as shipped.
63. **The album would deploy at matcher thresholds tuned for the policy it replaced.**
    `[the tracked path is DONE — iteration 17; the host manifest is NOT yet regenerated, which
    happens at Phase N's redeploy]`. **It needed no ninth authorization:** prd.md's ADR-0002
    supersession names the values itself (*"Use ADR-0002's measured starting values - `min_score`
    0.35, margin 0.1-0.2…"*) and the sixth amendment already ruled `min_match_score` /
    `min_match_margin` **free** parameters whose change is *"a decision to record"*. Iteration 16's
    "needs its own authorization" was over-cautious and is corrected here. What landed:
    `ALBUM_MIN_MATCH_SCORE` / `ALBUM_MIN_MATCH_MARGIN` beside the policy they calibrate, the
    accuracy harness pointed at them instead of a copy, and the finalizer given required
    `--min-match-score` / `--min-match-margin` flags that write `identity_config`, hash-cover it,
    print it in the plan and the evidence, and refuse a pair the runtime's own reader rejects.
    Its surviving homes are the **Phase N step index row `1b - recalibration`** and **decision 16**;
    the "candidate-63 block" this line used to point at went to progress.txt with the **fourth**
    compaction and the pointer was left dangling until iteration 14 found it. *The `[open]` history - the deployed thresholds against
    ADR-0002's 0.35/0.1, the 93.4 / 91.0 / 75.0 % fixture scores that made this a shipping
    requirement rather than a refinement, and iteration 16's over-cautious "needs its own
    authorization" - is retired to progress.txt with the seventh compaction.* **Decision 16 carries
    the number that matters and corrects all of it:** what was actually deployed was `0.5 / 0.05`
    (83.72 % mean / 69.20 % min), below ADR-0002's >= 90 % bar, not the `0.5 / 0.2` those blocks
    recorded.
64. **RULED 2026-07-29 AS PHASE Q ITEM (b) — see candidate 70.** The operator did **not** pick (a),
    (b) or (c) as written: the ruling is *"a gate definition, not a filter"* — **state a minimum span
    duration below which RTF is not a meaningful ratio, derive it from measurement rather than
    choosing it to pass, and always report the excluded count**. A silent exclusion does not answer
    the clause. Every *"needs its own authorization"* below is superseded.
    **The decoder RTF clause measures per-call overhead on a sub-100-ms span, not throughput.**
    `[open, new — iteration 30; **F1's second RED**]`. Measured on `7a4f59c`: p95 RTF **2.365** over
    52 spans, and **only 3 spans exceed 1.0** — durations **0.03 s / 0.06 s / 0.07 s**, elapsed
    0.108 / 0.194 / 0.166 s. A span of 0.03 s can never satisfy RTF < 1: that would need a GPU decode
    round trip under 30 ms, which nothing here does. The same three spans put p50 at **0.142** and
    total decode wall at **17.09 s over an 86 s meeting — aggregate 0.20, i.e. 5× headroom.** The
    mechanism is not new (iteration 6's max was 3.908 on a 0.36 s span) and is **not** a Phase N
    regression; what changed is that this run's span shape put a micro-span *at* p95.
    **Do not answer this by filtering the reducer.** Three honest answers exist and the choice is a
    decision, not a tuning: (a) rule the clause per-span as written and accept that a meeting with
    micro-endpoints fails it; (b) rule it on decode *throughput* — total decode wall over meeting
    wall — which is what "the decoder keeps up" means and what the plan's RTF < 1 was for; (c) keep
    per-span but require a floor duration, and say what the floor is and why. (b) and (c) are gate
    definitions, so they need the operator: **needs its own authorization**, and the reasoning must be
    recorded before any reducer change, exactly as candidates 57/59/61/62 were. Loop tooling *only* if
    the answer is (a); otherwise it touches the acceptance contract.
    **PROVED A MEASUREMENT CONTRACT, NOT A DEFECT — run `20260729-094359` iteration 1.** F2 on the
    **same deployed code the same day** returned p95 RTF **0.577 GREEN** over **171** spans with
    max **2.529** and total decode **58.3 s over a 319 s meeting**. The micro-spans are still there;
    at n=171 they sit below p95, at F1's n=52 one of them *was* p95. So the clause's verdict is a
    function of the meeting's span count, not of whether the decoder kept up — which is (b)'s
    argument, made by measurement rather than by preference. The decision is still the operator's.
    **ITERATION 15: 64 IS F1's RTF RED AND IS NOT ITS LATENCY RED.** The two were carried as one line
    in the routing rule and they have different answers — F1's *user-visible latency* RED is now
    **priced** and is answerable by the plan's own second ordered remedy (see the latency-remedy block
    above and candidate 68), while 64 is untouched by that remedy and stays a gate-definition ruling.
62. **The reducer asked a certification run the soak's questions.** `[done — iteration 11]`. See
    "THE REDUCER STOPPED ASKING A CERTIFICATION THE SOAK'S QUESTIONS" in progress.txt. Loop tooling; it made
    F2 ungreenable for candidate 60, a defect outside F2's clause list.
68. **The user-visible latency gate's analytic half is an unenforced duplicate of the portal's poll
    cadence — so the gate can be moved 500 ms without changing what a human sees.** `[ANSWERED by
    Q3, iteration 23 — two enforcing nodes, one per language, and both constants at 0.5 s. The
    diagnosis below is unchanged and is why the fix has the shape it has; read candidate 71 for what
    was done. Found in iteration 15 while pricing F1's latency RED.]` `CaptureLatencyProbe.swift:328` computes
    `renderBoundMS = portalCycleSeconds*1000 + snapshotP95 + eventsP95`, and
    `userVisibleMS = committedP95 + renderBoundMS` — **verified to 0.000000000 ms residual** on F3's
    real `latency-final.json` (`portalCycleMS` 1000, snapshot p95 241.501792, events p95 191.003041,
    render 1432.504833, committed 2674.0095, user-visible 4106.514333). The 1000 ms term asserts what
    the **server's** portal does, and the server's own value is `live_portal.py:146`
    `const pollDelayMs = 1000`. **Nothing ties the two:** 0 hits for `pollDelayMs` in `tests/`, 0
    cross-language references either way, and the only assertion on the term
    (`CaptureControllerTests.swift:5699` `XCTAssertEqual(report.portalCycleMS, 1_000)`) compares the
    Swift constant **to itself**. Two consequences, and the second is the one that matters: if the
    portal's cadence ever moves alone the gate silently mismeasures by the difference; and a PRD
    acceptance number can be improved by **500 ms** by editing one Swift constant, with **no change
    to what a human sees**. *Shape of the fix, not a decision:* a node that fails when the two
    disagree — worth having whatever is decided about the cadence itself, because today the clause is
    measured through a duplicate nothing enforces.
    **ITERATION 16 SHARPENED IT, AND "CAUSALLY DISCONNECTED IN BOTH DIRECTIONS" IS A STRONGER
    STATEMENT THAN "NOTHING TIES THEM".** Measured on **tracked** source (probe section 5):
    `portalCycleSeconds` has **three** sites — declaration, report default, the `renderBound` sum —
    and reaches **no scheduling site**, so moving it moves the *number* and no request rate;
    `pollDelayMs` has **two** — the constant and `schedulePoll(pollDelayMs)` — and **0 hits under
    `macos/`**, so moving it moves what a *browser* waits and the gated number by **0.0 ms**. Moving
    the Swift one alone relaxes the gate while looking like a remedy; moving the server one alone
    hands a human the whole 500 ms and the PRD number never records it. **Either half alone is wrong,
    in a different direction** — which is why the enforcing node is the durable part of the ask
    whatever is decided about the cadence. And the gated fetch p95s are untouched by either: they are
    the app probe's own fetches at `CaptureLatencyContract.pollInterval` **0.25 s** (F3: **4001**
    samples over **1019.724 s** = 0.2549 s implied), a cadence neither constant reaches.
66. **The portal's browser-storage hygiene has evidence but no regression.** `[open, new — run
    `20260729-094359` iteration 10; the **evidence** half is DONE, see the portal-storage block
    above]`. `tests/test_live_portal.py` builds a recording `localStorage`/`sessionStorage` Proxy,
    threads `storageWrites` back to Python through two scenarios — and **no node asserts it**
    (measured: `grep -n storageWrites tests/test_live_portal.py | grep -i assert` matches nothing,
    while the file's 14 nodes pass). Iteration 10 measured the deployed page green on all five
    clauses, so the PRD row is answered *today*; what is missing is the one line that keeps it
    answered tomorrow. *Shape of the fix, not a decision:* assert `storageWrites == []` in the two
    nodes that already receive it, and give the harness's fake `document` a recording `cookie`
    accessor so the surface the static check names is also the surface the runtime check can see.
    Tracked test source under the post-merge freeze, and it can never reach `main` while the guard
    refuses a ninth merge — so it **needs its own authorization**, and it is the cheapest item on
    that list by a wide margin (two asserts and one accessor). Until then the probe is the only
    thing standing between a reintroduced write and a green gate, and **nothing runs the probe
    automatically**.

### Phase N - live speaker identity - FOLLOW ADR-0002, NOT THE SIXTH AMENDMENT

> **STEPS 1-3 ARE MERGED, PUBLISHED AND DEPLOYED as of iteration 29 (`7a4f59c`, four checkouts, host
> manifest at 0.35/0.1).** Every `[NOT gated, NOT merged, NOT deployed]` tag on the per-step blocks
> below is **historical as of that iteration** — each records the state at the moment that step
> landed, and they are kept unedited because each block's red-before evidence is only meaningful
> against the tree it was written for. **GATE STEP (d) IS NOW COMPLETE** — F1 in iteration 30 of run
> `20260729-025318` (5 GREEN, 2 RED) and F2 in iteration 1 of run `20260729-094359` (rc=0, 6 GREEN).
> What is still open in Phase N: the **two F1 REDs** (candidates 64 and the latency remedies, both
> needing the operator), the fact that **an empty cadence sweep leaves no record either way**
> (candidate 65's surviving half — iteration 7 proved the **session-end** sweep publishes and
> iteration 12 proved the **cadence** sweep does too, three corrections over ~17 deadlines, so
> ADR-0002's second acceptance half is reachable on **both** paths; what is unrepaired is candidate
> 55's fragmentation, never a reassignment in 49 corrections), and **step 4** (batch Tier-B
> unification).

**Read `docs/adr/0002-two-tier-diarization-fingerprint-album.md` and
`docs/design-streaming-diarization.md` first.** They are the operator's own accepted design, with
prototype gates A/B/C passed on **LibriSpeech** meetings using the production embedder and
production live semantics (2.5 s span cap, 0.6 s silence split, one-to-one score/margin matching,
abstain, birth, 16-speaker cap). The supervisor's TTS-based numbers below are superseded wherever
they disagree; they agree on the mechanism and the injection point.

Measured there, not here: album **98.5% mean** live accuracy (96.4-99.5%) against production's
latest-span overwrite at **66.4% mean** (51.7-87.4%), which reproduces the sibling project's <80%
failure. Starting parameters: `min_score` 0.35, margin 0.1-0.2, admission 1.0-2.0 s, k=10, sweep
every 60 s, merge threshold 0.70. Sweep cost ~0.1 ms at 600 s, <10 ms extrapolated to 3 h.

**The album alone is step 1 of 4 and is a terminal-state failure if shipped alone** - without the
retrospective sweep, live accuracy diverges from whole-file. Order: album -> tape recorder -> sweep
-> batch unification. Acceptance is >= 90-95% live accuracy AND demonstrated live->file convergence.

Note for the PRD: ADR-0002 deliberately changes the retention posture (the server keeps meeting
audio, ~0.3 GB/hr) as the substrate for sweeps, so "no raw audio is persisted" must be re-read
against the ADR rather than enforced blindly. Also open per the ADR's own §7: the prototypes used
clean read speech, so a real conversational recording is required before production sign-off - which
compounds with the measured fact that m4mbp's built-in mic cannot hear a second voice across the room.

**Phase N step index - steps 1-3 are LANDED, GATED, MERGED (`7a4f59c`), DEPLOYED 4/4 and
CERTIFIED.** The twelve per-step blocks (N-album, N-recal, N-tape's precondition, N-tape,
N-tape-wiring, N-tape-declaration, N-sweep, N-convergence, N-sweep-wiring, N-revision, N-sweep-end,
N-gate) are **retired verbatim to progress.txt** under `ARCHIVE OF context.md SUPERSEDED BLOCKS -
RUN 20260729-094359 ITERATION 2`. Each carried a payload manifest, a suite count and a red-before
revert table that was only meaningful against the tree it was written for, and all three are history
now that the code is merged, deployed and certified. What is **not** history is the decisions list
below the table.

| step | what landed | iterations | principal files |
| --- | --- | --- | --- |
| **1 - album** | `FingerprintAlbum` + the `canonical_embedding` wiring that already existed and was never passed. Measured on production code over 8 LibriSpeech meetings: **93.44 / 92.18 %** against overwrite's **72.02 / 55.68 %**, >= 90 % on every meeting | 15, measured 16 | `live_identity_album.py`, `live_provider_bundle.py` |
| **1b - recalibration** (candidate 63) | `ALBUM_MIN_MATCH_SCORE` **0.35** / `ALBUM_MIN_MATCH_MARGIN` **0.1** named once beside the policy they calibrate, the accuracy harness importing them instead of holding a copy, and the finalizer **requiring** and hash-covering `--min-match-score` / `--min-match-margin` so "measured at one pair, deployed at another" is no longer expressible | 17 | `live_identity_album.py`, `live_manifest_finalizer.py` |
| **2 - tape** | ADR-0003 first (the retention decision in writing before any code), then the appender, the five live call sites, and the three `MOSS_LIVE_RETENTION_*` keys - **opt-in, off by default, and still off on the host** | 18, 19, 20, 21 | `live_tape.py`, `live_transport.py`, `web_cli.py`, `ops/moss-live.env.example` |
| **3 - sweep** | the engine; its ADR-0002 gate-B score (**99.26 / 98.48 %**, `residual_corrections` **0**, merges **0**); the `LiveIdentitySweeper` ledger + cadence on the live path; `revise_labels` + the label track + the portal render; and the session-end `finalize_identity` with its `identity_finalized` event | 22, 23, 24, 25, 26 | `live_identity_sweep.py`, `live_session.py`, `live_span_bounds.py`, `live_coordinator.py`, `live_service_runtime.py`, `live_portal.py` |
| **gate** | (a) GREEN at `1e1cf3f` -> (b) merge **`7a4f59c`** -> (c) deployed 4/4 with the host manifest regenerated at 0.35/0.1 -> (d) F1 **5 GREEN / 2 RED**, F2 **6 GREEN / 0 RED** | 27, 28, 29, 30, then it. 1 of this run | see the gates index |
| **4 - batch unification** | **OPEN, PRICED ON BOTH SIDES, AND DEFERRED BY THE NINTH AMENDMENT** - the engine it would replace scores **80.07 % mean / 63.33 % min** (its Tier B worth **exactly zero**) where the album engine on the **same batch input** scores **100.00 %**, i.e. **+19.93 pp** — but only with a *perfect* causal pass; degrade it and the *"album replaces both tiers"* reading **loses by 27 pp** while *"album replaces Tier B only"* wins by 21.5, so **step 4 must keep Tier A**. prd.md's Phase Q puts step 4 **out of scope**, *"worth its own authorization later"*: neither the work nor the merge is open now. See N-batch below | baseline 17, counterfactual 18, degradation 20 | `batch-tierb-baseline-probe.py`, `album-batch-counterfactual-probe.py`, `degraded-causal-pass-probe.py` |

**N-batch — STEP 4, THE ONLY OPEN PHASE N ITEM, and it needs no new authorization.** Steps 1-3 are
code-complete, gated, merged (`7a4f59c`), deployed 4/4 and certified by F1 and F2; step 4 is
ADR-0002's own fourth of four, *batch Tier-B unified onto the same album engine*, and prd.md's
*"Phase N remains authorized. Take it in ADR-0002's shape"* covers it.
*Read these three constraints before designing it.* **(1)** Decision 4 above: a sweep re-matches
retained vectors and never re-hears audio, so it repairs an **assignment**, never a
**segmentation** — re-VAD from the tape is explicitly not part of step 3 and would be a separate,
separately-measured change. **(2)** Decision 5: the matcher is already **one** function
(`live_identity.assign_speakers`) called by both the live path and the sweep, so unification means
the batch path calls *that*, not a third implementation. **(3)** Decision 18 and the convergence
block's honest reading: the file answer live already converges to **is the same album engine run
non-causally**, i.e. what the session-end sweep computes — which is step 4's own end state, so a
convergence number alone proves nothing and only the ground-truth accuracy score carries weight.
*The sequencing caveat that used to stand here is FALSIFIED and is corrected in the seventh
compaction:* it said *"candidates 60 and 65 mean neither half of step 3 publishes a correction on the
deployed system, so unifying batch onto an engine whose live half is inert would be measured offline
only"* — and **both halves demonstrably publish on the deployed service**: the session-end sweep
revised **19 of 31** spans (iteration 7) and the cadence sweep published **three** mid-meeting
revisions across ~17 deadlines (iteration 12, inside F3). Step 4 would therefore be unified onto a
**live** engine, not an inert one. *What survives of the caveat, restated honestly:* the deployed
sweep has never published a **reassignment** — all 49 corrections across four swept meetings are
`S00 -> Sxx` — so a convergence measurement on a meeting shaped like candidate 55's would be
measuring fill-ins, not repairs.
***THE HEADLINE ABOVE AND THE LAST SENTENCE OF THIS PARAGRAPH ARE SUPERSEDED BY THE NINTH AMENDMENT,
which landed mid-iteration-20*** `[6e3e4fe, 10:14:08]`. They read *"the only open Phase N item, and it
needs no new authorization"* and *"the one item here the loop can start without the operator"* — the
**work** reading iteration 18 already narrowed. prd.md's Phase Q now settles it in the operator's own
words: step 4 is **"Out of scope: ADR-0002 step 4 (batch unification) … worth its own authorization
later."** It is not the loop's next work; **Phase Q is.** Everything above this line about *how* step
4 must be built is unaffected and still binding.

***STEP 4 NOW HAS THE BASELINE IT NEVER HAD, AND THE ENGINE IT WOULD REPLACE IS WORSE THAN THE LIVE
ONE ON THE SAME AUDIO*** `[iteration 17; `scripts/ralph-afk/batch-tierb-baseline-probe.py`, rc=0,
15/15 checks, offline, 6.5 s. No product source, no host, no session, no authorization.]* The album's
93.44 % has had **no counterpart on the batch side since ADR-0002 was written**, so "unify" could not
be told from "rewrite for tidiness". It can now. The probe drives the **production**
`IdentityResolver.resolve` over the **same eight LibriSpeech meetings** at the shipped batch geometry
(`plan_windows` 150 s / 120 s), substituting only the encoder by the same cached-real-encoder
discipline `tests/live_identity_accuracy.py` uses, and scores it with **the album's own
`speaker_accuracy`**.

| engine, identical corpus and identical scorer | mean | min |
| --- | --- | --- |
| live album, label a reader saw at commit | **93.44 %** | 92.18 % |
| **batch, as `ops/start-web.sh` deploys it** (`--speaker-identity-tier-b`) | **80.07 %** | **63.33 %** |
| batch, Tier B **off** (the `IdentityResolverConfig` default) | 80.07 % | 63.33 % |
| batch, Tier B at the album's 0.35 / 0.1 | 80.07 % | 63.33 % |
| batch, Tier B at the album's k=10 intervals per node | 80.07 % | 63.33 % |
| batch, both | 80.07 % | 63.33 % |

**Three findings, and the second is the one that decides step 4's shape.**
1. **The product's file mode is worse than its live mode on the same audio** — −13.38 pp mean,
   −28.85 pp min — and the batch figure is an **upper bound**, because the probe hands Tier A a
   *perfect* local diarization identical in both windows of every overlap. The gap is entirely at
   k >= 3: batch scores **100 %** on both k=2 meetings (beating the album by +7.19 / +5.69) and
   63.33-84.77 % on the six k>=3 ones.
2. **Batch Tier B moves the score by exactly zero — `max |delta| = 0.0000000000 pp` on every
   meeting and every arm — and recalibrating it to the album's parameters does not change that.**
   It is not inert: it accepted **5** links and merged real canonicals (19 → 16 on `meet_k6_s1`).
   The cause is **structural, not a threshold**: `_tier_b_evidence:726` offers Tier B only
   `len(component) == 1` components, so two multi-window chains of the same speaker can **never** be
   merged, and of the corpus's **71** components only **36** are ever eligible. Among those, the
   dominant refusal is `cannot_link_conflict` **195 of 310** proposals (a singleton cannot link to a
   component sharing its window), then `low_similarity` 95, `low_margin` 10, `accepted_similarity` 5.
   ***So porting the album's thresholds into `IdentityResolverConfig` is measured to buy nothing;
   step 4 has to replace the linking structure, not retune it.***
3. **Batch fragments the same way live does, from a different cause.** 6 speakers → **19** Tier-A
   components → 16-17 canonical labels, against candidate 55's 16 on the live side. Live fragments by
   *birth without a duration floor*; batch fragments by *a chain Tier B may not touch*. Two defects,
   one symptom — and one more reason the fix is one engine rather than two calibrations.

**Two engines, proved on tracked source:** `speaker_identity.py` references no live identity module
and the three live identity modules reference no batch resolver (0 hits each way), and the two
similarity rules disagree by contract on the same pair — `_cosine` returns −1.000 unclamped where
`cosine_similarity` returns 0.000. Both build a reference as a mean of per-interval embeddings, so at
these thresholds the duplicate is a **maintenance hazard, not a measured behavioural difference**;
decision 5's "the matcher is ONE function" holds on the live path and has never held across the batch
seam.
**The three fidelity limits are printed by the probe itself with their directions** — perfect Tier A
(upper bound for batch), <= 2.5 s evidence units (pessimistic for Tier B, which is why the k=10 arm
exists and still moves nothing), LibriSpeech read speech (ADR-0002 §7's own caveat).

***AND THE COUNTERFACTUAL THE BASELINE DELIBERATELY DID NOT MEASURE IS NOW MEASURED: +19.93 pp***
`[iteration 18; `scripts/ralph-afk/album-batch-counterfactual-probe.py`, rc=0, 9/9 checks, offline,
~20 s. No product source, no host, no session, no authorization.]* The **production live identity
engine** — `assign_speakers`, `FingerprintAlbum`, `cosine_similarity`, `duration_weighted_centroid`,
`SweepLedger`, `sweep` — driven over the **identical batch input**: the probe imports
`batch-tierb-baseline-probe.py`'s own `build_case` by `importlib` rather than re-deriving it, because
"two engines saw the same windows" is the one precondition a second copy of that code would quietly
break. A window is a span; its local speakers are matched one-to-one at 0.35/0.1, the unmatched are
born, every labelled local is offered to the album under the live admission rule.

| arm | mean | min | vs shipped batch |
| --- | --- | --- | --- |
| batch shipped (recomputed in-process, never copied) | 80.07 % | 63.33 % | — |
| **`album_only`** — the album replaces **both** tiers | **100.00 %** | **100.00 %** | **+19.93 pp** |
| `album_only_top3` — query from batch Tier B's own top-3 units | 100.00 % | 100.00 % | +19.93 |
| `album_only_batch_thresholds` — the album engine at **batch's 0.70/0.20** | 99.97 % | 99.74 % | +19.90 |
| `tier_a_album` — the album replaces **Tier B only**, Tier A links kept | 100.00 % | 100.00 % | +19.93 |
| `*_swept` — either, plus the production `sweep()` | 100.00 % | 100.00 % | +19.93 |

**Four findings, and the second is the one to carry.**
1. **Per meeting the gain is entirely at k >= 3**, exactly where the baseline falls: +0.00/+0.00 on
   the two k=2 meetings (batch already scores 100 %), then **+15.23 to +36.67 pp** on the six k>=3
   ones. And **30 births for 30 true speakers** — *exactly one canonical per voice*, against batch's
   16-17 labels for 6 speakers and candidate 55's 16 on the live side.
2. **THE 100 % IS A CEILING, AND THE PROBE MEASURES WHY IT SATURATES RATHER THAN ASSERTING IT DOES
   NOT.** A 150 s window hands the matcher **20-61 s** of one speaker (median per meeting; min 1.0 s),
   and at that duration the worst per-meeting gap between the **lowest** same-speaker cross-window
   cosine and the **highest** cross-speaker one is **+0.190** (best +0.616; same-speaker minima
   0.570-0.915, cross-speaker maxima 0.214-0.479). So window stitching on clean read speech with a
   perfect local diarization is a **separable** task. ***What this establishes is the cause, not the
   production number: an engine that loses ~20 pp on a task this separable is losing it
   STRUCTURALLY, NOT PERCEPTUALLY.***
3. **The mirror of iteration 17 completes the ruling in both directions.** Batch's engine at the
   album's thresholds moves by **0.0000000000 pp**; the album's engine at **batch's own** 0.70/0.20
   still wins by **+19.90 pp**, and ADR-0002's 0.35/0.10 is worth only **+0.03 pp** here. Only
   **9 of 335** same-speaker cross-window node pairs fall below batch's 0.70 floor (**0** below the
   album's 0.35), so the floor is not what loses the 20 pp either. **Step 4 is not a recalibration in
   either direction.**
4. **Tier A adds ZERO once the album is present** — `album_only` == `tier_a_album` to the digit — and
   it is at its most favourable here, handed a perfect local diarization. That limit inflates
   `tier_a_album` and the 80.07 % baseline **equally** and does not touch `album_only`, so the
   headline comparison is the conservative one.
   ***FALSIFIED AS A GENERAL CLAIM BY ITERATION 20, AND THIS IS THE FINDING THE NEXT ONE SHOULD
   CARRY.*** It is true **only** when the causal pass is perfect, which is the one condition under
   which the two arms cannot differ — Tier A links what the album would have linked anyway. Degrade
   the causal pass and the two arms separate by **49 pp**. Read finding 4 as *"a perfect causal pass
   hides which reading of step 4 is right"*, never as *"Tier A is redundant"*.
*Two things the probe does NOT establish, printed by it as limits:* the **sweep half is untested** —
production `sweep()` proposed **0** corrections and **0** merges, because the causal pass was already
perfect, which is convergence by vacuity; and this is a **prototype**, not a resolver.
**BOTH LIMITS ARE NOW MEASURED — see the degraded-causal-pass block immediately below.**

***THE CEILING IS REMOVED, THE SWEEP IS NO LONGER VACUOUS, AND ONE OF STEP 4's TWO READINGS IS
FALSIFIED*** `[iteration 20; `scripts/ralph-afk/degraded-causal-pass-probe.py`, rc=0, all checks
passed, offline, 6.6 s. No product source, no host, no session, no authorization spent.
Evidence `/tmp/i20-degraded.txt`.]* Iterations 17 and 18 both measured a **perfect** local
diarization — `build_case` hands every window each unit's true speaker, rotated per window — so
`album_only` and `tier_a_album` both read 100.00 % and ADR-0002's two readings of step 4 looked
interchangeable. This probe degrades the causal pass the two ways a real diarizer is wrong and hands
the **identical** labels to both engines through **one monkeypatched `base.build_case`** (never a
copy — the batch resolver reaches it as a bare global, the album arm through `base.`). The
degradation is label-only, so window geometry, unit intervals, the encoder cache and truth are
untouched; it is a pure CRC32-seeded function of (meeting, mode, rate) and memoised, so the several
calls each arm makes return identical labels. **The `none` control reproduces the published
80.0667 / 63.3330 / 100.0000 / 100.0000 to the last digit**, which is what makes the degraded rows
measurements of the engines rather than of the harness.

| causal pass | batch | album only | album+sweep | **Tier A + album** |
| --- | --- | --- | --- | --- |
| perfect (control) | 80.07 | **100.00** (+19.93) | 100.00 | 100.00 |
| over-segmented @0.30 | 57.84 | 30.50 (**−27.34**) | 44.80 (−13.04) | **79.34** (+21.50) |
| over-segmented @0.60 | 42.73 | 17.74 (**−24.99**) | 27.82 (−14.91) | **58.58** (+15.85) |
| confused @0.10 | 47.17 | 87.45 (+40.27) | 87.45 (+40.27) | **88.47** (+41.29) |
| confused @0.25 | 27.06 | **51.06** (+24.00) | 47.00 (+19.94) | 47.00 (+19.94) |

**Three findings, and the first is a design constraint on step 4 rather than a number.**
1. **STEP 4 MUST KEEP TIER A.** *"The album replaces both tiers"* is **worse than the engine it
   replaces** under over-segmentation (−27.34 pp, and still −13.04 after the sweep); *"the album
   replaces Tier B only"* wins at **every** condition. **The mechanism is counted, not inferred:**
   at @0.30 the causal pass adds **44** nodes and the album mints only **6** extra canonicals, so
   **38 cut halves were matched onto an *existing* canonical**. `assign_speakers` is one-to-one
   *within a span* — and **a window is not a span**. Two local labels in one window *can* be the
   same person, so the live path's one-to-one rule is **false on the batch path**, and it pushes the
   second half of a cut turn onto **another speaker**, which is worse than a spurious birth because
   it poisons that speaker's centroid too.
2. **§6(7) IS CLOSED: the sweep is not vacuous once the causal pass is imperfect.** **25 corrections
   / 6 merges** at @0.30 worth **+14.30 pp** (30.50 → 44.80) and **23 / 16** at @0.60 worth
   **+10.08 pp**, each reaching a **fixpoint** (residual 0). ADR-0002 step 3's machinery
   demonstrably helps a batch resolver. ***And it can hurt:*** under label **confusion** at @0.25
   the sweep moved the mean the **wrong way, 51.06 → 47.00 (−4.06 pp)** — a merge over blended
   centroids can join two real speakers. **Step 4's gate must measure both directions.**
3. **§6(6)'s ceiling now has a floor.** The winning arm falls to **79.34 %** / **58.58 %** under
   degradation and still beats batch by +21.50 / +15.85 pp: *the ranking survives, the level does
   not.* Robust to confusion, fragile to over-segmentation.

**Two limits, and the second bounds the headline.** The error model is **synthetic and uniform** — a
real diarizer errs where the audio is hard, so these scores are optimistic about *which* units break
and honest about *how many*; read the gap and the counts, not the level. And **the degradation moves
labels and never boundaries, while Tier A links on boundaries**, so `tier_a_album` is an **upper
bound**. That is not a biased comparison — the batch baseline runs the same Tier A over the same
exact intervals, so the inflation is shared and the gap is the comparable quantity, while
`album_only` reads no boundary at all and is the **conservative** arm. **A boundary-jitter
degradation is the probe that closes this, and the loop can run it without an authorization.**

*Sequencing, restated for the ninth amendment:* step 4 is filed as **§4(f)** of
`authorization-request-55-60-65.md` and prd.md's Phase Q now puts it **out of scope**, *"worth its
own authorization later"* — so neither the work nor the merge is open. §6(6), §6(7), §6(8) and
§6(9) of that document carry these numbers and limits.

**Decisions that outlive the retired step blocks - recorded here so they are not re-argued, because
step 4 and any future identity work are constrained by them.**

1. **Admission is 1.0 s and `min_segment_samples` does NOT move.** The superseded sixth amendment's
   flat ">= 2.0 s enrollment floor" is refuted by measurement: admission 0.01 / 1.0 / 2.0 gives
   93.5 / 93.4 / 93.4 %, while **k=1 gives 79.2 %** and k=3 gives 89.7 %. ***k*, not the duration
   gate, is what beats overwrite** - a full bank *is* a duration gate, since `_admit` evicts the
   shortest. `min_segment_samples` is the **evidence** floor: raising it makes short spans
   unlabelable, the exact opposite of the asymmetry this phase exists for. 1.0 s over 2.0 s because
   ADR-0002's gate A passed at 1.0 s under production live semantics, and a 2.0 s admission under a
   2.5 s span cap with 0.6 s silence splits would starve the album.
2. **The margin half of admission is enforced upstream, so it is recorded rather than
   re-implemented.** The album only ever observes assignments out of a **`prepared`** preparation,
   and the preparer abstains for the whole span below `min_match_score` / `min_match_margin`, so an
   assignment that reaches the album carries the margin by construction.
3. **A provisional stand-in, kept while the bank is empty and discarded - never averaged - by the
   first admitted exemplar.** ADR-0002 requires birth semantics to be unchanged, and without the
   stand-in a speaker born from a 0.6 s span would have **no reference at all**, would never be
   matchable, and every recurrence of that voice would birth another id: strictly worse than
   candidate 55 measures today. Tie rules differ by tier on purpose - the bank replaces the oldest
   equally-long exemplar (a sample benefits from recency), the stand-in keeps the incumbent (a
   placeholder benefits from not churning, and churn is the defect being removed).
4. **A sweep re-matches retained evidence; it NEVER re-hears audio.** ADR-0002's prose says
   "re-embed/re-cluster the assembled tape"; its **measured** gate B says a sweep costs ~0.1 ms at
   600 s while the same document measures embedding at **332-343 ms per unit**, and those two numbers
   cannot both describe re-embedding. *Take the measured one.* The consequence, stated so no
   convergence number is over-read: **a sweep repairs an assignment, never a segmentation** (ADR-0002
   §7 carries the identical caveat), so **the tape is not yet paid for by step 3** - re-VAD from it
   is a later, separately-measured refinement, and the tape's nearer value is crash/resume.
5. **The matcher is ONE function called by both paths.** `live_identity.assign_speakers` was
   extracted behaviour-preservingly from `BoundedCausalIdentityPreparer._assign`, and
   `cosine_similarity` / `duration_weighted_centroid` live once in `live_identity_album.py`. A sweep
   that re-implemented the matcher would issue "corrections" that are a second opinion from a second
   implementation - the exact hazard `tests/live_identity_accuracy.py` exists to rule out, and the
   one ADR-0002's own prototype fell into.
6. **Three rules bound what a sweep may change:** it never invents a canonical speaker (birth is a
   live decision under the 16-cap); it never removes a label it cannot replace (J2 - enforced by the
   **type**, `SweepCorrection.canonical_speaker` being non-optional, so an erasure is unrepresentable
   rather than merely unimplemented); and a move must beat the incumbent by `min_match_margin`. The
   third is measurably redundant at the deployed 0.35 / 0.1 and is kept for a deployment whose margin
   exceeds its own match floor.
7. **A merge needs an admitted bank on BOTH sides**, two album centroids at or above **0.70** are one
   voice born twice, the group's reference is the duration-weighted centroid over the **union** of
   the exemplars, and the surviving id is the one with the most admitted speech - so birth order
   never decides identity. **Measured: the merge fires ZERO times on all eight fixture meetings**, so
   the sweep's entire +5.82 pp is **re-matching**. The album ends a meeting holding 3-6 of the 16
   minted speakers, only 2-3 banked, and those centroids sit at **0.19-0.43** against the 0.70
   threshold - genuinely different voices. The node asserts `merges == 0` in falsifiable form so a
   parameter change re-opens the question instead of inheriting it. **The "3-6 held / 2-3 banked"
   range is stale — re-measured in iteration 4 of run `20260729-094359` it is 3-9 held and 2-7
   banked (42 held, 31 banked over the eight meetings). The `merges == 0` finding is unaffected.**
8. **The ledger retains every embedded unit, labelled or not**, because an **abstained** span never
   reconciles and is exactly the span a later album has the most to say about. Bound measured, not
   estimated: one 256-dim `array("f")` vector costs **1104 bytes** against **8232** as a tuple, so
   `SWEEP_LEDGER_MAX_UNITS` 20 000 is **~22 MB**; F3's real soak ran 0.43 spans/s, so three hours is
   well under 10 000 units. A full ledger **refuses new units rather than evicting old ones** (the
   opposite of a cache): a sweep's value is in correcting the *early* decisions against a *later*
   album.
9. **Cadence is meeting time, never wall time**, the next deadline is computed **from the time
   reached** (so a burst after an outage schedules one sweep, not a catch-up burst over time in which
   nothing was retained), and the cadence never sees the span being prepared - because the reconcile
   runs first, every span but the one in flight is settled at cadence time. **The cadence is nearly
   free of effect:** 600 s gives 99.22 % against 60 s's 99.26 %, so `SWEEP_INTERVAL_SECONDS` 60 buys
   a reader earlier corrections, not a better ending. The value is in the **session-end** sweep.
10. **A correction is published BESIDE the transcript** (`CanonicalCommit.revised_transcript`);
    `transcript` and `prefix_hash` never move, because the chain records what was *said* and a living
    document's corrections are a different fact. Three enforced rules make it safe: a span is revised
    **only if it re-renders to itself byte for byte** (which is why the span grammar has exactly one
    writer, `live_span_bounds.render_segments`, with three readers), a span never puts two of its own
    locals on one identity, and every refusal is one of six **named** counts on `canonical_processed`.
    **A correction is addressed by `(span, local speaker)`**, which is why the session retains a label
    track: addressing by displayed label is impossible for exactly the span that matters, since an
    abstained span shows `S00` for every one of its local speakers. A **closed** session is still
    revisable, because the session-end sweep is where the value was measured.
11. **Reconcile then sweep at session end, and the order is load-bearing.** Reversed, the final sweep
    re-matches the last span while the ledger still holds it unlabelled and proposes a `labelled`
    correction for a span the live path had already labelled correctly - a rewrite that changes
    nothing, reported as if it had. The **abort path deliberately does not sweep** (a terminal session
    is not in `VIEWABLE_SESSION_STATUSES`, so the correction would reach no reader); a stack that
    raises on the way out is **named** (`identity_finalize_failed`) rather than terminal; and the
    `identity_finalized` event is recorded **whether or not anything changed**, because "found
    nothing" and "never ran" are opposite facts about a meeting. ***Candidate 65 is that same ruling
    withheld from the cadence half*** - `sweep_now` sets `_unconsumed` and logs only when the revision
    is non-empty.
12. **The bundle cannot build an album without a sweeper** - `_identity_evidence_provider`'s
    `identity_config` is **required**, not defaulted, so a sweeper with its own calibration is
    unwritable. And **a tool states the calibration; it does not default it**: a free parameter has no
    derivation a tool could verify, so a built-in default would be a guess wearing a contract's
    clothes. The finalizer therefore requires the flags, writes them into the plan, the evidence and
    the regenerated `identity_config_hash`, and refuses a pair **the runtime's own reader** rejects
    rather than re-implementing its rules.
13. **The tape never raises because of a frame** - cap reached, write failed, or a frame it cannot
    place gives one typed degradation (`tape_capacity_exhausted` / `tape_write_failed` /
    `tape_frame_not_admissible`), taping stops, the call returns. But **`declared()` refuses a bad
    root loudly at construction**, because a root that cannot hold audio safely must stop the service
    starting with retention enabled rather than silently disabling it. Placement is computed from
    `capture_timestamp_ns`, **never** arrival order, and the gap manifest is the complement of a
    merged coverage list, so a late frame *removes* a gap rather than appending a correction. The tee
    is **after** the ingress ack (the tape records what the session accepted). The tape's lifecycle is
    the **mixed track's** - `release` paired with `v2_mixers.release`, not with
    `access.release_session` - which is what makes a **lease expiry**, the usual terminal path on the
    real hosts, release it at all. The never-raises rule is enforced at the recorder, not at eight
    call sites, and every swallow logs one WARNING naming the action.
14. **ADR-0002's gate-B sweep cost is off by ~300x, and the answer is batch scoring.** Measured on
    production code at F3's own shape (443 spans / 886 units / 16 speakers / 256 dims), scoring pair
    by pair costs **295 ms at 17 min, 1032 ms at 1 h, 3098 ms at 3 h** - and the sweep runs inline on
    the serial canonical pump, so a 3.1 s stall is **longer than the 2.5 s span cap**. Scoring a whole
    span against a reference matrix built **once per sweep** gives **39 / 125 / 366 ms**, 7.5-8.5x,
    with the eight-meeting harness still measuring 99.26 / 98.48 swept and 93.44 / 72.0 unswept,
    unchanged, `residual_corrections` 0.
15. **A green node can be measuring the wrong cause, and only a revert finds out.** Three consecutive
    iterations hit it: a reconcile-seam node stayed green because a cadence sweep also writes labels
    through `ledger.apply` (it now runs with the cadence off); an abort revert was a no-op because
    `abort` calls `_fail` first and the finalize early-returns on a terminal session; and an ordering
    revert was a no-op because `session_closed` is recorded **after** the `try` block - the honest
    instrument turned out to be the **snapshot version each event is stamped with**, not event order.
16. **The durable rule out of the recalibration: a threshold recorded out of a document is a claim
    about the document - read the value off the host before pricing what changing it buys.** What was
    actually deployed was **`0.5 / 0.05`** (measured **83.72 % mean / 69.20 % min**), not the
    `0.5 / 0.2` every block since iteration 16 had recorded (75.00 / 39.97), so the regeneration
    bought **+9.72 pp mean / +22.98 pp min**, not the +18.4 pp on record. The conclusion survives and
    is now honest: what was running sat **below ADR-0002's >= 90 % bar**, so a redeploy that skipped
    the regeneration would have shipped a 93 % album into an 84 % matcher.
17. **The retention posture, from ADR-0003 (step 2's precondition, recorded before any code).** The
    PRD clause is **not** a prohibition on audio reaching a disk - live audio touches disk on every
    span today (`live_adapters.py:298` and `live_provider_bundle.py:561` both write PCM into a
    `TemporaryDirectory(prefix="mtd-live-")`). It is a statement about a **horizon**, today **one
    span**, moved to **one meeting**. D1 the horizon becomes the session; D2 opt-in and off by
    default (a privacy posture must not arrive as a side effect of an upgrade); D3 default TTL after
    session end is **zero**, and a positive TTL is stated by the deployment, never defaulted by a
    tool; D4 one declared root, 0600/0700, outside the checkout, **not on the batch runs filesystem**
    and on a filesystem that enforces modes - which disqualifies `/mnt/d` twice over; D5 storage
    pressure **degrades the tape, never the meeting**; D6 the service reaps, at startup too; D7 no
    audio on the Mac, in a log, in an evidence directory, or under batch `runs/`. ***The measured
    argument that is easy to miss:*** a runaway tape breaks the PRD's *"batch service unharmed"*
    clause **without touching the batch service** - `server.py:447` answers **507** when free space
    drops below `2 x content_length + 512 MB`, and at ~0.3 GB/hr that headroom is under two hours of
    one meeting. That is why D4(3) is a rule and not a preference.
18. **What is still NOT done, so a green suite is not mistaken for a finished job.** The album is
    **never itself merged**. The accuracy corpus is clean read speech with no overlap, and
    `min_segment_samples` skips the sub-floor fragments a real room produces, so **99.26 % is the
    identity layer's ceiling on easy audio**, not a production forecast - ADR-0002 §7's own caveat,
    compounded by candidate 51's measured microphone limit. The harness records each unit already
    carrying its final canonical speaker, so it never models the transient one-span reconcile lag.
    ***The fourth sentence of this decision was FALSIFIED and is corrected in the seventh
    compaction.*** It read *"on the deployed system neither half of step 3 publishes a correction
    (candidates 60 and 65), so the convergence half of the acceptance bar is unmet in production"* —
    but iteration 7 measured the **session-end** sweep revising 19 of 31 spans on the deployed
    service and iteration 12 measured the **cadence** sweep publishing three mid-meeting revisions, so
    both halves publish. **The honest statement of what is still unmet:** all **49** deployed
    corrections are `S00 -> Sxx` fill-ins of a *missing* label and **not one is a reassignment**, so
    the sweep has never been observed to repair candidate 55's minted junk labels — which is what
    convergence on a real fragmented meeting would require. Unmet, but for a reason two measurements
    narrower than the sentence it replaces.
19. **A sweep publishes nothing on a FRAGMENTED meeting, and the cause is a PRODUCT — reference
    multiplicity ×
    references too short to bank** (filed iteration 3 of run `20260729-094359`; premise and mechanism
    both corrected in iteration 4 by `album-bank-shape-probe.py`, settled in iteration 5). *The two
    superseded readings are retired to progress.txt with the fifth compaction.* Four things they
    leave behind, because a future run would otherwise re-derive them: at the deployed admission
    **31 of 42** album speakers are banked, and on the canonical-speaker denominator F1/F2 used it is
    **31/128 = 24.2 %** against F2's 12.5 % and F1's 16.7 % — the "fixture vs real corpus" contrast
    was two different denominators; **an all-stand-in reference set still sweeps** (140 corrections,
    11.4 % `kept_ambiguous`, 82.89 → 88.54 %), so `_album_view`'s deliberate admission of stand-ins
    is **not** the defect and ADR-0002's +5.82 pp is **not** shown to be a fixture artefact; of the
    16 canonical labels a reader sees per fixture meeting only **~5.25** ever reach the album at all
    (decision 2 — it observes only `prepared` assignments), a third category neither this decision
    nor decision 7 had named; and ambiguity tracks **references per real voice** (1.40 → 1.1 %,
    1.77 → 11.4 %, against F2's 8.0). *The durable lesson:* iteration 3 measured the right numbers on
    invented vectors and attributed them to the one difference it could see, while its own
    sensitivity sweep was already saying the result came from reference *similarity*.
    **ITERATION 5 RAN THAT DECISIVE EXPERIMENT AND THE ANSWER IS A PRODUCT, NOT A FACTOR —
    `sweep-multiplicity-probe.py`, rc=0, ~47 s, real encoder geometry, deployed live path in every
    row.** The knob iteration 4 said did not exist does: the album's **public `observe`** will
    redistribute a speaker's own exemplars across `m` labels, so multiplicity moves while the
    matcher, the live path and the vectors do not. Measured over the 8 fixture meetings:
    | reference set | refs/voice | `kept_ambiguous` | merges | final accuracy |
    | --- | --- | --- | --- | --- |
    | album as built (control) | 1.40 | **1.1 %** | 0 | **99.26 %** |
    | split over 2, **banked** | **1.40** | **1.1 %** | **51** | **99.26 %** |
    | split over 8, banked | 3.10 | 20.3 % | 278 | 91.43 % |
    | all stand-in, **not split** (control) | 1.40 | **3.8 %** | 0 | **98.93 %** |
    | split over 2, **stand-in** | 2.40 | **74.4 %** | 0 | 69.85 % |
    | split over 8, stand-in | **8.40** — F2's ratio | **84.1 %** | 0 | 46.82 % |
    ***The mechanism, and it reconciles iterations 3 and 4 instead of choosing between them:
    `_album_view`'s MERGE is the defence against multiplicity, and a stand-in disables it.***
    Splitting 42 references into 84 changes **nothing** when the shards are banked — the sweep
    merges them straight back to 42 and both ambiguity and accuracy are unmoved — and the identical
    split held sub-admission cannot merge at all (decision 7 requires an admitted bank on *both*
    sides), so every shard survives into the reference set and the matcher's margin rule abstains.
    **Neither stand-ins alone (3.8 %) nor multiplicity alone (1.1 %) does it; the product does
    (74.4 %).** Iteration 3 was right that the stand-in is load-bearing and wrong about *why* —
    it is not that a stand-in is confusable, it is that a stand-in is **unmergeable**.
    *Two honest limits.* (1) Extreme splitting defeats the merge even when banked — at m=8 a shard
    holding one exemplar drifts below the 0.70 threshold, which is why that row reaches 20.3 %; the
    defence is strong, not absolute. (2) The final-accuracy column is a **model** collapsing: it
    holds the live labels healthy (93.44 %) while the album is fragmented, and a real meeting
    fragments both together, so read it as "the corrections stop tracking truth", **not** as a
    forecast of what a real swept meeting would score.
    ***(3) — ADDED IN ITERATION 9, AND IT IS THE LIMIT THE OTHER TWO DID NOT SEE.*** Every row of
    this table **gives** the sweep a reference for each shard; the experiment could only shard
    vectors that exist. Production gives it **none** — decision 20's `no_reference` births are
    never embedded, so they hold no ledger unit and the sweep never scores them. Measured on the
    deployed service at F2's own shape: the sweep repaired **7 of 8** abstained spans, a *higher*
    conditional rate than the healthy control's 20 of 34, and published **zero** reassignments (as
    did every other deployed run — 46 corrections, all `S00 → Sxx`). **The table's direction is
    right and its door is wrong:** at F2's fragmentation the sweep is not ambiguous, it is
    uninformed. Read the 84.1 % as an upper bound on what a *repairable* fragmentation would cost,
    never as what production's does.
20. **A canonical speaker is minted from audio the system refused to embed, and that one site
    produces BOTH halves of decision 19's product** (filed iteration 6 of run `20260729-094359`,
    `birth-floor-probe.py`, rc=0, offline, no product change). `BoundedCausalIdentityPreparer.
    prepare` (`live_identity.py:129`) births a canonical speaker for every local speaker that did
    not match, with **no duration condition of any kind**. The evidence floor
    (`_speaker_intervals_by_label`, `min_segment_samples` 8000) and the album's admission gate
    (`ALBUM_ADMISSION_SECONDS` 1.0) both sit *below* it, so a birth lands in one of three states
    and only the third is a reference the sweep can merge: **no_reference** (no segment cleared
    0.5 s, so the encoder was never asked — not even a stand-in), **provisional** (one
    sub-admission fragment, unmergeable by decision 7), **banked**.
    *Measured on the two real meetings whose span bodies survive:*
    | run | canonical | refs/voice | no_reference | provisional | banked |
    | --- | --- | --- | --- | --- | --- |
    | **F2** (300 s, `7a4f59c`, album live) | 16 | **8.0** | **14** | 1 | 1 |
    | **F3** (17 min, `42abc5a`) | 16 | **8.0** | **13** | 1 | 2 |
    F2's span 16 is `'........................'` — the decoder emitting no words on the silence
    window — and it minted **two** canonical speakers. The floor is **per segment**, so F3's `S04`
    (1.08 s in nine 0.12 s fragments) produced no vector either.
    *The counterfactual, which BOUNDS and does not simulate* (suppressing a birth changes the
    matcher's later inputs, so these are a lower bound on the count under a floor): a floor on
    embedded seconds at 0.5 s leaves **2 / 3** speakers (**1.0 / 1.5** refs per real voice), at
    1.0 s leaves **1 / 2** — and at 1.0 s every survivor is banked **at birth by construction**,
    so "a canonical speaker with no admitted bank" stops being representable and decision 19's
    product cannot form. 1.0-1.5 is the fixture's own 1.40 regime (1.1 % ambiguous, 99.26 %).
    *Recorded so they are not re-proposed:* raising `max_speakers` 16 → 32/64 buys +4.5 pp of live
    accuracy on the fixture but raises refs/voice, so by decision 19's mechanism it should make
    the sweep **more** inert on a real meeting (an inference, not a measurement); lowering
    `min_segment_samples` is refuted by the 0.5 s overlap (same-speaker 0.378, cross-speaker
    0.360). **This changes birth semantics, which Phase N decision 3 records ADR-0002 as requiring
    unchanged — hence an amendment, not "Phase N remains authorized".**

### (superseded) Phase N as first written - retired to progress.txt

The sixth amendment's `N1`-`N5` list and the supervisor's TTS-based measurements are **retired
verbatim to progress.txt** with the fourth compaction. prd.md's own supersession section carries
everything that survives: replacement at `_reconcile_committed_vectors` is the defect, the fix is
injected through the existing `canonical_embedding` hook so matcher/abstain/birth semantics are
unchanged, and re-embedding 0..t is rejected on O(T^2) cost. Everything else in it - the flat
">= 2.0 s enrollment floor" above all - is superseded by ADR-0002 and refuted by the measured
`k`-not-duration finding (decision 1 above).
**Numbering, repaired in iteration 29:** Phase N items are `N1`-`N5` and carry **no** number. They
were minted as 55-59 by the sixth amendment on the same day iterations 12 and 26 minted diagnostic
candidates **55, 56 and 57**, so each of those three numerals meant two different things and
"candidate 56 needs authorization" resolved to either the viewability blocker or the centroid.

### Phase P — CLOSED; the candidate list is retired to progress.txt

The seventh amendment's cycle (P1 monotonic measurement, P2 untrustworthy timing degrades, P3 four
real-seam nodes, P4 the class swept) landed at `5bc4f7f`, merged as `42abc5a`, deployed 4/4, and is
proven dead on the server. The rule it shipped is the **Duration vs timestamp** row in Shipped
contracts; the Phase P gate and P7 merge rows are retired to progress.txt. The full list —
including P4's four-site sweep table and P3's per-half red-before table — is in progress.txt under
**"Phase P candidate list (P1-P5, the sweep table, the per-half red-before table)"**.
**Its candidate 58 leftover is closed**, in the numbered list above: coherent declared-null timing
is visible but not corrupt, while malformed timing still fails closed. Explicitly out of scope:
mandatory client retention of the 409 refusal body — the right fix, needing its own authorization.

### Real-audio evidence, operator-supplied 2026-07-29 (bench `b6b6c5c`) - BINDING

The operator's benchmark harness now lives in the repo at `prototypes/streaming-diarization/` with
`AGENTS.md` method norms. It closes ADR-0002 §7's own caveat ("clean read speech - replay a real
conversational recording"). **These numbers are real conversational audio, not fixtures, and they
outrank the LibriSpeech figures wherever the two disagree.**

- **album+sweep on 9 golden interview clips: 95.2 % mean, 87.4 % worst clip; every 3-minute clip
  >= 97.4 %.** Against LibriSpeech's 99.26 % and production's 66.4 %. The drop from fixture to real
  audio is expected and still clears ADR-0002's 90-95 % bar.
- **The terminal (session-end) sweep is load-bearing** - confirmed on real audio, not inferred.
- **Merge threshold 0.70 is safe**: the maximum real cross-speaker centroid similarity measured is
  **0.259**, so the 0.70 merge gate has wide margin on real voices.
- **`min_match_score` 0.5 caps real-audio accuracy at 90.7 % mean; 0.35 reaches 95.2 %.**

**Phase N decision (recorded per the operator's instruction): the calibrated matcher is
`min_match_score` 0.35 / `min_match_margin` 0.1, and the justification is now real-audio measurement
rather than fixture measurement.** Supervisor check on the deployed host, 2026-07-29: the live
manifest already reads `{"max_speakers": 16, "min_match_margin": 0.1, "min_match_score": 0.35}` -
candidate 63 shipped it with the Phase N merge at `7a4f59c`. So this decision **confirms** the
deployed value rather than changing it; the 90.7 % figure prices the pre-recalibration configuration
and is the strongest evidence yet that candidate 63 was necessary. **Do not "recalibrate" again -
verify the manifest reads 0.35/0.1 and record that it does.**

**Adopt the real corpora in the F-certification distinct-voice harness, alongside TTS** (operator
instruction). Provisioning is in `prototypes/streaming-diarization/README.md`: `data/real/` holds
`benchmark_diarization_1min` and `calibration_diarization_3min`, fetched from
`ga0@m4mbp:/Users/ga0/Desktop/AI_Projects/LiveTranscribe/data/`. Candidate 51's harness currently
speaks TTS through the Mac's output; real corpora give the label clause material that TTS cannot,
and they do **not** remove candidate 51's hardware limit - the built-in microphone still cannot hear
a second voice across the room, measured six times. Play them into the lanes rather than the room.

### Phase Q - the birth floor, the stop, the RTF gate, the cadence (2026-07-29, ninth amendment)

**AUTHORIZED: candidates 55, 60, 64 and the cadence fix.** Candidate 65 is **withdrawn** - both
sweeps publish on the deployed service; the two "it never runs" readings were blind instruments.
Read `scripts/ralph-afk/authorization-request-55-60-65.md` **with its iteration-7 correction banner**
before starting, and do NOT re-argue 55's mechanism from the record: it was corrected twice and is
now measured on the deployed service.

69. **Q1 - the birth floor, at the album's admission (1.0 s of embedded speech).** `[LANDED ON THE
    BRANCH - iteration 21. NOT merged, NOT deployed.]` The operator took option 1 on the
    supervisor's recommendation.
    **The rule, as implemented: a birth must be enrollable.** Evidence too short to become a
    *reference* is too short to create the speaker that would hold one. That is ADR-0002's
    matching-is-not-enrollment asymmetry applied to the one path it never covered - the album made
    a fragment unable to *overwrite* a prototype and left it able to *mint* one.
    **Where the threshold lives, and why not in this module.** `BoundedCausalIdentityPreparer` owns
    what a deferral *means*; the number is the album's own `admission_seconds`, read off the album
    through a new optional provider capability `birth_deferrals(span_id, candidates)` asked for by
    name exactly as `take_identity_revision`/`finalize_identity` are. So the birth floor and the
    enrollment floor are **one number by construction** - a manifest that states
    `album_admission_seconds` moves both, and there is no second constant to drift. **A stack with
    no album defers nothing**: that is `NoLiveSpeakerEvidence`, every test double, and the
    `policy="overwrite"` measurement baseline, which must keep measuring the album rather than the
    floor.
    **Per speaker, not per span.** A deferred local publishes `UNATTRIBUTED_SPEAKER` while a matched
    local in the same span keeps its label; an abstain would drop a label the session had every
    reason to write. `revise_labels` already exempts `S00` from its collision rule, and the
    coordinator already carries `local_speakers` on the *prepared* path, so a deferred unit stays
    addressable by a later sweep with no further change. Diagnostics gain
    `deferred_births=S02=0.500`, seconds included, so a voice the encoder was never asked about
    (0.000) is distinguishable from one that missed admission by a tenth.
    **MEASURED, production objects, `tests/live_identity_accuracy.py`** (control = the capability
    removed, which reproduces every pre-patch digit): canonical speakers **16 on all eight meetings
    -> 2,2,4,3,4,4,7,6** for true k of 2,2,3,3,4,4,6,6; live accuracy **93.44 % -> 99.13 %**; swept
    **99.26 % -> 99.65 %**; `policy="overwrite"` unchanged at **72.02 %** (the control that proves
    the floor is album-scoped). **The 16-speaker cap stops binding entirely** - `max_speakers=64`
    is now byte-identical to 16 on every meeting.
    **MEASURED ON REAL CONVERSATIONAL AUDIO** (`prototypes/streaming-diarization/proto_real_replay.py`
    `--` bench extended with `simulate(birth_floor=)`; 9 golden interview clips): canonical speakers
    **3.56 -> 3.00 mean, worst clip 5 -> 4**, and album+sweep accuracy **95.2 % mean / 87.4 % worst
    clip, identical on every clip**. The "a 1.0 s floor starves labelling on messy turns" risk did
    **not** materialise. Two limits, both conservative: the bench cannot represent the
    never-embedded case (so 3.56->3.00 is a **lower bound**), and 60-180 s clips never approach the
    16-speaker cap, which is why the *accuracy* gain the LibriSpeech 600 s meetings show cannot
    appear there. Residual over-birth survives on 4 of 9 clips - the floor bounds the *unenrollable*
    births, not all of them.
    **Which number governs, under the ninth amendment's item (e).** Real audio outranks the fixtures
    wherever they disagree, and here they disagree on **magnitude, not direction**: both say the
    canonical count falls and no correct label is lost; only LibriSpeech shows an accuracy gain,
    because only a 600 s meeting saturates 16 speakers and pays the capacity-abstain cost. So
    **quote 3.56 -> 3.00 with accuracy unchanged as Q1's headline** and treat 93.4 -> 99.1 as what
    the fix is worth *on a meeting long enough to saturate* - which is what F3 is, and what F1 is
    not.
    **The amendment's first consequence needs one correction, and it is not cosmetic.** "Deferred,
    not lost - the ledger retains it, a sweep relabels it" is true only **above the 0.5 s evidence
    floor**, where a vector exists to retain. Below it nothing was embedded, nothing reaches the
    ledger, and no sweep can ever relabel those words: they publish `S00` and stay `S00`. That is
    the correct outcome - there is no evidence to identify with - but it is *not identifiable*,
    not *deferred*. Say it that way.
    **Second consequence, checked and found sound:** no evidence contradicts reading ADR-0002's
    "birth semantics unchanged" as constraining the album. `live_identity_album`'s own docstring
    says the provisional tier exists *because* "a speaker born from a 0.6 s span would have no
    reference at all" - i.e. the album was written to compensate for this defect, not to bless it.
    **A live consequence of that:** with the floor at admission, every birth now carries an
    *admitted* exemplar from its first span, so `PROVISIONAL` is unreachable on the live path. Left
    in place deliberately as the guard that keeps the two numbers safe if a deployment ever
    decouples them - see candidate 74.
    Measured wrong, do not re-propose: raising `max_speakers`; lowering `min_segment_samples`. And
    now measured wrong too: the **weaker "any embedded speech at all" floor** (admission 0.01) gives
    canonical **6.25 mean against 4.00** and lower accuracy - option 1 beats it on the corpus, which
    is the choice the operator made without this number.
    **Coverage (Q5's first half, done):** nine red-before/green-after nodes proved by two semantic
    reverts - `del WeSpeakerLiveEvidenceProvider.birth_deferrals` (6 red) and
    `_deferred_births -> {}` (3 red). Two further nodes deliberately stay green under both reverts:
    a short span is still *labelled*, and a provider without the capability births as before.
70. **Q2 - the decoder-RTF gate definition (candidate 64).** `[DONE - iteration 22. Loop tooling
    only; no product source, no `macos/`, no host, no session, so the Swift half of the gate is
    still untouched.]`
    **The floor is 0.13 s and it is DERIVED, in four independent readings** over a corpus of
    **1361 spans from five real certification directories on two builds** (`42abc5a` and the
    deployed `7a4f59c`). `scripts/ralph-afk/rtf-floor-probe.py`, rc=0, **9/9**, reproduces every
    number; the constant itself lives once, in `live-canary-clauses.py`'s `RTF_FLOOR_SEC`, and the
    probe **imports** it rather than restating it, so an edit is caught rather than drifting.
    - **(1) ARITHMETIC.** `elapsed = C + W(duration)`, so `RTF = C/duration + W/duration`: the
      first term is an artifact of the denominator. The fastest decode ever observed is
      **0.0564 s**, so no span at or below that can read RTF < 1 whatever the decoder does.
    - **(2) EMPIRICAL - this is the reading that fixes the value.** All **15** spans shorter than
      0.130 s read RTF >= 1 (range 1.112-5.735), and the **shortest span that ever read RTF < 1 is
      exactly 0.130 s** (elapsed 0.1184, RTF 0.911). Below it the ratio has never discriminated;
      its verdict is a restatement of the span's length.
    - **(3) DOMINATION.** Theil-Sen over the pooled spans: `elapsed = 0.0827 + 0.0890 * duration`,
      so fixed overhead is the **majority** term - the amendment's own parenthetical - right up to
      **0.930 s**. The floor is **7.2x** more conservative than the criterion would allow.
    - **(4) INSENSITIVE.** Across 25 floors spanning 0.0564-0.930 s **every one of the five runs
      keeps the same verdict**. The value is not load-bearing, which is what makes "chosen to
      pass" impossible: the weakest defensible floor already does the whole job and the strongest
      buys nothing.
    **Which reading governs, because "conservative" alone is ambiguous and this cost a rewrite.**
    Conservatism chose the **empirical boundary over the domination point** (0.13 against 0.93) -
    that is the whole of its work. It is **not** a licence to sit *below* the boundary: a 0.06 s
    floor would leave in the 0.111 s and 0.120 s spans that also never discriminated, which
    under-applies the definition rather than applying it carefully. **The probe fences both
    directions** - at 0.0 two checks fail, at 0.93 three fail, and **only 0.12-0.13 passes all
    nine**.
    **The exclusion cannot be silent, in three ways.** The excluded count, share and RTF range are
    inside the verdict **sentence**, so a verdict quoted anywhere carries them; the unfiltered
    p95 is still printed "for the record"; and a new **aggregate RTF** clause is gated beside the
    p95 - total decode seconds over total audio seconds across **every** span, nothing excluded -
    which is the throughput claim no exclusion can touch (0.177-0.247 on the five runs, an order
    of magnitude under the gate).
    **The guard is a sample size, not an exclusion share, and the share cap was WRONG.** A 5 %
    cap was written first and made F1 it.30 UNDECIDED at 3 excluded spans of 52 (5.8 %) - a run
    with 49 gated spans that plainly *can* answer the clause. That is candidate 57's own defect
    ("a verdict word must name the thing it decides") re-committed. Replaced by
    `RTF_MIN_GATED_SPANS = 20`, derived from the estimator: below 20 a nearest-rank p95 **is** the
    maximum wearing a percentile's name. It moves no run (smallest gated population 46).
    **Effect on the record, stated rather than hidden:** the definition turns **exactly one** run
    from RED to GREEN - F1 it.30, p95 **2.365 -> 0.580** over 49 spans, 3 excluded - and leaves
    four unchanged (F1 it.6 0.911->0.842, F2 0.577->0.568, F3 it.12 0.568->0.553, F3 it.9
    0.546->0.546, nothing excluded). A rule that re-coloured several runs at once would be a
    filter wearing a definition's clothes; the probe asserts it moves at most one.
    **Why not per-run self-calibration** (tried and rejected): the same robust fit applied to each
    run *alone* puts `C/m` between **0.590 s and 2.007 s**, because a 60 s canary has ~50 spans
    and the fit follows whichever runaway decodes it happened to see. A self-calibrating floor
    would move with the noise it exists to be immune to.
    **Coverage, red-before/green-after by semantic revert:** `--rtf-floor-sec 0` restores the
    pre-Q2 verdict exactly (F1 RED at 2.365) and drops the probe to **7/9**; `--rtf-floor-sec
    0.93` drops it to 6/9. Both UNDECIDED paths are exercised - all-spans-below-floor
    (`--rtf-floor-sec 3.0`, above the 2.5 s hard cap) and too-few-gated (a 25-span fixture with 5
    above the floor) - and so is the duration-unknown branch, where a span from an older event
    schema is **COUNTED, never excluded**.
71. **Q3 - the cadence fix, both halves or neither.** `[LANDED ON THE BRANCH - iteration 23. NOT
    merged, NOT deployed.]` `portalCycleSeconds` moves the number and no request rate;
    `pollDelayMs` moves the browser's wait and the number by 0.0 ms. Moving the Swift one alone
    relaxes the gate while looking like a remedy - forbidden.
    **The value decision, recorded before the patch as the fifth amendment's shape requires: 1.0 s
    -> 0.5 s on BOTH halves**, i.e. the plan's own **second** ordered latency remedy, applied in the
    one form the PRD's Constraints permit. Remedy 1 (2.0 s span cap) moves `hard_cap_samples`, which
    prd.md declares a **domain-contract value**, so the loop cannot take it under any reading;
    remedy 2's portal poll is absent from that list, term by term (the probe's section 4 asserts
    this, and *"pump interval 0.5 s"* in the list is the client's frame tick, a different quantity
    that happens to share the number). Worth **exactly -500.0 ms** on the gated sum, which takes F1
    from **4150.8 -> 3650.8** against its 4000 ms gate (**3.3x** the 150.8 ms miss) and moves F2 and
    F3 further inside their 6000 ms one. **The cost is a real browser's request rate doubling** -
    `schedulePoll` fires that long *after* both fetches complete, so cycles cannot pile up, and the
    two endpoints are incremental (`since_version` / `since_seq`). F1/F2/F3 open no browser, so a
    re-run records the full -500 ms and leaves the viewer cost unpriced: **the gate under-counts the
    cost, it does not over-count the benefit.** Say that when quoting the re-run.
    **The enforcing node - the durable part, and it is TWO nodes because one is not enough.** A node
    on either side alone leaves the other language free to move: the Swift half
    (`CaptureControllerTests.testPortalCycleContractMatchesTheServedPortalCadence`) reads
    `live_portal.py` from the checkout and compares the **reported** `portalCycleMS` - not the
    constant - against the served `pollDelayMs`; the Python half
    (`test_live_portal_poll_cadence_and_the_app_render_bound_are_one_number`) renders the **served**
    page through `TestClient`, reads the Swift constant, and additionally asserts the render bound
    is still **built from** the constant rather than from a literal. Both also assert
    `schedulePoll(pollDelayMs)` is what schedules, because a constant nothing reads would satisfy an
    equality check while the page polled at any rate at all.
    **Red-before, four directions, by temporary semantic revert with guaranteed restore** (backups
    in `/tmp/i23-*.bak`): Swift constant moved alone, portal constant moved alone, cadence declared
    but not scheduled, render bound built from a literal - **each fails the Python node**, and the
    first two fail the Swift node as well (`XCTAssertEqual failed: ("500.0") is not equal to
    ("1000.0")`). Python **809 -> 810**, Swift **158 -> 159**, 0 failures, 0 warnings on a fresh
    scratch.
    **`latency-remedy-probe.py`'s section 3 is INVERTED, and the inversion is the evidence.** Its
    four "nothing ties them" checks asserted the **defect**; a probe that keeps asserting a defect
    exists is a probe asserting the fix did not land. They now assert the tie, plus a new check that
    both halves read 0.5 s so *neither alone* can pass. `git show dafcae1 --
    scripts/ralph-afk/latency-remedy-probe.py` is the pre-fix reading. Two scoping repairs went with
    it, both narrowing a claim to what it always meant: *"pollDelayMs appears nowhere in the
    measurement path"* now reads **code** lines under `Sources` only (the constant's doc comment
    names the server's copy on purpose, and a doc comment is not a read), and the self-comparison
    check is inverted rather than deleted.
    **Considered and declined:** documenting the cadence in ADR-0001/CONTEXT.md beside the 5 s drain
    and the two 10 s timeouts. That fence covers *documented* constants and adding one is a doc
    review this amendment does not scope; the tie is enforced from both sides in code instead.
    **Also declined, and it is the deeper fix if this ever drifts again:** serving the cadence in
    `/api/live/descriptor` and having the probe read it, so there is one number rather than two and
    an enforcing node becomes unnecessary. That is a product contract change on both sides and needs
    its own authorization.
72. **Q4 - a clean stop must reach the server (candidate 60).** `[LANDED ON THE BRANCH -
    iteration 24. NOT merged, NOT deployed, and NOT on the installed app.]` The route works and the
    portal's Stop calls it; the Mac client did not, so view authority outlived a clean stop by up to
    the 30 s lease (29.4 / 29 s measured) and the session's final sweep never ran.
    **The seam: a third adapter, not a third method on an existing one.** `CaptureSessionStopAdapter`
    sits beside `CaptureTransportAdapter` and `CaptureHealthAdapter` for the reason those two are
    separate from each other - one endpoint, one seam - so "this stack publishes frames but cannot
    end a session" is a **wiring fact a test reads** rather than a behaviour to be inferred.
    `CaptureHTTPSessionStopAdapter` posts `{"deadline": 5.0}` to `.../stop` on the same pinned
    client the frames and heartbeats share.
    **Optional on the controller, and the hazard that creates is answered directly.** A required
    parameter would have edited ~20 existing constructions for nothing; the price is that a shipped
    stack left unwired would compile and silently do nothing. That is exactly the "known but not
    shown" shape this loop keeps finding, so the existing production-wiring node
    (`testProductionPumpTicksOncePerCanonicalWireFrameOnOneSharedPinnedProvider`) now also asserts
    `sessionStop: CaptureHTTPSessionStopAdapter(` appears in `main.swift` and that it is handed the
    one shared provider. Direction D of the red-before ladder is that node, failing.
    **Ordering, decided: after the final drain.** The meeting's last partial frame only exists once
    the source has flushed, and a server told to stop while frames are still unconsumed spends its
    whole drain deadline waiting for them (measured once already: `{"deadline": 0.0}` with queued
    work answers 409 `stop deadline expired with unresolved work`). The node reads the *transport's*
    published count at the moment the stop is sent - 1, not 0 - so the ordering is asserted rather
    than commented.
    **Both numbers are the portal's, not this client's.** `CaptureStopContract.drainDeadlineSeconds`
    5.0 and `requestTimeoutSeconds` 10.0 are the `/stop` route's two documented control timings
    (ADR-0001, CONTEXT.md, `tests/test_live_portal.py:319,505`). One node reads `live_portal.py`
    from the checkout and compares both. **Only ONE node, where Q3 needed two**, and the difference
    is the reason: the portal's constants are already pinned on the Python side by tracked tests, so
    Swift is the only side a drift can enter from. It also asserts `timeout > drain`, because a
    request that expires before the drain it asked for would report every clean stop failed.
    **The failure rule (fifth amendment): a stop that cannot reach the server still stops locally.**
    Every failure is swallowed - the capture is already off and the audio already drained, so
    rethrowing would report a failed stop for a meeting that ended either way and leave
    `alreadyRunning` refusing the next one. What a failure *may* change is the report: a refusal is
    recorded, so `status` says the session was already gone. The node asserts the next `start`
    succeeds, which is the operator-visible half. **It is attempted even when a refusal is already
    on record** - a client cannot know what the server holds, and assuming it could is the whole of
    this defect; the cost of being wrong is one request that answers 403.
    **Coverage: five Swift nodes, six red-before directions, each naming a different node** (see the
    fence). **The server half needed no new node** - `tests/test_live_api.py:503` already drives
    capture-bearer -> `/stop` -> view 401, and `CAPTURE_ACTIONS` carries `"stop"`.
    Swift **159 -> 164**, 0 failures, 0 warnings on a fresh scratch; Python **810**, unchanged and
    correctly so. The Darwin tracer stays 4 passed / 0 skips - on MacStudio it takes the
    `permissionDenied` branch, where `stop` throws `notRunning` before any transport call, **so the
    tracer proves nothing about this item**.
    Buys neither convergence nor `identity_finalized`.
73. **Q5 - close the coverage gap, then gate/merge/redeploy.** Nothing asserts what a canonical
    speaker was born from. Red-before/green-after per decision, plus a node that fails if a birth
    can be minted from a span with no embedded evidence. Then the full gate, the accuracy harness
    showing the birth floor's effect on canonical count, **F1 and F3 re-run**, one merge
    (`expected_main` is `7a4f59c` -> advance in-script), push, redeploy.
    **THE REDEPLOY HAS TWO HALVES THIS TIME, AND THE SECOND HAS NOT BEEN NEEDED SINCE M6c.** Q3 put
    `CaptureLatencyProbe.swift` in the payload, so the server checkout is not enough: **m4mbp needs a
    rebuild + reinstall** or the app keeps reporting a 1000 ms render bound and F1 measures the
    remedy at 0.0 ms. Re-check both TCC grants after it. See the install block in Deployed reality.
    **Q1's half is done (iteration 21):** the birth node exists, nine nodes are red-before by
    semantic revert, Python is **809 passed / 2 skipped / 368 subtests** (was 801), and the harness
    number the gate asks for is recorded in candidate 69. **Q2's half is done (iteration 22):** its
    coverage is `rtf-floor-probe.py` (9/9, two-sided fence) rather than a `tests/` node, because Q2
    changed only loop tooling - Python's 809 is therefore **unchanged and un-re-run**, correctly.
    **Q3's half is done (iteration 23):** two enforcing nodes, one per language, each red-before in
    four directions by temporary semantic revert; Python **810**, Swift **159**, 0 warnings on a
    fresh scratch. **Q4's half is done (iteration 24):** five Swift nodes, six red-before directions,
    Swift **164**, Python **810** unchanged, tracer 4/0. **ALL FOUR PHASE Q ITEMS ARE NOW ON THE
    BRANCH, so what remains of Q5 is the gate itself** - full Swift/Python (both re-run clean this
    iteration), the accuracy harness's canonical-count number, **F1 and F3**, one merge, push,
    redeploy including the m4mbp rebuild+reinstall.
74. **`PROVISIONAL` is unreachable on the live path now that Q1 has landed** `[open, no
    authorization needed to decide, product change would need one]`. The album's second tier holds
    exactly one sub-admission observation *while a speaker has no exemplars*; with the birth floor
    at admission, every born speaker is admitted from its first span, so the branch cannot be
    reached. Left in place this iteration - it is the guard that makes the coupling safe if a
    deployment ever states a birth floor below `album_admission_seconds`, and removing it is a
    second change. **Decide before Phase Q's merge whether it is defence-in-depth or dead code**,
    and if it stays, say in `live_identity_album`'s docstring that it is now reachable only through
    a decoupled configuration. `tests/test_live_identity_album.py` still covers it directly, so the
    branch is tested even though the live path no longer reaches it.
75. **A manifest whose span cap is shorter than `album_admission_seconds` can never birth a
    speaker** `[open, found in iteration 21, no gate sees it]`. The two numbers are unrelated in
    the admission checks, so a bundle declaring `hard_cap_samples` 160 (0.01 s) and the default
    1.0 s admission produces a live session that publishes every word under `S00` and reports
    nothing wrong. It was found because exactly that configuration is what
    `tests/test_live_provider_bundle.py`'s shared `_manifest` declares - two nodes flipped to
    `S00` - and it was answered there by making the manifest state `album_admission_seconds`
    0.005, which is the honest fix for a test bundle and **not** a fix for the hazard. The
    deployed manifest is safe (2.5 s cap against a 1.0 s admission) and this is therefore not
    urgent, but the guard belongs in `_validate_bundle` beside the existing
    `min_segment_samples` check. Product source; needs an authorization.

Out of scope, worth its own authorization later: ADR-0002 step 4, batch unification - the album
engine measured **100 %** on the batch path where the shipped resolver scores **80 %**, and batch's
disabled Tier-B moves the score by **zero**.

## Non-candidates

- **The RTX 4090.** The operator fixed the 4070Ti as the target; the 4090 is committed elsewhere.
- **Resuming the governed `aisight-coding-loop`.** Its `.stop-after-current-role` sentinel stays;
  two autonomous writers would interleave branches and promotions.
- **Provisional/partial decode.** Measured decode makes span-cap tuning sufficient;
  `begin_provisional`/`publish_provisional` stay test-only.
- **Server-side resampler rework.** Phase-B conversion makes the mixer grid 1:1,
  so the linear-interpolation path stops mattering.
- **Durable transcript persistence, export, speaker rename/merge, search, browser-initiated
  capture start, linking `/live` from the batch UI.** Post-MVP.
- **Developer ID, notarization, Gatekeeper or SIP changes.** A local self-signed identity is
  proven sufficient.
- **Windows client / IDEA-041.** Deferred until the Mac path is certified.
- **Intermittent-speaker identity calibration (CTR-043 / IDEA-027).** A pre-existing batch quality
  issue, not a live blocker.
- **30-minute live soaks.** Certification is 60 s, 300 s, and one 16-minute active-view soak.
