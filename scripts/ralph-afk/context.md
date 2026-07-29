# Context - MOSS live meeting transcription MVP

> **Compacted in run `20260728-181020` iteration 10 (candidate 52).** The pre-compaction file —
> every per-iteration gate transcript, every contract block in full, every redeploy record and every
> closed-phase candidate list, **verbatim** — is appended to `progress.txt` under the banner
> `ARCHIVE OF context.md AS OF RUN 20260728-181020 ITERATION 10`. Nothing was deleted. Any block
> named in the two indexes below is findable by grepping `progress.txt` for its title, e.g.
> `grep -n "Span-cap authority contract" scripts/ralph-afk/progress.txt`.
> **Keep this file compactable:** new evidence goes in as the *conclusion plus the numbers that
> justify it*; the full transcript belongs in progress.txt when it is written, not later.
> *Measured, so the next reader does not have to guess:* **339 018 → 129 832 bytes** (3985 → 1509
> lines) at the compaction. The Read tool's binding limit is **tokens, not bytes** — 25 000 tokens ≈
> **51 KB** of this file's prose — so it became **three sequential `Read`s with no searching**, not
> one. Going to one `Read` would mean cutting the Validation fence or the live F1/F3 evidence; that
> is a deliberate trade, not a free win. See candidate 52.
> **Drift since, measured in iteration 20: back up to 194 236 bytes / 2256 lines** — i.e. ~1.5× the
> compacted size in ten iterations, or about **four** `Read`s. It grew despite each iteration's block
> being written as conclusion-plus-numbers, so the growth is *cumulative blocks*, not verbose ones.
> The cheapest correction available now is retiring superseded blocks rather than trimming live ones:
> once F1 and F3 pass against `77e0014`, the F1/F3 diagnosis blocks and the Phase L/M mechanism
> narratives become history and belong in progress.txt. Do that at that moment, not before.
>
> **Second compaction, run `20260728-181020` iteration 30 (candidate 52 again).** By then the file
> had reached **257 135 bytes / 2977 lines** — five sequential `Read`s. The trigger above was met in
> substance, so **twenty** superseded blocks (K5d, the F1 and F3 diagnoses, the whole Phase L/M
> mechanism narrative, the three D-c measurement blocks, the merge and redeploy records) went to
> progress.txt **verbatim** under `ARCHIVE OF context.md SUPERSEDED BLOCKS — RUN 20260728-181020
> ITERATION 30`, replaced by the "Retired evidence — index" table below. *Not literally the recorded
> trigger:* F1 did **not** pass — it was cut short by candidate 56, a different and newly found
> defect. What the trigger was for did happen: iteration 26 proved 53/48/49/D-a/D-c work on the real
> hosts, so the blocks that diagnosed those defects are history. **Measured: 257 135 → 183 529 bytes
> (2977 → 2081 lines), −28.6 %**, i.e. five `Read`s down to four. Reaching two would still mean cutting
> the Validation fence, which is unchanged and still load-bearing.
>
> **Third compaction, run `20260729-025318` iteration 14 (candidate 52 a third time).** The file had
> drifted back to **245 562 bytes / 2693 lines** — five `Read`s again. **26** superseded blocks went
> to progress.txt **verbatim** under `ARCHIVE OF context.md SUPERSEDED BLOCKS - RUN 20260729-025318
> ITERATION 14`, and this time the cut reached the two places the earlier passes declared off-limits:
> **eleven ranges of the Validation fence** (every closed phase's per-node `--filter` recipe and every
> spent one-time host recipe — E1/E2b/E3, D1/K5c/J5c/H4c/E2a/D3, the superseded F1 driver) and the
> **Phase L/M/P candidate lists**. What was kept is what a *future* run needs: the full gate, the
> probes, the three drivers, the reducers, the two redeploy templates, and the live F1/F2/F3
> evidence. **Measured: 245 562 → 148 157 bytes (2693 → 1540 lines), −39.7 %** — five `Read`s to
> three (the Read tool reported this file at **101 131 tokens** before the cut, ≈ 2.43 bytes/token,
> so 148 KB ≈ 61 k tokens against the 25 k cap). *Verified, not assumed:* all 26 archived bodies were
> checked to appear byte-for-byte in the pre-compaction file **and to be absent from the new one**,
> and the surviving fence still passes `bash -n` (414 lines).
> *The retirement trigger for the NEXT pass, recorded now so it is not re-argued:* the F1/F2/F3 green
> blocks and the candidate-60 block are the only large live evidence left, and they retire when their
> PRD clauses are closed by a later run — not before. After that, the next cheapest cut is the
> "Gates, merges and redeploys" index, whose closed-phase rows are already summarised elsewhere.

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
G, H, J, K, M, P). **Seven keeper merges have been made and all seven are spent** — `f9285d6` (C4),
`317df4d` (G5), `b817871` (H4), `6a540fe` (J5b), `fc7097d` (K5b), `77e0014` (M6, iteration 19),
**`42abc5a` (P7, run `20260729-025318` iteration 4)** — and `merge-keeper.sh`'s `expected_main`
guard now refuses an **eighth** (rehearsed non-vacuously: `main moved from expected pre-merge SHA
77e0014…`, rc=1). **Phase P's product work is merged, published and DEPLOYED to all four checkouts
at `42abc5a`** (run `20260729-025318` iteration 5), so the branch carries no unmerged tracked
product source. Every tracked product change since `f9285d6` was made under a named
amendment. Per-phase detail is in the closed-phase index below and in full in the progress.txt
archive.
**One non-Ralph commit is on the branch.** `00620ab` *"docs: streaming diarization design +
ADR-0002 (two-tier, fingerprint album)"* was authored by **AlphaSightInc** at 03:23:50Z on
2026-07-29 — i.e. the operator committed to the feature branch **while iteration 5 was running**, and
the branch tip moved under the loop. It adds two files under `docs/` and **no product source, no
test and no `ops/`**, so it changes nothing this loop has measured and nothing the service reads. It
is why `git diff --name-only 42abc5a HEAD -- ':!scripts/ralph-afk'` now lists
`docs/adr/0002-two-tier-diarization-fingerprint-album.md` and `docs/design-streaming-diarization.md`
instead of being empty. **Do not revert it** and do not treat it as loop drift; do re-check the tip
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

**PRD acceptance scoreboard (rows unchanged since iteration 9 except where noted; Phase M's local
gate is green at `21a73ea`, the sixth merge landed as `77e0014` in iteration 19, and **it is now
deployed to all four checkouts (iteration 20)** — so the two certification rows are RED-and-stale
rather than RED-and-current: F1 and F3 have never run against Phase M.)**

| clause | state |
| --- | --- |
| IDEA-044 compatibility checkpoint | GREEN, frozen at `1ede498` (10/10 and 16/16, 11 commands, 0 Darwin skips) |
| Production client gate | GREEN (B6 `3fb5567`, re-gated G4 `23dc163`, K5a `cd7faf9`) |
| Server meeting-reliability gate | GREEN at `f400d426`, clause→node map recorded |
| One reviewed keeper merge (+ 6 authorized follow-ups) | GREEN, seven merges, each reviewed against its amendment's scope |
| One exact SHA everywhere | **GREEN — 4/4 at `42abc5a`** (run `20260729-025318` iteration 5). Local `main`, `origin/main`, the server checkout and the m4mbp checkout all print `42abc5aec2d2ec6b8f72aa9af307a4e8ff4ef870`. |
| Live service answering | GREEN — `/live` and `/api/live/descriptor` 200 over the pinned leaf from MacStudio **and from m4mbp** |
| Batch service unharmed | GREEN — `http://192.168.68.38:7860/` and `/api/jobs` 200; batch MainPIDs never restarted |
| Signed app installed | GREEN — and "DR unchanged across a rebuild" proven *across an actual rebuild* in K5c |
| Permissions granted | **GREEN** — both TCC grants `auth_value=2`; `mtd-capture status` reported both lanes `capturing` through a 672-frame meeting (K5d) |
| Rollback rehearsed and recorded | GREEN (F4a) |
| 60 s canary (F1) | **GREEN on `42abc5a`** (iteration 6, `live-canary-clauses.py` rc=0): user-visible p95 **3909.3 ms** ≤ 4000 **and qualified**, decoder p95 RTF **0.911** < 1, 329 published == 329 accepted all 200, 370/370 view polls 200, no lane fault. **One half is NOT certified:** "two speakers" were both on the *system* lane — the microphone carried room noise only (candidate 51's recorded harness limit). See the F1-green block. |
| 300 s certification (F2) | **GREEN on `42abc5a`** (iteration 11, `live-canary-clauses.py --interrupt-report` rc=0): six GREEN, no RED, no UNDECIDED. user-visible p95 **3859.6 ms** ≤ 6000 **and qualified**, decoder p95 RTF **0.670** < 1, **1257 published == 1257 POST /frames, and every one of the session's 4748 HTTP requests answered 200**, a **5.050 s** interruption seen by the client and survived, outbox 0 → **10** → 0. **One half is NOT certified and was deliberately not attempted:** the separate mic-granted / system-audio-denied run, which would spend a TCC grant. See the F2-green block |
| 16-minute soak (F3) | **RAN AGAINST `42abc5a` AND FINISHED ITS WHOLE PLAN (iteration 9) — 5 clauses GREEN, 1 RED.** Candidate 53's minute-14.6 death is gone: 17/17 full minutes, every poll 200, view authority live at age 1024 s. The RED is **new candidate 60** — a clean stop does not revoke view authority, because no client code path calls the server's `POST …/stop`. `live-canary-clauses.py` rc=3. See the F3 block. |
| Secret hygiene | static half green; run-time half green in F1 and F3 as far as those runs went |
| Final close (F4b) | open |

**What stands between the loop and the bar (rewritten iteration 30; the Phase M narrative it used to
carry is in the retired-evidence index below).**
- **THE SEVENTH AUTHORIZATION WAS GRANTED, and Phase P's code half is DONE (run `20260729-025318`
  iteration 1).** Candidate 56 — a live session stops being viewable mid-meeting because the server
  host's wall clock steps ~1.5 s backwards every ~32.3 s and a negative `elapsed_sec` was terminal —
  is **fixed in source**: P1 (the decode measures itself monotonically), P2 (untrustworthy timing
  metadata degrades to null and is logged, stated once as a conversion), P3 (four real-seam nodes,
  red-before proved per half) and P4 (the class swept: three sites fixed, one ruled deliberate).
  Python 608/2/368 green. See the Duration-vs-timestamp row in Shipped contracts, the Phase P gate
  and P7 merge rows in the gates index, and the retired Phase P list in progress.txt.
- **PHASE P IS FULLY LANDED and its gate step (d) IS RUN, both halves.** (a) gate green at `5bc4f7f`,
  (b) seventh merge `42abc5a`, (c) published and deployed 4/4, **(d) F1 GREEN (iteration 6)** and
  **F3 RUN TO COMPLETION (iteration 9) — 5 GREEN, 1 RED**. The same is true of Phase M's gate steps
  (a) `21a73ea` / (b) `77e0014` / (c) deployed / (d). **What Phase M and P set out to fix is proven
  fixed:** candidate 53's minute-14.6 death did not recur, candidate 56 did not fire in 17 minutes,
  D-c capped 67 of 443 spans and RTF p95 was 0.546. **What now stands in front of Phase N is one new
  defect, candidate 60**, and the decision of whether the F3 clause it fails is worth an eighth
  authorization before identity work. See the F3 block and candidate 60.
- **ITERATION 8 OF THIS RUN LEFT NO RECORD AND NO COMMIT.** It launched the F3 soak at 03:52:58Z
  (label `ralph-i7-f3-…`, so it reused iteration 7's pre-recorded rollback block) and then died —
  context, timeout or crash, nothing says which. Iteration 9 found the driver still running at
  minute 6 and let it finish; this is why the F3 evidence exists at all. *The durable lesson:* the
  soak driver is `nohup`'d on m4mbp by design, so **it survives the iteration that started it** —
  before concluding a host is idle, `ps -eo pid,etime,command | grep live-soak`. Killing it would
  have thrown away 17 minutes of the loop's last uncertified gate.
- **Phase M's product work is PROVEN on the real hosts** (iteration 26, two F1 re-runs against the
  deployed `77e0014`): 53/48 kept the heartbeat alive through **165 × 200** ticks with a permanently
  failing publish, D-a/49 produced **no lane fault at all**, and D-c took the committed p95 from
  8343–9148 ms to **2567/2592 ms**. Neither run is a qualified latency measurement — both were cut
  short by candidate 56 and `sufficientSamples` is false in both.
- **Candidate 55 — identity capacity saturates in the first minute** (iteration 12; **reproduced in
  iteration 6's GREEN F1**). The 16-speaker bound is reached at t+45.5 s / t+51.8 s / **t+65.6 s**,
  so a voice arriving later can never be labelled. Iteration 6 named its consumer exactly: **9 of the
  16 slots were minted by one-word `Hi.` fragments** of microphone ambient noise. Degrades quality
  without ending a session, so no gate sees it — and now demonstrably not even a passing one.
  Tracked product source; needs its own authorization, and Phase N's `N1`/`N3` may subsume it.
- **Phase N's sequencing question is CLOSED by the operator, not by the loop** (`0456177`,
  iteration 15): *"Phase N remains authorized. Take it in ADR-0002's shape, not the sixth
  amendment's."* The evidence had already emptied the gate's reason — the sixth amendment sequenced
  N after M because "identity quality cannot be certified on a meeting that dies at minute 14.6",
  and F3 ran 17 minutes with a degraded lane — but the call was the operator's and they made it.
  Candidate 60 is a **stop-time** authority-revocation defect and cannot touch an identity
  measurement taken during a meeting.
- **THE EIGHTH AUTHORIZATION LANDED, AND PHASE N IS OPEN — read `docs/adr/0002-…` first.** prd.md
  gained *"Phase N is SUPERSEDED by ADR-0002"* in operator commit `0456177`. It does **not** create a
  new fix cycle; it **re-shapes the already-authorized Phase N** and ends its "after Phase M's gate"
  sequencing question by saying plainly *"Phase N remains authorized. Take it in ADR-0002's shape."*
  The mechanism is unchanged from the sixth amendment (replacement is the defect, the album is the
  fix, injected at `canonical_embedding`, re-embedding 0..t rejected on O(T²)); the **parameters and
  the scope** change — `min_score` 0.35, margin 0.1–0.2, admission **1.0–2.0 s**, k=10, sweep every
  60 s, merge 0.70, and the album is **step 1 of 4** and *"a terminal-state failure if shipped
  alone"*. Acceptance is ADR-0002's **≥ 90–95 % live accuracy and live→file convergence**, not
  centroid stability. Two consequences the loop must carry: the ADR deliberately **changes the
  retention posture** (the server will keep meeting audio, ~0.3 GB/hr), so the PRD's *"no raw audio
  is persisted"* clause must be re-read against the ADR rather than enforced blindly; and the
  prototypes used **clean read speech**, so a real conversational recording is needed before
  production sign-off — which compounds with candidate 51's measured limit.
- **PHASE N STEP 1 (THE ALBUM) IS LANDED IN SOURCE (iteration 15) AND MEASURED (iteration 16).**
  `live_identity_album.py` + wiring, 27 nodes; then N-gate's accuracy harness, 21 nodes, Python
  **656 / 2 / 368**. Not gated as a phase, not merged, not deployed. **The album clears ADR-0002's
  bar on production code: 93.4 % mean live speaker accuracy against overwrite's 72.0 %, ≥ 90 % on
  every meeting.** Three things the measurement changed: candidate 55 costs **4.5 pp** and is *not*
  subsumed by the album; the **deployed matcher thresholds** (0.5/0.2) put the album at **75.0 %**,
  so recalibration is a shipping requirement; and the enrollment-floor instruction from the
  superseded sixth amendment is refuted — **k**, not the duration gate, is what beats overwrite.
  **ITERATION 17 CLOSED THE SECOND OF THOSE (candidate 63) IN SOURCE:** the calibrated pair is
  named once beside the album, the accuracy harness imports it instead of holding a copy, and the
  manifest finalizer now **requires** the deployment to state `--min-match-score` /
  `--min-match-margin` and hash-covers them — so the album can no longer be measured at 0.35/0.1
  and deployed at 0.5/0.2. **The host manifest still carries the old pair** until Phase N's
  redeploy regenerates it; see the N-recal block.
  See the Phase-N block below. **The branch carries unmerged tracked product source**, so
  every offline probe has stopped speaking for the deployed service until a merge and redeploy —
  see the rule under "What survives those blocks". (The harness itself is `tests/` only.)
- **F2 RAN AND IS GREEN (iteration 11).** That was the loop's one unblocked PRD acceptance clause
  and it is now spent. **Nothing measurable is left that the loop can do alone.** What remains:
  (1) candidate 60 — F3's one RED — is tracked product source under the post-merge freeze and needs
  an eighth authorization; (2) candidates 55 and 58 likewise; (3) **Phase N is OPEN and step 1 is
  landed** — this sentence's "nothing is left" reading expired at `0456177`; (4) the PRD's F2
  **system-audio-denied variant** and F1's
  "two speakers" half are both blocked on inputs the loop is forbidden to spend or has measured it
  cannot produce (see those two blocks); (5) F4b closes only when everything else has evidence.
  **Iterations 12 and 13 spent the loop-tooling half of that list entirely:** candidate 61 gave F2
  and F3 a lane-separation verdict at all, and candidate 59 made that verdict *correct* — F1 and F2
  now name their system marker instead of calling it absent. *That conclusion held for exactly one
  iteration.* `0456177` re-opened Phase N and iteration 15 spent it on step 1. **Still needing the
  operator: 55, 58, 60, the F2 denied-lane variant, F1/F2's second-voice half, F4b.
  NOT needing
  one: Phase N steps 2–4, its gate, and — read out of prd.md rather than assumed — the matcher
  recalibration (candidate 63), which the ADR-0002 supersession names in its own words and the
  sixth amendment already ruled a *free* parameter. Iteration 16 filed it as needing an
  authorization; iteration 17 re-read the contract and landed it.** The accuracy half of the gate
  was built in iteration 16; step 2 collides with the PRD's no-raw-audio clause by design (a
  decision to record before any code).
- **Candidate 57 — the clause reducer called a passing latency number RED** `[done — iteration 29]`.
  Loop tooling, no authorization; fixed and proved on four real evidence directories. See "The
  reducer stopped calling a passing number RED" in progress.txt.
- **Candidate 52 — the third compaction** `[done — iteration 14]`. With the loop-tooling queue empty
  and every product item needing an authorization prd.md does not yet carry, iteration 14 spent the
  one remaining thing the loop owns: its own working memory. **245 562 → 148 157 bytes, −39.7 %**,
  five sequential `Read`s down to three, 26 blocks archived verbatim and verified. *The measured
  reason it is worth an iteration:* loading context.md was costing every iteration five `Read` calls
  before any work began, and iterations 12–14 each paid it. Repair-from-evidence is an explicitly
  valid iteration in prompt.md, and this is the only one available while the freeze holds.
Candidates 55 and 56 are tracked product source under the post-merge freeze. **Candidate 54 is ANSWERED**
(iteration 11) and **candidate 51 is DONE** (iteration 12), neither spending an authorization: the
409 is `LiveV2SessionTerminalError` — `"v2 system lane is failed."` — armed by the client's *own*
heartbeat, **not** the `v2_out_of_order_frame` that was on record as likeliest; and the two lanes
now carry different content, which took no product change at all. See those two blocks and Phase M.

**E3 was the blocker for four runs; the clicks were necessary and not sufficient.** Both grants are
recorded and survive a bundle replacement. **Never ask the operator for those clicks again.**

**Test totals on the branch.** Swift **158 passed**
(67 → 81 → 92 → 95 → 98 → 106 → 116 → 121 → 131 → 132 → 134 → 139 → 142 → 146 → 150 → 151 → 154
→ 158); Python **662 passed / 2 skipped / 368 subtests** (604 → 608 with Phase P's four seam nodes,
→ 635 with Phase N step 1's 27, → 656 with N-gate's 21 accuracy nodes, **→ 662 with N-recal's 6,
iteration 17**) — the two
skips are the pre-existing
`tests/test_large_upload.py:155,175` Python-3.10 compatibility contract, **never** Darwin skips.
Suite wall clock **71.25 s** (was ~60 s; the accuracy harness costs ~11 s and is the only accuracy
evidence in the repo). Per-file: `test_live_pipeline_seams.py` **60**, `test_live_identity.py` **8**,
`test_live_identity_album.py` **17**, `test_live_identity_accuracy.py` **21**,
`test_live_provider_bundle.py` **28**,
`test_macos_uds_tracer.py` **4 / 0 skips**, `test_macos_packaging_tools.py` **9**,
`test_live_manifest_finalizer.py` **23** (17 → 23 with N-recal), `test_live_deployment_credentials.py` **14**,
`test_live_service_deployment.py` **30**.

## Read before any certification run or client fix

**Retired evidence — index (compacted in run `20260728-181020` iteration 30).** Twenty blocks that
diagnosed, decided or recorded Phases K/L/M were moved to progress.txt **verbatim** under the banner
`ARCHIVE OF context.md SUPERSEDED BLOCKS — RUN 20260728-181020 ITERATION 30`. Nothing was deleted:
grep progress.txt for any title below to read it in full, e.g.
`grep -n "The decode is bounded" scripts/ralph-afk/progress.txt`. **Any cross-reference elsewhere in
this file of the form "see <title> above/below" now resolves through this table.**
*The retirement trigger was recorded at the top of this file and is now met.* Every defect these
blocks diagnose is fixed, merged at `77e0014`, deployed to all four checkouts, and **proven on the
real hosts** by iteration 26's two F1 re-runs: no lane fault at all, **165 × 200** heartbeats through
a permanently failing publish, and a committed p95 of **2567/2592 ms** where these blocks measured
**8343–9148 ms**. What killed those runs is candidate 56, whose block stays below.

| retired block (grep this title) | what it settled | still carried by |
| --- | --- | --- |
| **K5d — the re-read, and the answer** (it. 7) | both lanes failed `macos_buffer_overrun`, and the cause was a client-side wedge in `CaptureController.start` — not TCC, pinning, schema or duplicate helpers | candidates 48/49; the eliminations line under the closed-phase index |
| **F1 — the 60 s canary, RED** (it. 8) | user-visible p95 10426 ms and 0.5 s of lane loss; the tail is **two** runaway spans, not a floor — which refuted candidate 43's premise | candidate 50; evidence `/tmp/ralph-f1-evidence` |
| **F3 — the 16-minute soak, RED at minute 14.6** (it. 9) | 14 healthy minutes, then a throwing publish skipped `emitHealth` and the 30 s lease ended the meeting | candidate 53; evidence `/tmp/ralph-f3-evidence` |
| **The three Phase M decisions, taken and binding** (it. 13) | D-a / D-b / D-c with the reasoning the amendment required in writing before the patch | the one-line rulings in the Phase M list |
| **The heartbeat is uncoupled from the publish** (it. 14) | 53 + 48 as one shape, three red-before/green-after nodes | Phase M list, entries 53 and 48 |
| **D-a is landed** (it. 15) | overrun → degradation, two enums, the mailbox fence removed, the mailbox overflow given its own code | Phase M list, D-a; the K2 grep rule in Shipped contracts |
| **The decode is bounded** (it. 16) | the `68 + ceil(87 × duration_sec)` cap and **how the tokens were counted** | candidate 50; the `/tokenize` recipe in the Validation fence |
| **The failed lane is in the suite** (it. 17) | the Phase M coverage gap closed, both nodes red-proved by semantic revert | the Coverage-gap line in the Phase M list |
| **The Phase M gate is green / the ORDER is settled by precedent** (it. 18) | gate (a) green at `21a73ea`; the certification order | gate step (a); the order rule below |
| **The sixth merge is made — `77e0014`** (it. 19) | both fences satisfied, payload 10 files / +983/−51, the guard now refuses a **seventh** | gate step (b); the Gates/merges index |
| **M6c is deployed** (it. 20) | 4/4 at `77e0014`, deployment proven by a witness with a control word rather than by SHA | gate step (c); Deployed reality |
| **F1's re-run is blocked on a sleeping Mac** (it. 21) | m4mbp off the tailnet; `live-canary-clauses.py` built and validated on three real directories | the Validation fence's canary recipe |
| **F3 has a repo driver now** (it. 22) | `live-soak.sh`, the pruned snapshot body, and the reducer that had been passing two red runs | the fence; `live-canary-clauses.py` §8 |
| **D-c is MEASURED on the deployed service** (it. 23) | 58/58 spans carry the product's own cap; `capped_count` 0, so it was live-but-unexercised | candidate 50 |
| **D-c's latency effect is MEASURED** (it. 24) | 8.129 s → 1.074 s, **7.571×**, on the deployed engine, reproducing F1's runaways within 4 % | candidate 50 |
| **D-c's OTHER half is settled** (it. 25) | a capped span commits 18 segments; 9062 cut points, **0** terminal; F1's runaways held zero words | candidate 50 |
| **The F3 driver would have aborted at minute 1** (it. 26) | the soak driver's abort glob matched every healthy poll — 85/90 wrong, then 90/90 | `soak-abort-probe.py`; the driver ruling below |
| **Candidate 49's mechanism was wrong in the record** (it. 13) | the watermark, not the projection | candidate 49 |
| **The lanes are separated** (it. 12) | muting separates the lanes, and the echo was **not** what made 16 canonical speakers | candidates 51 and 55 |
| **The 409 is NAMED, and the meeting was survivable** (it. 11) | `LiveV2SessionTerminalError` → `"v2 system lane is failed."`; the peer lane and a later heartbeat both 200 | candidate 54; `live-lane-refusal-probe.py` |
| **F1 RAN TWICE AGAINST `77e0014`** (run `20260729-025318` it. 6 archive banner) | both runs cut at one instant with three simultaneous symptoms; the eliminations that ruled out lanes, heartbeat, host load and decode | candidate 56, which Phase P fixed; **superseded by the F1-green block** |

**What survives those blocks, because nothing else in this file says it.**
- ***An offline probe speaks for the deployed service only while
  `git diff --name-only <deployed sha> HEAD -- ':!scripts/ralph-afk'` is empty*** — compare against
  the **deployed** SHA, never against `main`, because between a merge and its redeploy those differ.
  **FALSE AGAIN SINCE run `20260729-025318` iteration 15**: Phase N step 1 put four files of tracked
  product source and tests on the branch, so `live-lane-refusal-probe.py` and every other offline
  probe are **SPENT as evidence about the deployed `42abc5a`** until Phase N's gate, merge and
  redeploy. They remain valid as *local* regressions. (It was true from iteration 5 to iteration 14,
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
- **macOS host procedure.** There is no `timeout(1)`: use
  `perl -e "alarm shift; exec @ARGV" <sec> <cmd>…`. `pair` **reuses** the stored
  `capture-device-id`, so it mints no new device row. **Do not read an empty `log show` as an absent
  log line** — widen the window and drop `--style` before concluding anything.

**Retired in the THIRD compaction — index (run `20260729-025318` iteration 14).** Twenty-six blocks
that diagnosed or recorded Phases K/L/M/P, the spent host recipes, and the four loop-tooling fixes
were moved to progress.txt **verbatim** under the banner `ARCHIVE OF context.md SUPERSEDED BLOCKS —
RUN 20260729-025318 ITERATION 14`. Grep a title to read it in full. Nothing was deleted.

| retired block (grep this title) | what it settled | still carried by |
| --- | --- | --- |
| **PHASE P IS DEPLOYED AND CANDIDATE 56 IS DEAD ON THE REAL SERVER - P5(c)** | the deployed `42abc5a` ran the identical probe that died at t+31.5 s on `77e0014` — 300/300 ticks, 0 non-200s — and gave the project its first trustworthy RTF (p95 **0.18**) | candidate 56 `[CLOSED]`; the F1/F2/F3 green blocks; Deployed reality |
| **CANDIDATE 56 IS ANSWERED, AND THE CAUSE IS THE HOST'S WALL CLOCK** | the failure record, the mechanism (`vllm_runner.py:111` wall clock → negative `elapsed_sec` → non-retryable `LiveProviderError`), and the host clock stepping −1.5 s every 32.3 s | candidate 56; the Duration-vs-timestamp contract row; Deployed reality's clock paragraph |
| **Candidate 56 did NOT reproduce under continuous two-lane audio** | the eliminations: heartbeat/lease, drift, span density, identity — none of them | the four durable readings below |
| **The reducer stopped calling a passing number RED - candidate 57** | `live-canary-clauses.py` splits *missed the gate* from *cannot answer it* | the reducer-verdict rules below |
| **THE REDUCER STOPPED ASKING A CERTIFICATION THE SOAK'S QUESTIONS - candidate 62** | a soak is a directory that declares `VIEW_CLAUSE_AGE` in `times.env`, not one that has `view-checks.tsv` | candidate 62 `[done]`; the F2-green rc=0 |
| **TCC-verification contract / E3 command surface / Prompt order is fixed by the source** | how the grants are read read-only and how the operator's two clicks were spent | the condensed TCC + CLI block under Deployed reality |
| **Rollback rehearsal - the PRD clause is GREEN (F4a)** | disable → revert → prove batch → restore, and the four facts that make it safe | the condensed rollback block under Deployed reality; the F4a recipe in the fence |
| **Validation fence — G1/G2/G3, B1-B4/C3c/C2/C3a/C3b/B5, E1/E2b/E3, H3/H1/J1-J4, H blocker 4, token accounting, decode-cap, D1/K5c/J5c/H4c/E2a/D3, the superseded F1 driver** (11 archived ranges) | the narrow per-node and one-time host recipes of the closed phases | the full gate, the probes, the drivers and the two redeploy templates that remain in the fence |
| **Phase L and Phase M candidate lists (48-55, D-a/D-b/D-c)** | the diagnosis and the landed record of the fifth amendment's cycle | the Phase M row in the gates index; candidate 55, still open, in the numbered list |
| **Phase P candidate list (P1-P5, the sweep table, the per-half red-before table)** | the seventh amendment's cycle, landed and merged at `42abc5a` | the Duration-vs-timestamp contract row; the Phase P gate/merge rows in the gates index; candidate 58 |

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
   invalid.`. And `live-pipeline-probe.py --lane-audio continuous` tiles each lane so no frame is
   silent (`alternating` stays the default so earlier runs stay comparable).

***How to read any `live-canary-clauses.py` verdict, out of the retired candidate-57 block.***
Three disqualifiers make the latency clause **UNDECIDED** rather than RED — `userVisibleMS` null,
`mixerOriginResolved` false, `sufficientSamples` false — and only a qualified report is compared to
the gate. `timelineIntact` false is deliberately **not** a disqualifier; the caveat is appended to
the verdict string instead, because the surviving samples are real but cover a **prefix**. A missing
`latency-final.json` is UNDECIDED, never silence. *The rule behind all of it, now paid for four
times:* **a verdict word must name the thing it decides.**

**F1 IS GREEN — the 60 s canary passed on the real hosts, run `20260729-025318` iteration 6.
READ THIS BEFORE F3.** First green certification run in this loop's history, on the deployed
`42abc5a` with candidate 51's muted lane-separating harness. `live-canary-clauses.py` **rc=0**.
Session `3386547d…`, evidence `/tmp/i6-f1-evidence/ralph-canary`, reductions `/tmp/i6-clauses.txt`
and `/tmp/i6-analyze.txt`.

| PRD clause | measured |
| --- | --- |
| continuously updating transcript with labels | version **0 → 308**, **47** committed spans (38 non-empty), speakers `S01`–`S16`, status `active` throughout |
| view authority for the whole run | **370/370** view requests 200 — and the number decomposes: **52** portal-poller polls + **318** app-latency-probe polls, the two readers whose *simultaneous* 401 was candidate 56's signature |
| **user-visible p95 ≤ 4000 ms** | **3909.3 ms — GREEN, and QUALIFIED for the first time**: `sufficientSamples` **true** (n=44), `mixerOriginResolved` true, `timelineIntact` true, `fetchFailures` 0, rejected 0/0/0. Components separately: committed p95 **2402.4 ms** + render bound **1506.8 ms** (cycle 1000 + snapshot p95 285.9 + events p95 220.9) |
| **decoder p95 RTF < 1** | **0.911** over 47 spans (p50 0.160, max 3.908 on a 0.36 s span). Second trustworthy RTF this project has recorded — Phase P's monotonic measurement |
| zero loss, zero double count | client `publishedFrameCount` **329** at stop == server's **329 POST /frames, all 200**. Stop drain `retained=0`, both lanes `stopped`, `sessionRefusal` null. Both v2 lanes `health=active`, `failure_code=None`, `failed_samples=0` |
| no lane fault, no terminal | **165** heartbeats all 200, `terminal_failure` null, 0 journal tracebacks; the only terminal line is `helper_lease_expired lanes=none` **29 s after the run's own stop** |
| secret hygiene, run-time half | `handoff` returns `viewAuthority: copied-to-pasteboard` (never the token), the unauthenticated portal HTML carries only the *header name*, pasteboard cleared to **0**, no audio artifact anywhere, `live-runs` 0, no `/tmp/mtd-live-*` |

***The system marker LANDED, and the reducer said it did not.*** `cardamom` was delivered isolated
and repeated at −r 130 (the fix written in iteration 12 and never exercised until now) and comes back
as span 15, **`[0.11][S03]Cockamom, cockamom, cockamom.[1.75]`**, at t+30.6 s — inside `program-a`,
the phase whose marker it is, three times, on the system lane, in a **muted** run. That is the
cross-check passing: the tap is upstream of the output mute and the marker survived to the
transcript. `live-canary-analyze.py` scored it **absent** because it matched the word exactly, so it
printed `rc=5` on a run whose marker clause holds. That was **candidate 59** — same shape as 57 — and
it is **FIXED in iteration 13**: this directory now reduces to `rc=4`, naming
`REWRITTEN as 'cockamom' x3 (similarity 0.60) span 15 at t+30.6s`.
***The room marker did not land, and that is the harness's recorded limit, not a defect.*** MacStudio
spoke `obsidian` isolated and repeated into the room window; m4mbp's microphone (default input was
the **built-in** `MacBook Pro Microphone` this run, not iteration 12's AirPods) returned only
one-word fragments. **So "two speakers" is still two voices on the SYSTEM lane**, program A vs
program B, with the microphone lane carrying room noise. Candidate 51's limit stands and the PRD's
"two speakers plus identifiable system audio" half is *not* fully certified by this run.
***And candidate 55 is now measured inside a GREEN run, which is exactly why no gate sees it.***
Identity **saturated at t+65.6 s of an 85 s meeting**: 16 canonical speakers for 2 real voices, and
**9 of them (`S07`–`S15`) were minted by one-word `Hi.` fragments** of microphone-lane ambient noise
during the room window. Span 44 then abstained `speaker_capacity_exceeded` (J2 held — it published
under `S00` rather than ending the meeting). One decode hallucinated on that noise
(span 34, *"I'm sorry, I can't assist with that request."*). The meeting was perfect; the identity
was not.
*Hosts left clean:* server `HEAD 42abc5a` worktree clean, live MainPID **355607** / batch **301112**
and **322117**, all `NRestarts=0`, batch `/` 200, `live-runs` 0, device store **13 / 1 unrevoked**
(m4mbp's — never revoked, and `pair` minted no new row). m4mbp: app killed, `/tmp` scratch removed,
volume back to 31 unmuted, pasteboard 0, both TCC grants still `auth_value=2`, app inode
`212080356` and CLI sha `450c20bf…` unchanged (no rebuild, so no TCC exposure).

**F3 RAN ITS WHOLE PLAN AND FOUND ONE REAL DEFECT — the 16-minute soak, run `20260729-025318`
iteration 9. READ THIS BEFORE PHASE N OR ANY EIGHTH-AMENDMENT DECISION.** 17 minutes on the
deployed `42abc5a` with the muted lane-separating harness, session `331d8c57…`, label
`ralph-i7-f3-20260729T035258Z`. `live-canary-clauses.py --user-visible-gate-ms 6000` **rc=3**:
**five clauses GREEN, one RED**. Evidence `/tmp/i9-f3-evidence/ralph-soak`, reduction
`/tmp/i9-clauses.txt`.

| PRD soak clause | measured |
| --- | --- |
| capture remains active for the whole soak | **17/17 full wall-clock minutes** each carried ≥ 57.8 s of accepted audio and 24-29 new committed spans; version 0 → 3646, **443 spans**, status `active` throughout, `terminal_failure` null, **0** journal tracebacks |
| `/live` polling holds | **355/355** portal polls 200 across t+2.2 s .. t+1029.1 s |
| **the same view authority works after minute 15** | **GREEN** — `post900` 200/200/200 at age 904.7 s and `post15` 200/200/200 at age **1024.1 s**, the same token minted at t+1.2 s |
| **then clean stop immediately revokes it** | **RED — see candidate 60.** 0.2 s after `stop` returned `ok:true running:false`, snapshot and events both still **200** |
| user-visible p95 ≤ 6000 ms | **4557.2 ms GREEN and QUALIFIED** (`sufficientSamples` true n=199, `mixerOriginResolved` true, `fetchFailures` 0): committed p95 **3009.4 ms** + render bound **1547.7 ms**. Caveat travels with it — `timelineIntact` **false**, 234 advances rejected after the break, so the number covers a **prefix** |
| decoder p95 RTF < 1 | **0.546** over 443 spans (p50 0.123, max 1.402). D-c capped **67 of 443**; slowest decode 1.47 s |
| lane fault | system lane **degraded** `macos_buffer_overrun` at t+474.2 s and **kept capturing to the end** — D-a working, not a clause failure. Both v2 lanes finished `health=active`, `failure_code=None`, `failed_samples=0` |
| clean stop drain | `retained=0`, both lanes `stopped`, `sessionRefusal` null, 4099 frames published |

***What this run PROVES about the last three phases, which is the point of running it.*** Candidate
53 killed the previous F3 at **minute 14.6**; this one ran 17 minutes with a *permanently degraded*
lane and never lost the heartbeat. Candidate 56 killed three runs inside 32 s; this one survived
~31 clock steps. D-c's cap fired on 67 spans and the RTF tail stayed at 0.546 where F1's was 0.911.

***The honest quality reading, which no clause captures and which is the argument for Phase N.***
**262 of the 325 non-empty spans (81 %) transcribe to nothing but `Hi.`** — the decoder hallucinating
on a lane carrying near-silence between the soak's one utterance per 60 s. Identity saturated at
**t+117 s** (16 canonical speakers for 2 voices), so **1100 of 1371** label tags are `S00`; J2 held
throughout (`speaker_capacity_exceeded` abstains published under `S00` rather than ending the
meeting). *This is candidate 55's mechanism at 17-minute scale*: `Hi.` fragments are what mint the
phantom speakers, and they are also what fills the transcript. **The system marker LANDED verbatim
this time** — span 5 at t+9.5 s reads `[0.08][S03]Cardamom, Cardamom.` — so candidate 59's phonetic
question does not arise here; the room marker `obsidian` again did not reach the microphone, the
third measurement of candidate 51's recorded harness limit.
*Hosts left clean, measured after:* server `HEAD 42abc5a` worktree clean, live MainPID **355607** /
batch **301112** and **322117**, all `NRestarts=0`, batch `/` 200, `live-runs` 0, no `/tmp/mtd-live-*`,
0 tracebacks, device store **13 / 1 unrevoked**. m4mbp: app killed, all `/tmp` scratch removed,
volume back to 31 unmuted, pasteboard 0, both TCC grants `auth_value=2`, app inode `212080356` and
CLI sha `450c20bf…` unchanged (no rebuild).

**CANDIDATE 60 — A CLEAN STOP NEVER REACHES THE SERVER (new, iteration 9). This is F3's one RED and
it is a product defect, not a harness artifact.** The PRD clause is *"then clean stop immediately
revokes it"*; measured, the view authority outlived the stop by **29.4 s**.
***Three independent confirmations, so nobody re-derives it.***
1. **The wire.** `grep` of the live service journal for `…/331d8c57…/stop` returns **0**. The
   session's only terminal line is `live helper terminal: … reason=helper_lease_expired lanes=none`
   at epoch 1785298234.27 — **29.4 s after** `t_stop` 1785298204.83, i.e. the 30 s helper lease, not
   the stop.
2. **The snapshot.** The portal poller kept answering 200 with `status=active` for 4 s past the stop
   (last poll t+1026.6 s, version 3646).
3. **The source.** The Swift client builds live URLs in exactly one place, `liveURL(base:sessionID:
   action:)` (`CaptureHTTPTransport.swift:450`), and it has **three** callers: `frames` (`:239`),
   `heartbeat` (`:292`) and the latency probe's snapshot/events (`CaptureLatencyProbe.swift:576`).
   There are only **two** `URLRequest(url:)` sites in the whole client. `CaptureController.stop`
   (`CaptureController.swift:473-496`) stops the source, drains the outbox and returns — it never
   tells the server anything.
***And the server half is already built and already tested.*** `POST /api/live/sessions/{id}/stop`
exists at `live_transport.py:325` and takes a `deadline`; `tests/test_live_api.py:502` is literally
`test_clean_stop_immediately_revokes_view_authority` and passes. **So this is the loop's familiar
class one turn further out:** the behaviour is implemented, contracted and covered on one side of the
seam, and *nothing calls it from the other*. The C1 node proves the route revokes; the Swift suite
proves the controller stops; **no test puts a real client's `stop` in front of a real server**, which
is exactly the gap H1/K1/53 each occupied.
***It was visible in F1 and was not named.*** The F1-green block records "the only terminal line is
`helper_lease_expired lanes=none` **29 s after the run's own stop**" as a curiosity. It was this
defect, in a run whose reducer had no soak clause to test it with.
***Severity, stated so the authorization decision is a decision.*** The exposure is **bounded at
30 s** and self-heals — the lease expires, the session goes terminal and view authority 401s — and no
audio is lost, because the client drains before returning. What fails is the PRD's word *immediately*
and the promise that closing a laptop's meeting closes the browser's access to it. It also costs the
accounting clause its clean read: F3's `accepted − accounted = 14484 samples` is INCONCLUSIVE only
because the session was still active when the last snapshot was taken.
*Tracked product source under `macos/` (and a test under `tests/`), so it is frozen: **needs its own
authorization**. Shape of the fix, not a decision: `CaptureController.stop` gains a transport call
after the final drain, with the same "a publish failure must not stop the meeting ending" rule — a
stop that cannot reach the server must still stop locally, and the lease then does what it does
today.*

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
**F2 IS GREEN — the 300 s locked certification passed on the real hosts, run `20260729-025318`
iteration 11. READ THIS BEFORE ANY EIGHTH-AMENDMENT DECISION.** Second green certification run in
this loop's history, on the deployed `42abc5a` with the muted lane-separating harness.
`live-canary-clauses.py --user-visible-gate-ms 6000 --interrupt-report` **rc=0** — six GREEN, **no
RED and no UNDECIDED**. Session `0047a5ad…`, label `ralph-i11-f2-20260729T044456Z`, evidence
`/tmp/i11-f2-evidence/ralph-cert`, reduction `/tmp/i11-clauses.txt`.

| PRD F2 clause | measured |
| --- | --- |
| simultaneous lanes | both `capturing` from t+2.2 s; server-side both v2 lanes finished `health=active`, `failure_code=None`, `failed_samples=0`; system 4 990 123 samples, microphone 5 059 200 |
| silence/mute window | 30 s at t+70..100 s; version kept advancing (365 → 371 across it), spans kept committing, session `active` throughout |
| **a 5-second network interruption** | **5.050 s measured on CLOCK_MONOTONIC** at the server, `deletes=1`, `rule_still_present=no`, chain back to `-P INPUT ACCEPT`. **The client saw it** — 1 refused poll (`000`) — and resumed (first 200 at t+239.3 s) |
| ambiguous retry / duplicate retry | the mechanism, sampled at 1 Hz: `publishedFrameCount` **froze at 902** for 5.2 s, `outboxRetainedFrames` rose 2 → **10**, `pumpFailure transportUnavailable`, then published replayed 902 → 909 → 923 → 928 → 933 and retention drained to **0**. The server accepted the replay **exactly once** — see the accounting row |
| two speakers | 16 canonical speakers for 2 voices (candidate 55 again); the two program voices are both on the **system** lane — candidate 51's limit, fourth measurement |
| clean stop/drain | `retained=0`, both lanes `stopped`, `sessionRefusal` null, `outboxRetainedFrames` 0 |
| **user-visible p95 ≤ 6000 ms** | **3859.6 ms — GREEN and QUALIFIED**: `sufficientSamples` **true** (n=113), `mixerOriginResolved` true, `fetchFailures` 0, rejected 0/0/39. Components separately: committed p95 **2459.0 ms** + render bound **1400.6 ms** (cycle 1000 + snapshot p95 223.9 + events p95 176.7). Caveat travels with it — `timelineIntact` **false**, so the number covers a **prefix** |
| decoder p95 RTF < 1 | **0.670** over 161 spans (p50 0.131, max 20.577 on a 0.069 s span; total decode 50.0 s, max 1.42 s). D-c capped **4 of 161** |
| **zero accepted-audio loss, zero double count** | client `publishedFrameCount` **1257** at stop == the server journal's **1257 × `POST …/frames` all 200**. And the stronger statement the journal supports: **4748 of the session's 4749 log lines are HTTP `200`** — the 4749th is the terminal line. **Zero non-200 on the server for the entire run**, interruption included |
| outbox and memory bounded | outbox run-wide peak **10** frames against its 15 s/lane bound, back to 0 within 3 s; retained samples 23 996 of the 960 000 bound (2.5 %) |

***What this run proves that F1 could not.*** F1 was 85 s of undisturbed meeting. This is 300 s with a
**deliberate 5 s outage**, and the three fixes the last three phases bought are visible in the same
ten seconds of evidence: 53 kept the heartbeat alive (**622 heartbeats, all 200**), D-a turned the
resulting `macos_buffer_overrun` at t+233.0 s into a **degradation** that kept capturing to the end,
and the outbox retained-until-ACK contract replayed every frame without the server double-counting
one. *The outage is also what caused the overrun* — backpressure from a blocked uplink — which is
the exact sequence D-a was authorized for and had never been observed end to end.

***The system marker landed and was rewritten PHONETICALLY — candidate 59's fourth measurement, and
the clearest one yet.*** `cardamom`, delivered isolated and repeated at `-r 130` at the end of phase
A, comes back as span 29 at t+67.5 s: **`[0.06][S01]Pardon me, pardon me, pardon me.[1.68]`** —
three repetitions, right phase, right lane, right instant, in a **muted** run. The in-sentence
delivery is span 138, `The cold word cardigan is recorded once more for` (the driver said "The
codeword cardamom is recorded once more for the system lane"). So the tap is upstream of the output
mute and the marker survives to the transcript; **the decoder's language model is what the exact
string match loses to**, not the capture path. Any future marker check must be phonetic.
***The room marker did not land — candidate 51's limit, fourth measurement.*** MacStudio spoke
`obsidian` isolated and repeated 10 times into the room window; m4mbp's default input was again the
**built-in** microphone, and spans 90–107 hold nothing but hallucinated near-silence
(`I'm sorry, I can't assist with that request.` × 9, `Hi.`, `Okay.`, `Mm-hmm.`). So "two speakers"
is again two voices on the SYSTEM lane.
***And candidate 55 saturated inside a second GREEN run*** — 16 canonical speakers by t+93.9 s of a
300 s meeting for 2 real voices, then `speaker_capacity_exceeded` abstains published under `S00`
(J2 holding). 24 of 151 spans committed empty (H1). No refusal, no terminal.
*Hosts left clean, measured after:* server `HEAD 42abc5a` worktree clean, live MainPID **355607** /
batch **301112** and **322117**, all `NRestarts=0`, batch `/` and `/api/jobs` 200, `live-runs` **0
entries** (no raw audio persisted), no `/tmp/mtd-live-*`, **0** journal tracebacks, device store
**13 / 1 unrevoked** (`pair` minted no new row), `iptables -S INPUT` = `-P INPUT ACCEPT`, server
scratch removed. m4mbp: app killed, all `/tmp` scratch removed, volume back to 31 unmuted,
pasteboard **0**, both TCC grants still `auth_value=2`, app inode `212080356` and CLI sha
`450c20bf…` unchanged (no rebuild, so no TCC exposure).
*The one known defect this run re-recorded rather than rediscovered:* **candidate 60** — the only
terminal line is `helper_lease_expired lanes=none` at 00:50:44, **29 s after** the run's own stop,
and the journal contains **0** calls to `…/stop`. Printed under section 9 as OBSERVED; it is not an
F2 clause. See candidate 60.

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

## Deployed reality — all four checkouts at `42abc5a`

**Server (`ga0-alienware-rtx4070ti`, WSL Ubuntu, checkout `/mnt/d/Coding/MOSS-Transcribe-Diarize`).**
Detached at **`42abc5a`** since P5(c) (run `20260729-025318` iteration 5), **MainPID 355607**,
`NRestarts=0`; before that `77e0014` (M6c), `fc7097d` (K5c),
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
  `0.0.0.0:7861`, **MainPID 355607** (was 350731 before P5(c)), `NRestarts=0`. `/live` answers 200
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
- `provider_manifest_hash 61d97ffe…`. `/api/live/descriptor` reports `source_revision f9285d69…`,
  which is a **manifest field stamped at D2 time, not the running code's revision** — never use it as
  the deployed-SHA check. Use the four-way `git rev-parse` plus venv introspection.
- `live-auth.json` holds one **unrevoked** device, m4mbp's
  `AB600574-FD93-4321-967E-652AB064A70B`, plus several revoked probe devices from F0/H2/J5d. Device
  *count* is not a signal; count unrevoked devices — **13 devices / 1 unrevoked** after P5(c).
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
with `BatchMode=yes`, **detached at `42abc5a`** (tree `06d78525…`, the merge's own tree), clean.
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
  mtime `2026-07-28T18:22:32Z`. **The checkout is `42abc5a` but the INSTALL is still the `77e0014`
  product, and that is correct, not drift:** P7's payload touched **0** files under `macos/`, so the
  two SHAs build a byte-identical client. Re-measured after P5(c)'s checkout — inode `212080356` and
  CLI sha256 `450c20bf…` **unchanged**, which is the positive proof no rebuild happened and therefore
  that the TCC grants were never at risk. (K5c's `fc7097d` install was digest `267ada93…`, CLI `c11e89ff…`,
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
| **Fingerprint album** (N-album, it. 15 of run `20260729-025318`; **in source only, not deployed**) | **Matching is not enrollment.** The evidence floor (`identity_provider.min_segment_samples`) does not move, so a short span is still *labelled*; enrollment needs ADR-0002's **1.0 s**. Per canonical speaker: up to **k=10** exemplars, matched against their **duration-weighted centroid**; plus **one** sub-admission stand-in used only while the bank is empty, discarded — never averaged — by the first real exemplar. Neither tier is recency-driven. Every refusal is a named disposition and nothing here raises. |
| **Manifest calibration** (N-recal, it. 17 of run `20260729-025318`; **in source only, not deployed**) | A **free** deployed parameter is stated by the deployment, never inherited. `finalize-live-provider-manifest.py` requires `--min-match-score` / `--min-match-margin`, writes them into `identity_config`, hash-covers them, names them in the plan and the evidence, and refuses a pair `live_provider_bundle._identity_config` rejects. The calibrated pair is named once, in `live_identity_album.py`, and the accuracy harness imports it — so the measured pair and the deployable pair cannot diverge. |
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
| **Phase B client gate** | GREEN at **`3fb5567`** — Swift 121, Python 466+2, tracer 3/0 skips *from a deleted lab bundle*, discriminator 10/10, leak-scan clean. |
| **Server meeting-reliability gate** | GREEN at **`f400d426`** — every PRD clause mapped to a named node (60 virtual minutes, exact 12 h cap, five lifecycle statuses, operator/device revoke, restart, 5 s outage, ambiguous + duplicate retry, 429, outbox overflow). The 900 s expiry is proven gone **by absence**. |
| **C4 keeper merge #1** | **`f9285d6`**, feature tip `f400d426`; `git diff` empty. Published D1. |
| **G4 gate + merge #2** | GREEN at `23dc163`; merge **`317df4d`** — 12 files, server tree byte-identical, so no restart was needed. |
| **H4 gate + merge #3** | GREEN at `8b852f2`; merge **`b817871`** — 21 files, **server-only**, restart required, no Mac rebuild. |
| **J5a gate + merge #4** | GREEN at `517306b`; merge **`6a540fe`** — 21 files (+1475/-134), **server-only**. |
| **K5a gate + merge #5** | GREEN at `cd7faf9`; merge **`fc7097d`** — 19 files, **not server-only** (7 under `macos/`), so K5c needed a restart **and** a Mac rebuild+reinstall. |
| **G5 / H4c / J5c / K5c redeploys** | All four published and redeployed cleanly. K5c is the one to copy: rollbacks committed **before** any host was touched, admission checked **after** the checkout under the code about to start, content parity proven by hashing files whose **content differs** across the two SHAs (a file that is unchanged proves nothing), and the TCC grants measured — not assumed — to survive the bundle replacement (inode moved `211648186 → 211995344`). |
| **F0 probe / H-diagnosis / H4d / boundary sweep** | The server-side probe chain that found and then closed blockers 1-4. All four are fixed, merged and deployed; the blocks are historical and live in the archive. The reusable half is in the Validation fence below. |
| **J5d gate** | **GREEN at `6a540fe`** — the first run in the loop's history to finish: 40/40 ticks, `non_200_count` 0, nine committed spans tiling the meeting end to end, `accepted == accounted == committed == 320000`, speakers S01-S04, and **both degrade-not-die paths fired inside the same green run** (H1's empty span, J2's `S00`). Decoder RTF 0.055-0.431. |
| **F4a rollback rehearsal** | GREEN — see the rollback block above. |
| **K5d re-read** | Named the lane failure `macos_buffer_overrun` and traced it to Phase L. Phase K closed; the fourth amendment spent. |
| **F1 canary (it. 8) / F3 soak (it. 9)** | **RED** — one defect, candidate 53, since fixed. Both blocks retired to progress.txt. |
| **F1 canary, run `20260729-025318` it. 6** | **GREEN, rc=0** — the first green certification run. user-visible p95 **3909.3 ms** ≤ 4000 **and qualified** (`sufficientSamples` true, n=44), decoder p95 RTF **0.911** < 1, **329 published == 329 accepted**, 370/370 view polls 200 across both readers, 165/165 heartbeats 200, no lane fault, `terminal_failure` null, 0 tracebacks, hosts left clean. Not certified by it: the "two speakers" half (both voices were on the system lane). See the F1-green block. |
| **F3 soak, run `20260729-025318` it. 9** | **rc=3 — 5 GREEN, 1 RED.** 17/17 full minutes, 443 spans, 355/355 portal polls 200, view authority 200 at age 1024.1 s, user-visible p95 **4557.2 ms** ≤ 6000 qualified, decoder p95 RTF **0.546**, one lane degraded at t+474 s and kept capturing, clean drain `retained=0`, hosts clean. RED: the clean stop did not revoke view authority — **candidate 60**. |
| **F2 certification, run `20260729-025318` it. 11** | **GREEN, rc=0** — six GREEN, no RED, no UNDECIDED. user-visible p95 **3859.6 ms** ≤ 6000 qualified (`sufficientSamples` true, n=113), decoder p95 RTF **0.670**, a **5.050 s** CLOCK_MONOTONIC interruption seen by the client and survived, outbox 0 → **10** → 0, **1257 published == 1257 `POST /frames`**, **4748/4748 HTTP responses 200**, 622/622 heartbeats 200, one lane degraded by the outage and kept capturing, clean drain, hosts left clean. Not certified by it: the system-audio-denied variant (deliberately not attempted — it would spend a TCC grant) and the "two speakers" half (both voices on the system lane). See the F2-green block. |
| **Phase M gate step (a)** | GREEN at **`21a73ea`** — Swift 158/0 (0 warnings, fresh scratch), Python 604+2/368, tracer 4/0 skips, 10/10, lane-refusal probe rc=0, 7/7 hard-cap cases, leak-scan clean, tree clean; payload 10 files / +983/-51 all in scope. |
| **M6 gate + merge #6** | Merge **`77e0014`**, parents `fc7097d` + feature tip `4ac5d95`; join `1b6a9f4` proven content-free first. In-worktree gate on the merged tree: Swift 158/0, Python 604+2/368 in 64.4 s. Merge tree == feature tree `d2094369…`. **Not server-only** (4 files under `macos/`), so step (c) is the K5c shape: restart **and** Mac rebuild+reinstall. Guard rehearsed: a seventh merge refuses. |
| **Phase P gate step (a)** | GREEN at **`5bc4f7f`** (run `20260729-025318` it. 2) — Swift **158/0** with **0 warnings** on a fresh scratch, Python **608 passed / 2 skipped / 368 subtests** in 59.95 s, tracer **4/0 skips**, discriminator **10/10**, lane-refusal probe rc=0 (a **local** regression only — the branch carries unmerged product source, so it does **not** speak for the deployed `77e0014`), seven hard-cap cases rc=0, `soak-abort-probe` 90/90, `view-reader-probe` pass, leak-scan clean, tree clean. Payload **7 files / +285/−38**, all in `moss_transcribe_diarize/` + `tests/`, **none under `macos/`**. *Payload review added one thing the four-site sweep table could not:* `grep -rnE '(time\.time\(\)\s*-\|-\s*time\.time\(\))' moss_transcribe_diarize/` returns **nothing** — the class is empty by search, not merely by enumeration; every surviving `time.time()` is a persisted or expiry **timestamp** (`live_transport._request_now`, `jobs` `created_at`/`updated_at`, `windowed_transcription:367`), which is P4's recorded ruling. |
| **P7 merge #7** | Merge **`42abc5a`** (run `20260729-025318` it. 4), parents `77e0014` + feature tip `96137b1`; join `cfa3a96` proven content-free first (`merge-tree --write-tree` returned HEAD's own tree). In-worktree gate on the merged tree: Swift **158/0**, Python **608 passed / 2 skipped / 368 subtests** in 61.83 s. **Merge tree == feature tree `06d78525…`** — the merge added nothing and dropped nothing. **Server-only** (0 files under `macos/`), so step (c) is the J5c shape: restart, and on m4mbp a checkout with **no rebuild and no reinstall**. Guard rehearsed non-vacuously: an **eighth** merge prints `main moved from expected pre-merge SHA 77e0014…`, rc=1. Temp worktree removed by the EXIT trap; `git worktree list` back to one. |
| **P5(c) redeploy** | GREEN — four-way SHA **4/4 at `42abc5a`**. Push fast-forwarded `77e0014..42abc5a`; server MainPID 350731 → 355607 with `/live` 200 at 8 s and the descriptor 200; manifest admission re-checked **after** the checkout under the service venv (`available=True`, `failures=[]`, hash `61d97ffe…` unchanged); content parity by hashing all **five** changed product files against `git show` at **both** SHAs (each matches the new and differs from the old); the deployed fix **exercised**, not hasattr'd; m4mbp checked out with the app inode and CLI hash unchanged (no rebuild, no TCC exposure); both grants still `auth_value=2`; batch MainPIDs unmoved and `/` 200. Then the 150 s probe above. |
| **M6c redeploy** | GREEN — four-way SHA **4/4 at `77e0014`**. Server MainPID 346453 → 350731, `/live` 200 in 9 s, batch untouched; D-c exercised on the host (cap 286/112) and the venv proven editable-from-the-checkout; Mac rebuilt + reinstalled (inode 211995344 → 212080356), DR byte-identical a fourth time, both TCC grants still `auth_value=2`, and the install proven to carry D-a by a strings witness **with a control word**. |

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

**The port-publish race — why the first merge attempt failed, and the standing lesson (new,
iteration 5).** The keeper script's own gate came back `596 passed, 2 skipped, **2 errors**` while
the *identical tree* had just passed `598 passed / 2 skipped` in the primary worktree. Both errors
were fixture setup in `tests/test_live_deployment_credentials.py`:
`ValueError: invalid literal for int() with base 10: ''` at `:591`.
*Not luck and not a product defect.* The `live_server` fixture treats the port file's **existence**
as the signal that the port is readable, and the generated server published it with
`port_file.write_text(...)`, which creates the file **before** it holds anything. A reader polling
inside that window sees an existing, empty file.
*Measured rather than assumed* (`/tmp/moss-port-race-probe.py`, 4000 rounds with writer and reader
released from one barrier): the shipped `write_text` tears **168/4000** reads (4.2%); staging file +
`os.replace` tears **0/4000**. The fix is the atomic publish, so existence and completeness become
one event — **not** a tolerant reader, which would have left the window open.
*Why the merge worktree lost a race the primary worktree wins:* nothing about the worktree. Another
agent's full pytest suite was running on this MacStudio at the time, so the CPU contention widened
the window. **Treat that as the standing lesson: an unexplained failure inside `merge-keeper.sh`
that does not reproduce in the primary worktree is a scheduling-sensitive test, not a bad merge.**
Re-running the merge until it passes would have hidden a 4%-per-run flake under an authorized merge.
Verification: the two nodes 14 passed **×5** consecutively, full suite 598/2/368, then the merge's
own gate green on the retry.

## Validation

```bash
# --- narrow: live server slice (~5 s) ------------------------------------
python3 -m pytest tests/test_live_auth.py tests/test_live_portal.py -q
python3 -m pytest tests/test_live_service_runtime.py tests/test_live_provider_bundle.py \
  tests/test_live_mixer.py tests/test_live_ingest.py -q

# --- C1 view-authority nodes (10 = 9 new + the pre-existing action/session scope node:
#     60 virtual minutes, exact cap, five lifecycle statuses, unwired fail-closed, operator
#     revoke, restart, clean stop, failed stop, loopback-only route) ----------------------------
python3 -m pytest tests/test_live_auth.py tests/test_live_api.py -q \
  -k 'view_authority or view_revocation or revokes_the_view'

# --- N-gate: live speaker accuracy on production code, 21 nodes, ~11 s (iteration 16) ---------
#     Fixture integrity + the two silence splits (16 parametrised) then five measured claims.
python3 -m pytest tests/test_live_identity_accuracy.py -q
# The numbers themselves, any configuration, without pytest -- this is how a future run
# re-measures rather than re-derives. Configs are lru_cached, so each costs ~1.2 s once.
python3 -c "
import sys; sys.path.insert(0,'tests'); sys.path.insert(0,'.')
import live_identity_accuracy as H
for p in ('album','overwrite'):
    r = H.replay_all(policy=p)
    print(p, round(H.mean_accuracy(r)*100,1), round(H.min_accuracy(r)*100,1))
"

# --- K3 terminal record (8 nodes: the terminal heartbeat's codes into expiry/journal/log, the
#     lease expiry's `lanes=none`, the record's bounded shape, the default sink's level, three
#     expiry-stamp nodes, and the real coordinator+v2 registry+runtime seam plus its
#     one-failed-lane guard). ~4 s. --------------------------------------------------------------
python3 -m pytest tests/test_live_helper_failure.py tests/test_live_session_v2.py \
  tests/test_live_pipeline_seams.py -q
# Proof the line survives the deployed logging config (prints to stderr; no service needed):
python3 -c "import logging.config,uvicorn.config as u; \
from moss_transcribe_diarize.app.live_helper_failure import LiveHelperTerminalRecord as R, log_live_helper_terminal as L; \
logging.config.dictConfig(u.LOGGING_CONFIG); L(R(session_id='s1',reason='helper_all_lanes_failed',lane_failures={'system':'device_unavailable'}))"

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

# Reinstall the fixed lab bundle from scratch (safe: gitignored build output). Do this only to
# re-prove the first-install path; normal runs must reuse it.
rm -rf macos/MOSSCapture/.build/idea044-lab

# --- Phase A discriminator (the A4 gate; run it before and after any Phase-A change) --------
PYTHONDONTWRITEBYTECODE=1 python3 \
  "/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/spikes/idea-044-attempt2-red-control/repro.py" \
  --target "$PWD"        # 10/10 since iteration 4; must stay 10/10
# The 16-check sibling is historical after B1 and reads 14/16 on the tip (09 and 15 assert the
# superseded Keychain default). Its frozen green is commit 1ede498, not the tip.

# --- B1/B2/B3/B4/C3c Swift --filter recipes and the C2/C3a/C3b/B5 pytest slices and by-hand tool
#     invocations are RETIRED to progress.txt (closed phases; the full gate below runs them all).
#     The one warning worth keeping: NEVER pass `--rotate` to ops/generate-live-tls.sh again — it
#     invalidates every pairing payload and every pin a Mac has stored. -----------------------------
# --- E1 (signing identity), E2b (build/sign/install on m4mbp) and E3 (the TCC read-only checks and
#     the operator's GUI steps) are SPENT and RETIRED to progress.txt. E3 is closed forever; the
#     read-only TCC check that remains live is in the Deployed-reality TCC block. The m4mbp
#     rebuild+reinstall recipe, which is the only one of these still re-runnable, is kept below. ----
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
#     current host will REWRITE (the host carries the pre-album 0.5/0.2), print a
#     `rollback: mv <backup> <output>` line first, and change identity_config_hash,
#     combined_config_hash and the provider manifest hash. That change is the signature of
#     the recalibration - a redeploy expecting 61d97ffe… is checking it did NOT happen.
printf '%s\n' \
  'set -euo pipefail' \
  'cd /mnt/d/Coding/MOSS-Transcribe-Diarize' \
  '"$HOME/.local/share/moss-transcribe-diarize/venv/bin/python3" ops/finalize-live-provider-manifest.py --input "$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.provisional.json" --output "$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json" --source-revision "$(git rev-parse HEAD)" --hard-cap-samples 40000 --max-retained-samples 960000 --frame-samples 8000 --min-match-score 0.35 --min-match-margin 0.1' |
  ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local \
    "wsl.exe -d Ubuntu -- bash -s"
# Run it --dry-run FIRST and read the two `plan: set identity_config.…` lines and the
# `evidence: identity_min_match_*` lines; they are what makes the calibration reviewable.

# --- host manifest admission by the runtime's own readers (read-only; re-run any time) ----------
#   from_manifest -> _endpoint_config(payload["endpoint_config"]) and _bounds(payload["bounds_config"])
#   (they take their own sub-mappings, NOT the whole payload), then _preflight_payload(path)
#   Expect available=True, failures=[], manifest_hash 61d97ffef1bbdc0d4278c0fd719d5d31b0ac5f69e1654573ada5091653fecb95

# --- the H3/H1/J1-J4 per-node counts and their semantic-revert red-prove recipes are RETIRED to
#     progress.txt. The file itself is still the live seam suite (60 nodes): ------------------------
python3 -m pytest tests/test_live_pipeline_seams.py -q
# --- H blockers 2 and 3, offline and deterministic (no server, no GPU, no network, ~0.4 s each).
#     Defaults are the deployed manifest values; rc=3 means reproduced, rc=0 means survived.
#     Every case below is rc=0 from H2 (iteration 3) on; `--session-hard-cap` is retired and only
#     'none' is accepted, because LiveSession no longer partitions audio. -------------------------
python3 scripts/ralph-afk/live-hardcap-repro.py --frames 8                      # blocker 2, speech
python3 scripts/ralph-afk/live-hardcap-repro.py --frames 8 --speech-pattern 0   # blocker 2, silence
python3 scripts/ralph-afk/live-hardcap-repro.py --frames 45 --frame-samples 1000  # not frame-size
python3 scripts/ralph-afk/live-hardcap-repro.py --frames 8 --session-hard-cap none  # retired knob
python3 scripts/ralph-afk/live-hardcap-repro.py --frames 24 --speech-pattern 1100   # endpoints, ok
python3 scripts/ralph-afk/live-hardcap-repro.py --speech-provider webrtc --frame-samples 5808 \
  --frames 3                                    # blocker 3 - rc=3 before H3, now rc=0 (survives)
python3 scripts/ralph-afk/live-hardcap-repro.py --speech-provider webrtc --frame-samples 8000 \
  --frames 4                                                                   # blocker 3 control
# The webrtc cases use a stand-in VAD enforcing only webrtcvad's 10/20/30 ms length contract,
# because MacStudio has no native webrtcvad wheel. The real exception is recorded from the host.

# --- The probe's own instruments, offline, no server and no pairing code (iterations 26, 28) -----
#     Run BOTH before spending a host run on the driver they belong to: an instrument that has
#     never run is not evidence that it works, and both of these found a real defect on first run.
python3 scripts/ralph-afk/soak-abort-probe.py      # live-soak.sh's abort decision: 90/90, rc=0
python3 scripts/ralph-afk/view-reader-probe.py     # live-pipeline-probe.py's ConcurrentViewReader
# view-reader-probe.py caught `self._stop = threading.Event()` shadowing threading.Thread._stop,
# which threading.Thread.join() calls internally: every run would have died at reader.join().

# --- H blocker 4's host probe and its boundary sweep are RETIRED to progress.txt (J1's clamp
#     superseded them; the surviving rule is the Span-bounds row in Shipped contracts). ------------
# --- J5d: the third amendment's gate, GREEN in iteration 16. Re-runnable end to end; each run
#     costs one pairing code, one device (REVOKE IT) and one session, and no service restart. ------
# 1. offline half first, because it mutates nothing (all seven cases above -> rc=0).
# 2. online half: mint on the host loopback, pipe the payload on STDIN, never argv, never a file.
#    The zsh trap applies here too - run the whole thing under `bash -c`, or the probe receives one
#    argument and argparse rejects it ("unrecognized arguments: --frames 8" for a real option).
#    printf '%s' "$PAYLOAD" | python3 scripts/ralph-afk/live-pipeline-probe.py \
#      --host 100.64.0.8 --port 7861 --pin a35ca9fc… --device-id "ralph-j5d-probe-<utc>" \
#      --seconds 20 --lead-seconds 1.0 --lane-offset-ms system=137 --report /tmp/moss-j5d.json
#    PASS = rc 0 (rc 5 = spans committed but every speaker is S00; rc 3 = nothing committed),
#    publish.non_200_count 0, stop.snapshot accepted == accounted == committed, and
#    transcript.attributed_speakers non-empty. Then REVOKE the device (loopback, on the host).
# 3. J1 on real audio, deterministically - do NOT wait for a live span to overshoot (only ~6 % do):
#    python3 scripts/ralph-afk/build-span-sweep.py --out-dir /tmp/moss-j5d-sweep \
#      --report /tmp/moss-j5d-sweep/index.json --seconds 20 --lead-seconds 1.0 \
#      --lane-offset-ms system=137 --cut 92208:40000 --cut 268208:40000
#    sha256 must be 844e6eff… / 038cf855… (the build is byte-deterministic across iterations), then
#    ship both wavs + live-identity-seam-probe.py in ONE stdin script and run them under the
#    service venv. Pre-J1 both were rc=4 timestamp_outside_span; deployed they are rc=0 prepared.
#    `rm -f "$D"/*.wav` in the SAME invocation - audio does not belong in /tmp on the server.
# 4. after any run: host HEAD unchanged, both MainPIDs unchanged with NRestarts=0, live-runs/ 0,
#    no /tmp/mtd-live-*, 0 journal tracebacks, both probe devices revoked, m4mbp device NOT revoked.
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
#     It was SPENT from iteration 16 (candidate 50 changed moss_transcribe_diarize/) until M6c
#     redeployed in iteration 20; it is VALID again now that all four checkouts hold 77e0014.
#     THE DURABLE RULE, because this flipped twice: compare against the DEPLOYED SHA, never against
#     `main` — between a merge and its redeploy those are different commits, and branch-vs-main
#     parity then says nothing about the running service.
git diff --name-only 77e0014 HEAD -- ':!scripts/ralph-afk'   # deployed SHA; non-empty == probe != service
git diff --name-only main    HEAD -- ':!scripts/ralph-afk'   # branch parity; NOT the same question
python3 scripts/ralph-afk/live-lane-refusal-probe.py --json /tmp/ralph-lane-refusal.json
# It imports tests/test_live_api.py BY FILE PATH (`tests/` is not a package, so
# `import tests.test_live_api` fails with ModuleNotFoundError) to reuse the tracked payload
# builders - restating them here would let the probe drift from the shapes the suite asserts.

# --- the /tokenize accounting recipe and the decode-cap latency probe are RETIRED to progress.txt.
#     D-c is landed, deployed and measured (7.571x on the deployed engine); the cap derivation is
#     re-checked on every run by `cap_derivation_holds` in live-pipeline-probe.py's report. --------
# --- secret-hygiene scan (lives with the tracer spike, not in scripts/ralph-afk) ----------
bash "/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/spikes/idea-044-real-uds-tracer/leak-scan.sh"

# --- Phase A compatibility checkpoint (historical; frozen at 1ede498) ----
# Run the exact eleven registered commands from:
# /Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/context/VALIDATION_COMMANDS.md
# section "IDEA-044 attempt-2 exact commands". `validate-phase-a-locality.sh` belongs to that
# checkpoint and now fails on the tip by design — see the locality note above.

# --- the pre-redeploy manifest admission check (read-only; run before ANY live restart from H2 on).
#     Both new refusals fail the service closed, so check them before bouncing the unit, not after.
#     Expect endpoint == bounds == 40000, speech_provider.frame_samples in {160,320,480}, and no
#     `session_hard_cap_samples` anywhere in the document. -----------------------------------------
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

# --- keeper merge #1: SPENT in iteration 16, main was f9285d6. ----------------------------------
# --- keeper merge #2: SPENT in iteration 5 of run 20260728-072601. main is now 317df4d. ---------
# --- keeper merge #6: SPENT in iteration 19 of run 20260728-181020. main is now 77e0014, and the
#     six spent pre-merge SHAs in order are af3ac36 / f9285d6 / 317df4d / b817871 / 6a540fe /
#     fc7097d. Both fences satisfied honestly again: join 1b6a9f4 proven content-free by
#     `git merge-tree --write-tree main HEAD` == HEAD's own tree BEFORE running it, then
#     expected_main advanced in-script and committed as 4ac5d95 so it became the captured tip.
# Both fences were satisfied honestly (join first, then the in-script expected_main) and the guard
# is live again: the dry run below now REFUSES, which is the proof no further merge can slip through.
RALPH_MERGE_DRY_RUN=1 bash scripts/ralph-afk/merge-keeper.sh   # expect rc=1, "main moved from …"
# To dry-run the guard while the tree is DIRTY (e.g. to check a proposed expected_main before
# committing it), the script needs BOTH flags — RALPH_MERGE_DRY_RUN=1 alone still refuses:
#   RALPH_MERGE_DRY_RUN=1 RALPH_MERGE_ALLOW_DIRTY=1 bash scripts/ralph-afk/merge-keeper.sh
# If a further merge is ever authorized, run the script in the BACKGROUND: a foreground timeout kill
# skips its EXIT trap and strands a worktree holding `main`, which then blocks the retry. Recover
# with: git -C <wt> merge --abort && git worktree remove --force <wt>

# --- M6c: publish + redeploy the SIXTH merge (SPENT in iteration 20 of run 20260728-181020) ------
# The push fast-forwarded fc7097d..77e0014; never re-run it and never force-push. The K5c shape
# again (server restart AND a Mac rebuild+reinstall). Everything K5c's block below says still holds;
# only the three things this run ADDED are recorded here.
# 1. PROVE THE VENV RESOLVES THE PACKAGE FROM THE CHECKOUT, or "restart picks up the checkout" is an
#    assumption. One line, read-only, under the SERVICE's own interpreter:
#      "$HOME/.local/share/moss-transcribe-diarize/venv/bin/python" -c \
#        "import moss_transcribe_diarize.app.live_adapters as a; print(a.__file__)"
#      # must print /mnt/d/Coding/MOSS-Transcribe-Diarize/... — an editable install
# 2. EXERCISE the deployed change instead of hasattr-ing it. For D-c, on the host:
#      canonical_decode_token_cap(sample_count=40000) -> 286 ; (sample_count=8000) -> 112
#      NOTE the parameter is KEYWORD-ONLY; a positional call raises TypeError, which under
#      `2>/dev/null` looks exactly like the symbol being absent.
# 3. A STRINGS WITNESS NEEDS A CONTROL WORD. New-vs-backup 1/0 proves the bytes changed; a third
#    word present in BOTH proves the grep works and the 0 is a real absence:
#      for w in macos_health_facts_dropped degraded macos_buffer_overrun; do
#        strings -a <binary> | grep -c "$w"; done      # new 1/1/1, pre-M6c backup 0/0/1
#    Run it on the APP binary too, not only the CLI — the app is what captures.
# Rollback for THIS install (the ONLY copy of the fc7097d bytes):
#   rm -rf '/Applications/MOSSCapture.app' && mv '/Applications/MOSSCapture.app.backup-20260728T222244Z' '/Applications/MOSSCapture.app'
#   rm -f  '/Users/ga0/.local/bin/mtd-capture' && mv '/Users/ga0/.local/bin/mtd-capture.backup-20260728T222244Z' '/Users/ga0/.local/bin/mtd-capture'
# Two traps this run hit, both of which report a SKIPPED check as a passing one:
#   * `set -o pipefail` + `ls /tmp/glob-with-no-match 2>/dev/null | wc -l` -> ls exits 2, the
#     pipeline fails, `set -e` aborts, and every later check silently never runs.
#   * `live-runs/` is /mnt/d/Coding/MOSS-Transcribe-Diarize/live-runs (the unit's --runs-dir), NOT
#     under ~/.local/share. A "0 entries" answer from a nonexistent path is not evidence.
# --- m4mbp rebuild + reinstall (the half J5c did NOT need). Stop any running app FIRST or the
#     re-read interrogates the old product: pkill -f '/Applications/MOSSCapture.app/Contents/MacOS/MOSSCaptureApp'
#   git fetch alphasight main --quiet && git checkout fc7097d…   # rollback: checkout 6a540fe…
#   macos/scripts/build-app.sh --dry-run && macos/scripts/build-app.sh --configuration release
#   macos/scripts/install-app.sh --dry-run && macos/scripts/install-app.sh
# Rollback for THIS install (the ONLY copy of the pre-K5c bytes; SwiftPM is not reproducible here):
#   rm -rf '/Applications/MOSSCapture.app' && mv '/Applications/MOSSCapture.app.backup-20260728T191937Z' '/Applications/MOSSCapture.app'
#   rm -f  '/Users/ga0/.local/bin/mtd-capture' && mv '/Users/ga0/.local/bin/mtd-capture.backup-20260728T191937Z' '/Users/ga0/.local/bin/mtd-capture'
# MEASURED, not assumed: the TCC grants SURVIVE a rebuild+reinstall (both still auth_value=2) even
# though the inode changes (211648186 -> 211995344). They are keyed to bundle id + signing identity.
# Always re-run the E3 read-only query after any reinstall anyway — it is the one input this loop
# cannot re-obtain, and it costs one ssh.
# Prove the INSTALLED product (not just the checkout) carries the cycle, with a DISCRIMINATING
# witness — a vocabulary absent from the backup binary and present in the new one:
#   strings /Users/ga0/.local/bin/mtd-capture | grep -c '^sessionRefusal$'          # 3 (K4)
#   strings /Users/ga0/.local/bin/mtd-capture.backup-20260728T191937Z | grep -c '^sessionRefusal$'  # 0
# --- the J5c and K5c and D1 publish/redeploy recipes are RETIRED to progress.txt; M6c above is the
#     kept template (it is the strictly larger one: restart AND Mac rebuild). ----------------------
# --- m4mbp: `origin` IS NOT THE ALPHASIGHT FORK THERE. The names are INVERTED relative to this
#     host: on m4mbp `origin` = OpenMOSS upstream and the fork is `alphasight`. `git fetch origin`
#     there fetches the wrong repo and the checkout then fails `fatal: unable to read tree (<sha>)`,
#     which looks like corruption and means "never fetched". Resolve the remote by URL:
ssh -o BatchMode=yes ga0@m4mbp 'cd /Users/ga0/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize && \
  git remote -v | grep AlphaSightInc'
#   then: git fetch alphasight main --quiet && git checkout <sha>     # rollback: checkout 317df4d…
#   Check whether the app was disturbed (STALE PREMISE: iteration 6 proved the inode does NOT carry
#   the TCC grants — the bundle id + signing identity do; see the K5c block):
#     stat -f "inode=%i mtime=%Sm" -t "%Y-%m-%dT%H:%M:%SZ" /Applications/MOSSCapture.app
#     current: inode=211995344 mtime=2026-07-28T15:19:30Z  (K5c's rebuild; was 211648186 from G6)
# --- m4mbp cannot reach the batch service and that is TOPOLOGY, not a regression: m4mbp is
#     192.168.1.240, the batch address is 192.168.68.38 (different LAN, 100% loss). The hosts meet
#     only on the tailnet 100.64.0.4 -> 100.64.0.8. Measure the batch clause from MacStudio.
# --- H4c's redeploy, E2a's m4mbp checkout and D3's live-service install are SPENT and RETIRED to
#     progress.txt. All three are one-time steps whose result is in Deployed reality. --------------
# --- F4a: the rollback rehearsal (SPENT in iteration 8; re-runnable, and re-run it exactly in this
#     order — see the rollback-rehearsal block for why ExecStart forces it). Everything below is on
#     the server; pipe each as a script on stdin per the remote-quoting gotcha. -------------------
systemctl --user disable --now moss-live-web.service          # rollback: enable --now
git -C /mnt/d/Coding/MOSS-Transcribe-Diarize checkout 163e969  # rollback: checkout 317df4d…
# ... assert from a client: 7861 dead (000) on tailnet AND LAN, http://192.168.68.38:7860/ 200,
#     /api/jobs 200 (141 jobs), /api/runtime 200; batch MainPIDs 322117/301112 with NRestarts=0.
# ... optional, and worth it: the batch-restart argv probe below, run at 163e969, must still print
#     tests/test_live_service_deployment.py:51-62's BATCH_ARGV.
git -C /mnt/d/Coding/MOSS-Transcribe-Diarize checkout 317df4d728b6765dbe365a3166158ba581299557
systemctl --user enable --now moss-live-web.service
# Then POLL (~10 s) for https://127.0.0.1:7861/live -> 200; a single probe at 6 s returns 000.
# Stop condition: the served leaf must still hash to the D2 pin a35ca9fc…, else every paired Mac
# is broken — do not proceed, record a blocker.
# While rolled back, `git status --porcelain` reports `?? ops/moss-live.env`. That is expected.
# NEVER `git clean` there: it would delete the untracked live profile the restore depends on.

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
24. **F1 — 60 s canary** per prd.md. `[GREEN — run 20260729-025318 iteration 6, rc=0; see the
    F1-green block. The RED history below is iteration 8's run and is kept only for what it
    diagnosed.]` See the F1
    block above. Green: continuously updating labelled transcript (42 spans, version 0 → 283),
    decoder p95 RTF **0.706**, zero double count (340 published == 340 accepted), run-time secret
    hygiene, no raw audio persisted. Red: **user-visible p95 10426 ms vs ≤ 4000 ms**, and **0.5 s of
    system-lane loss** to a mid-meeting `macos_buffer_overrun`. The diagnosis (candidate 50) is the
    part that matters; the label/marker clauses are confounded by the harness (candidate 51) and
    must be re-run, not re-argued. F1 is re-runnable end to end from
    `/tmp/ralph-f1-canary.sh` and costs no operator input.
25. **F2 — 300 s locked run** with 5 s interruption and the system-audio-denied variant.
    `[GREEN — iteration 11, rc=0, six GREEN / no RED / no UNDECIDED; see the F2-green block]`.
    user-visible p95 **3859.6 ms** ≤ 6000 qualified, decoder p95 RTF **0.670**, a **5.050 s**
    interruption seen and survived, **1257 published == 1257 accepted, every one of the session's
    4748 HTTP requests 200**, outbox 0 → 10 → 0, clean drain. **The denied-lane half is still open
    and is NOT a scripting problem** — it is a separate
    run by the PRD's own wording and producing it means taking a TCC grant away from
    `com.alphasight.moss.capture`, i.e. spending the one input this loop is forbidden to ask for
    again. It needs its own recorded plan before anyone writes code for it.
26. **F3 — 16-minute active-view soak**: capture and `/live` polling stay active with periodic
    two-lane audio; same authority works after minute 15; clean stop immediately revokes it.
    `[RE-RUN against `42abc5a` — 5 GREEN, 1 RED — run 20260729-025318 iteration 9. See the F3 block
    above; the RED is candidate 60, and the two soak halves this entry called "unproven" are now
    PROVEN: the same authority answered 200 at age 1024.1 s. Only "clean stop immediately revokes
    it" fails, and it fails for a reason nothing to do with the soak.]*
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

55. **Identity capacity saturates in the first minute** (iteration 12). The 16-speaker bound is
    reached at t+45.5 s (t+51.8 s in F1), so a voice arriving later can never be labelled. Degrades
    quality without ending a session, so no gate sees it. Tracked product source; **needs its own
    authorization**. **PRICED IN ITERATION 16 and NOT subsumed by the album**: the accuracy harness
    reproduces it offline and deterministically — all eight fixture meetings exhaust 16 canonicals
    for 2–6 real voices *with the album on*, and lifting the bound to 32/64 moves the album from
    **93.4 % → 97.9 % / 98.7 %**. So it costs **4.5 pp of live speaker accuracy** and is the whole
    of the gap between production and ADR-0002's 98.5 %. The album was the hypothesis for its cause
    and the hypothesis is now measured wrong: births are unchanged by design, so the fragmentation
    survives the fix. It needs its own authorization and its own mechanism.
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
60. **A clean stop never reaches the server, so it does not revoke view authority.** `[open, new —
    run `20260729-025318` iteration 9; **F3's one RED**]`. `CaptureController.stop` drains and
    returns; no client code path calls `POST /api/live/sessions/{id}/stop`, which exists at
    `live_transport.py:325` and is covered by `tests/test_live_api.py:502`. Measured: view authority
    answered 200 for **29.4 s** after a clean stop, until the 30 s helper lease expired. Bounded and
    self-healing, but it is the PRD clause's word *immediately*, and it was already visible in F1's
    "29 s after the run's own stop" line without being named. Tracked product source under `macos/`;
    **needs its own authorization**. Full detail in the candidate-60 block above.
58. **The replay evaluator calls a declared absence an invalid measurement.** `[open, new — run
    20260729 iteration 1]`. `live_service_replay._canonical_decode_rtf_evaluation` fails the RTF
    summary for a `canonical_processed` event whose `canonical_decode_elapsed_sec` is null, so a
    *degraded* measurement is indistinguishable from a *corrupt* one — iteration 29's lesson one
    layer down. Pre-existing (J3 has emitted nulls since Phase J) but now reachable by design.
    Tracked product source; needs its own authorization and a recorded decision about what a run
    with degraded spans should be allowed to certify. The exact site is
    `live_service_replay._canonical_decode_rtf_evaluation:660-694`, which runs every payload through
    `_required_finite_non_negative_float`; detail in progress.txt under `Phase P candidate list…`.
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
    See the candidate-63 block below. *Originally:* `[open, new
    — iteration 16]`. `identity_config.min_match_score` **0.5** / `min_match_margin` **0.2** are what
    the live runtime ships; ADR-0002 §7's measured starting values are **0.35 / 0.1–0.2**. Measured
    on production code over the eight-meeting fixture: the album scores **93.4 %** at 0.35/0.1,
    **91.0 %** at 0.35/0.2 and **75.0 % (min 40.0 %)** at the deployed 0.5/0.2 — i.e. *below
    ADR-0002's ≥ 90 % bar at the only configuration that would actually run*. Phase N's own
    acceptance bar is therefore unreachable without this, which makes it a shipping requirement
    rather than a refinement; the ADR says as much (*"matcher thresholds need recalibration against
    album centroid statistics"*). The change is a **generated, hash-covered manifest** field, so it
    is tracked product source under the post-merge freeze and **needs its own authorization** — and
    the eighth amendment already warns that changing these *"is a decision to record, not a knob to
    tune until green"*. Reproduce with `tests/live_identity_accuracy.replay_all`; see the N-gate
    block.
62. **The reducer asked a certification run the soak's questions.** `[done — iteration 11]`. See
    "THE REDUCER STOPPED ASKING A CERTIFICATION THE SOAK'S QUESTIONS" in progress.txt. Loop tooling; it made
    F2 ungreenable for candidate 60, a defect outside F2's clause list.

### Phase N - live speaker identity - FOLLOW ADR-0002, NOT THE SIXTH AMENDMENT

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

**N-album — STEP 1 IS LANDED IN SOURCE** `[done — iteration 15; NOT gated, NOT merged, NOT
deployed]`. New `moss_transcribe_diarize/app/live_identity_album.py` (`FingerprintAlbum`), wired
into `WeSpeakerLiveEvidenceProvider` and `_identity_evidence_provider`. Payload **4 files**, all
under `moss_transcribe_diarize/` + `tests/`; **none under `macos/` or `ops/`**. Python
**635 / 2 / 368** (+27). ***The red-before is on the real seam and needs no revert to reproduce,
because the old policy is still reachable as `album=None`:*** same voice, three spans (2.0 s enroll
→ 0.5 s fragment of a different voice → the original voice again) scores **0.0 pre-album and 1.0
with the album**. That single pair of numbers *is* ADR-0002's 66.4 %-vs-98.5 % defect, reproduced
offline in one command.
***The four decisions this step took, with the reasoning, so they are not re-argued.***
1. **Admission is 1.0 s, and `min_segment_samples` does NOT move.** The sixth amendment's flat
   "≥ 2.0 s enrollment floor" is superseded; the eighth says the top-k admission gate does the work
   that floor was compensating for. `min_segment_samples` is the **evidence** floor — it decides
   which local speakers get embedded and scored *at all*, so raising it would make short spans
   unlabelable, the exact opposite of the asymmetry. 1.0 s over 2.0 s because ADR-0002's gate A
   passed at 1.0 s **under production live semantics**, and a 2.0 s admission under a 2.5 s span cap
   with 0.6 s silence splits would starve the album.
2. **The margin half of admission is already enforced upstream, so it is recorded, not
   re-implemented.** ADR-0002 admits on "≥2 s clean speech **and** sufficient match margin". The
   album only ever observes assignments out of a **`prepared`** preparation, and
   `BoundedCausalIdentityPreparer._match_rejection_reason` abstains for the whole span when a match
   fails `min_match_score` or `min_match_margin` — so an assignment that reaches the album carries
   the margin by construction. A second margin knob would have had no independent evidence behind it.
3. **A provisional stand-in, because ADR-0002 requires birth semantics to be unchanged.** Under a
   pure admission gate a speaker born from a 0.6 s span would have **no reference at all**, would
   never be matchable, and every recurrence of that voice would birth another id — strictly worse
   than candidate 55 measures today. One sub-admission observation per speaker is kept while the
   bank is empty and **discarded, never averaged**, by the first admitted exemplar.
4. **Tie rules differ by tier, on purpose.** The bank replaces the oldest equally-long exemplar (an
   exemplar is a *sample* of a voice and benefits from recency, so an album filled in minute one
   still tracks the meeting); the stand-in keeps the incumbent on a tie (a placeholder benefits from
   not churning, and churn is the defect being removed).
*Also fixed in the same function, because leaving it would have been worse than touching it:*
`_pending_vectors` was popped only on a **prepared** reconcile, so every abstain leaked a span's
vectors for the length of the meeting — and an abstain is a *designed* outcome (J2). Now bounded at
`_PENDING_SPAN_LIMIT = 8`. Red-before by absence: `git show HEAD:…live_provider_bundle.py |
grep -c _forget_stale_pending` → **0**.
*Manifest surface, deliberately optional:* `identity_provider.album_admission_seconds` and
`album_exemplars_per_speaker` override the ADR defaults **when present**. The deployed manifest is
generated and hash-covered, so requiring the keys would refuse the document running today; absent
keys mean ADR-0002 §7's values, and the ADR's recalibration stays a manifest edit.
**What N-album does NOT do, stated so a green suite is not mistaken for a finished job.** ADR-0002
classes the album alone as a **terminal-state failure**: without the retrospective sweep, live
accuracy diverges from whole-file. It also does **not** fix candidate 55 — births are unchanged by
design, so `Hi.` fragments still mint canonical speakers and still exhaust the 16-speaker bound.
And its acceptance bar's accuracy half was **not measurable by anything in this repo** until
iteration 16 built the harness below; the convergence half still is not, because it needs step 3.
*Superseded by measurement:* this block's guess that the album might explain candidate 55 is wrong —
see candidate 55 and finding 2 under N-gate.

**N-tape / N-sweep / N-batch — steps 2, 3 and 4, open.** Tape recorder (per-lane + mixed durable
assembly with a gap manifest and a retention TTL), retrospective sweep (re-VAD/re-embed/re-cluster
the tape, seeded by live labels, **never re-ASR**, versioned silent corrections), then batch Tier-B
unified onto the same album engine. Step 2 is where the PRD's *"no raw audio is persisted"* clause
and the ADR's retention posture collide; the PRD amendment says to re-read the clause against the
ADR, which is a decision to record before any code, not a licence to start writing audio.

**N-gate — THE HARNESS EXISTS AND THE ALBUM IS MEASURED ON PRODUCTION CODE** `[iteration 16]`.
`tests/live_identity_accuracy.py` + `tests/test_live_identity_accuracy.py` +
`tests/fixtures/live_identity_accuracy/` (8 meetings, 1.85 MB). It drives the **real**
`BoundedCausalIdentityPreparer` + `WeSpeakerLiveEvidenceProvider` + `FingerprintAlbum`, span by
span, snapshot carried forward exactly as the coordinator does; only the ONNX forward pass is
substituted, by replaying the **real** encoder's cached vectors. 21 nodes, Python **656 / 2 / 368**
(+21, +11 s). Full table in progress.txt under `THE LIVE IDENTITY ACCURACY HARNESS`.
*Numbers, at production defaults + ADR-0002 §7 thresholds (`min_score` 0.35, margin 0.1,
admission 1.0 s, k=10, cap 16):*

| | mean | min | ADR-0002's own figure |
| --- | --- | --- | --- |
| **album** | **93.4 %** | 92.2 % | 98.5 % (96.4–99.5) |
| **overwrite** (`album=None`, still reachable) | **72.0 %** | 55.7 % | 66.4 % (51.7–87.4) |

***Four findings the unit suite could not have produced.***
1. **The gap is +21.4 pp and the album clears ADR-0002's ≥ 90 % bar on every meeting** — so
   step 1 is measured, not asserted. The **red-before needs no revert**: the same assertions run
   against `policy="overwrite"` give 72.0 % mean / 55.7 % min.
2. **The 16-speaker bound is what holds production 5 pp under the ADR.** At cap 32 the album is
   **97.9 %**, at cap 64 **98.7 %** — and overwrite at cap 64 is **66.4 %**, *the ADR's own number
   to one decimal*. That coincidence is the strongest available check that this harness measures
   what ADR-0002 measured, and it prices **candidate 55**: 4.5 pp of live accuracy, deterministic,
   offline, every meeting saturating 16 canonicals for 2–6 real voices.
3. **Accumulation does the work; the admission floor is nearly free of effect.** adm 0.01 → 93.5 %,
   adm 1.0 → 93.4 %, adm 2.0 → 93.4 %; but k=1 → **79.2 %** and k=3 → 89.7 %. A full bank *is* a
   duration gate (`_admit` evicts the shortest), so the floor's real job is the birth path. **The
   superseded sixth amendment's central instruction — "raise the enrollment minimum to ≥ 2.0 s" —
   is refuted as the load-bearing change**, and ADR-0002's "the top-k admission gate does the work
   that floor was compensating for" is right about the *k*, not the *duration*.
4. **The deployed matcher thresholds cost the album its bar.** At the shipping `min_match_score`
   0.5 / margin 0.2 the album measures **75.0 % mean, 40.0 % min** — below the bar entirely; at
   0.35/0.2 it is 91.0 %. ADR-0002's "matcher thresholds need recalibration" is therefore a
   **shipping requirement**, not a refinement, and it is a tracked-source change needing its own
   decision. (Overwrite at the deployed thresholds is 35.2 %.)

**N-gate — what is still open.** Live→file convergence (needs the sweep, step 3); F1/F2 with the
label clause meaningfully verified — still blocked by candidate 51's measured hardware limit; then
one merge, push, redeploy. The accuracy half of the bar is now instrumented and green for step 1.

**N-recal — THE CALIBRATION THE ALBUM IS MEASURED AT IS NOW THE ONE A DEPLOYMENT CAN STATE**
`[candidate 63, iteration 17; source only — the host manifest is regenerated at Phase N's redeploy]`.
Payload **6 files**: `live_identity_album.py`, `live_manifest_finalizer.py`, `LOCAL_DEPLOYMENT.md`,
and three under `tests/`. Python **662 / 2 / 368** (+6). ***The red-before is the whole existing
finalizer suite:*** with the flags made required, all 17 pre-existing nodes fail until the helper
states a calibration — which is exactly the defect, since until now `identity_config` was *carried
through untouched* from an untracked host file that no review has ever seen.
***The three decisions, recorded so they are not re-argued.***
1. **The values are ADR-0002 §7's — 0.35 / 0.1 — and they needed no ninth authorization.** prd.md's
   supersession section names them; the sixth amendment already ruled the pair *free*. Measured on
   production code over the eight-meeting fixture: **93.4 % mean / 92.2 % min** at 0.35/0.1 against
   **75.0 % / 40.0 %** at the deployed 0.5/0.2 — the difference between clearing ADR-0002's ≥ 90 %
   bar and missing it entirely.
2. **The tool states them; it does not default them.** A free parameter has no derivation a tool
   could verify, so a built-in default would be a guess wearing a contract's clothes. Required flags
   put the pair in the plan (`plan: set identity_config.min_match_score=0.35`), in the evidence
   (`evidence: identity_min_match_score=0.35`) and in the regenerated `identity_config_hash`. The
   *named* pair lives in `live_identity_album.py` beside the policy it calibrates, and
   `tests/live_identity_accuracy.py` now imports it rather than holding a second copy — so
   "measured at one pair, deployed at another" is no longer expressible.
3. **The check is the runtime's own reader, not a second copy of its rules.** `_identity_config`
   from `live_provider_bundle` validates the finalized section; a refusal reads
   `refused: identity_config is not one the live runtime admits: min_match_score must be between
   0 and 1.` Three parametrised nodes prove it.
***What this does NOT do.*** The deployed host manifest still carries 0.5 / 0.2 — nothing on the
server was touched. Until Phase N's redeploy regenerates it, **the live service would run the album
at 75.0 %**. And the regeneration *will* change `identity_config_hash`, `combined_config_hash` and
the provider manifest hash away from `61d97ffe…`; that is the recalibration's signature, not drift.

### (superseded) Phase N as first written (2026-07-28, sixth amendment; AFTER Phase M)

Authorized by the sixth prd.md amendment, which **overrides** the out-of-scope entry for
intermittent-speaker identity calibration. **Do not start until Phase M's gate is green** - identity
quality cannot be certified on a meeting that dies at minute 14.6.

Measured by the supervisor on the real encoder (numbers and method in the amendment):
- deployed enrollment floor 0.5 s gives same-speaker agreement **0.378** against cross-speaker
  **0.360** - no separation, and below the deployed `min_match_score` 0.5;
- separation appears at ~2 s (0.715 vs 0.289) and is clean by ~4 s;
- strategy A (today, `live_provider_bundle.py:597` replacement) oscillates 0.95 -> 0.51 between
  spans; C (duration-weighted centroid) reaches 0.975 oracle alignment at ~1.1x today's cost;
  B (re-embed 0..t) reaches 0.999 but is quadratic (~23 min compute for a 16-min meeting) **and**
  has the worst short-probe match. B is rejected on evidence.

**Numbering, repaired in iteration 29 — Phase N items are `N1`-`N5` and carry NO number.** They
were minted as 55-59 by the sixth amendment on the same day iterations 12 and 26 minted diagnostic
candidates **55, 56 and 57**, so every one of those three numbers meant two different things and
"candidate 56 needs authorization" resolved to *either* the viewability blocker *or* the centroid.
The amendment and every cross-reference already say `N1`-`N5`, so dropping the duplicate numerals
costs nothing and the three diagnostic numbers are now unambiguous.

- **N1 - separate matching from enrollment.** The core defect: one threshold does both jobs, so a
  0.5 s fragment can overwrite a good prototype. A short span may be *labelled* against a
  prototype; it must never *become* one. Everything else in this phase depends on this split.
- **N2 - duration-weighted centroid (strategy C).** Wire it through the `canonical_embedding` hook
  that already exists in `WeSpeakerLiveEvidenceProvider.__init__` and that
  `_identity_evidence_provider` never passes. O(1) memory and compute per span.
- **N3 - raise the enrollment minimum to >= 2.0 s.** `identity_provider.min_segment_samples` is
  **not** a domain-contract value; the contractual 8000 is the *live frame size*, a different
  quantity sharing the number. Do not change the frame size. Treat 2.0 s as a lower bound - the
  supervisor's voices were synthetic TTS and cleaner than real humans.
- **N4 - bounded bank (strategy D), only if measurement justifies it.** D and C were within 0.2%
  of each other; adopt D only if a prototype must demonstrably survive a bad patch.
- **N5 - gate, merge, redeploy.** A tracked regression reproducing the duration curve that fails
    if the enrollment floor drops below the measured separation point; C must beat A on oracle
    alignment **and** same-speaker probe minimum on the real encoder; then F1 and F2 with candidate
    51's distinct-voice harness and the speaker-label clause **meaningfully verified**; then one
    merge, push, redeploy.

Keep the abstain path throughout: an ambiguous span stays unlabelled rather than guessing, and J2
already ruled that an abstain must not end the meeting.

### Phase P — CLOSED; the candidate list is retired to progress.txt

The seventh amendment's cycle (P1 monotonic measurement, P2 untrustworthy timing degrades, P3 four
real-seam nodes, P4 the class swept) landed at `5bc4f7f`, merged as `42abc5a`, deployed 4/4, and is
proven dead on the server. The rule it shipped is the **Duration vs timestamp** row in Shipped
contracts; the numbers are in the Phase P gate and P7 merge rows of the gates index. The full list —
including P4's four-site sweep table and P3's per-half red-before table — is in progress.txt under
**"Phase P candidate list (P1-P5, the sweep table, the per-half red-before table)"**.
**Its one open leftover is candidate 58**, in the numbered list above: the replay evaluator calls a
declared absence an invalid measurement. Explicitly out of scope then and now: mandatory client
retention of the 409 refusal body — the right fix, needing its own authorization.

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
