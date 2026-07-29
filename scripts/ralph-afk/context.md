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
  Python 608/2/368 green. See the Phase P block.
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
- **Phase N (live speaker identity) is authorized but gated** behind Phase M's green. F3 has now run
  and is **not** unconditionally green — one clause fails on candidate 60. *Whether that gates
  Phase N is the operator's call, and the evidence for either answer is in the F3 block:* the
  amendment's reason for sequencing N after M was "identity quality cannot be certified on a meeting
  that dies at minute 14.6", and **that meeting no longer dies** — it ran 17 minutes with a degraded
  lane. Candidate 60 is a stop-time authority-revocation defect that cannot affect an identity
  measurement taken during the meeting.
- **F2 RAN AND IS GREEN (iteration 11).** That was the loop's one unblocked PRD acceptance clause
  and it is now spent. **Nothing measurable is left that the loop can do alone.** What remains:
  (1) candidate 60 — F3's one RED — is tracked product source under the post-merge freeze and needs
  an eighth authorization; (2) candidates 55 and 58 likewise; (3) **Phase N is authorized but gated
  on "Phase M's gate green"**, which F1 GREEN + F2 GREEN + F3 5-GREEN/1-RED leaves as the
  operator's call, not the loop's; (4) the PRD's F2 **system-audio-denied variant** and F1's
  "two speakers" half are both blocked on inputs the loop is forbidden to spend or has measured it
  cannot produce (see those two blocks); (5) F4b closes only when everything else has evidence.
- **Candidate 57 — the clause reducer called a passing latency number RED** `[done — iteration 29]`.
  Loop tooling, no authorization; fixed and proved on four real evidence directories. See "The
  reducer stopped calling a passing number RED" below.
Candidates 55 and 56 are tracked product source under the post-merge freeze. **Candidate 54 is ANSWERED**
(iteration 11) and **candidate 51 is DONE** (iteration 12), neither spending an authorization: the
409 is `LiveV2SessionTerminalError` — `"v2 system lane is failed."` — armed by the client's *own*
heartbeat, **not** the `v2_out_of_order_frame` that was on record as likeliest; and the two lanes
now carry different content, which took no product change at all. See those two blocks and Phase M.

**E3 was the blocker for four runs; the clicks were necessary and not sufficient.** Both grants are
recorded and survive a bundle replacement. **Never ask the operator for those clicks again.**

**Test totals on the branch.** Swift **158 passed**
(67 → 81 → 92 → 95 → 98 → 106 → 116 → 121 → 131 → 132 → 134 → 139 → 142 → 146 → 150 → 151 → 154
→ 158); Python **608 passed / 2 skipped / 368 subtests** (604 → 608 with Phase P's four seam nodes,
run `20260729-025318` iteration 1) — the two skips are the pre-existing
`tests/test_large_upload.py:155,175` Python-3.10 compatibility contract, **never** Darwin skips.
Per-file: `test_live_pipeline_seams.py` **60**, `test_live_identity.py` **8**,
`test_macos_uds_tracer.py` **4 / 0 skips**, `test_macos_packaging_tools.py` **9**,
`test_live_manifest_finalizer.py` **17**, `test_live_deployment_credentials.py` **14**,
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
  **TRUE FOR PRODUCT SOURCE since run `20260729-025318` iteration 5**: the deployed SHA on every host
  is `42abc5a` and the only paths that diff are the operator's two `docs/` files from `00620ab`,
  which no runtime reads. Read the rule as *no product source, no test, no `ops/`* — it was never
  about docs, and a blanket "non-empty" reading of it would now block every probe for no reason.
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

**PHASE P IS DEPLOYED AND CANDIDATE 56 IS DEAD ON THE REAL SERVER — P5(c), run `20260729-025318`
iteration 5. READ THIS BEFORE F1 OR F3.** `42abc5a` is published and running on all four checkouts,
and *the identical probe invocation that killed a session at t+31.5 s three iterations ago now runs
its whole plan.*

***The green-after, and it is the SAME command as the red-before.*** 150 s from MacStudio over the
tailnet: `--lane-audio continuous --lane-offset-ms system=137 --lead-seconds 0
--concurrent-readers 2 --reader-interval 0.22`, byte-for-byte iteration 28's invocation, device
`ralph-i5-p5c-verify-20260729T032746Z` (**revoked**, 13 devices / 1 unrevoked). Report
`/tmp/i5-probe.json`.

| | iteration 28, on `77e0014` | iteration 5, on `42abc5a` |
| --- | --- | --- |
| ticks | died at **63 of 300** (t+31.5 s) | **300 / 300**, wall 150.01 s |
| `POST /frames` | **409**, `non_200_count` 1 | **`non_200_count` 0** |
| the two view readers | **both 401 at 31.287 / 31.289 s** | **463 + 462 polls, every one 200** |
| accounting | 64+63 frames, then nothing | `accepted == accounted == committed == 2 400 000` (exactly 150 s) |
| spans | 11, then terminal | **60 committed, 0 empty**, `terminal_failure` null, status `closed` |

Also green in the same run: **6 canonical speakers**, 22 unattributed spans published as `S00` (J2
holding at volume), decode **62/62 measured**, `capped 0`, `cap_derivation_holds` true, and view
authority correctly 401 **after** the stop. Host after: `HEAD 42abc5a` clean, live MainPID 355607 /
`NRestarts=0`, batch **301112 / 322117** and `NRestarts=0` unmoved, batch `/` 200, `live-runs` 0,
no `/tmp/mtd-live-*`, **0** journal tracebacks.

***Why a 150 s survival is not the whole argument, and what makes it conclusive anyway.*** Iteration
27's 150 s run **also** survived on the broken build — at ~13 % duty cycle a 150 s window carries only
~0.6 expected kills, so survival alone proves little. Three measurements together do:
1. the hazard was **live during this very run** — the host clock still steps **−1.464 / −1.437 /
   −1.466 s at 32.29 s intervals**, measured immediately after (see Deployed reality), so ~4-5 steps
   fell inside the 150 s;
2. the **deployed source can no longer reach the wall clock** on the decode path — verified under the
   service's own venv, not by SHA: `vllm_runner` and `model_runner` each hold **0** `time.time() - `
   and **1** `time.monotonic() - `, and `RunnerBoundedWavInference.transcribe_pcm` no longer contains
   `_runner_elapsed_sec` at all while it does contain `time.monotonic() - started`;
3. the failure record itself is reproduced **field for field from a test** by P3's seam nodes, so the
   red-before does not depend on catching a host in the act.

***The honest limit, so nobody misreads the journal.*** `spans_measured == spans_total == 62` and
**0** `live.decode` WARNINGs — i.e. **no span degraded to a null elapsed**. That is the *expected*
green shape, not a sign the fix is inert: P1 removed the wall clock from the measurement, so P2's
null path is defense in depth for a *different* untrustworthy input and is exercised by the seam
tests, never by this host. A run that logged P2 degradations would mean something else is wrong.

***And this is the PRD's `decoder p95 RTF < 1` clause's first trustworthy measurement.*** Every RTF
this project ever recorded came off the stepping clock. Measured monotonically across 62 spans:
**p95 0.18**, p50 0.131, max 0.288, `p95_under_bound` true; elapsed p95 0.45 s, max 0.72 s.

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
transcript. `live-canary-analyze.py` scores it **absent** because it matches the word exactly, so it
printed `rc=5` on a run whose marker clause holds. Logged as **candidate 59** — same shape as 57.
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

**F2 HAS AN INSTRUMENT, AND THE 5 s NETWORK INTERRUPTION IS PROVEN ON THE REAL SERVER — iteration
10. READ THIS BEFORE RUNNING F2.** Three files, one logical instrument: `live-cert.sh` (m4mbp, the
300 s locked program), `live-cert-interrupt.sh` (the server, in WSL, the interruption) and
`live-canary-clauses.py --interrupt-report` (section 10). No product source, no `ops/`, no deploy.

***The mechanism, chosen against three alternatives rather than by convenience.*** A 5 s outage has
to leave the live SESSION alive or the rest of the run measures nothing.
| candidate | ruling |
| --- | --- |
| drop the tailnet on m4mbp | **rejected** — no passwordless sudo there, `tailscale` not on PATH (only `/Applications/Tailscale.app`), and **ssh to m4mbp rides the tailnet** (100.64.0.1 → 100.64.0.4), so a client-side drop strands the host behind a recovery path that may need GUI auth |
| restart/stop `moss-live-web` | **rejected** — the session lives in that process's memory; a restart destroys it. That is a server crash, not a network interruption |
| `kill -STOP`/`-CONT` the live process | **rejected** — it does produce client timeouts, but the server then RECEIVES every frame after CONT, so "the network dropped it" and "the server got it late" stop being distinguishable, and the clause is about audio retained *because it never arrived* |
| **`iptables -I INPUT ! -i lo -p tcp --dport 7861 -j DROP` for 5 s** | **CHOSEN** — packets dropped, process untouched, session survives. `! -i lo` keeps the server's own loopback (`ops/live-pair.sh`) working; `--dport 7861` cannot reach the batch service's 7860 |

***Measured twice on the live server, and the second run was the packaged script.*** Ad-hoc rehearsal
first (live 7861 timed out for ~4.6 s of observed drop while **batch 7860 answered 200 on all 22
probes**), then `live-cert-interrupt.sh --delay 4 --duration 5`: **`measured_duration_s` 5.110 on
CLOCK_MONOTONIC** (wall 5.108), `deletes` 1, `rule_still_present` **no**, `chain_after`
`-P INPUT ACCEPT;`. Server after both: `HEAD 42abc5a` worktree clean, live **355607** / batch
**301112** and **322117** all `NRestarts=0`, `live-runs` 0, no `/tmp/mtd-live-*`, **0** journal
tracebacks, batch `/` and `/api/jobs` 200. *The instrument measures itself on CLOCK_MONOTONIC on
purpose:* this host's wall clock steps ~1.5 s backwards every ~32.3 s (candidate 56), so a
wall-clock duration here could report a 5 s outage as 3.5 s — repeating in the instrument the exact
defect Phase P removed from the product.

***Three properties that are the point, not decoration.***
1. **It self-deletes from a detached `setsid` child, in a loop, so an orchestrator that dies
   mid-window cannot leave the live port blocked.** Rollback if it ever does:
   `sudo iptables -D INPUT ! -i lo -p tcp --dport 7861 -j DROP`, then `-S INPUT` must print exactly
   `-P INPUT ACCEPT`.
2. **Arm the server job BEFORE launching the driver.** Then nothing after launch depends on the
   orchestrator being alive — iteration 8's lesson. The price is clock skew, paid for by a **60 s
   wide** `program-interrupt` phase and **1 Hz** status sampling for the whole run.
3. **The reducer's positive control.** A run where the network never actually went down passes every
   other clause trivially and looks identical to one that survived an outage. So section 10 credits
   survival **only** if the client itself refused at least one poll inside the window; otherwise
   **UNDECIDED — "THE CLIENT NEVER SAW THE OUTAGE, so surviving it proves nothing."**

***And section 1 had to learn about the window, which is the near-miss worth recording.*** An F2 run
causes its own refusals on purpose; before this change the reducer called that
`RED the portal stopped answering 200 at t+42.7s` — *a run failed for the outage it exists to
produce*. Fourth instance of the class candidates 57 and 59 name. Excluded polls are **printed, never
subtracted silently**, and they must earn their keep in section 10.

*Validated:* `bash -n` on both drivers; the two real evidence directories reduce **byte-identically**
without the flag (F3 rc=3, F1 rc=0); six branches exercised on synthetic reports — real outage
**rc=0 GREEN**, no refusal seen **UNDECIDED**, `rule_still_present=yes` **RED**, short window
**UNDECIDED**, window outside the meeting **UNDECIDED**, report absent **UNDECIDED**. Cases
`/tmp/i10-case-*.txt`.
***Two corrections the real F2 run made to this block (iteration 11), both worth more than the
numbers above.***
1. **`--delay 215` is the wrong arming number and 240 is the right one.** The window must land inside
   the driver's `[T_START+200, T_START+260]` interrupt phase; with `Δ = T_ARM → T_START`, that needs
   `Δ ∈ [D-255, D-200]`. `D=215` tolerates only `Δ ∈ [0,15] s` — a scp, an ssh and two
   `system_profiler` calls can spend that. **`D=240` tolerates `Δ ∈ [0,40] s`** and is what the green
   run used. Measured `Δ` was 2.0 s and the drop landed at **T_START+226.7 s**, 33 s inside the phase.
2. **The report's `t_drop_begin_wall` is a SERVER wall-clock reading and must not be trusted to
   locate the window on the client's timeline.** The child sleeps monotonically but stamps the wall
   clock, and this host's wall clock is the one that steps (candidate 56): the report said
   `T_ARM + 229.2 s` for a 240 s delay, i.e. **10.8 s of apparent drift**. It happened not to matter —
   the reducer's `INT_SKEW` is ±6 s and the client's one refused poll landed 0.9 s inside the
   window — but that was luck, not design. *The client-side signal is the reliable one and it is
   unambiguous:* `publishedFrameCount` freezes and `outboxRetainedFrames` rises. A future run should
   correlate on that, or the child should stamp CLOCK_MONOTONIC **and** the arm-time offset.
*Known limits, stated so the run is not over-read:* `$OUT` on the server is **root-owned** (the child
runs under sudo) — readable by anyone, removable only with sudo. `wsl.exe -d Ubuntu -- bash -lc
"echo <base64> | base64 -d | bash"` **fails with "The command line is too long"** for a 6 KB script;
pipe the file on **stdin** instead (`ssh host "wsl.exe -d Ubuntu -- bash -c \"cat > /tmp/x.sh\"" <
file`, md5 verified). And the server's WSL user is **`devcontainers`**, reached as
`ssh gyauo@ga0-alienware-rtx4070ti.local` then `wsl.exe -d Ubuntu` — `ssh ga0@ga0-alienware-rtx4070ti`
is publickey-denied.

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

**THE REDUCER STOPPED ASKING A CERTIFICATION THE SOAK'S QUESTIONS — candidate 62 (new, iteration 11;
`[done]`). READ THIS BEFORE TRUSTING SECTION 9 ON ANY DIRECTORY.** `live-canary-clauses.py` keyed
"this is a soak" on the **presence of `view-checks.tsv`**, and `live-cert.sh` writes that file too.
So a 300 s certification silently acquired the 16-minute soak's two view-authority clauses: the
900 s boundary it cannot reach (**UNDECIDED**) and "a clean stop immediately revokes it" (**RED**, on
candidate 60). **F2 could never have gone green**, for a defect outside its own clause list that no
300 s run can reach — the fifth instance of the class candidates 57 and 59 name.
- **The discriminator is evidence, not a flag.** A soak is a directory that **declares**
  `VIEW_CLAUSE_AGE` in `times.env` — the boundary it asks to be measured against — which only
  `live-soak.sh` writes. A flag would be forgettable, and a forgotten flag is the silent-omission
  failure iteration 22 already paid for.
- **The certification still prints every line**, marked `OBSERVED (not a clause of this run)`.
  Nothing is subtracted silently; section 9's header states which reading it took and why.
- **Section 9(a) stays ASSERTED for both.** The per-minute accepted-audio floor is not the soak's
  "after minute 15" clause wearing another name: a minute of a locked 300 s program below the floor
  means the two lanes were not capturing simultaneously, which **is** F2's own first clause.
  Measured, so the silence window is not a false alarm: `accepted_samples` advances on every
  published frame whether or not anyone speaks — F3 speaks once a minute and still records
  57.8–61.5 s per minute.
*Red-before/green-after, on real evidence for the negative control and synthetic for the defect.*
**Five real directories reduce byte-identically** (`/tmp/i9-f3-evidence/ralph-soak` rc=3 — the soak
RED intact — `/tmp/i6-f1-evidence/ralph-canary` rc=0, `/tmp/i26-f1-evidence` and `/tmp/i26b-f1-evidence`
rc=2, `/tmp/ralph-f1-evidence` rc=3). Two synthetic certification directories built from F3's data
with a cert-shaped `times.env` went **rc=3 → rc=0**, the soak findings moving to `OBSERVED`.
Evidence `/tmp/i11-before-*.txt` / `/tmp/i11-after-*.txt`.

**CANDIDATE 56 IS ANSWERED, AND THE CAUSE IS THE HOST'S WALL CLOCK (new, iteration 28).
READ THIS BEFORE ANY FURTHER CERTIFICATION RUN OR LATENCY CLAIM.** One probe run with iteration
27's recorded next step — two concurrent view readers — reproduced the Mac's death
symptom-for-symptom on the deployed `77e0014`, and the probe kept the body the app discards.

***The failure record, which no host has ever recorded:***
```json
{"kind": "integrity", "code": "canonical_decode_failed", "retryable": false,
 "message": "runner result elapsed_sec must be finite and non-negative.",
 "detail": {"error_type": "LiveProviderError"}}
```
`POST /frames` 409 at tick 63 (**t+31.5 s**); **both** readers 401 `invalid bearer authority.` at
**31.287 / 31.289 s** — the same instant, both readers, exactly the Mac's three-symptom cut. The
session was healthy to that instant: 11 spans, all submitted, RTF p95 **0.162**, `capped 0`,
`terminal_failure` null in the last readable snapshot, no lane fault, no heartbeat involved.

***The mechanism, one line, and the product already contains its own fix.***
`vllm_runner.py:111` returns `elapsed_sec=time.time() - started` — the **wall** clock.
`RunnerBoundedWavInference.transcribe_pcm` takes `started = time.monotonic()` at
`live_adapters.py:305` and uses it on the **empty-transcript** path (`:317`), then **throws that
measurement away on the success path** and takes the runner's wall-clock number
(`:344 _runner_elapsed_sec`). `_finite_non_negative_float` rejects a negative one as a
**non-retryable** `LiveProviderError`, which `_process_in_flight_item` turns into
`_fail` → terminal → every view 401 and every frame 409. The right measurement is sitting unused
in the same function, on the branch next door.

***And the wall clock on `ga0-alienware-rtx4070ti` is not monotone — measured, not inferred.***
90 s of paired `time.time()` / `time.monotonic()` sampling at 20 ms on the host: **3 backward steps
of −1.523 / −1.504 / −1.503 s**, at monotonic 1731399.207 / 1731431.460 / 1731463.740 — a
**~1.5 s step backwards every ~32.3 s**, on a host whose `timedatectl` says *"System clock
synchronized: yes, NTP service: active"*. Evidence `/tmp/i28-clock.txt`. This is the WSL2 clock
being resynchronised, and it is a *host* fact, not a code fact — but a meeting must not end because
NTP corrected a clock.
***Which is why the death time looked random and why two probe runs survived.*** A decode brackets
~0.33 s of wall time and spans freeze every 2.5 s, so a decode is in flight ~13 % of the time; one
step every 32.3 s therefore kills a session with ~13 % probability per step. F1 run A died at
**t+18.1 s**, run B at **t+32.1 s**, this run at **t+31.5 s**; iteration 23's 120 s run and
iteration 27's 150 s run survived. That distribution is exactly what a periodic external event
sampled by a 13 % duty cycle produces, and nothing about the audio explains it — which is why five
audio hypotheses all came back clean.
***The class is the same one the third amendment settled, for the fifth time.*** A decoder whose
*timing metadata* is untrustworthy still returned a transcript. The span is fine; only the number
used for RTF is not. `LiveProviderTransientError` (J3) already exists for "the decoder blinked" and
degrades one span; this condition is strictly less serious and is terminal.
***A second consequence, and it touches a PRD clause.*** `elapsed_sec` is the numerator of
**`decoder p95 RTF < 1`**. Every RTF this project has recorded was measured on a clock that steps
1.5 s backwards every 32 s, so any decode bracketing a step is wrong by ~1.5 s in either direction.
Surviving spans are unaffected only because a *negative* one kills the run before it is reported.
F1's two 8.5 s runaways are **not** clock artifacts — 1.5 s is far too small and both were
corroborated by 2024/2019 generated tokens.
*Reusable:* `scripts/ralph-afk/live-pipeline-probe.py --concurrent-readers N --reader-interval S`
(default 0, so every earlier run stays comparable) and `scripts/ralph-afk/view-reader-probe.py`,
which exercises the reader against a local pinned-TLS stub. Report `/tmp/i28-probe.json`, host
baselines `/tmp/i28-host-baseline.txt` / `/tmp/i28-host-after.txt`. Device
`ralph-i28-c56-readers-20260729T003541Z` **revoked** (12 devices / 1 unrevoked); all three MainPIDs
and `NRestarts=0` unmoved, `live-runs` 0, 0 tracebacks, batch 200.
*Whether the concurrent readers were load-bearing is UNSETTLED and probably no:* a reader takes the
runtime lock and mutates nothing, and a 13 %-per-step hazard reproduces on its own eventually. They
are still worth keeping — they are what dated the cut to the millisecond and proved both readers
fail together.

**The reducer stopped calling a passing number RED — candidate 57 (new, iteration 29; `[done]`).
READ THIS BEFORE TRUSTING ANY `live-canary-clauses.py` VERDICT LINE.** Iteration 26's two canaries
printed `USER-VISIBLE p95 = 3970.7 ms vs gate 4000 ms  RED` — a threshold comparison that **passed**,
wearing the word for failing it — because `ok = uv <= gate and sufficientSamples` folded *the run is
too short to answer* into *the run missed the gate*. Both landed in the `red` bucket, so the verdict
line asserted the opposite of the truth and the operator-facing summary would have read "latency is
red" when the honest reading is "latency is unproven".
- **The split, and where the rule comes from.** The app-owned probe already publishes its own
  validity flags (`CaptureLatencyProbe.report`, `CaptureLatencyProbe.swift:335-338`), so the reducer
  **reads** them instead of re-deriving the probe's minimum — a second copy of that constant would
  drift. Three disqualifiers → **UNDECIDED**, and the threshold comparison is not asserted at all:
  `userVisibleMS` null, `mixerOriginResolved` false, `sufficientSamples` false. Only a qualified
  report is compared to the gate.
- **`timelineIntact` false is deliberately NOT a disqualifier.** The probe latches it and rejects
  every later advance (`rejectedAfterTimelineBreak`), so the surviving samples are real and
  `sufficientSamples` already decides whether enough remain — but they cover a **prefix** of the
  meeting, so the caveat is appended to the verdict string and travels with it.
- **A missing `latency-final.json` is now UNDECIDED too**, not silence. It used to print one line
  and add nothing to any bucket, so a directory with no latency report could reduce to **rc=0** on
  the strength of the clauses it did carry — the exact omission this reducer exists to prevent, and
  the same shape as iteration 22's finding.
*Red-before/green-after on four REAL evidence directories, plus four synthetic ones for the branches
no real run has produced.* Before: `/tmp/i26-f1-evidence` and `/tmp/i26b-f1-evidence` both
`RED user-visible p95 3922/3971 ms vs gate 4000 ms`; F3 `RED … 10446 vs 6000`; `/tmp/ralph-f1-evidence`
(no latency report) **silent**. After: the two cut-short canaries are
`UNDECIDED … UNPROVEN, not failed (the run's own number, 3971 ms, is not admissible):
sufficientSamples=false - 12 committed advances …`, **F3 is still RED** (the negative control that
matters — a qualified miss must not become "undecided"), and F1's directory is UNDECIDED. Synthetic
patches over F3's report exercised the rest: qualified-pass → **GREEN**; qualified-pass with
`timelineIntact=false` → **GREEN + the prefix caveat**; `mixerOriginResolved=false` and null
`userVisibleMS` → **UNDECIDED**. Evidence `/tmp/i29-before-*.txt` and `/tmp/i29-after-*.txt`.
*Nothing else moved:* the only changed file is `scripts/ralph-afk/live-canary-clauses.py`; no
product source, no host touched, and rc on all four real directories stays **3** because other
clauses in those runs are genuinely red.
*The general lesson, third time this loop has paid for it:* **a verdict word must name the thing it
decides.** "Missed the gate", "cannot answer the gate" and "no data" are three states; two of them
were sharing one word here, exactly as F1's lane failure once shared a word with "printed".

**Candidate 56 did NOT reproduce under continuous two-lane audio, and two of its likeliest causes
were ELIMINATED (iteration 27; superseded by the block above — kept for the eliminations, which
still hold).** The recorded next step was "drive `live-pipeline-probe.py` with a program that
resembles the Mac's real capture more closely than iteration 23's did". The measured difference was
found first, then run.
- **What the probe could not produce, and now can.** `build_lane_track` lays a few utterances on a
  silent timeline, so between turns a lane sends frames whose every sample is zero and whose wire
  `silent` flag is **true**. A real capture never does that — the microphone hears the room and the
  tap carries the program — so on the Mac **both lanes are non-silent continuously**. Measured, not
  assumed: F1 run B committed **13 spans in 30 s, every one `hard_cap`**, while iteration 23's 120 s
  probe run committed **36 of 59 spans empty**. `--lane-audio continuous` tiles each lane's lines
  back to back so no frame is silent; `alternating` stays the default so every earlier run stays
  comparable. Verified offline before the host run: **300/300 voiced frames on both lanes** at
  `--lead-seconds 0`, against 250/300 for the old schedule.
- ***And it did not reproduce.*** 150 s on the deployed `77e0014`, `--lane-offset-ms system=137`,
  device `ralph-i27-c56-probe-20260729T001817Z` (**revoked**): 300 ticks, 600 frames,
  `non_200_count` **0**, `accepted == accounted == committed == 2 400 000` (exactly 150 s),
  **60 committed spans, all submitted, 0 empty**, `terminal_failure` null, `status` `closed`, and
  view authority correctly 401 after the stop. **Span density matched the real run** — 0.40
  spans/s here against run B's 0.43 — so "the Mac freezes spans faster" is not the trigger either.
  Report `/tmp/i27-probe.json`.
- **The identity path was exercised hard and stayed non-terminal:** 43 `prepared` + **17 `abstain`**
  (15 `ambiguous_identity`, 2 `same_span_cannot_link_conflict`), **all 60 submitted**, 0 refusals —
  J2's ruling holding at volume on real audio. **7** canonical speakers in 150 s, so dense synthetic
  speech does *not* saturate candidate 55's 16-speaker bound the way the real microphone lane does.
- ***The heartbeat/lease family is eliminated too, from data already in hand.*** Run A was cut at
  **t+18.1 s**; the helper lease is **30 s** and is armed by the first heartbeat, so the earliest
  possible expiry is t+30 s. And `_terminal_reason` fires only on `helper_failed` or all lanes
  failed, which both runs' healthy lanes contradict. **The reading correction that matters:**
  `LiveHelperFailureCoordinator.observe` returns early on `session_id in self._terminal_sessions`
  and the route still answers **200** — so *"165 × 200 heartbeats" is NOT evidence the session was
  alive*, and adding a heartbeat to the probe would be the wrong experiment.
- **Drift is eliminated as well.** F1 run B's mixed mono frame sizes are **periodic with period 9**
  (5305, 2460, 7764, 5774, 1990, 7765, 6243, 1521, 9172 — sum 47 994 ≈ 3 s, repeating), i.e. the two
  lanes ran in **fixed-offset lockstep**, which is exactly what `--lane-offset-ms` already models.
- ***Why the recorded evidence can never hold the answer, stated so nobody re-reads it hoping.***
  `_fail` appends the `terminal_failure` event **under the same lock** that makes the very next view
  request 401 (`live_transport.py:87-101` → `live_auth.py:377`), so an events poller is structurally
  blind at the one instant that matters. Run B's merged event stream confirms it: 150 events, the
  last is `frame_accepted` seq 149 with **all 13 spans submitted and `submission_refusal` null**, and
  every later poll 401s.
- **Where the answer does live:** a terminal `LiveServiceError` on `POST /frames` returns
  `_failure_status(exc)` = **409** with a body carrying `failure.to_dict()` **and** the snapshot's
  `terminal_failure` (`live_transport.py:267-272`). The probe keeps that body; the app discards it.
- ***The strongest remaining un-mirrored property, and the next experiment.*** `live_snapshot` and
  `live_events` are **sync `def`** handlers (`live_transport.py:285,307`) so Starlette runs them in
  its threadpool, while `accept_live_frame` is **`async def`** and runs on the event loop. On the Mac
  **two** view readers poll concurrently (the app's own latency probe *and* the portal poller) while
  frames are posted; this probe is single-threaded and strictly serial, so it **structurally cannot**
  overlap a read with a write. Give the probe a background reader thread before concluding anything
  else.
*Host untouched, checked after:* `HEAD` `77e0014`, worktree clean; `moss-live-web` **350731**,
`moss-web` **301112**, `moss-vllm` **322117**, all `NRestarts=0`; `live-runs` 0, no `/tmp/mtd-live-*`,
**0** tracebacks, batch `/` 200, device store **11 devices / 1 unrevoked** (m4mbp's `AB600574…`).
*Reusable, and it cost one pairing code to learn:* `ops/live-pair.sh` prints **`payload: <PAYLOAD>`**,
so the payload must be extracted with `sed -n 's/^payload: //p'` — `tail -1` alone hands the probe a
122-byte string and the server answers **401 `pairing payload is invalid.`**.

**Feasibility — settled, do not re-litigate.**
- Warm 12-run decode p95: 7.5 s span → **0.241 s**; 2.5 s → **0.162 s**. One pre-warm
  2.5 s request took 3.851 s, so certification must warm the resident engine before timing.
  Output already carries `[t][S01]` speaker labels.
- Live decode reuses the **already-resident** vLLM engine (`web_cli.py:87-98`) → **no extra
  VRAM**. GPU free 1328 MiB of 16376 after the probe is not a blocker.
- Latest m4mbp → 4070Ti tailnet probe: ping avg **72 ms**, max **146 ms**. Treat callback cadence
  and tailnet latency as variable; no fixed request-rate assumption is valid.
- Uplink: 48 kHz lanes = 2.05 Mbit/s of base64 JSON; 16 kHz lanes = 0.68 Mbit/s.

**Open risk — system-tap prompt on a GUI host (M36).** `AudioHardwareCreateProcessTap` is the
documented System Audio Recording prompt trigger and is still called on the control thread. On
MacStudio it returns promptly (iteration-1 `sample` proved the hang was in the microphone path,
not the tap), but nothing yet proves it returns promptly on m4mbp while its prompt is on screen.
If E3 shows it blocking, move system admission onto the coordinator's own thread in Phase B; do
not add a Screen Recording preflight in its place (M31 forbids it).
*Its consequence, made concrete in iteration 23:* `UnixDomainControlServer.serve()` is a **serial**
accept loop (`CaptureSecurity.swift:897-902`) and `UnixDomainControlClient` sets no `SO_RCVTIMEO`.
So if the tap call does block, `mtd-capture start` blocks with **no timeout** and every other
`mtd-capture` command — `status` included — queues behind it. An apparently hung `start` at E3 is
the expected appearance of an unanswered prompt, not a defect, and a hung `status` is not evidence
that the app died. Diagnose it with `pgrep -x MOSSCaptureApp` and `sample`, never by killing the app.

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

**TCC-verification contract (new, iteration 23).** The PRD's "Permissions granted" clause has a
**read-only, scriptable** check, so the loop never needs to go near a TCC write.
`~/Library/Application Support/com.apple.TCC/TCC.db` on m4mbp is `-rw-r--r-- ga0:staff` and opens
over plain SSH **without** Full Disk Access — measured: 320 rows across 20 services. The two service
names are read off that live table, not guessed: Microphone = `kTCCServiceMicrophone` (21 rows),
**System Audio Recording = `kTCCServiceAudioCapture`** (3 rows). `auth_value` 2 = allowed, 0 = denied
(both appear on this host, e.g. `com.openai.chat|2` vs `com.google.antigravity|0`); `client_type`
0 = bundle identifier, 1 = absolute path, so an app bundle is keyed by its identifier.
*Baseline recorded this iteration:* **zero** rows match `%moss%` in either service — both lanes are
undetermined, consistent with the app never having been launched.
*The csreq is the DR.* Each row carries a `FADE0C00` code-requirement blob that
`sqlite3 … writefile()` plus `csreq -r <file> -t` decodes. Decoded on the `com.livetranscribe.app`
precedent (a locally-signed app on this same host that already holds **both** grants):
`identifier "com.livetranscribe.app" and certificate leaf = H"51e289ba70a36bcdd063f1efa660d56aebd83da7"`
— byte-for-byte the *form* of the E1 designated requirement. So after E3 the two moss rows must
decode to `identifier "com.alphasight.moss.capture" and certificate leaf =
H"e118d874377746c4bd25beb8252bb84302b73e72"`, and that decode is the **direct observation** that the
grants key on the DR rather than the cdhash — the reason a byte-different SwiftPM rebuild keeps them.
Until E3 that link was argued from the DR's stability alone, never seen in TCC's own storage.

**E3 command surface (new, iteration 23; read out of the reviewed source at `f9285d6`).** Three
facts decide whether the human step succeeds on the first try:
1. **The pairing payload goes on stdin, never on argv.** `CaptureCommandLine.swift:121` is
   `input.readAll()`; empty stdin is `rc=65`. So the operator runs
   `mtd-capture pair --server <https-url>`, pastes the payload, presses **Ctrl-D** — that keeps it
   out of argv *and* out of shell history, which is what the PRD's secret-hygiene clause needs.
   Since G2 (run 20260728-072601 iteration 2) a Return pressed before Ctrl-D is harmless; before it
   that keystroke failed the pair with `invalidPinnedHash`. That fix reaches the host only when
   E2b is re-run there after the G4 merge.
   Full surface: `pair --server <https-url> | start [--label <name>] | stop | status | handoff |
   latency`; anything else is the usage line and `rc=64`.
2. **The CLI cannot launch the app by itself here.** `NSWorkspaceLaunchServicesCaptureAppLauncher`
   launches only when the control socket is absent **and** `MOSS_CAPTURE_APP_URL` is set
   (`CaptureCommandLine.swift:69`); nothing in the product, the install tool or a shell profile sets
   it, so a bare CLI call answers `{"ok":false}` `rc=70` and starts nothing. The app must be started
   from the GUI session (Finder double-click or `open -a`), or the operator exports
   `MOSS_CAPTURE_APP_URL=/Applications/MOSSCapture.app`. Never run
   `…/Contents/MacOS/MOSSCaptureApp` from a shell: TCC would attribute the grant to the terminal
   instead of the bundle, and the DR-keyed grant would not apply to the app.
   Socket path is `/tmp/moss-capture-$(id -u)/control.sock` = `/tmp/moss-capture-501/control.sock`.
3. **`LSUIElement` is `true`** (`macos/MOSSCapture/Resources/Info.plist`), so a launched app shows no
   window, no Dock icon and no menu-bar item. "Running" is observed by `pgrep -x MOSSCaptureApp` and
   by the socket existing — never by a visible UI. Nothing appearing on screen is the correct result.

**Prompt order is fixed by the source, and the TCC clicks are NOT bound to D4's 300 s window
(new, iteration 23).** `NativeDualCaptureSource.start` admits **system audio first**
(`NativeDualCaptureSource.swift:191`) and the microphone second (`:192`). System audio has no request
API — `AudioHardwareCreateProcessTap` inside `SystemAudioTap.start` *is* the request, called inline
on the control thread — while the microphone request is the asynchronous
`AVCaptureDevice.requestAccess(for: .audio)` that leaves the lane `pending`. So the operator sees
**System Audio Recording first, Microphone second**, and only the first one can block.
*The decoupling:* `CaptureController.start` (`CaptureController.swift:230-246`) requires only
`loadControlSecret() != nil` — which the app writes for itself at launch — and calls
`source.start` at `:242`, **before** the first publish at `:250`. Pairing is needed only by that
publish. An **unpaired** `start` therefore still raises both prompts; the publish then fails
`missingCaptureBearer`, which `CaptureFrameRetryPolicy` classes as not retryable, so the controller
unwinds the source and throws — but the user's two decisions are already durable in TCC.db, because
TCC records the click, not the capture outcome. That converts E3 from "clicks inside a five-minute
window" into two independent steps: grants first, verified read-only, then D4's mint and pairing with

**Rollback rehearsal — the PRD clause is GREEN (new, iteration 8 / F4a).** Disabled → reverted →
proved batch → restored, all on the real server, batch never restarted. Four durable facts came out
of it, and they are the reasons to read this block rather than re-derive it:
1. **Order is forced by `ExecStart`.** The live unit runs `ops/start-web.sh` *from the checkout*, and
   at `163e969` that script predates `MOSS_WEB_PORT`/`MOSS_RUNS_DIR` — a live unit started while the
   checkout is rolled back would ignore the live profile and try to bring up a **batch** server.
   So: `disable --now` **before** the checkout moves back, restore the checkout **before**
   `enable --now`. Use `disable`, not `stop`, so `default.target` cannot pull it back in.
2. **A correct restore reads as a broken one for ~10 s.** `enable --now` at 05:06:05 →
   `Uvicorn running on https://0.0.0.0:7861` at 05:06:15; a probe at 6 s returned **000**. Poll for
   200, never sample once.
3. **A rolled-back tree is not a clean tree.** `163e969`'s `.gitignore` predates the
   `ops/moss-live.env` entry, so while rolled back `git status --porcelain` reports
   `?? ops/moss-live.env`. The checkout does not delete the profile; only `git clean` would, and an
   operator tidying the "unclean" tree would destroy the one file the restore depends on.
4. **Nothing that a paired Mac hashes can move.** The TLS pair, the manifest and `live-auth.json`
   live under `~/.local/share/…/live` on ext4, outside the repo: after the whole cycle all four kept
   inode *and* sha256, the served leaf was byte-identical, and the descriptor still reported
   `provider_manifest_hash 61d97ffe…` / `source_revision f9285d69…`. That is why this rollback is
   safe to run against already-paired devices — and the stop condition for any future run is the pin
   changing.
`163e969` is "before the MVP", not "before anything named live": `live_transport.py` exists there,
`live_auth.py` does not. The Windows portproxy/firewall half was deliberately **not** torn down —
it is outside the PRD clause, and the client probes showed a forward with no listener behind it
answers `000` anyway.

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

# --- G1 ATS declaration: the three shape gates. There is no behavioral gate and there cannot be
#     one on a single host - see the ATS contract block. ------------------------------------------
swift test --package-path macos/MOSSCapture --filter 'BundleDeclaresTheTransport'
python3 -m pytest tests/test_macos_packaging_tools.py -q -k entitlement_the_identity
python3 -m pytest tests/test_macos_uds_tracer.py -q -k 'immutable_first_install or unpinned_leaf'
# --- G2 pairing-payload trim + canonical wire form (2 Swift nodes; the tracer's second real
#     pairing now feeds `payload + b"\n"`, so the whole stdin -> UDS -> app -> HTTPS path is
#     covered at no extra runtime). ---------------------------------------------------------------
swift test --package-path macos/MOSSCapture --filter 'PairingPayloadTrims|PairingPayloadWhitespace'
python3 -m pytest tests/test_macos_uds_tracer.py -q -k cross_real_uds
# --- G3 control-channel classification + logging (5 Swift nodes: the three unclassified NSError
#     shapes with no message/URL on the wire, the four typed families keeping their names with no
#     detail and no log line, one log record per unclassified failure with its command, the log
#     line's fixed vocabulary, and the app-wires-it/CLI-does-not entrypoint scan). The real-process
#     half is the tracer's pin refusal, strengthened in place to assert -999 with no underlying. ---
swift test --package-path macos/MOSSCapture \
  --filter 'UnclassifiedTransportFailure|AlreadyNamedControlFailures|UnclassifiedControlFailureIsLogged|AppFailureLogWritesOnly|WiresTheControlChannelFailureLog'
python3 -m pytest tests/test_macos_uds_tracer.py -q -k unpinned_leaf

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

# --- B1 secret-store behavioral nodes (the replacement for discriminator 09/15) ------------
swift test --package-path macos/MOSSCapture --filter 'SecretStore|ProductEntrypoints|DormantKeychain'

# --- B2 outbox behavioral nodes (8 nodes: outage, ambiguous/duplicate, 429/5xx/401, overflow,
#     stalled lane, wire-sequence authority, per-session numbering, start unwind) --------------
swift test --package-path macos/MOSSCapture \
  --filter 'Outbox|Ambiguous|RetryPolicy|Stalled|NumbersItsLane|Unwinds'

# --- B3 wire-format behavioral nodes (11: timebase, steady frames, 48/44.1 kHz duration,
#     cross-lane domain, refused instant, terminal flush, gap splice, source+controller tail, and
#     two realtime-callback source gates) --------------------------------------------------------
swift test --package-path macos/MOSSCapture \
  --filter 'HostTicks|CanonicalFrames|ConserveDuration|HostTimeDomain|CaptureInstant|TerminalFlush|TimelineGap|RealtimeCallbacks|FlushedTail'

# --- B4 bounded-transport behavioral nodes (5: lane rendezvous + per-lane in-flight bound, late
#     tick skips, stop waits, one session per pin, shipped cadence/provider) --------------------
swift test --package-path macos/MOSSCapture \
  --filter 'LanesPublishConcurrently|ATickArrivingDuringADrain|StopWaitsForTheRunningPass|PinnedProviderKeepsOneSession|ProductionPumpTicksOnce'

# --- C3c app-owned latency probe (10 nodes: origin/mapping math, three disqualifier classes,
#     trailing-partial vs mid-stream short frame, waits-then-freezes origin, separate committed and
#     render components, one poll's requests + header-only token + advancing cursors, default-off
#     and idempotent measure + typed unavailable, stops with the session, acknowledged-frame
#     observer sees accepted audio only and cannot reach PCM, plus the CLI relay). ---------------
swift test --package-path macos/MOSSCapture --filter 'Latency|AcknowledgedFrameObserver'

# --- C2 manifest bounds (17 nodes: retune + regenerated hashes, descriptor admission, reconnect-
#     burst capacity headroom on both lanes with replayable acks, 9 refusals, dry-run, unchanged
#     re-run, backup + working rollback, tracked ops tool end to end). Scratch paths only. -------
python3 -m pytest tests/test_live_manifest_finalizer.py -q

# --- C3a live-credential tools (14 nodes: pin identity across three independent readers plus a
#     real handshake, four-SAN deployment invocation, no-rotate re-run, refusal + reversible
#     rotation, half-installed pair, dry runs, address parity with live_auth, 15 malformed-input
#     refusals, failed-generation cleanup, one-payload secrecy, served-vs-on-disk mismatch,
#     pre-send refusals via a curl stub, library vocabulary parity). Scratch paths only; the one
#     server it starts is loopback-only on an ephemeral port. -----------------------------------
python3 -m pytest tests/test_live_deployment_credentials.py -q

# --- C3a tools by hand (scratch paths; never the deployed live dir) --------------------------
ops/generate-live-tls.sh --dry-run --dns moss-live.fixture.invalid --ip 10.11.12.13 \
  --cert /tmp/moss-tls/live.crt --key /tmp/moss-tls/live.key
# The D2 invocation - SPENT in iteration 18, and it needed `--rotate` because the staged pair had
# no tailnet SAN. Re-running it WITHOUT --rotate now prints `unchanged:` and rotates nothing, which
# is the safe way to re-assert the pin; never add --rotate again unless a name really changes,
# because rotation invalidates every pairing payload and every pin a Mac has stored.
#   ops/generate-live-tls.sh --dns ga0-alienware-rtx4070ti.tailnet.aisight.us \
#     --dns ga0-alienware-rtx4070ti.local --ip 100.64.0.8 --ip 192.168.68.38 \
#     --common-name ga0-alienware-rtx4070ti.tailnet.aisight.us \
#     --cert "$HOME/.local/share/moss-transcribe-diarize/live/live.crt" \
#     --key "$HOME/.local/share/moss-transcribe-diarize/live/live.key"
# Rollback for that rotation, still valid until the backups are removed:
#   L="$HOME/.local/share/moss-transcribe-diarize/live"
#   rm -f "$L/live.crt" "$L/live.key" \
#     && mv "$L/live.crt.backup-20260728T044132Z" "$L/live.crt" \
#     && mv "$L/live.key.backup-20260728T044132Z" "$L/live.key"
# D4 mints exactly once, on the host, and the payload line is never redirected to a file:
#   ops/live-pair.sh --url https://127.0.0.1:7861 \
#     --cert "$HOME/.local/share/moss-transcribe-diarize/live/live.crt"

# --- C3b two-service deployment bundle (30 nodes: recorded batch argv, complete live argv from
#     the tracked template, every live variable required, live-off leaks no live flag, batch-port
#     and batch-runs-dir refusals, 8 malformed ports, 4 non-binary enablements, template/adapter
#     variable parity, gitignored host profile, unit layout + one deployment root, installer
#     default/refusal/explicit-live/backup-rollback/dry-run, doc coverage, Windows two-port guard).
#     Scratch paths only; `systemctl` and `getent` are stubbed, no unit is installed for real. ----
python3 -m pytest tests/test_live_service_deployment.py -q

# --- C3b tools by hand ------------------------------------------------------------------------
# `install-services.sh` is Linux-only and stops on MacStudio at
# `error: required tool not found on PATH: systemctl`. Exercise it through the test file, which
# stubs systemctl/getent; the real invocation belongs to D3 on the host.

# --- B5 packaging tools (9 nodes: entitlement drop, reproducible bundle, install-location
#     refusal, untouched idempotent install, backup + working rollback, tampered-bundle refusal,
#     three dry-run plans, keychain refusals). Scratch paths only; no keychain/app is mutated. ---
python3 -m pytest tests/test_macos_packaging_tools.py -q

# --- B5 tools by hand (build output is gitignored; ad-hoc signing needs no identity) --------
macos/scripts/build-app.sh --configuration debug --no-build \
  --output /tmp/moss-build --sign-identity -
macos/scripts/install-app.sh --bundle /tmp/moss-build/MOSSCapture.app \
  --cli /tmp/moss-build/mtd-capture --applications /tmp/moss-apps --bin-dir /tmp/moss-bin
macos/scripts/bootstrap-signing-identity.sh --dry-run   # never run for real on MacStudio
# Real signing identity + install belong to E1/E2 on m4mbp, not to this host.

# --- E1: the signing identity on m4mbp (SPENT in iteration 21) --------------------------------
# Run from the m4mbp checkout; re-running is safe and prints `unchanged:` without touching the
# keychain, the password file or the search list.
#   ssh -o BatchMode=yes ga0@m4mbp 'bash -s' <<< 'cd <checkout> && \
#     macos/scripts/bootstrap-signing-identity.sh'
# Rollback (rehearsed for real this iteration; `delete-keychain` also removes the search-list entry):
#   security delete-keychain "$HOME/Library/Keychains/moss-signing.keychain-db" \
#     && rm -f "$HOME/.config/moss-capture/signing-keychain.password"
# DO NOT apply it after E2b/E3: the re-created identity has a different leaf, so the DR changes and
# the human's TCC grants die with it.
# Verify the identity by codesign, NEVER by `security find-identity -v -p codesigning` (0 valid for
# a self-signed leaf). A fresh SSH session must unlock first or codesign says errSecInternalComponent:
#   security unlock-keychain -p "$(cat "$HOME/.config/moss-capture/signing-keychain.password")" \
#     "$HOME/Library/Keychains/moss-signing.keychain-db"
#   codesign --force --identifier com.alphasight.moss.capture --sign 'MOSS Capture Local Signing' <bin>
#   codesign -d -r- <bin> | tail -1   # must be the DR recorded in the signing-identity block

# --- E2b: build, sign and install on m4mbp (SPENT in iteration 22; RE-RUN as G6 in iteration 7 of
#     run 20260728-072601, which is what put G1+G2+G3 into the product) -------------------------
# The G6 re-run's own rollback, still valid while these backups exist (they are the ONLY copy of the
# pre-G6 bytes - SwiftPM is not byte-reproducible here):
#   rm -rf '/Applications/MOSSCapture.app' && mv '/Applications/MOSSCapture.app.backup-20260728T085551Z' '/Applications/MOSSCapture.app'
#   rm -f  '/Users/ga0/.local/bin/mtd-capture' && mv '/Users/ga0/.local/bin/mtd-capture.backup-20260728T085551Z' '/Users/ga0/.local/bin/mtd-capture'
# A redundant pre-copy also exists at /tmp/moss-g6-prebackup (volatile; `rm -rf` it any time).
# DR satisfaction, positively and negatively - note the requirement has NO `designated => ` prefix:
#   codesign --verify -R='identifier "com.alphasight.moss.capture" and certificate leaf = H"e118d874377746c4bd25beb8252bb84302b73e72"' /Applications/MOSSCapture.app
# The one-line proof the ATS fix is in the PRODUCT (errors before G6, prints the G1 shape after):
#   plutil -extract NSAppTransportSecurity xml1 -o - /Applications/MOSSCapture.app/Contents/Info.plist
# Run from the m4mbp checkout. build-app.sh writes only under .build/product (it refuses an install
# location) and unlocks the signing keychain itself, so no manual unlock is needed.
#   macos/scripts/build-app.sh --dry-run  &&  macos/scripts/build-app.sh --configuration release
#   macos/scripts/install-app.sh --dry-run  &&  macos/scripts/install-app.sh
# Re-running either prints `unchanged:` — but only while the binary is unrebuilt. A rebuild changes
# the bytes (SwiftPM is not reproducible here) and therefore always takes the replacement path.
# Rollback for a FIRST install (what iteration 22 recorded and rehearsed):
#   rm -rf '/Applications/MOSSCapture.app' && rm -f '/Users/ga0/.local/bin/mtd-capture'
# Rollback for a REPLACEMENT, printed by the tool with its own <utc> stamp — note it backs up the
# CLI too, and that backup file is left behind for you to remove:
#   rm -rf '/Applications/MOSSCapture.app' && mv '/Applications/MOSSCapture.app.backup-<utc>' '/Applications/MOSSCapture.app'
#   rm -f  '/Users/ga0/.local/bin/mtd-capture' && mv '/Users/ga0/.local/bin/mtd-capture.backup-<utc>' '/Users/ga0/.local/bin/mtd-capture'
# DO NOT apply the install rollback after E3 without a reason: re-installing is safe (the DR is
# stable) but each replacement resets the bundle's inode, and only the DR keeps the grants.
# The PRD's "Signed app installed" clause, re-assertable read-only at any time:
ssh -o BatchMode=yes ga0@m4mbp 'ls -ld /Applications/MOSSCapture.app; \
  codesign -dv /Applications/MOSSCapture.app 2>&1 | sed -n "2p"; \
  codesign -d -r- /Applications/MOSSCapture.app 2>&1 | tail -1; \
  codesign --verify --strict /Applications/MOSSCapture.app && echo bundle_ok'
# The CLI is on the human's interactive PATH but NOT on the non-interactive SSH PATH — over SSH
# always call it as /Users/ga0/.local/bin/mtd-capture.

# --- E3: verify the TCC grants READ-ONLY (never write TCC; see the TCC-verification contract) ----
# The user TCC.db opens over plain SSH without Full Disk Access. Before E3 both queries print
# nothing; the PRD's "Permissions granted" clause is green when the first prints exactly two rows
# with auth_value 2 and the second decodes to the E1 designated requirement.
ssh -o BatchMode=yes ga0@m4mbp 'DB="$HOME/Library/Application Support/com.apple.TCC/TCC.db"; \
  sqlite3 "$DB" "select service,client,client_type,auth_value from access \
    where client=\"com.alphasight.moss.capture\" order by service;"'
#   expect: kTCCServiceAudioCapture|com.alphasight.moss.capture|0|2
#           kTCCServiceMicrophone|com.alphasight.moss.capture|0|2
#   auth_value 2 = allowed, 0 = denied. System Audio Recording IS kTCCServiceAudioCapture.
ssh -o BatchMode=yes ga0@m4mbp 'DB="$HOME/Library/Application Support/com.apple.TCC/TCC.db"; \
  T=$(mktemp -d /tmp/moss-csreq.XXXXXX); \
  sqlite3 "$DB" "select writefile(\"$T/req.bin\", csreq) from access \
    where client=\"com.alphasight.moss.capture\" and service=\"kTCCServiceMicrophone\";" >/dev/null; \
  csreq -r "$T/req.bin" -t; rm -rf "$T"'
#   expect: identifier "com.alphasight.moss.capture" and certificate leaf = H"e118d874377746c4bd25beb8252bb84302b73e72"
#   That decode is the proof the grant keys on the DR, so a byte-different rebuild keeps it.
# Sanity-check the reader itself before trusting an empty result — a 0-row answer and a broken
# query look identical: `sqlite3 "$DB" "select count(*) from access;"` must print a few hundred.

# --- E3: the operator's own checks (run in the GUI session, not over SSH) ---------------------
#   pgrep -x MOSSCaptureApp                 # the app is LSUIElement: no window, no Dock icon
#   ls -l /tmp/moss-capture-$(id -u)/control.sock
#   /Users/ga0/.local/bin/mtd-capture status
# A hung `status` while a prompt is on screen is expected: serve() is a serial accept loop and the
# client has no timeout. Never kill the app to "fix" it.

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

# --- host manifest finalization (SPENT in iteration 18/D2; re-run only to re-prove idempotence) --
# MUST use the deployment venv python, not `python3` - see the open defect above. Re-running is
# safe: it prints `unchanged:` and does not touch the inode.
printf '%s\n' \
  'set -euo pipefail' \
  'cd /mnt/d/Coding/MOSS-Transcribe-Diarize' \
  '"$HOME/.local/share/moss-transcribe-diarize/venv/bin/python3" ops/finalize-live-provider-manifest.py --input "$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.provisional.json" --output "$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json" --source-revision "$(git rev-parse HEAD)" --hard-cap-samples 40000 --max-retained-samples 960000 --frame-samples 8000' |
  ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local \
    "wsl.exe -d Ubuntu -- bash -s"

# --- host manifest admission by the runtime's own readers (read-only; re-run any time) ----------
#   from_manifest -> _endpoint_config(payload["endpoint_config"]) and _bounds(payload["bounds_config"])
#   (they take their own sub-mappings, NOT the whole payload), then _preflight_payload(path)
#   Expect available=True, failures=[], manifest_hash 61d97ffef1bbdc0d4278c0fd719d5d31b0ac5f69e1654573ada5091653fecb95

# --- H3 + H1 regression nodes, one file, 10 passed (~3.5 s). H3 (5): the real WebRtcSpeechProvider
#     under the real coordinator - unaligned mixed frames incl. the host's 5808, the carried tail
#     decided for real on completion, a 1-sample accepted range, the shipped 8000-sample control,
#     admission refusal. H1 (5): the real vLLM response validation under the real runtime - F0's
#     leading_silence span committed empty, a pure-silence meeting stopping with exact accounting,
#     all three no-speech answers, a decoder that returns garbage without raising, and a decoder
#     that failed staying terminal. The aligned control passes before AND after H3's fix. ----------
python3 -m pytest tests/test_live_pipeline_seams.py -q
# Red-prove either half without touching git history (restore is sha256-verified). H3 is one file
# (live_provider_bundle.py -> 4 failed / 1 passed); H1 is five (vllm_runner, live_adapters,
# live_coordinator, live_session, live_service_runtime -> its 5 nodes fail, H3's 5 still pass):
#   for f in $FILES; do cp "$f" "$TMP/$(basename $f)"; git show HEAD:"$f" > "$f"; done
#   python3 -m pytest tests/test_live_pipeline_seams.py -q
#   for f in $FILES; do cp "$TMP/$(basename $f)" "$f"; done   # then compare sha256 both ways
# J1 (iteration 9) adds 11 nodes to the same file -> 24 passed (~3.6 s). Red-prove it the same way
# with FILES = live_session.py live_identity.py live_adapters.py; the new leaf live_span_bounds.py
# is untracked at HEAD, so it survives the restore and the three seam nodes fail for the real
# reason (3 failed / 21 passed), rather than the file failing to import.
# J2 (iteration 10) adds 8 more -> 32 passed (~3.6 s). Red-prove it by restoring ONLY
# live_coordinator.py: UNATTRIBUTED_SPEAKER and unattributed_transcript live in live_session.py and
# live_identity.py, so restoring those too would break the import instead of the behaviour. The
# blast radius is five nodes across three files, so run them together:
#   python3 -m pytest tests/test_live_pipeline_seams.py tests/test_live_coordinator.py \
#           tests/test_live_replay.py -q            # 5 failed / 36 passed before, 41 passed after
# J3 (iteration 11) adds 12 more -> 44 passed (~3.6 s). Red-prove it by restoring ONLY
# vllm_runner.py: TransientTranscriptionError, LiveProviderTransientError and the coordinator's three
# policy constants are all imported by the test module, so restoring their files breaks collection
# instead of behaviour. With no transient classification at the source the whole chain reverts, so
# this one restore reds all seven transient nodes (7 failed / 37 passed) while the four permanent
# status rows stay green - which is also the proof that the 400/401/404 path was never touched.
# J4 (iteration 12) adds 6 more -> 50 passed (~3.7 s), plus 1 node in tests/test_live_identity.py
# (8 passed). Red-prove it by restoring ONLY live_service_runtime.py: the test module imports
# CanonicalSubmission from live_session, so restoring that one is a collection error rather than a
# red. The runtime holds both halves of J4 that the nodes read - the canonical_processed payload and
# _failure_from_exception - so this single restore reds exactly the six (6 failed / 44 passed).

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

# --- H blocker 4: the decode -> identity seam, ON THE HOST (iteration 7) ------------------------
#     Reads the deployed manifest, sends ONE inference request to the same vLLM endpoint the
#     service uses, and loads a second copy of the ONNX identity encoder (CPU). It mutates nothing:
#     no session, no auth state, no service. rc=0 means the span would publish, rc=4 means it
#     would make the session terminal. Ship it to the host on stdin (see the remote-quoting gotcha)
#     and run it with the SERVICE'S venv from the deployed checkout:
#       V="$HOME/.local/share/moss-transcribe-diarize/venv"
#       L="$HOME/.local/share/moss-transcribe-diarize/live"
#       cd /mnt/d/Coding/MOSS-Transcribe-Diarize
#       "$V/bin/python" /tmp/live-identity-seam-probe.py \
#         --manifest "$L/live-provider-manifest.json" --wav <one span of 16 kHz mono audio> \
#         --vllm-base-url http://127.0.0.1:8000/v1 \
#         --vllm-model OpenMOSS-Team/MOSS-Transcribe-Diarize --vllm-timeout 300
#     It runs the preparation twice — with the manifest's real evidence provider and with none —
#     so the verdict names which side of the evidence call the defect is on. Measured 2026-07-28:
#       span 1 rebuilt from the pipeline probe's own schedule (2.5 s, speech to the end)
#         -> "[0.11][S01] Good morning everyone. This is the microphone.[2.51]"
#         -> failed/timestamp_outside_span, rc=4, both with and without evidence
#       the same audio + 0.5 s trailing silence (3.0 s span) -> "[0.00 ... 2.54]" -> prepared, rc=0
#       golden.wav (2.1 s) -> generated_tokens 0, transcript "" -> H1's empty path, handled
#     Rebuild that span-1 audio on MacStudio by importing live-pipeline-probe.py's own
#     build_schedule/build_lane_track, shifting the system lane by the --lane-offset-ms you used,
#     mixing with live_mixer's own _HEADROOM_GAIN/_LIMITER_* constants, and slicing [12208:52208].
#     Delete the WAV from the host afterwards; audio does not belong in /tmp on the server.

# --- H blocker 4, the BOUNDARY SWEEP (iteration 8). The single-span probe says *that* a timestamp
#     can land past its span; it cannot say how far or how often, and those two numbers are what
#     the fix has to be chosen against. `build-span-sweep.py` cuts N spans out of the pipeline
#     probe's OWN mixed timeline - same schedule, voices, lane offset and mixer arithmetic, all
#     imported rather than restated - so a cut is the audio the service would have mixed, by
#     construction. Cuts are START:COUNT[:PAD] in samples; PAD appends silence, the control that
#     moves speech off the span end. The build is deterministic: two independent runs of the same
#     arguments produced the same `mixed_sha256` and the same per-cut sha256.
python3 scripts/ralph-afk/build-span-sweep.py --out-dir /tmp/moss-span-sweep \
  --report /tmp/moss-span-sweep/index.json --seconds 20 --lead-seconds 1.0 \
  --lane-offset-ms system=137 --cut 12208:40000 --cut 12208:40000:8000   # repeat --cut per span
# A stride sweep is one bash line: for k in $(seq 0 32); do CUTS+=(--cut $((12208+k*8000)):40000); done
# (zsh does NOT word-split an unquoted "$CUTS" string - build an array and run it under `bash -c`.)
# Then ship the wavs and live-identity-seam-probe.py to the host in ONE stdin script (a base64
# heredoc per file), run the probe per wav under the service venv, `rm -f "$D"/*.wav` in the SAME
# invocation, and print the reports. ~5-25 s per span (ONNX encoder load dominates the short ones).
# GOTCHA: `sha256sum "$D"/*.wav | head -3` under `set -o pipefail` aborts the whole script with
# rc=141 - SIGPIPE. Write the digests to a file and count lines instead.

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

# --- token accounting for a live transcript, on the host (iteration 16; read-only, no GPU work,
#     no state touched, ~2 s for 78 spans). This is how candidate 50's cap was derived, and how any
#     later claim about tokens per second of audio must be re-derived - characters are a different
#     quantity and would be a guess. The resident vLLM answers `/tokenize` on its ROOT, not /v1. ---
#   POST http://127.0.0.1:8000/tokenize
#     {"model": "OpenMOSS-Team/MOSS-Transcribe-Diarize", "prompt": <text>, "add_special_tokens": false}
#     -> {"count": n, "tokens": [...]}
#   Calibrate first: the empty string must answer 0 with AND without special tokens, or the counts
#   carry a chat template nobody asked for. Ship the transcripts to the host base64'd on stdin (the
#   remote-quoting gotcha applies) and print one JSON line back; the committed spans come out of any
#   run's snapshot.tsv at `snapshot.session.committed[*].{transcript,start_sample,end_sample}`.
#   Note what is being counted: the COMMITTED (relabeled) transcript, not the decoder's raw output.
#   They differ only in the speaker tag, which is why it is a sound proxy for a token budget.

# --- the decode-cap latency probe (iteration 24). Answers what D-c's token cap COSTS a runaway,
#     which no live run can answer until a span happens to run away. Induces the runaway instead.
#     Read-only on deployed state: no session, no device, no auth write, no restart - it sends
#     inference requests to the resident vLLM, like live-identity-seam-probe.py. ~35 s.
#     rc 0 runaway reproduced AND capped AND faster / 3 no runaway (INCONCLUSIVE, not a pass) /
#     4 the cap did not stop generation / 2 could not run.
# 1. BUILD THE AUDIO FIRST, and do NOT reach for golden.wav: it decodes to ZERO tokens (the fence
#    already recorded that under H blocker 4) so every condition comes back empty and the run is
#    wasted. Use a real-speech span, byte-deterministically:
python3 scripts/ralph-afk/build-span-sweep.py --out-dir /tmp/i24-sweep \
  --report /tmp/i24-sweep/index.json --seconds 20 --lead-seconds 1.0 \
  --lane-offset-ms system=137 --cut 92208:40000 --cut 268208:40000
#    sha256 must still be 844e6eff… / 038cf855… (re-verified in iteration 24, two runs apart).
# 2. Ship probe + wav base64'd on ONE stdin script, run under the SERVICE venv from the deployed
#    checkout, and `rm -f "$D"/*.wav` in the SAME invocation - audio does not belong in /tmp there.
#      "$V" probe.py --wav span.wav --checkout /mnt/d/Coding/MOSS-Transcribe-Diarize \
#        --span-samples 40000 --repeats 3 --extra-field temperature=2.0 --extra-field seed=20260728
#    The seed makes the capped run a true PREFIX of the uncapped one, so the pair is comparable.
# 3. THE TRIGGER IS MEASURED, NEVER ASSUMED. There is no `ignore_eos` and no `min_tokens` on this
#    endpoint (read off its own /openapi.json). Surveyed in iteration 24 against control 49 tokens:
#      temperature=2.0                      -> 2048  RUNS AWAY  <- the only one that works
#      repetition_penalty=0.5               -> 0     SUPPRESSES generation entirely
#      frequency_penalty -2.0/-1.0, presence_penalty -2.0, both, repetition_penalty 0.9 -> 27
#      repetition_penalty=1.05              -> 49    unchanged
#    Re-answer it with `--survey --candidate 'label:field=value[,field=value]'` if the engine moves.
# 4. COUNT TOKENS AT THE ENGINE SEAM, NOT THE PRODUCT'S. `RunnerBoundedWavInference` maps an
#    unparseable answer onto H1's empty path and reports **0** generated tokens however long the
#    engine ran, so a genuine 8.2 s runaway scores as "0 tokens, no runaway". The probe reads
#    `usage.completion_tokens` off the response itself and flags `product_lost_the_count`.
#    Measured iteration 24 on 77e0014: 2048 tok / 8.129 s uncapped vs 286 tok / 1.074 s capped.

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

# --- D1: publish the reviewed merge --------------------------------------
# SPENT in iteration 17. `git push origin main` fast-forwarded 163e969..f9285d6 on the AlphaSight
# fork (118 commits) and the host is detached at f9285d6. The push is one-way - the PRD forbids
# force-push - so do not re-run any of this. `upstream` is OpenMOSS: never push there.
# Standing rollback for the host checkout, still valid until D3 changes the host:
#   git -C /mnt/d/Coding/MOSS-Transcribe-Diarize checkout 163e969
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
# --- K5c: publish + redeploy the FIFTH merge (SPENT in iteration 6 of run 20260728-181020) -------
# The push fast-forwarded 6a540fe..fc7097d; never re-run it and never force-push. This was the first
# NOT-server-only redeploy: server restart AND a Mac rebuild+reinstall. Server side, J5c's order:
#   cd /mnt/d/Coding/MOSS-Transcribe-Diarize && git fetch origin main --quiet
#   git checkout fc7097d0c729ee9a96b8bf95878582e07b5b1145   # rollback: checkout 6a540fe… + restart
#   <manifest admission check, under the venv python, AFTER the checkout>
#   systemctl --user restart moss-live-web.service
#   for i in $(seq 1 40); do curl -sk … https://127.0.0.1:7861/live …; done   # POLL; 200 at 8 s
# PARITY WITNESS WHEN THE MERGE ADDS NO NEW FILE (J5c's rule does not apply): hash each CHANGED file
# on the host and compare against BOTH `git show <new>:<f>` and `git show <old>:<f>`. Matching the new
# hash while differing from the old is the same discriminator a new file gives you. Hashing an
# unchanged file proves nothing. Here: live_helper_failure.py 728f26ce… (old df9a1428…),
# live_service_runtime.py 832b1878… (old fba8c4c1…), live_v2_session.py 9b145d2e… (old c961f2d6…).
# Prove the DEPLOYED code carries K3 under the service's own venv (read-only, re-runnable):
#   LiveHelperTerminalRecord(session_id=…, reason=…, lane_failures={…}).to_dict()["lane_failures"]
#   "lane_failure_codes" in inspect.signature(LiveV2SessionRegistry.expire).parameters
#   "detail" in inspect.signature(LiveServiceRuntime.abort).parameters
#   and the journal line under the DEPLOYED logging config (the K3 one-liner above), which must print
#   `live helper terminal: session=… reason=… lane.<lane>=<code>` — that exact string is what K5d
#   greps the host journal for.
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
# --- J5c: publish + redeploy the fourth merge (SPENT in iteration 15 of run 20260728-112922) -----
# The push fast-forwarded b817871..6a540fe; never re-run it and never force-push. The host side, in
# THIS order (the admission check AFTER the checkout, so it exercises the code about to start):
#   cd /mnt/d/Coding/MOSS-Transcribe-Diarize && git fetch origin main --quiet
#   git checkout 6a540fe086cf819ba0e07a948da9fec0766202c3   # rollback: checkout b817871…
#   <the pre-redeploy manifest admission check below, under the venv python>
#   systemctl --user restart moss-live-web.service          # rollback: restart after the checkout
#   for i in $(seq 1 40); do curl -sk … https://127.0.0.1:7861/live …; done   # POLL; 200 at 9 s
# Parity witness: hash a file that DID NOT EXIST at the previous SHA (here
# moss_transcribe_diarize/app/live_span_bounds.py, sha256 1b299fd1…) alongside a pre-existing one —
# only the new file distinguishes "the new tree landed" from "a stale checkout that agrees".
# Prove the DEPLOYED code carries J1-J4 under the service's own venv, and exercise J1 with H4d's
# input rather than a hasattr (read-only, no server needed, re-runnable any time):
#   J1: from moss_transcribe_diarize.app.live_span_bounds import span_segments
#       span_segments("[0.11][S01] Good morning everyone. This is the microphone.[2.51]",
#                     sample_count=40000) -> [(0.11, 2.5)]        # clamped, not refused
#   J2: live_session.UNATTRIBUTED_SPEAKER == "S00"; hasattr(LiveSession,"submit_unlabeled_canonical")
#       live_identity.unattributed_transcript("[0.11][S01] hello[2.51]", sample_count=40000)
#         -> '[0.11][S00]hello[2.5]'
#   J3: issubclass(TransientTranscriptionError, RuntimeError);
#       issubclass(LiveProviderTransientError, LiveProviderError);
#       live_coordinator.DECODE_ATTEMPTS_PER_SPAN == 2; MAX_CONSECUTIVE_UNANSWERED_SPANS == 3
#   J4: CanonicalSubmission(submitted=False, refusal=None) raises ValueError;
#       LiveProviderError("x", detail={"span_id": 1}).detail == {"span_id": 1}
# NOTE `_preflight_payload` returns a **dict**, not an object: use r["available"], r["failures"],
# r["manifest_hash"] — `r.available` is an AttributeError, not a failed check.
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
# --- H4c: publish + redeploy the third merge (SPENT in iteration 6 of run 20260728-112922) -------
# The push fast-forwarded 317df4d..b817871; do not re-run it and never force-push. The host side,
# in this exact order (pipe as a script on stdin per the remote-quoting gotcha):
#   <the pre-redeploy manifest admission check below>          # BEFORE the restart, not after
#   cd /mnt/d/Coding/MOSS-Transcribe-Diarize && git fetch origin main --quiet
#   git checkout b817871414fcc8f609c6f5eb2898ec2957c7768c      # rollback: checkout 317df4d…
#   systemctl --user restart moss-live-web.service             # rollback: restart after the checkout
#   for i in $(seq 1 30); do ... curl -sk https://127.0.0.1:7861/live ... done   # POLL, ~11 s
# Prove the DEPLOYED code carries the fixes rather than trusting the SHA — run under the service's
# own venv, from the deployed checkout (read-only, no server needed, re-runnable any time):
#   "$HOME/.local/share/moss-transcribe-diarize/venv/bin/python3" -c '...'
#     H2: "hard_cap_samples" not in inspect.signature(LiveSession.__init__).parameters,
#         not hasattr(LiveSession, "_freeze_hard_cap_spans"),
#         hasattr(LiveServiceRuntime, "_require_one_span_cap")
#     H1: issubclass(EmptyTranscriptionError, RuntimeError), hasattr(LiveSession, "submit_empty_canonical")
#     H3: WebRtcSpeechProvider(vad=lambda pcm, rate: False, frame_samples=5808) raises
#         LiveProviderBundleAdmissionError, while frame_samples=160 constructs.
#         The constructor is keyword-only and `vad=` is REQUIRED — omitting it raises TypeError,
#         which looks like a refusal and is not one. Assert the exception TYPE, never just "raised".
# Four-way SHA check — the PRD clause in full. **GREEN 4/4 at
# 77e0014ac2a1eee1edb29b109024807e9489daa5 since iteration 20 of run 20260728-181020 (M6c)**, all
# four checkouts. It was 4/4 at fc7097d from K5c, 4/4 at 6a540fe from J5c, 3/4 at b817871 (m4mbp
# offline through H4c), and green at 317df4d / f9285d6 before that. The row goes RED by construction
# between a merge and its redeploy — say so rather than carrying the old green. Re-run it read-only
# any time — all four lines must print the same 40 hex characters:
git rev-parse main; git ls-remote origin refs/heads/main | cut -f1
printf '%s\n' 'cd /mnt/d/Coding/MOSS-Transcribe-Diarize && git rev-parse HEAD' |
  ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local "wsl.exe -d Ubuntu -- bash -s"
ssh -o BatchMode=yes ga0@m4mbp 'cd /Users/ga0/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize && git rev-parse HEAD'
ssh -o BatchMode=yes ga0@m4mbp \
  'git -C /Users/ga0/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize rev-parse HEAD'

# --- E2a: the m4mbp checkout (SPENT in iteration 20) -----------------------------------------
# Fences first (HEAD == 40cf854, branch main, clean), then remote + fetch + detached checkout.
# `main` and `origin` (OpenMOSS) are never touched, so the rollback moves only HEAD:
#   git -C /Users/ga0/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize checkout main
#   git -C … remote remove alphasight        # optional cleanup of the added remote
# Re-running the checkout is a no-op; re-adding the remote prints `unchanged:`. Verify with
# HEAD/tree/clean/159-files plus independent `shasum -a 256` of the reviewed tools against this
# host — do not treat `git status` alone as content proof of a cross-host copy.

# --- D3: install and start the live service (SPENT in iteration 19) --------------------------
# The profile is host-local and untracked. It was written with `$HOME` expanded AT WRITE TIME, so
# the file itself holds literal absolute paths (systemd expands nothing). Re-creating it is safe
# only if the live unit is stopped first; `install-services.sh` refuses --with-live without it.
#   /mnt/d/Coding/MOSS-Transcribe-Diarize/ops/moss-live.env  ->  MOSS_LIVE_ENABLED=1,
#   MOSS_WEB_PORT=7861, MOSS_RUNS_DIR=<checkout>/live-runs, and four absolute paths under
#   /home/devcontainers/.local/share/moss-transcribe-diarize/live/ plus
#   MOSS_LIVE_HELPER_LEASE_SECONDS=30 (key set identical to the tracked example).
# Spent invocations, in order:
#   ops/install-services.sh --with-live --dry-run     # plan/rollback/evidence, mutates nothing
#   ops/install-services.sh --with-live               # installs + enables + starts the live unit
#   powershell: & 'D:\Coding\MOSS-Transcribe-Diarize\ops\configure-windows-network.ps1' -IncludeLive
# Re-running either is safe and is the idempotence proof: the installer prints three `unchanged:`
# lines and `evidence: restart_required=none`; the PowerShell script re-asserts both portproxy rows.
# Standing rollback (still valid; apply in this order):
#   netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=7861
#   Remove-NetFirewallRule -Name 'MOSS-Transcribe-Diarize-Live'
#   & 'D:\Coding\MOSS-Transcribe-Diarize\ops\configure-windows-network.ps1'   # task back to batch-only
#   systemctl --user disable --now moss-live-web.service
#   rm -f "$HOME/.config/systemd/user/moss-live-web.service" && systemctl --user daemon-reload
#   rm -rf /mnt/d/Coding/MOSS-Transcribe-Diarize/live-runs
#   rm -f "$HOME/.local/share/moss-transcribe-diarize/live/live-auth.json"
#   rm -f /mnt/d/Coding/MOSS-Transcribe-Diarize/ops/moss-live.env

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

# --- F1 canary on the real hosts (RUN in iteration 8 of run 20260728-181020; re-runnable, ~2 min,
#     costs no operator input). Order matters: a stale in-process lane failure is sticky (K5d), so
#     always launch a FRESH app, and always `stop` before `pair`. -------------------------------
ssh ga0@m4mbp 'osascript -e "set volume output volume 45"; open -a /Applications/MOSSCapture.app'
#   ... wait ~4 s, then `pgrep -x MOSSCaptureApp` and `mtd-capture status` -> running:false, both
#   lanes "stopped". A stale /tmp/moss-capture-501/control.sock from a killed process is harmless:
#   the freshly launched app replaces it.
# Mint on the server loopback, pipe to the CLI as its OWN ssh invocation - never share that stdin
# with a remote `bash -s` script (the K5d hygiene incident):
#   PAYLOAD="$(printf '%s\n' "$MINT" | ssh … "wsl.exe -d Ubuntu -- bash -s" 2>/dev/null)"
#   printf '%s\n' "$PAYLOAD" | ssh ga0@m4mbp '~/.local/bin/mtd-capture pair --server https://100.64.0.8:7861'
# Then the driver (transfer it first; it re-execs itself for its two pollers):
#   scp /tmp/ralph-f1-canary.sh ga0@m4mbp:/tmp/ && ssh ga0@m4mbp "bash /tmp/ralph-f1-canary.sh ralph-f1-$(date -u +%Y%m%dT%H%M%SZ)"
# It pins the served leaf before trusting it, arms the app-owned probe with an early
# `mtd-capture latency` (measure() only schedules the poll on the FIRST call while running - call it
# right after `start` or the report has no samples), takes view authority through `handoff` +
# `pbpaste` into `curl -K -` on stdin, speaks the program, then reads status/latency, stops, clears
# the pasteboard. Reduce with /tmp/ralph-f1-analyze.py after pulling *.tsv + times.env.
# ALWAYS afterwards: `osascript -e "set volume output volume 31"`, `pkill -x MOSSCaptureApp`,
# re-check both TCC grants (auth_value=2) and `pbpaste | wc -c` == 0.
# Server-side tally for one session (query strings must be stripped or the count is wrong):
#   grep "$SID" journal | grep -oE '(POST|GET) /api/live/sessions/[a-z0-9]+/[a-z_]+[^ ]* HTTP/1.1" [0-9]{3}' \
#     | sed -E 's#/api/live/sessions/[a-z0-9]+/##; s#\?[^ ]*##' | sort | uniq -c

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
# rc 0 both markers landed / 3 no system marker / 4 no room marker / 5 neither. rc is NOT the whole
# answer: read section 1's prose, which separates "the mute killed the tap" from "the decoder
# rewrote the marker word" - those look identical in a marker-only check and mean opposite things.
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

### Phase L - the start-path wedge (2026-07-28, found by K5d; CLOSED - both authorized by the fifth
### amendment and both fixed, 49 in iteration 13 and 48 in iteration 14)

The fourth amendment said the cause "may need its own authorization" once `status` named the codes;
the fifth amendment gave it. The two entries below are kept because they carry the *diagnosis* — the
fix records are in the Phase M list and in the two blocks above. Note 49's stated mechanism was
**wrong** and is corrected there.

48. **L1 - `start` leaks a hot capture when the start-time heartbeat fails** `[done - iteration 14;
    fixed as one shape with 53]`. `CaptureController.swift:403` `let status = try emitHealth(…)` sits
    **outside** the `do/catch` at `:387-402` that unwinds a non-retryable publish failure, and
    **before** `scheduler.schedule` at `:404`. A 403/401 on that first heartbeat therefore throws
    past `source.stop` + `state.rollbackStart()` and past the pump, leaving exactly the state the
    code's own comment forbids: both lanes hot, `running: true`, nothing draining them, and no
    `sessionRefusal` because only the tick and the stop drain record one. `alreadyRunning` then
    blocks recovery, so a re-`pair` cannot fix it. *Shape of the fix, not a decision:* the health
    emission belongs under the same guard as the publish, and the start path is a third caller that
    must record a refusal. Note this is the **same shape** as J's four blockers - a condition the
    design contemplates is handled everywhere except the one path that ends the meeting.
49. **L2 - a starved source overruns, and the failure survives `stop`** `[done - iteration 13;
    the mechanism below is WRONG, see the Phase M list and "Candidate 49's mechanism was wrong in the record" (RETIRED, grep progress.txt)]`. With no pump, the lanes overrun (`macos_buffer_overrun`,
    14005 / 1379 dropped) and `NativeLaneHealth` keeps `projection.failure` across a stop/start
    **inside the same process**, so the next `start` publishes a first heartbeat that says both lanes
    are dead and the server correctly ends a meeting that never began. Two questions the operator's
    authorization would have to settle: whether a new `start` resets lane failure state (K4 already
    ruled that "a new session id is a new question" for `sessionRefusal` - the same argument applies
    here), and whether an overrun is even a lane *failure* rather than a lane *degradation* with a
    dropped-frame count. Do not fix L2 alone: without L1 the starvation just happens again.
    *Iteration 11 raised the stakes on the second question:* an overrun classed as a **failure** is
    carried by the next heartbeat into `LiveV2Session.fail_lane`, which closes that lane on the
    **server** for the rest of the meeting with no way back. So the classification is not a reporting
    detail - it is what makes candidate 53's wedge permanent. See "The 409 is NAMED" (RETIRED, grep progress.txt).

### Phase M - what F1 and F3 found. 50/53 AUTHORIZED by the fifth amendment; 51/52/54 done; 55 open

**55 is NOT in the fifth amendment's scope.** Do not fold it into that cycle; it needs its own
authorization, and the cycle's gate (F1 and F3 both green) does not depend on it.

50. **A decode that runs away is unbounded, and it is what fails the latency gate** `[open - needs
    authorization; tracked server source under the post-merge freeze]`. Measured in F1: two of 42
    spans decoded at RTF **3.398** and **3.318** (8.49 s and 8.29 s for a 2.5 s span), both
    degenerate repeat loops, and because the decode queue is serial each one delayed every span
    behind it by up to 8.3 s. Committed p95 **9053 ms**; median lag ≈ 0 s. K5d's unrelated quiet
    meeting measured **9089 ms**, so this is not content-specific. *Shape of the fix, not a
    decision:* bound the decode - max new tokens derived from the span's own duration, a repetition
    guard, or a wall-clock deadline after which the span degrades (commits empty, or without labels)
    instead of holding the queue. **This is the same class prd.md's third amendment settled**: a
    condition the design contemplates must degrade rather than damage the meeting - here it damages
    latency instead of ending the session, which is why no existing gate sees it. Note two things
    before acting: (a) the two ordered remedies in the plan (2.0 s span cap, then 0.5 s poll
    interval) do **not** attack this term, so following them would burn a cycle for nothing; (b) a
    per-span deadline needs a decision about what a timed-out span publishes, exactly as H1 needed
    one for an unparseable span - decide it once and record it, as H1 did.
51. **The canary harness puts the SAME audio on both lanes, which confounds the label clause**
    `[done - run 20260728-181020 iteration 12; see "The lanes are separated" — RETIRED, grep progress.txt]`. Fixed by
    **muting the system output for the program**, which a run proved the process tap is upstream
    of. Echo gone (0 of 46 spans with a repeated fragment, vs F1's 3 of 42; 49 fragments vs 304)
    and the label clause verified for the first time (`S04`/`S06` stable for the two voices across
    the whole meeting). The harness is now **in the repo**, not `/tmp`:
    `scripts/ralph-afk/live-canary.sh` + `live-canary-analyze.py`. **Two things it did not buy,
    both now measured:** the microphone lane still has no content of its own (MacStudio's speaker
    at volume 60 never reached it — the mic is AirPods Pro over Bluetooth), so a run is *program vs
    room*, not two speakers; and the marker cross-check failed a second time (`umbrella` after
    `pineapple`), so the driver now says the marker alone and repeated — **written, not yet
    exercised**. Original text kept below because F2 still has to honour it.
    `[superseded]` `say` through the MacBook
    speakers reaches the system tap directly *and* the microphone acoustically, so the mixer sums the
    program with its own echo: 16 canonical speakers for 2 voices, duplicated sentences in the
    transcript, and a marker word ("pineapple" → "Hi Apple") that could not be cross-checked. Fix the
    harness before F2, not after: the lanes must carry **different** content, which is what a real
    meeting is. *Shape:* pre-render voice A to a file and play it through a process whose output the
    tap captures while the speakers stay muted, and give the microphone lane voice B from the room -
    or, if only one output device exists, accept that one lane is the program and the other is the
    room and say so in the record. Also worth pinning down while there: `AudioHardwareCreateProcessTap`
    with the default `CATapDescription()` (`isExclusive = true`, empty process list) captured `say`
    output as expected, so an arbitrary application's audio will be captured too.
52. **`context.md` no longer fits in one sitting** `[done - run 20260728-181020 iteration 10]`.
    It had reached **339 018 bytes / 3985 lines** and the Read tool refuses anything over 256 KB, so
    every iteration paid for a header scan plus targeted `sed` ranges before it could choose work.
    Compacted to **~129 KB / ~1500 lines** (2.6×) by *moving*, never deleting: the entire
    pre-compaction file is appended to progress.txt under
    `ARCHIVE OF context.md AS OF RUN 20260728-181020 ITERATION 10`, and what stayed behind is a
    two-table index (shipped contracts; gates/merges/redeploys) that carries each block's **rule and
    anchor** with its transcript one `grep` away. Live evidence — K5d, F1, F3, the rollback
    rehearsal, the TCC/E3 surface, the standing pre-merge procedure, the whole Validation fence and
    the open candidate lists — was carried forward **verbatim**. One real contradiction was repaired
    on the way: the "Server state" block still said the deployed SHA was `317df4d` while the K5c
    block said `fc7097d`; the new "Deployed reality" section states `fc7097d` once.
    *The standing rule that keeps it compact:* new evidence goes in as the conclusion plus the
    numbers that justify it, and the transcript goes to progress.txt **when it is written**.
    *What is NOT achieved, stated rather than implied:* the Read tool's binding limit is **tokens**,
    not the 256 KB byte cap — 25 000 tokens is ≈ **51 KB** of this file's prose (measured: an
    800-line / 70 013-byte slice of the old file cost 28 217 tokens, i.e. 2.48 bytes per token). So
    the file is now **three sequential `Read`s and no searching**, where it was "refuses to open,
    then grep + `sed` ranges". Reaching a single `Read` needs another 2.5× cut, and the only blocks
    big enough to supply it are the **Validation fence** (669 lines, ~54 KB — the whole recipe book
    for every gate, probe, canary, soak and rollback) and the **F1/F3 evidence** (165 lines — the
    live diagnosis candidates 50/53/54 rest on). Both are load-bearing today. Revisit after
    candidate 53 lands, when F1/F3 become history and the fence's client-side half can be pruned
    against a passing run.
    ***Second pass, iteration 30*** `[done]`. The revisit condition above was reached in substance
    (53/48/49/D-a/D-c merged at `77e0014`, deployed, and proven on the real hosts by iteration 26 —
    though F1 itself did not pass, being cut short by candidate 56). **Twenty** superseded blocks —
    K5d, the F1 and F3 diagnoses, the whole Phase L/M mechanism narrative, the three D-c measurement
    blocks, and the merge/redeploy records — moved to progress.txt verbatim under
    `ARCHIVE OF context.md SUPERSEDED BLOCKS — RUN 20260728-181020 ITERATION 30`, replaced by the
    "Retired evidence — index" table with each block's title, what it settled, and where its
    conclusion still lives. **257 135 → 183 529 bytes, 2977 → 2081 lines (−28.6 %)**: five sequential
    `Read`s down to four. *What was NOT cut, and why:* the **Validation fence** (~830 lines, ~66 KB)
    is the recipe book for every gate, probe, canary, soak and rollback, and nothing in it is
    superseded — the two `/tmp` driver recipes it still carries are the only candidates, and F1's
    prelude is shared by the in-repo drivers. Reaching two `Read`s means cutting it, which is a
    trade, not a free win. *The reusable half of this pass:* the retirement was **mechanical** — one
    splice script, both ranges asserted byte-identical in progress.txt afterwards
    (`R1 in prog` / `R2 in prog` both True against `git show HEAD:…`) — and the twelve dangling
    `See "<title>" above/below` cross-references were repointed at the archive rather than deleted,
    because a reference that silently stops resolving is the same defect class this loop keeps
    paying for.

53. **A throwing publish stops the heartbeat, so one dropped audio buffer ends the meeting**
    `[done - iteration 14; the diagnosis below is kept, the fix record is in the Phase M list and
    "The heartbeat is uncoupled from the publish" — RETIRED, grep progress.txt; ROOT CAUSE of both red certification runs]`. Measured in F3 and re-read in F1's journal: an overrun on one
    lane makes the next `POST /frames` answer 409, `publishPendingFrames` throws at
    `CaptureController.swift:413`, `emitHealth` at `:417` is skipped, the same frame is refused on
    every retry so the heartbeat never resumes, and the 30 s helper lease ends the session. F3 died
    at minute 14.6; F1 died 30 s after its own overrun, inside the window its `stop` hid.
    *Shape of the fix, not a decision:* the tick's health emission must survive a failed publish the
    same way it already survives contention (the comment at `:410-412` states the rule the code only
    half implements) - and, separately, a lane whose frames are permanently refused must degrade
    (stop publishing that lane and report it) rather than block the pump forever. **Iteration 11
    named the refusal and it changes this list** (see "The 409 is NAMED" — RETIRED, grep progress.txt): the 409 is
    `"v2 <lane> lane is failed."`, armed by the client's own heartbeat, and it is **permanent** -
    so *"the client resynchronises the lane sequence" is a dead remedy* and is struck from the
    decisions. What is left for whoever authorizes this: (a) whether a heartbeat may be sent while a
    publish is failing - **it must**, and iteration 11 measured that a heartbeat sent after the
    refusal still returns 200, so this alone would have kept F3 alive; (b) what the client does with
    a lane the server has permanently closed (it must stop publishing it - the peer lane still
    returns 200, so the meeting continues one-laned); and (c), one level up and cheapest of the
    three, whether `macos_buffer_overrun` should be a lane **failure** at all rather than a
    degradation with a dropped-buffer count - fixing (c) stops the chain before the server ever
    closes the lane. **Same class as Phase J and L1** - a condition the design contemplates ends the
    meeting.
54. **Nothing on either host records *why* a frame was refused** `[ANSWERED - run 20260728-181020
    iteration 11; no authorization was needed and none was spent]`. The question was which of the
    seven distinct 409 conditions on `POST /frames` F3 took.
    `scripts/ralph-afk/live-lane-refusal-probe.py` settled it against the real `create_app`:
    **`LiveV2SessionTerminalError` → `{"detail": "v2 system lane is failed."}`**, not the
    `LiveV2OutOfOrderFrameError` that was on record as likeliest - which the outbox's
    burns-no-sequence-on-refusal invariant (`CaptureOutbox.swift:116-120`) rules out by construction,
    and which the probe shows would have looked completely different on the wire (a machine-readable
    `failure.code`, and **recoverable**). *What remains, and it is now an ordinary durability
    candidate rather than a blocker:* the lane-failed 409 carries a bare `detail` and no
    `failure.code`, and the client discards the body by G3's contract - so a future authorization may
    log the refusal server-side, give it a typed code, or stop discarding it client-side. Pick one
    when 53 is authorized; nothing is blocked on it now.
56. **A live session stops being viewable mid-meeting, and nothing records why** `[open - needs
    authorization; found in iteration 26, reproduced twice]`. Both F1 re-runs against `77e0014`
    died at one instant (t+18.1 s and t+32.1 s) with three simultaneous symptoms: view routes
    **401 `invalid bearer authority`**, `POST /frames` **409 permanently on both lanes**, and the
    client's `pumpFailure: transportUnavailable`. No lane ever failed, the heartbeat returned
    **165 × 200** in both runs, and the only terminal record is the post-stop `helper_lease_expired`.
    `live_auth.py:282` raises that message only when `_view_for_digest` returns None, so for an
    unexpired unrevoked token `_session_is_viewable` (`:382-385`) went false - the **session left
    `VIEWABLE_SESSION_STATUSES`**, which is also what makes `POST /frames` answer the *closed-session*
    409. One cause, both symptoms. **This is the same class the third amendment settled and the
    fourth found again: a condition ends the meeting and the one word naming it is discarded** -
    no journal line, 0 tracebacks, an event stream that stops mid-sentence, and the 409 body (which
    *does* carry `terminal_reason`) thrown away by G3's client contract. *Shape of the next step,
    not a decision:* `live-pipeline-probe.py` already keeps the refusal body and needs no Mac -
    iteration 23's 120 s run on this same SHA was healthy, so the trigger is something real capture
    does that synthetic audio does not (variable frame sizes, real speech, the identity path).
    Reproduce it there before designing anything.
    **Iteration 27 tried and FAILED to reproduce, eliminating four hypotheses** (all still valid,
    and all about the audio): not continuously-voiced two-lane audio, not span density, not the
    identity path, not the helper lease or any heartbeat-driven terminal, not lane clock drift.
    ***ANSWERED IN ITERATION 28*** - see the candidate-56 answer block above. One probe run with
    `--concurrent-readers 2` reproduced it at t+31.5 s and kept the 409 body:
    `canonical_decode_failed` / *"runner result elapsed_sec must be finite and non-negative."* /
    `LiveProviderError`, non-retryable. `vllm_runner.py:111` measures `elapsed_sec` on the **wall**
    clock (`time.time() - started`) and the deployed host's wall clock steps **~1.5 s backwards
    every ~32.3 s** (measured: 3 steps in 90 s). `live_adapters.py:344` then rejects the negative
    number as a non-retryable provider error and `_process_in_flight_item` ends the meeting.
    *Shape of the fix, not a decision, and it needs authorization:* `transcribe_pcm` **already**
    takes `started = time.monotonic()` (`live_adapters.py:305`) and uses it on the empty-transcript
    branch (`:317`); the success branch discards it. Either use it, or degrade the timing metadata
    (elapsed/RTF null) instead of raising - a decoder that returned a transcript on an untrustworthy
    clock has not made the meeting impossible to continue. **Also fix the metric, not only the
    crash:** `elapsed_sec` is the numerator of the PRD's `decoder p95 RTF < 1` clause, so every RTF
    recorded so far came off that stepping clock.
57. **The clause reducer calls a passing latency number RED** `[open - loop tooling, no
    authorization needed; found in iteration 26]`. `live-canary-clauses.py` printed
    `USER-VISIBLE p95 = 3921.8 ms vs gate 4000 ms  RED`. The number is *under* the gate; it is red
    because `sufficientSamples=False`, which the line above it states. The message asserts a
    threshold comparison that passed, so a reader who trusts the verdict line learns the opposite
    of the truth. Same shape as iteration 22's finding that the reducer *printed* F1's lane failure
    and *decided* nothing - separate "the gate was missed" from "the run cannot answer the gate".
55. **Identity capacity saturates in the first minute, so no later voice can ever be labelled**
    `[open - needs authorization; tracked server source under the post-merge freeze; found in
    iteration 12]`. `max_identity_speakers` is **16** (a domain-contract bound). Two independent
    runs reach it mid-meeting: the echo-free canary at **t+45.5 s** of 89 s, and F1 - re-reduced -
    at **t+51.8 s** of 89 s. The consumer is low-content fragments, mostly the microphone lane's
    ambient noise, each minting a fresh canonical speaker. After saturation `live_identity.py:121`
    (exhausted speaker capacity) is the designed outcome, so a participant who first speaks at
    minute 5 of a real meeting can **never** receive a label. This is what actually produces F1's
    "16 canonical speakers for 2 voices"; the echo was the wrong explanation. *Shape of the fix,
    not a decision:* the capacity is a contract value and must **not** be raised to hide this - the
    question is what may **consume** a slot (a minimum span energy or duration before a fragment
    may mint a speaker; reuse or eviction of slots that never recur). Same class the third
    amendment settled for terminal failures: a condition the design contemplates quietly degrades
    the meeting. It does **not** end a session - J's cycle already made `abstain` non-terminal - so
    no existing gate sees it, exactly like candidate 50.

### Phase M - survive a lane fault (2026-07-28, fifth amendment: 48, 49, 50, 53 AUTHORIZED)

The operator authorized candidates **48, 49, 50 and 53** together on 2026-07-28. Candidate 54 is
**closed** - answered by `scripts/ralph-afk/live-lane-refusal-probe.py` with no product change.
Read the "The 409 is NAMED, and the meeting was survivable" block before designing anything: the
peer lane survives a lane fault, a heartbeat after the refusal returns 200, and **the only thing
that killed F3 was the skipped `emitHealth`**.

Governing rule from the amendment: **a fault on one lane must not end the meeting.** No publish
failure may stop the heartbeat; a transient resource condition must not permanently disable a lane.

**D-a, D-b and D-c are TAKEN (iteration 13)** - see "The three Phase M decisions, taken and binding" — RETIRED, grep progress.txt
above for the rulings and progress.txt for the full reasoning. In one line each: an overrun is a
**degradation**, not a failure (so the server needs no change and the chain breaks at step 1); a
failed lane does **not** recover inside a generation but **always** does across a `stop`/`start`
(K4's rule), and `LiveV2Session` gains no un-fail path; a runaway decode is bounded by a
**duration-derived token cap** whose span still commits.

**D-a is IMPLEMENTED (iteration 15)** - `[done]`, see "D-a is landed" — RETIRED, grep progress.txt. D-b needed no code (its
ruling was that `LiveV2Session` gains no un-fail path, and it has none). **D-c is IMPLEMENTED
(iteration 16)** - `[done]`, see "The decode is bounded" — RETIRED, grep progress.txt. **All four authorized candidates,
all three decisions and the coverage gap have landed; what remains in Phase M is the gate alone.**

53. **[done - iteration 14]** The tick's `emitHealth` now has its own `do/catch` after the publish's,
    so a throwing publish cannot skip it; the publish's `pumpFailure` is left standing and only a
    successful publish clears it. See "The heartbeat is uncoupled from the publish" (RETIRED, grep progress.txt).
48. **[done - iteration 14, with 53 as one shape]** The start's `emitHealth` came under the same
    guard the publish above it already used: retryable -> degraded start with the pump scheduled,
    non-retryable -> `source.stop` + `rollbackStart()` + rethrow, and the refusal recorded either
    way. `rollbackStart()` now keeps `sessionRefusal` (cleared by `beginStart`), so a refused start
    is visible in `status` instead of silent.
49. **[done - iteration 13]** Not `NativeLaneHealth`'s projection, which `beginGeneration()` resets
    correctly. `NativeDualCaptureSource.start` zeroed the `reportedDroppedBuffers` watermark while
    the queue's per-lane drop counter is cumulative for the whole process, so the new generation's
    first drain replayed every historical drop as fresh loss and failed the lane on its first
    heartbeat. Now re-baselined against the queue; red-before/green-after. See "Candidate 49's mechanism was wrong in the record"
    (RETIRED, grep progress.txt). **D-a still has to land** - this fix stops a *previous* generation's drops failing a
    lane; it does nothing about the current one's.
50. **[done - iteration 16]** Bounded per D-c: `canonical_decode_token_cap` =
    `68 + ceil(87 × duration_sec)`, each term an observed maximum times an explicit margin of 4,
    derived by tokenising F1's and the canary's committed spans with the deployed decoder's own
    tokenizer. The bound in force before this was `VllmRunner`'s 2048 default, which is exactly
    where both runaways stopped (2024 / 2019 tokens). A capped span commits its words and the
    `canonical_processed` event carries `canonical_decode_token_cap` / `canonical_decode_capped`.
    See "The decode is bounded" — RETIRED, grep progress.txt. **DEPLOYED in iteration 20** — the host's own interpreter
    reproduces the cap as 286 (2.5 s) / 112 (0.5 s), so the offline probes speak for the service
    again. **MEASURED ON THE WIRE in iteration 23**: 58/58 spans of a real 120 s pipeline-probe run
    carry a per-span cap matching the product's own function (21 distinct values 89…286), and the
    cap's **safety** is confirmed on an independent third dataset (min headroom **7.64×**, vs 4.88×
    on the derivation dataset). `capped_count` was 0 there, so the cap was deployed and
    *unexercised*. **ITS LATENCY EFFECT IS NOW MEASURED (iteration 24)**, by inducing the runaway
    rather than waiting for one: on the deployed engine, over the same 2.5 s span and the same
    trigger, a decode costs **8.129 s at the pre-D-c 2048 bound** and **1.074 s at the deployed cap
    of 286** — **7.571×**, 7.056 s off the head of the serial queue, RTF 3.277 → **0.431**. It
    reproduces F1's own runaways within 4 % (2048 tok / 8.13 s vs F1's 2024 / 8.49 s), which
    confirms iteration 16's 238 tok/s prediction at a measured **251.9 tok/s**. Since F1's mean span
    arrival was 1.745 s, a capped decode sits *below* the arrival interval and cannot build backlog
    where the uncapped one is 4.66× it and must. **ITS "COMMITS ITS WORDS" HALF IS MEASURED TOO
    (iteration 25)**, offline against the deployed tokenizer and the real live coordinator: the
    capped decode's transcript is the greedy token *prefix* of the uncapped one, re-tokenising F1's
    two runaways returns exactly the **2024 / 2019** tokens their own decode reported, and at the
    286-token cap each still commits **18 segments** with `empty_reason` None — while an
    exhaustive sweep of **9062 cut points** finds **0** terminal and **0** unclassified outcomes.
    The same run found that F1's two runaways carry **zero word characters** (127 segments of
    `...`), so the spans that set F1's whole latency tail bought no transcript content at all.
    **Still open and only F1 can close it:** the *rate* of runaways and the end-to-end p95 on the
    Mac. See "D-c's OTHER half is settled" — RETIRED, grep progress.txt.
D-a. **[done - iteration 15]** `macos_buffer_overrun` is a lane degradation. Two code enums, a
    `degraded` state the server's contract already had, the mailbox's overrun fence removed (it
    would have silenced a still-producing lane), the mailbox overflow given its own code, and K2's
    log following the condition. Server unchanged. See "D-a is landed" — RETIRED, grep progress.txt.
54. **[CLOSED - answered, not fixed]** The refusal reason is known. 53's fix **may** stop discarding
    the server's refusal detail where it must tell a permanent lane-failed 409 from a recoverable
    one; that is the only part of 54 in scope.

**Coverage gap - CLOSED in iteration 17.** `tests/test_live_api.py` now posts a frame on the lane
that **failed** (409, permanent, peer + lease survive) and on the lane that **degraded** (200,
health stays active), both red-proved by semantic revert of the two guards that decide them. See
"The failed lane is in the suite" above. **Nothing remains in Phase M except the gate.**

**Gate, in four steps. The order is decided — see "The Phase M gate is green" — RETIRED, grep progress.txt — for why the
amendment's literal order is unreachable and why this one drops nothing.**
- **(a) full local gate + payload review** `[done - iteration 18]`. GREEN at `21a73ea`:
  Swift 158/0 with 0 warnings on a fresh scratch, Python 604+2/368 in 62.7 s, tracer 4/0 skips,
  discriminator 10/10, lane-refusal probe rc=0, seven hard-cap cases rc=0, leak-scan clean, tree
  clean. Payload 10 files / +983/-51, all in `macos/`, `moss_transcribe_diarize/`, `tests/`.
- **(b) the sixth merge** `[done - iteration 19]`. `main` = **`77e0014`**, feature tip `4ac5d95`,
  join `1b6a9f4`, in-worktree gate Swift 158/0 + Python 604+2/368 on the merged tree, payload
  exactly the reviewed 10 files / +983/-51, guard rehearsed non-vacuously. See "The sixth merge is
  made" above.
- **(c) push + redeploy** `[done - iteration 20]`. Four-way SHA back to **4/4 at `77e0014`**; server
  MainPID 346453 → 350731 with `/live` 200 in 9 s and batch untouched; Mac rebuilt + reinstalled with
  the DR byte-identical and both TCC grants intact. D-c exercised on the host (cap 286/112) and D-a
  found in the installed binaries by a strings witness with a control word. See "M6c is deployed" — RETIRED, grep progress.txt
  above.
- **(d) F1 and F3, both required green** `[BLOCKED in iteration 21 - m4mbp is asleep/off the
  tailnet; setup completed, the meeting never ran. See "F1's re-run is blocked on a sleeping Mac" — RETIRED, grep progress.txt.
  Retry the moment `ssh ga0@m4mbp` answers: pkill the app left running, relaunch fresh, re-pair
  (the iteration-21 pairing code is spent), then the nohup'd driver]**, with candidate 51's harness
  — `live-canary.sh` for F1 and, since iteration 22, `live-soak.sh` for F3, both `OUTPUT_MODE=muted`
  — so the label clause is meaningfully verified, and the marker-alone-×3 change
  that is written but never yet exercised. Reduce both with `live-canary-clauses.py` (the soak with
  `--user-visible-gate-ms 6000`); it now decides the lane-health and view-authority clauses instead
  of printing them. **Run F1 first** — 60 s against F3's 17 minutes, so if
  the latency prediction is wrong it says so seventeen times cheaper. This is the first run that can
  see whether 53/48/49/D-a keep a meeting alive through a lane fault. **What it still has to decide
  about candidate 50 narrowed in iteration 24:** the per-span decode bound is no longer a prediction
  — 8.13 s → 1.07 s is measured on the deployed engine, and iteration 25 measured that a capped
  span still commits rather than going empty — so F1 is now measuring the *rate* of runaways and the
  end-to-end p95 on the Mac, not whether the cap works or what it costs the transcript. If F1's
  committed p95 is still ~9 s with `capped_count` 0, the cause is **not** the decode and the plan's
  ordered remedies become live for the first time. Both runs need their
  own pre-recorded rollbacks (volume, app, session, `/tmp` evidence) per iteration 12's list.

### Open diagnostic candidates — the numbered ones, in one place

55. **Identity capacity saturates in the first minute** (iteration 12). The 16-speaker bound is
    reached at t+45.5 s (t+51.8 s in F1), so a voice arriving later can never be labelled. Degrades
    quality without ending a session, so no gate sees it. Tracked product source; **needs its own
    authorization** — and Phase N's `N1`/`N3` may subsume it, since a 0.5 s fragment that becomes a
    prototype is a plausible source of the phantom speakers that exhaust the bound.
56. **A live session stops being viewable mid-meeting.** `[CLOSED — fixed run 20260729 it. 1,
    merged as 42abc5a it. 4, deployed and PROVEN ON THE SERVER it. 5]`. Cause: the server host's wall clock steps ~1.5 s
    backwards every ~32.3 s, `vllm_runner.py:111` measured `elapsed_sec` on it, and
    `live_adapters.py:344` turned a negative one into a non-retryable `LiveProviderError` that ended
    the meeting. Authorized as **Phase P** by the seventh amendment and implemented as P1-P4; see
    the candidate-56 answer block for the failure record and the clock measurement, and the Phase P
    block for what landed. **It blocks nothing now:** the same probe invocation that reproduced it at
    t+31.5 s ran its full 150 s plan on the deployed `42abc5a` with zero non-200s, while the host
    clock was measured still stepping every 32.29 s. The hazard is permanent; the defect is gone.
57. **The reducer called a passing latency number RED.** `[done — iteration 29]`. See "The reducer
    stopped calling a passing number RED" below. Loop tooling; no authorization was needed.
59. **The marker check calls a landed marker absent, because it matches the word exactly.**
    `[open, new — run `20260729-025318` iteration 6; loop tooling, no authorization needed]`.
    `live-canary-analyze.py` scored `cardamom` **NOT FOUND** in a run whose transcript contains
    `Cockamom, cockamom, cockamom.` — isolated, repeated, three times, in the correct phase, on the
    correct lane. The decoder rewrites a rare noun **phonetically**, which is precisely why the
    driver was changed in iteration 12 to say the marker alone and slowly; the reducer never learned
    the same lesson, so `rc=5` was printed over a marker clause that holds. *Shape of the fix, not a
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
    with degraded spans should be allowed to certify. Detail in the Phase P block.
61. **`live-canary-analyze.py` crashes on any pruned evidence directory.** `[open, new —
    run `20260729-025318` iteration 11; loop tooling, no authorization needed]`. It raises
    `KeyError: 'transcript'` at `live-canary-analyze.py:142` on an F2 directory, because it reads
    spans out of `snapshot.tsv`, whose rows every current driver **prunes to `span_id` only**
    (`SNAP_PRUNE` in `live-cert.sh`/`live-soak.sh`). The transcript survives in the periodic
    `snap-full-*.json` files, which the analyzer never opens. *Shape of the fix, not a decision:*
    read spans from `snap-full-*.json` when the TSV projection has no `transcript`, and — the part
    that matters — **fail with a named refusal instead of a traceback**, the same rule
    `live-canary-clauses.py` already applies to a layout it cannot read. It cost this iteration
    nothing (the markers were extracted by hand in five lines) but it means the lane-separation
    verdict is unavailable for F2 and F3 as shipped.
62. **The reducer asked a certification run the soak's questions.** `[done — iteration 11]`. See
    "THE REDUCER STOPPED ASKING A CERTIFICATION THE SOAK'S QUESTIONS" above. Loop tooling; it made
    F2 ungreenable for candidate 60, a defect outside F2's clause list.

### Phase N - live speaker identity (2026-07-28, sixth amendment; AFTER Phase M)

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

### Phase P - the wall-clock duration (2026-07-28, seventh amendment) - DO THIS FIRST

Authorized after iteration 28 root-caused candidate 56. **Phase P precedes Phase N, and F1/F3 must
NOT be re-run as a gate until it is deployed** - every certification run dies at ~13 % per 32 s
until then, so a red run measures this bug and nothing else.

60. **P1 - use the monotonic reading that is already taken.** `[done - run 20260729 it. 1]` The
    success branch no longer reads the runner's `elapsed_sec` **at all**; it takes
    `time.monotonic() - started` from the reading the function already had, so both branches now
    measure the same bracket on the same clock. A runner reports whatever clock it holds, so the
    durable rule is *the live decode measures itself*, not *the runner must be trusted*.
61. **P2 - untrustworthy timing metadata degrades, it does not end the meeting.** `[done - it. 1]`
    Stated once as `live_adapters.trustworthy_duration_sec(value) -> float | None`, a **conversion**
    rather than a guard, and applied at both layers that used to raise: `InferenceTranscript.
    __post_init__` and `live_coordinator._canonical_decode_measurement`. Elapsed and RTF are both
    recorded null on `canonical_processed`, the span still commits, and the degradation is
    **logged** (`moss_transcribe_diarize.live.decode`, WARNING, naming span id / field / value) -
    because a measurement that silently disappears is the "known but not shown" shape again.
62. **P3 - real-seam regression** `[done - it. 1]` Four nodes in `tests/test_live_pipeline_seams.py`
    under "The timing seam: a wall clock is not a duration". Red-before proved by semantic revert,
    one half at a time - see the Phase P block below for which revert reddens which node.
63. **P4 - sweep the class.** `[done - it. 1]` Four sites enumerated, three fixed, one ruled
    deliberate. See the sweep table in the Phase P block below.
64. **P5 - gate, merge, redeploy, THEN re-run F1 and F3.**
    - **(a) full local gate + payload review** `[done - it. 2]`. GREEN at `5bc4f7f`; the numbers are
      in the Phase P gate row of the gates index. Nothing regressed and nothing was weakened: the
      six `test_live_vad.py` nodes that asserted the *superseded* rule were **restated** with a
      docstring naming what they supersede, and the replacement assertion (a real monotonic
      measurement is present) is strictly stronger than the one it replaced.
    - **(b) the seventh merge** `[done - it. 4]`. Landed as **`42abc5a`**, parents `77e0014` +
      feature tip `96137b1`. The standing two-fence procedure ran in full: the join `cfa3a96` was
      proven content-free *before* it was made, `expected_main` was advanced **in the script**
      (`96137b1`) citing the seventh amendment rather than by `RALPH_MERGE_MAIN_BEFORE`, and
      `merge-keeper.sh` ran **in the background**. Numbers in the P7 row of the index below.
    - **(c) push + redeploy** `[done - it. 5]`. The J5c shape, exactly as planned: push
      fast-forwarded `77e0014..42abc5a`, the server checked out and restarted (MainPID 350731 →
      355607, `/live` 200 at **8 s**), and m4mbp checked out with **no rebuild**. Four-way SHA
      **4/4**. Evidence in the P5(c) block above, including the probe that used to die.
    - **(d) F1 then F3** `[F1 done - it. 6, GREEN, rc=0; F3 OPEN and NEXT]` — the Phase M gate step
      (d) that candidate 56 blocked. F1 passed on the first attempt against `42abc5a`; see the
      F1-green block. **F3 is now the single remaining item in front of Phase N.** Run it with
      `live-soak.sh OUTPUT_MODE=muted` nohup'd on m4mbp, reduce with
      `live-canary-clauses.py --user-visible-gate-ms 6000`, and read the F1 run's two live warnings
      into it: decoder p95 RTF was **0.911**, close to the bound and driven by short
      silence-endpointed spans (a 17-minute run has far more of them), and identity saturates at
      **t+65.6 s**, so every speaker label after minute 1 of the soak is `S00` by design.
    Note in the journal that this also repairs the PRD's decoder p95 RTF clause, measured from this
    same number and therefore unreliable in every prior run. `[recorded - it. 1]`

Explicitly out of scope: mandatory client retention of the 409 refusal body. Right fix, wrong cycle;
it needs its own authorization.

**P1-P4 ARE LANDED, GREEN AND MERGED as `42abc5a` (code from run `20260729-025318` iteration 1,
merged iteration 4) — but NOT YET DEPLOYED.** Six files:
`live_adapters.py`, `live_coordinator.py`, `vllm_runner.py`, `model_runner.py`, `jobs.py`,
`tests/test_live_pipeline_seams.py`, plus the two superseded nodes in `tests/test_live_vad.py`.
Python **608 passed / 2 skipped / 368 subtests** in 59 s (604 → 608: four new seam nodes).
No Swift file was touched.

***The red-before is per-half, by semantic revert, and each half has its own named node.*** Reverting
one edit at a time and re-running the four nodes:

| revert | node that goes red |
| --- | --- |
| `vllm_runner` reads `time.time()` again | `…the_real_runner_reports_a_duration_a_stepping_wall_clock_cannot_make_negative` |
| the adapter takes the runner's number again | `…a_runner_result_whose_elapsed_sec_is_negative_never_reaches_the_span` |
| the coordinator raises on an untrusted duration | `…a_decode_whose_timing_cannot_be_trusted_commits_the_span_with_no_rtf` |
| `InferenceTranscript` raises again | the same negative-elapsed node (it asserts the type-level rule too) |
| **both wall-clock halves together = the true pre-fix state** | `…a_wall_clock_step_backwards_mid_decode_does_not_end_the_meeting` |

That last revert reproduces **iteration 28's probe record field for field** —
`kind=integrity, code='canonical_decode_failed', retryable=False,
detail={'error_type': 'LiveProviderError'}`, message *"runner result elapsed_sec must be finite and
non-negative."* — from a test, with no host. That is the seam whose absence let this ship: nothing
in the repo had ever put a runner's **own duration measurement** under the live coordinator.
*Note what round B proved:* with only the adapter reverted the full-stack node still **passes**,
because the fixed runner hands it a positive number. Defense in depth is real here, and it is also
why the per-half nodes exist — the production node alone would not catch either half being undone.

**P4's sweep, all four sites, with the ruling for each.**

| site | ruling |
| --- | --- |
| `vllm_runner.py:71,111` (the named defect) | **fixed** → `time.monotonic()`. The live path no longer reads the field, but the **batch** path computes its own RTF from it, so a wrong number was still wrong. |
| `model_runner.py:129,151` | **fixed** → `time.monotonic()`. Identical shape in the local-GPU runner; same `TranscriptionResult.elapsed_sec` field, same consumers. |
| `jobs.py:700` `_should_save_live_progress` | **fixed** → `time.monotonic()`. `now - last_saved < 0.5` is an interval, and the dict is in-process only. A backward step silently suppressed progress saves for up to the step. |
| `live_transport.py:621` `_request_now()` | **deliberate, unchanged.** It is a *timestamp*, not a duration: it feeds view-authority expiry, the 12 h absolute cap and the 30 s helper lease, all of which must survive a restart and therefore must be wall-clock. A 1.5 s step shifts an expiry by 1.5 s; it cannot make a duration negative. Same for `jobs.py`'s persisted `created_at`/`updated_at`. |

**Known and NOT fixed this cycle — the replay evaluator calls a declared absence an invalid
measurement.** `live_service_replay._canonical_decode_rtf_evaluation` (`:660-694`) runs every
`canonical_processed` payload through `_required_finite_non_negative_float`, so a **null**
`canonical_decode_elapsed_sec` lands in `canonical_decode_rtf_invalid_measurements` and forces
`canonical_decode_rtf_passed` false. This is **pre-existing, not introduced here**: J3's
`_unanswered_span` has emitted a null elapsed since Phase J. But P2 makes the null a *designed*
outcome rather than only a decoder-outage one, so the evaluator now conflates *degraded* with
*invalid* — iteration 29's lesson, one layer down, in a verifier instead of a reducer. Logged as
**candidate 58**; it is a gate-reporting question, not a meeting-reliability one, and widening this
cycle to change a verifier's pass rule is exactly what "never weaken a gate to look better" forbids
without a decision recorded first.

**What F1's two runs already established, and must not be re-derived:** Phase M works - a publish
that failed on every tick for 50 s kept 165 consecutive heartbeats alive and left both lanes
healthy, which is exactly the condition that ended F3 at minute 14.6. Committed p95 fell from
8343-9148 ms across four prior runs to 2567/2592 ms, and user-visible to 3922/3971 ms against the
4000 ms gate - **both unqualified** (`sufficientSamples` false, n=8 and n=12 against 20, runs cut at
18 s and 32 s by this very bug). Do not quote those as a pass.

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
