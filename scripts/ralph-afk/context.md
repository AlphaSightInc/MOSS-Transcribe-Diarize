# Context - MOSS live meeting transcription MVP

> **Compaction log — five passes, every one archived VERBATIM to progress.txt, nothing deleted.**
> Grep progress.txt for `ARCHIVE OF context.md` to read any pass in full.
>
> | pass | run / iteration | before → after | what went |
> | --- | --- | --- | --- |
> | 1st | `20260728-181020` it. 10 | 339 018 → 129 832 B | every per-iteration gate transcript, contract block, redeploy record and closed-phase candidate list |
> | 2nd | `20260728-181020` it. 30 | 257 135 → 183 529 B (−28.6 %) | 20 blocks: K5d, the F1/F3 diagnoses, the Phase L/M mechanism narrative, the three D-c measurements, the merge and redeploy records |
> | 3rd | `20260729-025318` it. 14 | 245 562 → 148 157 B (−39.7 %) | 26 blocks, including **11 ranges of the Validation fence** (closed phases' per-node recipes, spent one-time host recipes) and the Phase L/M/P candidate lists |
> | 4th | `20260729-094359` it. 2 | 263 219 → 199 877 B (−24.1 %) | 8 ranges: the Phase-N landing narrative and its 12 per-step blocks, the superseded `N1`-`N5` list, 22 closed rows of the gates index, candidate 60's full block, F1-on-`42abc5a`, the test-totals chain |
> | 5th | `20260729-094359` it. 8 | 249 137 → 210 671 B (−15.4 %) | 14 ranges: the four compaction narratives themselves, the two retired-evidence index tables (merged into one), the standing summary's it. 3–7 bullets, the F1/F2/F3 certification narratives, Phase N's spent gate/merge/redeploy rows, the port-publish race, and the superseded layers of candidates 55/60/65 and decision 19 |
>
> **The trigger to watch is the `Read` tool's 256 KB HARD CAP, not a `Read` count.** At 263 219 B the
> fourth pass opened with `File content (257KB) exceeds maximum allowed size` and context.md had to be
> paged blind by offset before any work could start. Measured drift is **~5–10 KB per iteration**, so
> a pass is due roughly every ten. *Honest limit, unchanged since the second pass:* the `Read` tool's
> binding limit is **tokens** (25 000 ≈ 51–61 KB of this prose) and the Validation fence alone is
> 44 KB, so **one `Read` is not reachable** without cutting something load-bearing; three to four is
> the working target.
> **How to run one:** archive the ranges **verbatim** under a banner in progress.txt, then verify by
> script that each body appears byte-for-byte there **and is absent here**, and that the surviving
> fence still passes `bash -n`. New evidence goes in as *the conclusion plus the numbers that justify
> it* — the transcript belongs in progress.txt when it is written, not later. The fifth pass also
> confirms what the fourth found: a size pass catches **staleness**, because a claim that no iteration
> re-reads is exactly the claim that goes stale (this one retired five blocks asserting a fact
> iteration 7 had already falsified).
> **The fifth pass is the SMALLEST of the five (−15.4 % against −22.9/−24.1/−28.6/−39.7 %), and the
> reason is measured rather than guessed: the duplication is gone and the remaining bulk is the
> Validation fence.** Section sizes after this pass — fence **52.5 KB (25 % of the file)**, Phase N
> 27.5 KB, "Where the loop stands" 24.2 KB, "Read before any certification run" 23.7 KB, open
> candidates 24.7 KB, "Deployed reality" 16.9 KB, shipped contracts 14.0 KB, gates index 9.6 KB.
> **So the sixth pass has to take the fence, and it should be planned rather than improvised:** it is
> one 618-line code block that `bash -n` checks as a unit, the third pass already removed 11 spent
> ranges from it, and what remains is the full gate, the probes, the three drivers, the reducers and
> the two redeploy templates. *Headroom after this pass is only ~45 KB, i.e. about five iterations at
> the measured drift* — do not wait for the 256 KB error again.

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

**PRD acceptance scoreboard (rows unchanged since iteration 9 except where noted; Phase M's local
gate is green at `21a73ea`, the sixth merge landed as `77e0014` in iteration 19, and **it is now
deployed to all four checkouts (iteration 20)** — so the two certification rows are RED-and-stale
rather than RED-and-current: F1 and F3 have never run against Phase M.)**

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
| 60 s canary (F1) | **GREEN on `42abc5a`** (iteration 6, `live-canary-clauses.py` rc=0): user-visible p95 **3909.3 ms** ≤ 4000 **and qualified**, decoder p95 RTF **0.911** < 1, 329 published == 329 accepted all 200, 370/370 view polls 200, no lane fault. **One half is NOT certified:** "two speakers" were both on the *system* lane — the microphone carried room noise only (candidate 51's recorded harness limit). Full block retired to progress.txt with the fourth compaction. **RE-RUN ON THE DEPLOYED `7a4f59c` (iteration 30, Phase N gate step (d) first half): rc=3, five clauses GREEN and TWO RED** — user-visible p95 **4150.8 ms** (miss by 150.8 ms, 3.8 %) and decoder p95 RTF **2.365**, the latter carried entirely by **3 spans shorter than 0.1 s**. See the **F1 on Phase N** row in the gates index (the narrative block is retired to progress.txt with the fifth compaction). |
| 300 s certification (F2) | **GREEN ON THE DEPLOYED `7a4f59c`** (run `20260729-094359` iteration 1, `live-canary-clauses.py --user-visible-gate-ms 6000 --interrupt-report` rc=0): six GREEN, no RED, no UNDECIDED. user-visible p95 **4078.6 ms** ≤ 6000 **and qualified**, decoder p95 RTF **0.577** < 1, **1261 published == 1261 POST /frames, and every one of the session's 4766 logged requests answered 200**, a **5.090 s** interruption seen by the client and survived, outbox 0 → **5** → 0. (Was GREEN on `42abc5a` in iteration 11 of the previous run: 3859.6 ms, RTF 0.670, 1257 == 1257 — that block is archived in progress.txt.) **One half is NOT certified and was deliberately not attempted:** the separate mic-granted / system-audio-denied run, which would spend a TCC grant. See the **F2 on Phase N** row in the gates index (the narrative block is retired to progress.txt with the fifth compaction) |
| 16-minute soak (F3) | **RAN AGAINST `42abc5a` AND FINISHED ITS WHOLE PLAN (iteration 9) — 5 clauses GREEN, 1 RED.** Candidate 53's minute-14.6 death is gone: 17/17 full minutes, every poll 200, view authority live at age 1024 s. The RED is **new candidate 60** — a clean stop does not revoke view authority, because the **Mac** client never calls the server's `POST …/stop` — the route itself works and revokes **immediately**, measured in iteration 7. `live-canary-clauses.py` rc=3. See the **F3 soak** row in the gates index. |
| Secret hygiene | static half green; run-time half green in F1, F2 and F3 as far as those runs went. **The clause's *browser storage* half was never separately measured and the "static half" does NOT cover it** — `leak-scan.sh` scans only `macos/MOSSCapture/Sources`, the tracer test and the tracer's artifacts, never the portal (found iteration 7). What *does* cover it is tracked: `tests/test_live_portal.py:217-219` asserts the served page contains no `localstorage` / `sessionstorage` / `document.cookie`, and the token is an `autocomplete="off"` password input held in a JS local and sent only as `Authorization: Bearer`. **One gap, cheap and open:** the JS harness instruments `localStorage`/`sessionStorage` with a recording Proxy and returns `storageWrites` to Python (`:618,657,737,812,841`) — and **no node ever asserts it is empty**. Dead instrumentation; a runtime write would pass today |
| Final close (F4b) | open |

**What stands between the loop and the bar (rewritten iteration 30; the Phase M narrative it used to
carry is in the retired-evidence index below).**
- **THE SEVENTH AUTHORIZATION WAS GRANTED, and Phase P's code half is DONE (run `20260729-025318`
  iteration 1).** Candidate 56 — a live session stops being viewable mid-meeting because the server
  host's wall clock steps ~1.5 s backwards every ~32.3 s and a negative `elapsed_sec` was terminal —
  is **fixed in source**: P1 (the decode measures itself monotonically), P2 (untrustworthy timing
  metadata degrades to null and is logged, stated once as a conversion), P3 (four real-seam nodes,
  red-before proved per half) and P4 (the class swept: three sites fixed, one ruled deliberate).
  Python 608/2/368 green. See the Duration-vs-timestamp row in Shipped contracts; the Phase P gate
  and P7 merge rows and the retired Phase P list are both in progress.txt.
- **PHASE P IS FULLY LANDED and its gate step (d) IS RUN, both halves.** (a) gate green at `5bc4f7f`,
  (b) seventh merge `42abc5a`, (c) published and deployed 4/4, **(d) F1 GREEN (iteration 6)** and
  **F3 RUN TO COMPLETION (iteration 9) — 5 GREEN, 1 RED**. The same is true of Phase M's gate steps
  (a) `21a73ea` / (b) `77e0014` / (c) deployed / (d). **What Phase M and P set out to fix is proven
  fixed:** candidate 53's minute-14.6 death did not recur, candidate 56 did not fire in 17 minutes,
  D-c capped 67 of 443 spans and RTF p95 was 0.546. **What now stands in front of Phase N is one new
  defect, candidate 60**, and the decision of whether the F3 clause it fails is worth an eighth
  authorization before identity work. See the **F3 soak** row in the gates index and candidate 60.
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
- **THE FIVE-ITERATION CHAIN ON CANDIDATES 55 / 60 / 65 IS SETTLED, AND ITS INTERMEDIATE STEPS ARE
  RETIRED.** Iterations 3–7 of this run each measured, corrected or falsified its predecessor; the
  bullets that recorded them in full are in progress.txt under the fifth-compaction banner, and the
  **surviving conclusions live in exactly two places** — the numbered entries for candidates 55, 60
  and 65, and Phase N decisions 19 and 20. *Do not re-argue any of this from the record; the record
  was wrong twice and is now corrected.* What each step settled:
  - **it. 3** — the deployed album disagrees with the fixture, and 55's fragmentation is what makes
    the sweep inert. **Premise and mechanism both falsified in it. 4.**
  - **it. 4** (`album-bank-shape-probe.py`, real encoder geometry) — "every fixture speaker earns an
    admitted bank" is false (**31 of 42**), and an all-stand-in reference set **still sweeps** (140
    corrections, 11.4 % `kept_ambiguous`, 82.89 → 88.54 %). `_album_view`'s admission of stand-ins is
    **exonerated**, and ADR-0002's +5.82 pp is **not** shown to be a fixture artefact.
  - **it. 5** (`sweep-multiplicity-probe.py`, the decisive experiment) — the cause is a **product**:
    many references per voice **×** references too short to bank. **`_album_view`'s MERGE is the
    defence against multiplicity, and a stand-in disables it** (decision 7 needs an admitted bank on
    both sides). Controls on both sides: stand-ins without multiplicity **3.8 %** ambiguous,
    multiplicity without stand-ins **1.1 %**, the two together at F2's own **8.40** refs/voice
    **84.1 %**.
  - **it. 6** (`birth-floor-probe.py`) — the site is `live_identity.py:129`, which births a canonical
    speaker for every unmatched local speaker with **no duration condition of any kind**, while the
    evidence floor sits a layer down and is applied **per segment**. **14 of F2's 16 and 13 of F3's
    16 canonical speakers hold no reference whatever** (born from `'...'`, `Hi.`, `Mm-hmm.`). A birth
    floor at the evidence floor would leave **2 / 3** speakers — 1.0–1.5 refs per real voice, the
    fixture's own healthy regime. **The request is written and on the table:**
    `scripts/ralph-afk/authorization-request-55-60-65.md`.
  - **it. 7** (three `live-pipeline-probe.py` runs against the deployed service) — **the session-end
    sweep RUNS and PUBLISHES**: 19 of 31 spans came back with a label-changing `revised_transcript`.
    Every sentence of the form *"the session-end sweep never runs in a real meeting"* or *"ADR-0002's
    second acceptance half is unreachable in production"* is **WITHDRAWN**. Each was inferred from
    `identity_finalized` sightings, and that event is written to an **in-memory** list inside the same
    `stop` that revokes view authority and releases the session — so **no client can ever read it**
    and "0 sightings" was never evidence. Consequences: candidate 60 is a **client** defect and
    nothing more, candidate 65 is now its **cadence** half alone, and **the loop needs no
    authorization to measure the session-end sweep** because the probe already can. *The honest
    bound:* the probe's meeting held **2 canonical speakers for 2 real voices**, so it does not touch
    iteration 5's 84.1 % at 8.40 refs/voice — **candidate 55's argument and the 55-before-60 ordering
    survive whole.** See the session-end-sweep block below.
- **THE ROUTING RULE - what needs the operator and what does not.** **Needs an authorization:**
  candidates 55, 58, 60, 64 and 65; F1's two REDs; the F2 system-audio-denied variant (producing it
  means taking a TCC grant away from `com.alphasight.moss.capture`, i.e. spending the one input this
  loop is forbidden to ask for again); F1/F2's "two speakers" half (blocked by candidate 51's
  **measured** hardware limit - m4mbp's built-in microphone cannot hear a second voice across the
  room, five runs now say so); and F4b, which closes only when everything else has evidence.
  **Does NOT need one:** Phase N **step 4** (batch Tier-B unification - ADR-0002's own step 4 of 4,
  covered by prd.md's *"Phase N remains authorized. Take it in ADR-0002's shape"*), and this loop's
  own tooling and working memory. *Re-derive that list from prd.md's tail every iteration rather than
  from this line:* the operator has committed to this branch mid-iteration three times, once with an
  authorization inside it.
- **STEP 2's RETENTION IS CODE-COMPLETE AND OFF ON THE HOST.** `ops/moss-live.env` is host-local and
  untracked and the tracked template ships all three `MOSS_LIVE_RETENTION_*` keys **commented out**,
  so the deployed `7a4f59c` retains **no audio** and the PRD's *"no raw audio is persisted"* clause
  holds unchanged at every observable boundary. ADR-0003's two-form hygiene test is what to run at
  the moment an operator edits that host file.
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
- **Candidate 52 — the fourth compaction** `[done — run `20260729-094359` iteration 2]`. **This one
  was forced, not chosen.** The file had reached **263 219 bytes** and the `Read` tool refuses
  anything over **256 KB**, so iteration 2 opened with `File content (257KB) exceeds maximum allowed
  size` — context.md was unreadable in one call and had to be paged blind by offset. **263 219 →
  202 850 bytes (2709 → 2039 lines), −22.9 %**, 8 ranges archived verbatim and verified absent, fence
  still `bash -n` clean at 521 lines. *The durable correction:* the trigger to watch is the **256 KB
  hard cap**, not the `Read` count — at the measured drift of ~5–10 KB/iteration a pass is due about
  every ten iterations, and waiting for "it costs five `Read`s" waited too long. The pass also caught
  a staleness bug the size problem was hiding: **seven Shipped-contracts rows still read "in source
  only, not deployed"** for code merged and deployed in iteration 29.
- **Candidate 52 — the fifth compaction** `[done — run `20260729-094359` iteration 8]`. Taken on
  iteration 7's own recommendation (*"URGENT AND MECHANICAL, ahead of both"*): at **249 137 bytes**
  the next block of any size would have re-crossed the 256 KB cap. **249 137 → 210 671 bytes
  (2522 → 2162 lines), −15.4 %**; 14 ranges archived verbatim under `ARCHIVE OF context.md SUPERSEDED
  BLOCKS - RUN 20260729-094359 ITERATION 8`, each verified byte-for-byte present in progress.txt
  **and** absent here by script, fence still `bash -n` clean at **618 lines**, 0 dangling
  cross-references. ***The half that was not about size, and it is the reason this pass was worth an
  iteration on its own:*** five of the retired blocks and nine surviving sentences still asserted
  *"the session-end sweep never runs in a real meeting"* / *"ADR-0002's second acceptance half is
  unreachable in production"* — **which iteration 7 had already falsified by direct measurement**.
  A compaction is where a claim no iteration re-reads gets re-read; that is now two passes in a row
  (the fourth caught seven stale "not deployed" rows). *The measured lesson for the sixth pass:* this
  was the **smallest** of the five because the duplication is gone — the fence is now 25 % of the
  file and the next pass has to take it deliberately. See the compaction log at the top.
Candidates 55 and 56 are tracked product source under the post-merge freeze. **Candidate 54 is ANSWERED**
(iteration 11) and **candidate 51 is DONE** (iteration 12), neither spending an authorization: the
409 is `LiveV2SessionTerminalError` — `"v2 system lane is failed."` — armed by the client's *own*
heartbeat, **not** the `v2_out_of_order_frame` that was on record as likeliest; and the two lanes
now carry different content, which took no product change at all. See those two blocks and Phase M.

**E3 was the blocker for four runs; the clicks were necessary and not sufficient.** Both grants are
recorded and survive a bundle replacement. **Never ask the operator for those clicks again.**

**Test totals on the branch, measured whole at Phase N's gate (a) and re-measured on the merged tree
at the N8 merge - not carried forward.** Swift **158 passed / 0 failed**, 0 warnings on a fresh
scratch. Python **801 passed / 2 skipped / 368 subtests** in ~76 s; the two skips are the
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
  **TRUE AGAIN SINCE run `20260729-025318` iteration 29**, measured rather than assumed:
  `git diff --name-only 7a4f59c HEAD -- ':!scripts/ralph-afk'` is **empty**, so every offline probe
  speaks for the deployed service once more. It was false from iteration 15 (when Phase N steps 1-3
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

**F1 was GREEN on `42abc5a` as well (run `20260729-025318` iteration 6, rc=0)** - user-visible p95
**3909.3 ms** <= 4000 and qualified (`sufficientSamples` true, n=44), decoder p95 RTF **0.911**,
329 published == 329 accepted, 370/370 view polls 200, 165/165 heartbeats 200, no lane fault,
0 tracebacks. Superseded as evidence by the F1-on-Phase-N run (gates index) and **retired verbatim to
progress.txt** with the fourth compaction; it is kept in one line because it is the **only** run in
this loop's history where the user-visible clause passed at the **4000 ms** gate, which is the
baseline candidate 64 and the plan's ordered latency remedies are argued against. Not certified by
it: the "two speakers" half - both voices were on the system lane.

**THE THREE CERTIFICATION RUNS HAVE ONE HOME NOW, AND IT IS THE GATES INDEX.** F1 and F2 on the
deployed `7a4f59c` and F3 on `42abc5a`: their long narrative blocks are retired verbatim to
progress.txt with the fifth compaction, and the rows **F1 on Phase N**, **F2 on Phase N** and **F3
soak, run `20260729-025318` it. 9** under "Gates, merges and redeploys" carry every clause verdict,
every measured number and the identity half of each. *What the retirement deliberately removes:* each
block's `THE FINDING` paragraph asserted that no sweep publishes a correction in production, and
**iteration 7 of this run falsified that by direct measurement** — see the session-end-sweep block
below. The half of those paragraphs that survives is the **cadence** half: `identity_revision_version`
stayed **0** on all 52 spans of F1 and all 171 of F2, and F2 crossed **five** 60 s deadlines, so the
cadence sweep published nothing and left no record either way (candidate 65). *Not certified by any of
the three, unchanged:* the "two speakers" half — every run put both voices on the **system** lane,
candidate 51's measured microphone limit, five measurements — and F2's separate mic-granted /
system-audio-denied variant, deliberately not attempted because producing it would spend a TCC grant.

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
**THE SESSION-END SWEEP RUNS AND PUBLISHES ON THE DEPLOYED SERVICE — run `20260729-094359`
iteration 7. READ THIS BEFORE ANY 55/60/65 AUTHORIZATION, AND BEFORE TRUSTING ANY "0 sightings of
`identity_finalized`" LINE ANYWHERE IN THIS FILE.** Three `live-pipeline-probe.py` runs against the
deployed `7a4f59c` from MacStudio over the pinned leaf — no Mac, no TCC, no operator, no product
change, `git diff --name-only 7a4f59c HEAD -- ':!scripts/ralph-afk'` empty before and after.

| question | measured |
| --- | --- |
| is `POST …/stop` reachable by a client? | **yes, by both authorities.** `CAPTURE_ACTIONS` and `VIEW_ACTIONS` both contain `stop`; the `/live` portal's Stop button calls it; the F0 probe has called it since Phase F. Server journal: **1** hit on `sessions/…/stop` for the probe's session (F1/F2/F3: 0 — because *their drivers* never called it) |
| does a clean stop through the route revoke view authority? | **yes, immediately** — `view_authority_after_stop` `snapshot_status` **401**, `revoked: true`, on all three runs. The PRD soak clause's *immediately* is satisfied **by the route**; candidate 60 is exactly and only that the **Mac client** does not call it |
| can any client read `identity_finalized`? | **no.** Post-stop events read: **401** with the view token, **403 `session is not owned by this device.`** with the capture token. `_record_event` writes to an in-memory list and **never to the journal**, so every "0 in the journal" reading in this file is uninformative, not negative |
| did the session-end sweep run? | **yes** — `stop` **200** on all three runs, and `_finalize_identity_locked` runs *before* `session.stop`, so a raise would have failed the stop |
| did it publish? | **yes — 19 of 31 committed items carry a `revised_transcript`**, **19/19 change the label** (18 × `S00 → S01`, 1 × `S00 → S01,S00`), **0** byte-identical rewrites, and the **words are byte-identical in all 19** (decision 10 holding on the wire). Live histogram `{S00:25, S01:5, S02:1}` → final `{S01:24, S00:7, S02:1}` |

*Runs:* `/tmp/i7-probe.json` (baseline, event kinds not yet projected), `/tmp/i7b-probe.json` (post-stop
drain added → the 403), `/tmp/i7c-probe.json` (revision projection added → the 19). Each cost one
pairing code, one device and one session; **all three devices were revoked**, 200 with body, leaving
17 devices / **1 unrevoked**. *Hosts left clean, measured after:* server `HEAD 7a4f59c` worktree clean,
live MainPID **365632** / batch **301112** and **322117**, all `NRestarts=0`, `live-runs` **0**, no
`/tmp/mtd-live-*`, **0** journal tracebacks, batch `/` and `/api/jobs` **200**. m4mbp untouched.

***The honest bound.*** The probe's meeting held **2 canonical speakers for 2 real voices** — the
healthy ~1.0 refs/voice regime — against F2's **16 for 2**. This therefore does **not** refute
iteration 5's `sweep-multiplicity-probe.py` result that at 8.40 refs/voice the production sweep
answers `kept_ambiguous` on 84.1 % of units. **Candidate 55's fragmentation argument survives whole.**
What is falsified is only the claim built on top of it — that the session-end half *never runs* and
that ADR-0002's second acceptance half is *unreachable in production*. Both are false. *The next
measurement this makes possible, and it is the one that matters:* re-run this probe against a
meeting with F2's fragmentation and read the same `revised_transcript` field, which turns iteration
5's offline model into a deployed number.

*What changed in the instrument (loop tooling only, `scripts/ralph-afk/live-pipeline-probe.py`):*
`event_kinds` (a histogram, not a bare count — six runs reported `events_seen` as an integer, and a
count cannot answer "did the sweep run"); `_drain_events_after_stop`, which reads the post-stop
events with **capture** authority and reports the status rather than raising; and
`identity_revision_version` / `revised_transcript` / `revised_speakers` on each committed item —
without which an unswept and a swept span report identically, which is why every prior run of this
probe was silent on the thing it was standing right next to.

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
  that the TCC grants were never at risk. *One measurement trap:* `212080356` is the **bundle
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
| **F3 soak, run `20260729-025318` it. 9 - still the current F3 evidence** | **rc=3 - 5 GREEN, 1 RED.** 17/17 full minutes, 443 spans, 355/355 portal polls 200, view authority 200 at age **1024.1 s**, user-visible p95 **4557.2 ms** <= 6000 qualified, decoder p95 RTF **0.546**, one lane degraded at t+474 s and **kept capturing**, clean drain `retained=0`, hosts clean. RED: the clean stop did not revoke view authority - **candidate 60**. **Never re-run against Phase N**, so it speaks for `42abc5a`, not for the deployed `7a4f59c`. |
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

# --- C1 view-authority nodes (10 = 9 new + the pre-existing action/session scope node:
#     60 virtual minutes, exact cap, five lifecycle statuses, unwired fail-closed, operator
#     revoke, restart, clean stop, failed stop, loopback-only route) ----------------------------
python3 -m pytest tests/test_live_auth.py tests/test_live_api.py -q \
  -k 'view_authority or view_revocation or revokes_the_view'

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
# Expect: album 93.44/92.18 · overwrite 72.0/55.7 · swept 99.26/98.48 · swept cap64 99.26/98.48,
# merges 0 and residual 0 everywhere. `accuracy` is the transcript a reader ENDS with and
# `live_accuracy` the one they read DURING the meeting; without a sweep the two are equal.

# --- N-sweep: the retrospective sweep engine, 40 nodes, ~0.1 s (iteration 22). Pure; no host,
#     no server, no fixture. The matcher extraction is proved behaviour-preserving by the
#     accuracy numbers above staying at 93.4 / 72.0, not by these nodes. -------------------------
python3 -m pytest tests/test_live_identity_sweep.py -q
# Its ten red-before reverts, re-runnable against a COPY of the module (restore after). Each
# names DIFFERENT nodes; the third is over-broad and only evidences the union node:
#   1. `_union(parent, left, right)` -> `pass`                                   -> 6 red
#   2. leader `min(members, key=(-duration, id))` -> `min(members)`              -> 2 red
#   3. `union.extend(banks[speaker])` -> `pass`                                  -> 13 red
#   4. `ambiguous = True` -> count + `continue`                                  -> 1 red
#   5. `if unit.local_speaker in unscored:` -> `if False:`                       -> 1 red
#   6. the ledger cap check -> `if False:`                                       -> 1 red
#   7. `entry.canonical_speaker = correction.canonical_speaker` -> `pass`        -> 2 red
#   8. `duration_weighted_centroid(bank)` -> `... or album.reference(speaker)`   -> 1 red
#   9. `_finite_float32`'s `if not values:` -> `if False:`                       -> 1 red
#  10. `reference = album.reference(speaker)` -> `reference = None`              -> 1 red

# --- N-revision: a sweep's correction reaching the reader, 9 nodes (iteration 25). The seam node
#     is the one that matters -- real coordinator + session + preparer + provider + album + sweeper,
#     five 2 s spans, only the ONNX forward pass and the GPU decode scripted. ~4 s for all four. ---
python3 -m pytest tests/test_live_session.py tests/test_live_pipeline_seams.py \
  tests/test_live_portal.py tests/test_live_identity_sweep.py -q          # expect 145 passed
# Its ten red-before reverts, against COPIES of the four sources (restore after). Nine name
# DIFFERENT nodes; 3 and 4 both name the seam node:
#   1. portal `item.revised_transcript || item.transcript` -> `item.transcript`      -> 1 red
#   2. `_revised_span`'s `if not track:` -> `if True:`                               -> 7 red
#   3. the coordinator's `getattr(..., "take_identity_revision", None)` -> `None`    -> 1 red
#   4. drop `local_speakers=` on `submit_unlabeled_canonical`                        -> 1 red
#   5. the re-render guard -> `if False:`                                            -> 1 red
#   6. the label-collision guard -> `if False:`                                      -> 1 red
#   7. `if canonical_speaker in canonical_speakers:` -> `if True:`                   -> 1 red
#   8. `take_revision` returns without clearing `_unconsumed`                        -> 1 red
#   9. `published = commit.revised_transcript ... else transcript` -> `transcript`   -> 1 red
#  10. drop `local_speakers=` on the PREPARED path's `CanonicalResult`               -> 1 red
# The portal node needs `node` on PATH (it drives the real page's JS); it is skipped without it.

# --- N-tape: the session tape recorder, 37 nodes, ~3.6 s (iterations 19 + 20). ADR-0002 gate C's
#     assembly cases + ADR-0003 D2-D6, then the recorder. Offline, no host, no server, tmp_path. ---
python3 -m pytest tests/test_live_tape.py -q
# Its three red-before reverts, re-runnable by hand against a COPY of the module (restore after):
#   1. `offset_samples` -> `return self.sample_count`          (arrival-order placement)  -> 8 red
#   2. cap check + TTL comparison -> `if False:`                                          -> 3 red
#   3. D4's four admission rules -> `if False:`                                           -> 4 red
# --- N-tape-wiring: the tape teed onto the REAL routes, 4 nodes inside test_live_api.py (33) ------
python3 -m pytest tests/test_live_api.py tests/test_live_tape.py tests/test_live_helper_failure.py -q
# Its four reverts (copy the three sources to /tmp first; each names a DIFFERENT node):
#   1. drop `tapes.append_lane_frame` + `_tape_mixed` in the frames route            -> 1 red
#   2. the recorder's six `except Exception` guards -> a class never raised          -> 2 red
#   3. `LiveHelperFailureCoordinator._release_registries`'s tape release -> `if False:` -> 1 red
#   4. drop `tapes.release` on the stop path                                         -> 2 red
# A stop in these nodes needs `{"deadline": 5.0}`: with a queued span, deadline 0.0 answers 409
# `stop deadline expired with unresolved work` and reads exactly like a tape defect.

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

# --- candidate 65's two probes (iteration 3 of run 20260729-094359). Offline, no host, no session,
#     no product change; both import production's own parsers and matcher rather than modelling
#     them. Re-run either against any future evidence directory or after any identity change. ------
# What reached the album and the sweep on a FINISHED run. Takes span bodies from snap-full-*.json
# when the driver pruned snapshot.tsv (cert/soak) and from snapshot.tsv when it did not (canary),
# and always names which answered. rc=6 is a named refusal for an unreadable layout, never a
# traceback. Coverage is reported because the bodies are a prefix by design (candidate 61).
python3 scripts/ralph-afk/identity-evidence-probe.py /tmp/i1-f2-evidence/ralph-cert \
    /tmp/i30-f1-evidence/ralph-canary /tmp/i9-f3-evidence/ralph-soak    # rc=0
# What the PRODUCTION sweep does with a ledger and album in that shape, with its own dispositions
# as the answer. Asserts on the correction's *reason* (re-matched vs merge-driven), not on a count,
# and carries its own falsification control plus a sensitivity sweep over the one quantity it
# invents (the per-unit noise spread; F2's vectors were never retained).
python3 scripts/ralph-afk/sweep-fixpoint-probe.py                        # rc=0
# --- iteration 4's AUDIT of those two, on the real fixture instead of invented vectors. Wraps the
#     production album (subclass) and the production sweep (call-through) inside the tracked
#     accuracy harness, and moves ONLY the admission gate, so the bank/stand-in split is the one
#     thing that differs between its three configurations. ~9 s, no host, no product change.
python3 scripts/ralph-afk/album-bank-shape-probe.py                      # rc=0
# Expect: banked 42/42 refs, 1.1 % kept_ambiguous, 115 corrections, 93.50 -> 99.26
#         deployed 31/42, 1.1 %, 116 corrections, 93.44 -> 99.26   (the deployed shape)
#         standin  0/53,  11.4 %, 140 corrections, 82.89 -> 88.54  (the falsification control)
# The last row is the finding: an all-stand-in reference set STILL sweeps, so stand-ins are not
# what makes the deployed sweep inert. rc=2 is a named refusal if the harness or fixture will not
# load. See Phase N decision 19.
# --- iteration 5's DECISIVE experiment: does ambiguity track reference MULTIPLICITY? Same harness,
#     same wrapping discipline. ~47 s, no host, no product change. Two experiments, because the
#     obvious knob is confounded and the probe says so rather than picking the flattering one. -----
python3 scripts/ralph-afk/sweep-multiplicity-probe.py                    # rc=0
# A - the birth ladder: raise the LIVE min_match_score to force births, PIN the sweep's matcher at
#     the deployed 0.35/0.1 (sweep() takes its own config). Confounded on purpose-and-declared:
#     starving the live matcher also wrecks what the album learns. Superseded by B; kept because it
#     is production end to end. Expect at >= 6.0 refs/voice: 23.3 % ambiguous, 85 corrections.
# B - shard the album: the live path stays the deployed 0.35/0.1 in EVERY row, and only the
#     reference set moves. Each speaker's own exemplars are redistributed over m labels through the
#     album's PUBLIC observe(), so every reference is a real vector of a real voice.
# Expect (totals over the 8 meetings; the three controls are the first, fifth and second rows):
#   banked      m=1  1.40 refs/voice   1.1 % ambiguous   116 corr    0 merges  ->  99.26 %
#   banked      m=2  1.40              1.1 %            1143 corr   51 merges  ->  99.26 %
#   banked      m=8  3.10             20.3 %            1146 corr  278 merges  ->  91.43 %
#   provisional m=1  1.40              3.8 %             123 corr    0 merges  ->  98.93 %
#   provisional m=2  2.40             74.4 %             810 corr    0 merges  ->  69.85 %
#   provisional m=8  8.40             84.1 %             850 corr    0 merges  ->  46.82 %
# banked m=1 must reproduce the tracked deployed numbers exactly or the harness moved under it.
# THE FINDING IS THE CONTRAST, NOT ANY ROW: banked m=2 shards 42 references into 84 and `_album_view`
# MERGES THEM BACK to 42 (51 merges, ambiguity and accuracy unmoved); the identical split held
# sub-admission cannot merge (decision 7 needs a bank on both sides), and the sweep goes 74.4 %
# ambiguous. Neither factor alone does it. See Phase N decision 19.
# --- iteration 6: WHERE an unbankable reference comes from. Reads the two real meetings' own
#     published transcripts through production's span grammar and interval filter; no host, no
#     product change, no fixture, <2 s. Classifies every canonical speaker by its BIRTH span. -------
python3 scripts/ralph-afk/birth-floor-probe.py /tmp/i1-f2-evidence/ralph-cert \
    /tmp/i9-f3-evidence/ralph-soak --json /tmp/i6-birth-floor.json      # rc=0
# Expect F2: 16 canonical for 2 voices (8.0 refs/voice); born no_reference 14 / provisional 1 /
#            banked 1; a birth floor at 0.5 s leaves 2 (1.0 refs/voice), at 1.0 s leaves 1.
#        F3: 16; no_reference 13 / provisional 1 / banked 2; floors leave 3 (1.5) and 2 (1.0).
# rc=6 is a named refusal for an unreadable layout. `--real-voices` defaults to 2 (F1/F2/F3's
# harness limit, candidate 51); pass the truth for any future run. The floor columns are a
# COUNTERFACTUAL - suppressing a birth changes later matching - so they bound, never simulate.
# See Phase N decision 20 and scripts/ralph-afk/authorization-request-55-60-65.md.

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
    `[RE-RUN against `42abc5a` — 5 GREEN, 1 RED — run 20260729-025318 iteration 9. See the **F3
    soak** row in the gates index; the RED is candidate 60, and the two soak halves this entry called "unproven" are now
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
    **Iteration 22 changed what that mechanism has to cover, though not the authorization.**
    The sweep's merge (Phase N decision 7) — two album centroids at ≥ 0.70 are one voice born twice — is the first thing in
    this repo that can *reduce* the canonical count, so the fragmentation can be **healed
    retrospectively** while the births stay untouched. What a merge cannot buy back is the capacity
    itself: the 16-slot bound is still reached mid-meeting, so a voice arriving after saturation is
    still never labelled live. Measure the merge's share of the 4.5 pp before deciding what is left.
    **ITERATION 23 MEASURED IT, AND RE-PRICED THE CANDIDATE.** The merge's share is **zero** — it
    fires on none of the eight meetings, because a saturated capacity mints speakers from
    sub-admission fragments that never earn the admitted bank a merge requires on both sides. The
    **sweep's** share is **all of it**: capped-and-swept 99.26 % equals uncapped-and-swept 99.26 %,
    so the 4.5 pp is gone from the *final* transcript entirely. What survives is the **live** cost,
    now measured at **5.30 pp** (93.44 vs 98.74). So 55 is a **latency of labelling**, not a
    permanent loss — an authorization for it is now a decision about what a reader sees *during* a
    meeting, and should be weighed against wiring the sweep, which costs nothing more to authorize.
    See Phase N decisions 7 and 18.
    **MEASURED ON THE ALBUM AT 300 s SCALE (run `20260729-094359` iteration 1, F2 on `7a4f59c`):**
    saturation moved from `42abc5a`'s **t+93.9 s** to **t+127.1 s** — 33 s later, and still inside
    the first third of a 300 s meeting. 15 spans then abstained `speaker_capacity_exceeded` under
    `S00`. **The "latency of labelling" reading is conditional on the meeting not being fragmented**:
    it assumes the sweep repairs the fragmentation retrospectively, and iteration 5 measured that at
    F2's own 8.40 refs/voice the sweep abstains on 84.1 % of units. *Corrected in iteration 7:* the
    session-end sweep **does** run and publish on the deployed service (19 of 31 spans on a healthy
    2-speaker meeting), so what makes 55's cost permanent is 55's own fragmentation, not an inert
    sweep.
    **ITERATION 3's PROMOTION AND ITERATION 4's RE-ARGUMENT ARE RETIRED to progress.txt** with the
    fifth compaction. Both are superseded by iteration 5's measured mechanism below; what survives
    from them is the promotion itself, and it is the largest change to 55's price in the loop's
    history: **55 is not merely fragmentation the sweep can heal — 55 is why the sweep cannot heal
    anything**, so an authorization for 60 or 65 that leaves 55 open buys an `identity_finalized`
    event and few corrections. Iteration 23's "the sweep's share is all of it, 55 is a latency of
    labelling" is true on the fixture and false on a real meeting.
    **ITERATION 5 TURNED THAT CORRELATION INTO A MEASURED MECHANISM, and it is the sharpest
    statement of 55's cost the loop has: 55's two symptoms are ONE defect multiplied.** With the
    deployed live path untouched and only the sweep's reference set sharded
    (`sweep-multiplicity-probe.py`), splitting a voice over 2 labels costs **nothing** while the
    shards stay banked (the sweep merges them back; 1.1 % ambiguous, 99.26 % final) and costs
    **74.4 % ambiguity** the moment they are stand-ins. At F2's own **8.40** references per real
    voice the sweep answers `kept_ambiguous` on **84.1 %** of units. So the thing to put to the
    operator is: candidate 55 mints *many* ids per voice **and** mints them from fragments too
    short to bank, and the sweep's own defence against the first is disabled by the second. See
    Phase N decision 19.
    **ITERATION 6 LOCATED THE SITE AND MEASURED THE REMEDY, so 55 now has a cause, a mechanism and
    a predicted fix, and the loop should stop diagnosing it.** `birth-floor-probe.py`:
    `live_identity.py:129` births a canonical speaker for **every** unmatched local speaker with
    no duration condition at all, while the evidence floor sits a layer down in
    `_speaker_intervals_by_label` and is applied **per segment**. Result on the two real meetings:
    **14 of F2's 16 and 13 of F3's 16 canonical speakers hold no reference whatever** (born from
    `'...'`, `Hi.`, `Mm-hmm.`), 1 and 2 were banked at birth. A birth floor on *embedded* seconds
    would leave 2 / 3 speakers (1.0 / 1.5 refs per voice, the fixture's regime), and at the
    album's 1.0 s admission every survivor is banked by construction. **This is the request that
    is now on the table**: `scripts/ralph-afk/authorization-request-55-60-65.md`, with the three
    decisions it must make explicitly, the two measured-wrong alternatives (raising `max_speakers`,
    lowering `min_segment_samples`) and the honest limits. See Phase N decision 20.
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
    returns; **no MAC-CLIENT code path** calls `POST /api/live/sessions/{id}/stop` (as filed this read
    "no client code path", which iteration 7 falsified - the portal and the F0 probe both call it),
    a route that exists at
    `live_transport.py:325` and is covered by `tests/test_live_api.py:502`. Measured: view authority
    answered 200 for **29.4 s** after a clean stop, until the 30 s helper lease expired. Bounded and
    self-healing, but it is the PRD clause's word *immediately*, and it was already visible in F1's
    "29 s after the run's own stop" line without being named. Tracked product source under `macos/`;
    **needs its own authorization**. The full block is retired to progress.txt with the fourth compaction; the one-line form is in the certification section.
    **FOUR RE-PRICINGS BETWEEN ITERATION 30 AND ITERATION 5 OF THIS RUN ARE RETIRED to
    progress.txt** with the fifth compaction — upwards twice (to *"ADR-0002's second acceptance half
    is unreachable in production"*), then downwards twice on `sweep-fixpoint-probe.py` and
    `sweep-multiplicity-probe.py`. **Iteration 7 replaced all four with a direct measurement; read
    that, not them.** The three facts from those runs that survive unaltered: F1, F2 and F3's server
    journals each hold **0** hits on `…/{sid}/stop` (because *their drivers* never called it), the
    terminal line is `helper_lease_expired` about **29 s** after a clean stop in both F2 and F3, and
    at F2's own **8.40** references per real voice the production sweep answers `kept_ambiguous` on
    **84.1 %** of units — so wiring `stop` while 55 is open buys few corrections, and iteration 5's
    model says it also buys unmeasured risk. **Sequence 60 with or behind candidate 55.**
    **ITERATION 7 RE-SCOPED 60 BACK TO WHAT IT IS, AND DELETED ITS SECOND CLAUSE.** Measured on the
    deployed service: the route is reachable by **both** authorities, the `/live` portal's Stop
    button calls it, this loop's own F0 probe has called it since Phase F, and a stop through it
    **revokes view authority immediately (401)** *and* **ran the session-end sweep, which published
    19 corrections on 31 spans**. Candidate 60 is therefore a **client** defect and nothing more:
    `CaptureController.stop` does not call a route that works. Every sentence in this file of the
    form *"the session-end sweep never runs in a real meeting"* or *"ADR-0002's second acceptance
    half is unreachable in production"* is **withdrawn** — each was inferred from `identity_finalized`
    sightings, and that event is unreadable by every client (see the iteration-7 block). Two
    consequences: 60 buys neither convergence nor the `identity_finalized` event (it is worth having
    on its own merits — a Mac stop should behave like the portal's), and **the loop needs no
    authorization to measure the session-end sweep**, because the probe already can.
65. **Neither half of Phase N step 3 produces a correction on a real meeting, and an empty cadence
    sweep leaves no record to tell "found nothing" from "never ran".** `[open, new — run
    `20260729-094359` iteration 1; found by F2 on the deployed `7a4f59c`]`. Measured over a **319 s**
    meeting that minted **16 canonical speakers for 2 real voices**: `identity_revision_version`
    **0 on all 171 spans**, **0** `live identity sweep` lines in the server journal, and
    `identity_finalized` **0**. `LiveIdentitySweeper.maybe_sweep` is called per scored span
    (`live_provider_bundle.py:570`) with `meeting_seconds = span.start_sample / 16000` at
    `SWEEP_INTERVAL_SECONDS` **60**, so **five** deadlines were crossed — the cadence half ran and
    published nothing, while candidate 60 means the session-end half never ran at all. Iteration 23
    measured the sweep repairing exactly this fragmentation offline (**+5.82 pp**, 93.44 → 99.26 %),
    so the two facts have to be reconciled by measurement, not by argument: *either* the deployed
    ledger/album disagrees with the fixture in a way the harness cannot see, *or* the correction was
    proposed and something upstream of `take_identity_revision` dropped it.
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
    ***THE CAUSE HALF WAS ANSWERED IN ITERATION 3 AND RE-ANSWERED IN ITERATION 4; both are retired
    to progress.txt*** with the fifth compaction. Iteration 3 measured — and this part is a direct
    measurement of the real runs, so it stands — that only **2 of 16** (F2) and **2 of 12** (F1)
    canonical speakers ever hold an admitted album exemplar, and reproduced a 100 % `kept_ambiguous`
    sweep on that shape with invented vectors. Iteration 4 falsified its *explanation* on real
    encoder geometry (an all-stand-in fixture still sweeps). Both are superseded by iteration 5's
    mechanism below, which keeps iteration 3's F1/F2 measurements and replaces its cause.
    ***THE CAUSE HALF IS SETTLED IN ITERATION 5, on real geometry and with a control on both
    sides — `sweep-multiplicity-probe.py`, Phase N decision 19.*** The deployed cadence sweep
    publishes nothing because F2's reference set is **many stand-ins per voice**, and a stand-in is
    **unmergeable**, so the sweep's own defence against multiplicity never fires: at F2's 8.40
    references per real voice the production sweep is **84.1 % `kept_ambiguous`**, while the
    identical split with bankable shards merges back to the deployed shape and stays at 1.1 %.
    So 65's cause is candidate 55's fragmentation after all — but through the merge, not through
    confusability, and the two controls (stand-ins without multiplicity 3.8 %, multiplicity without
    stand-ins 1.1 %) are what make it a mechanism rather than a third correlation. **65's
    diagnosability half is unchanged and still the part that is cheap to authorize**, and it is
    now *more* clearly worth it: "swept and proposed nothing" is exactly what is happening, five
    times per 300 s meeting, and no surface says so.
    ***ITERATION 6 CLOSES THE DIAGNOSTIC CHAIN.*** The unbankable references decision 19 blames
    come from one unconditioned site (`live_identity.py:129`) and 14 of F2's 16 canonical speakers
    hold **no** reference at all — see Phase N decision 20. 65's diagnosability half is unchanged
    and is item (b) of `scripts/ralph-afk/authorization-request-55-60-65.md`; **no further probe
    of 65's cause is worth an iteration.**
    ***ITERATION 7 SPLITS 65 IN TWO AND WITHDRAWS ONE HALF.*** The **session-end** half never
    rested on a measurement: `identity_finalized` is written by `_record_event` into an in-memory
    list, **never to the journal**, **inside** the same `stop` that revokes view authority and
    releases the session — so no client can read it (measured: **401** with the view token, **403
    `session is not owned by this device.`** with the capture token), and "0 sightings" is the
    *expected* reading whether it ran or not. On the deployed service it **did** run and **did**
    publish: **19 of 31 spans came back with a label-changing `revised_transcript`**. What survives
    is **the CADENCE half**, unchanged and now the whole of 65 — `sweep_now` sets `_unconsumed` and
    logs only when the revision is non-empty, so an empty cadence sweep is still indistinguishable
    from one that never happened. *And iteration 7 adds a third item of the same shape:* even the
    session-end half's **payload** — the counts `identity_finalized` carries — is unreachable by any
    client, so a reader can see *that* labels moved and never *what the sweep decided*. All of it is
    one diagnosability defect and belongs in one authorization; **the cause half of 65 is closed**,
    since the sweep demonstrably publishes when the meeting is not fragmented.
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
    tune until green"*. Reproduce with `tests/live_identity_accuracy.replay_all`; see the Phase N
    step index and decision 1 (the N-gate block itself is retired to progress.txt).
64. **The decoder RTF clause measures per-call overhead on a sub-100-ms span, not throughput.**
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
62. **The reducer asked a certification run the soak's questions.** `[done — iteration 11]`. See
    "THE REDUCER STOPPED ASKING A CERTIFICATION THE SOAK'S QUESTIONS" in progress.txt. Loop tooling; it made
    F2 ungreenable for candidate 60, a defect outside F2's clause list.

### Phase N - live speaker identity - FOLLOW ADR-0002, NOT THE SIXTH AMENDMENT

> **STEPS 1-3 ARE MERGED, PUBLISHED AND DEPLOYED as of iteration 29 (`7a4f59c`, four checkouts, host
> manifest at 0.35/0.1).** Every `[NOT gated, NOT merged, NOT deployed]` tag on the per-step blocks
> below is **historical as of that iteration** — each records the state at the moment that step
> landed, and they are kept unedited because each block's red-before evidence is only meaningful
> against the tree it was written for. **GATE STEP (d) IS NOW COMPLETE** — F1 in iteration 30 of run
> `20260729-025318` (5 GREEN, 2 RED) and F2 in iteration 1 of run `20260729-094359` (rc=0, 6 GREEN).
> What is still open in Phase N: the **two F1 REDs** (candidates 64 and the latency remedies, both
> needing the operator), the fact that **the CADENCE sweep publishes no correction and leaves no
> record either way** (candidate 65; the **session-end** sweep was proven to run and publish in
> iteration 7, so ADR-0002's second acceptance half is reachable — it is candidate 55's
> fragmentation, not reachability, that is unproven at meeting scale), and
> **step 4** (batch Tier-B unification).

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
| **4 - batch unification** | **OPEN** - see N-batch below. Needs no new authorization | - | - |

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
*The honest sequencing caveat, so it is a decision and not a drift:* candidates 60 and 65 mean
**neither half of step 3 publishes a correction on the deployed system**, so unifying batch onto an
engine whose live half is inert would be measured offline only. Weigh that against the fact that
step 4 is the one item here the loop can start without the operator.

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
    carrying its final canonical speaker, so it never models the transient one-span reconcile lag. And
    on the deployed system **neither half of step 3 publishes a correction** (candidates 60 and 65),
    so the convergence half of the acceptance bar is unmet in production however green the harness is.
19. **The sweep is inert on a real meeting, and the cause is a PRODUCT — reference multiplicity ×
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
