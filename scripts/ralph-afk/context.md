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
landed on it (A-E client/server/deploy/install, then five operator-authorized post-merge fix cycles
G, H, J, K, M). **Six keeper merges have been made and all six are spent** — `f9285d6` (C4),
`317df4d` (G5), `b817871` (H4), `6a540fe` (J5b), `fc7097d` (K5b), **`77e0014` (M6, iteration 19)** —
and `merge-keeper.sh`'s `expected_main` guard now refuses a **seventh** (rehearsed non-vacuously:
`main moved from expected pre-merge SHA fc7097d…`, rc=1). **Phase M's product work is merged**, so
`git diff main HEAD -- ':!scripts/ralph-afk'` is **empty again** and the branch carries no
unmerged tracked source. Every tracked product change since `f9285d6` was made under a named
amendment. Per-phase detail is in the closed-phase index below and in full in the progress.txt
archive.

**PRD acceptance scoreboard (rows unchanged since iteration 9 except where noted; Phase M's local
gate is green at `21a73ea`, the sixth merge landed as `77e0014` in iteration 19, and **it is now
deployed to all four checkouts (iteration 20)** — so the two certification rows are RED-and-stale
rather than RED-and-current: F1 and F3 have never run against Phase M.)**

| clause | state |
| --- | --- |
| IDEA-044 compatibility checkpoint | GREEN, frozen at `1ede498` (10/10 and 16/16, 11 commands, 0 Darwin skips) |
| Production client gate | GREEN (B6 `3fb5567`, re-gated G4 `23dc163`, K5a `cd7faf9`) |
| Server meeting-reliability gate | GREEN at `f400d426`, clause→node map recorded |
| One reviewed keeper merge (+ 5 authorized follow-ups) | GREEN, six merges, each reviewed against its amendment's scope |
| One exact SHA everywhere | **GREEN — 4/4 at `77e0014`** (iteration 20): local `main`, `origin/main`, the server checkout and the m4mbp checkout. |
| Live service answering | GREEN — `/live` and `/api/live/descriptor` 200 over the pinned leaf from MacStudio **and from m4mbp** |
| Batch service unharmed | GREEN — `http://192.168.68.38:7860/` and `/api/jobs` 200; batch MainPIDs never restarted |
| Signed app installed | GREEN — and "DR unchanged across a rebuild" proven *across an actual rebuild* in K5c |
| Permissions granted | **GREEN** — both TCC grants `auth_value=2`; `mtd-capture status` reported both lanes `capturing` through a 672-frame meeting (K5d) |
| Rollback rehearsed and recorded | GREEN (F4a) |
| 60 s canary (F1) | **RED (stale)** — see the F1 block; every defect it named is now fixed **and deployed**, and it has not been re-run since. This is gate step (d). |
| 300 s certification (F2) | not run; the harness is ready (candidate 51, iteration 12) and 53/48/49/D-a/D-c have all landed, so the next F1/F3 run is the gate rather than another diagnosis |
| 16-minute soak (F3) | **RED** — see the F3 block |
| Secret hygiene | static half green; run-time half green in F1 and F3 as far as those runs went |
| Final close (F4b) | open |

**What stands between the loop and the bar (updated iteration 16).**
- **Candidate 53 + 48 — a throwing publish stopped the heartbeat, and a throwing start-time
  heartbeat leaked a hot capture.** `[done — iteration 14]`, both, as one shape. Root cause of
  *both* red certification runs. See "The heartbeat is uncoupled from the publish" below.
- **D-a — an overrun is a degradation, not a lane failure.** `[done — iteration 15]`. The chain
  that ended F1 and F3 is now broken at its first link as well as its fourth. See "D-a is landed"
  below.
- **Candidate 50 — a runaway decode is unbounded and sets the latency p95.** `[done —
  iteration 16]`. D-c implemented: the live decode now carries a token cap derived from the span's
  own duration, and a capped span commits its words and says so. See "The decode is bounded"
  below. **Its latency effect is now MEASURED on the deployed engine (iteration 24): a runaway
  costs 8.13 s uncapped and 1.07 s capped, 7.57x, reproducing F1's own runaways within 4 %.** And
  **its "commits its words" half is now MEASURED too (iteration 25)** — truncating F1's own
  runaways at the real cap commits 18 segments and never goes empty, no cut point of 9062 is
  terminal, and F1's two runaways turn out to hold **zero words at any length**. See "D-c's OTHER
  half is settled" below. What F1 still decides is the *rate* of runaways and the end-to-end p95 on
  the Mac. See "D-c's latency effect is MEASURED" below.
- **The coverage gap is CLOSED** `[done — iteration 17]`: two nodes in `tests/test_live_api.py`
  now post a frame on the lane that **failed** and on the lane that **degraded**. See "The failed
  lane is in the suite" below.
- **Phase M gate step (a) is GREEN at `21a73ea`** `[done — iteration 18]`, and the certification
  order is settled by precedent, not re-argued. See "The Phase M gate is green" below.
- **Phase M gate step (b) — the sixth keeper merge — is DONE** `[iteration 19]`. `main` is
  **`77e0014`**, feature tip `4ac5d95`, payload exactly the reviewed 10 files / +983/-51. See "The
  sixth merge is made" below.
- **Phase M gate step (c) — push + redeploy + Mac rebuild — is DONE** `[iteration 20]`. All four
  checkouts are at **`77e0014`**; the server runs D-c and the installed Mac product carries
  53/48/49/D-a, both proven by a discriminating witness rather than by the SHA alone. See "M6c is
  deployed" below. **What remains is (d): F1 and F3, both green.**
- **Gate step (d) was ATTEMPTED in iteration 21 and is BLOCKED on the capture Mac being awake.**
  The app was launched and the device re-paired, then m4mbp left the tailnet mid-setup and stayed
  gone; it was **still gone through iterations 22 and 23** (ssh timeout + 100 % ICMP loss on every
  poll). See "F1's re-run is blocked on a sleeping Mac" below.
  **Iteration 23 took the reachable half instead:** the *server* is up, and one 120 s
  `live-pipeline-probe.py` run against the deployed `77e0014` proved the merged pipeline healthy end
  to end on real audio and measured D-c on the wire — but `capped_count` 0, so the cap's **latency
  effect remains unmeasured** and F1 still decides candidate 50. See "D-c is MEASURED on the deployed
  service" below.
  **Both halves of the run are now instrumented and waiting:** the clause reducer (iteration 21)
  and `scripts/ralph-afk/live-soak.sh` (iteration 22 — F3 with candidate 51's harness, in the repo,
  in a layout the reducer reads). Running the reducer on the real evidence also found that it had
  been passing F1's red directory; see "F3 has a repo driver now" below.
- **Candidate 55 — identity capacity saturates in the first minute** (new, iteration 12). The
  16-speaker bound is reached at t+45.5 s (and at t+51.8 s in F1), so a voice arriving later can
  never be labelled. Degrades quality without ending a session, so no gate sees it — like 50.
All three are tracked product source under the post-merge freeze. **Candidate 54 is ANSWERED**
(iteration 11) and **candidate 51 is DONE** (iteration 12), neither spending an authorization: the
409 is `LiveV2SessionTerminalError` — `"v2 system lane is failed."` — armed by the client's *own*
heartbeat, **not** the `v2_out_of_order_frame` that was on record as likeliest; and the two lanes
now carry different content, which took no product change at all. See those two blocks and Phase M.

**E3 was the blocker for four runs; the clicks were necessary and not sufficient.** Both grants are
recorded and survive a bundle replacement. **Never ask the operator for those clicks again.**

**Test totals on the branch.** Swift **158 passed**
(67 → 81 → 92 → 95 → 98 → 106 → 116 → 121 → 131 → 132 → 134 → 139 → 142 → 146 → 150 → 151 → 154
→ 158); Python **604 passed / 2 skipped / 368 subtests** — the two skips are the pre-existing
`tests/test_large_upload.py:155,175` Python-3.10 compatibility contract, **never** Darwin skips.
Per-file: `test_live_pipeline_seams.py` **56**, `test_live_identity.py` **8**,
`test_macos_uds_tracer.py` **4 / 0 skips**, `test_macos_packaging_tools.py` **9**,
`test_live_manifest_finalizer.py` **17**, `test_live_deployment_credentials.py` **14**,
`test_live_service_deployment.py` **30**.

## Read before any certification run or client fix

**K5d — the re-read, and the answer (new, run 20260728-181020 iteration 7). READ THIS BEFORE ANY
FURTHER CLIENT WORK.** The lane failure is `macos_buffer_overrun` on **both** lanes, and its cause is
a client-side wedge in `CaptureController.start`. All three surfaces K1–K4 built printed it, in
agreement, on the real hosts:
- `mtd-capture status`: `lanes[{system, failed, macos_buffer_overrun}, {microphone, failed,
  macos_buffer_overrun}]`, `sessionRefusal: sessionDisowned`, `pumpFailure: transportUnavailable`
- the Mac's unified log (K2): `capture lane system failed: state=failed code=macos_buffer_overrun
  dropped=14005 discontinuities=0` and the same for microphone with `dropped=1379`
- the server journal (K3): `live helper terminal: session=f9a592ae… reason=helper_all_lanes_failed
  lane.system=macos_buffer_overrun lane.microphone=macos_buffer_overrun`

*The mechanism, read out of the source and then measured.* `CaptureController.start` unwinds a
non-retryable publish failure at `CaptureController.swift:396-400` (`source.stop` +
`state.rollbackStart()` + rethrow) — but the start-time heartbeat is the **next** statement,
`let status = try emitHealth(...)` at `:403`, **outside** that `do/catch`. A 403 there throws past the
unwind *and* past `scheduler.schedule` at `:404`. What is left is the exact state the comment at
`:394-395` says must never exist: both lanes hot, `running: true`, **no pump**, no heartbeat, and no
`sessionRefusal` (nothing outside the tick and the stop drain calls `recordSessionRefusal`).
Measured: `start` → `{"error":"nonSuccessStatus(403)","ok":false}` rc=70, then `status` →
`running:true`, both lanes `capturing`, `publishedFrameCount` frozen, `outboxRetainedFrames: 0`,
**no** `sessionRefusal`. A fresh `pair` cannot rescue it — the next `start` answers `alreadyRunning`
— so only an explicit `stop` clears it.
*Then the wedge poisons the next meeting.* With no pump draining the source, the lanes overrun:
14005 dropped frames on `system`, 1379 on `microphone`. The failure is **sticky across stop/start
inside one process** (`NativeLaneHealth`'s projection keeps `failure`), so the next `start` comes up
with both lanes already `failed`, its **first** heartbeat reports all lanes failed, and the server
correctly ends the meeting. `1 heartbeat 200 then 63 × 403` — byte-for-byte the pattern the fourth
amendment recorded from the attended run.
*The server is not at fault anywhere in this chain*: `helper_all_lanes_failed` on two failed lanes is
the designed answer, and the 403s are `release_session` being one-way.
*The attended run reconstructed from m4mbp's unified log*, which still holds it (`log show
--predicate 'processIdentifier == 14978'`, 186476 lines; CFNetwork prints body size + status, which
is enough to identify each route): pid 60550 paired at 11:58:34 and published a 21514-byte frame 200
at 13:51; it exited at 14:00:16. pid 14978 launched 14:00:45, and its **first** request at 14:01:07
was a 439-byte heartbeat → **403** (the stale session in the store) — the wedge. 14:03:17 two large
bodies → 403 (a `stop`, whose drain publishes and swallows the failure). 14:03:52 re-pair 200 + new
session 200. 14:04:03.031 heartbeat **200**; 14:04:03.608 heartbeat **403** — one pump interval later.
*What the fourth amendment got right and wrong.* Right: both lanes were reporting failed, deduced
correctly from `_terminal_reason`. Wrong by omission: nothing suggested the lanes had been **starved
by the client's own start path**, and the phrase "the app never sent a top-level failed" is still
true and still irrelevant. TCC, pinning, schema and duplicate helpers were correctly ruled out.
*And the clean path works.* Before the repro, one `pair` → `start` on a freshly launched process ran
a whole healthy meeting: **1767 requests, 1767 × 200, zero non-200** — 672 frame POSTs (equal to the
client's own `publishedFrameCount`, so accepted == published), 337 heartbeats, 377 snapshot + 377
events from the app-owned probe; both lanes `capturing` throughout; **23 committed spans**; a clean
stop with both lanes `stopped` and the outbox drained to 0; zero lane-failure log lines and zero
terminal records. This is the first end-to-end live meeting from the real Mac.
*First real-Mac latency figures, from `mtd-capture latency` (evidence for candidate 43, not authority
— this is not the plan's Phase F procedure):* committed p95 **9089 ms** (p50 1550, max 11556, n=23),
render bound **1359 ms**, user-visible **10448 ms**, snapshot p95 215 ms, events p95 145 ms,
`fetchFailures 0`, `timelineIntact true`, `mixerOriginResolved true`. The p50/p95 spread says
backlog, not a floor — do not read it as a second measurement of J5d's 4.2-5.1 s.
*Reusable procedure notes.* macOS has **no `timeout(1)`** — use
`perl -e "alarm shift; exec @ARGV" <sec> <cmd>…`. `open -a /Applications/MOSSCapture.app` over SSH
lands in the real GUI session (console user `ga0`, `launchctl print gui/501` resolves) and
`xpcproxy` in the log confirms LaunchServices spawned it, so TCC attributes to the bundle. `pair`
**reuses** the stored `capture-device-id` — no new device row; `live-auth.json` still has exactly one
unrevoked device (`AB600574…`) and its `paired_at` is simply refreshed. The user journal on the
server only retains ~40 min for this unit, so read the *Mac's* log for anything older.

**F1 — the 60 s canary, RED, and the diagnosis is the deliverable (new, run 20260728-181020
iteration 8). READ THIS BEFORE F2 OR ANY LATENCY WORK.** Session
`de088f0510ec492082972365127cebee`, label `ralph-f1-20260728T195125Z`, on the real hosts at
`fc7097d`. Fresh app launch → `pair` → `start` (K5d's clean sequence), 73.3 s of a two-voice program
spoken by `say -v Samantha` / `say -v Reed` through the MacBook speakers, `handoff` → the view token
onto the pasteboard → a portal poller on m4mbp that reads it through `curl -K -` on stdin. Server
side: **1271 requests, 1270 × 200 and exactly one 409** (381 snapshot + 381 events + 340 frames + 168
heartbeat + the one 409). `snapshotFetch.count` 325 (the app's own probe) + 56 (the poller) = 381
exactly — an independent cross-check that both readers were talking to this session.

*Green sub-clauses, with numbers.*
- **Continuously updating transcript with speaker labels.** Snapshot `version` 0 → 283 across 56
  polls, monotone; **42 committed spans**; `[S00]`…`[S16]` labels present throughout; the portal page
  itself 200 / 21282 bytes over the pinned leaf (hash re-verified against the D2 pin before trusting
  it); `terminal_failure` null and `status` still `active` at the last poll.
- **Decoder p95 RTF < 1: GREEN.** n=42, min **0.049**, p50 **0.139**, p95 **0.706**, max **3.398**.
- **Zero double count: GREEN.** `340 POST /frames → 200` is exactly the client's own
  `publishedFrameCount` 340.
- **Run-time secret hygiene held.** The token existed only in the app, on the pasteboard, and in one
  shell variable; it never reached argv, disk, a log or any output; pasteboard cleared to 0 bytes
  after. No raw audio persisted (`live-runs` 0 entries, no `/tmp/mtd-live-*`), 0 server tracebacks,
  both service MainPIDs and `NRestarts=0` unmoved, batch still 200.

*Red sub-clause 1 — user-visible p95 **10426 ms** against the canary's ≤ **4000 ms**.* Committed p95
**9052.9 ms** + render bound **1373.3 ms** (portal cycle 1000 + snapshot p95 227.3 + events p95
146.1). The report is otherwise sound: `sufficientSamples` true (**38** advances ≥ the plan's 20),
`mixerOriginResolved` true, `timelineIntact` true, `fetchFailures` 0, and all four disqualifier
counters (`rejectedNegative`, `rejectedClockRegression`, `rejectedAfterTimelineBreak`) **0**.

*Red sub-clause 2 — zero loss FAILED, and it is a NEW instance of `macos_buffer_overrun`.* At
~T+85 s, **inside a healthy meeting with a live pump**, the `system` lane went
`failed` / `macos_buffer_overrun`; K2's log line fired correctly
(`capture lane system failed: state=failed code=macos_buffer_overrun dropped=149 discontinuities=0`,
pid 68877, 15:53:25 local) and the server's v2 lane record carries `failed_samples: 8000`
(**0.5 s**), `health: failed`. The microphone lane stayed `capturing`. This is **not** L1: `start`
succeeded, the pump ran, frames published for 85 s. It is the *same code* reached by a different
road — the lane starved because publishing slowed, not because there was no pump. The stop drain
also left `outboxRetainedFrames: 3` and took the run's only 409 (`POST /frames` after the session had
stopped), where K5d's quiet meeting drained to 0 with zero non-200.

***The diagnosis, and it refutes candidate 43's premise.*** Per-span timing from the `events`
stream (`canonical_decode_elapsed_sec` / `canonical_decode_rtf`, each span's `span_frozen` and
`canonical_processed` first-seen poll times):
- **40 of 42 spans decode in 0.10–0.54 s** (RTF 0.049–0.706) and commit **0.0–1.6 s** after freezing.
- **Two spans do not: span 6 (8.49 s, RTF 3.398) and span 34 (8.29 s, RTF 3.318).** Both are
  degenerate decoder repeat loops — hundreds of `[0.99][S06]…[1.21]`-shaped fragments in one 2.5 s
  span.
- Each runaway **stalls the serial decode queue behind it**: the spans queued behind span 6 committed
  4.9 / 6.6 / 6.6 / 8.1 s late; behind span 34, 1.8 / 4.7 / 6.2 / 8.3 s late. That is the entire
  tail. Total decode was 26.7 s over 73.3 s of speech, so throughput was never the problem.
So **the committed p95 is set by two spans, not by a floor.** Candidate 43 reasoned "at a 2.5 s hard
cap the committed half is floor-bound near 2.5 s + decode, and the plan's first remedy — a 2.0 s span
cap — is aimed exactly there". Measured, the floor is **not binding** (median lag ≈ 0 s), and a 2.0 s
span that hallucinates a repeat loop still decodes for 8 s. **Neither of the plan's two ordered
remedies attacks this term.** The remedy that does is a bound on decode itself — max new tokens, a
repetition guard, or a decode deadline that degrades the span rather than blocking the queue — the
same shape as J3's transient-decode contract but for a decoder that answers *too slowly* rather than
not at all. It also plausibly explains sub-clause 2: the backlog window is exactly where accepted
samples fell to ~8.6 k/s (half real time) and the Mac's outbox and system-lane ring backed up.
*Corroboration across runs:* K5d's independent quiet meeting measured committed p95 **9089 ms**;
this run measured **9053 ms** on completely different audio. Two runs 36 ms apart on unrelated
content is what a small number of runaway decodes predicts and what a content-dependent floor does
not.

*Harness caveat, stated plainly because it bounds what F1 proves.* Both lanes carried the **same**
program: the `say` output reaches the system tap directly *and* the built-in microphone
acoustically, so the mixer summed the program with its own echo. The doubling is visible in the
transcript (span 1 renders "Good afternoon everyone." twice; span 27 repeats a whole sentence).
Consequences: **16 canonical speakers for 2 real voices** and many `S00` (J2's unattributed marker) —
so the *speaker-label* clause is expressible and present but **not meaningfully verified**; and the
marker cross-check could not be completed because `pineapple` was transcribed "Hi Apple" (span 26),
i.e. an ASR-accuracy miss, not a pipeline miss. The two red clauses above are **not** explained away
by the echo — the latency mechanism reproduced on K5d's echo-free run — but the label and marker
clauses are, and F2 must fix the harness: give the two lanes **different** content, which is what a
real meeting is.
> **Corrected by iteration 12's echo-free run.** The echo was real and is now removed, but it was
> **not** what produced 16 canonical speakers. An echo-free run saturates the same 16-speaker bound
> at t+45.5 s (F1 saturated at t+51.8 s). See "The lanes are separated" below.

*Reusable.* The canary driver is `/tmp/ralph-f1-canary.sh` on m4mbp (sha256 `e768a6dc…`, also at
`/tmp/ralph-f1-canary.sh` on MacStudio) with its evidence in `/tmp/ralph-f1/` there and a pulled copy
in `/tmp/ralph-f1-evidence/` here; the reducer is `/tmp/ralph-f1-analyze.py`. Neither holds a secret.
`log show --predicate 'subsystem == …' --last 20m --style compact` returned nothing for lines that a
plain `--last 90m` found — **do not read an empty `log show` as an absent log line**; widen the
window and drop `--style` before concluding anything.

**F3 — the 16-minute soak, RED at minute 14.6, and it names the defect that also ended F1 (new,
run 20260728-181020 iteration 9). READ THIS BEFORE ANY FURTHER CERTIFICATION RUN.** Session
`6e4f280535424114baf7bb10f66c31f1`, label `ralph-f3-20260728T200827Z`, on the real hosts at
`fc7097d`. K5d's sequence (fresh app → `pair` → `start` → `latency` → `handoff`), then one short
utterance per minute for **1020 s** with a 2 s portal poller and a 10 s `status` poller.

*The first 14 minutes are exactly what the clause asks for.* Per wall-clock minute the mixer
accepted **56–62 s of audio** on every one of minutes 0–13 (no minute below 30 s, no minute without
a new committed span); snapshot `version` **0 → 2647** monotone over 348 polls, **412 committed
spans**, `terminal_failure` null and `status` `active` in every 200; `retained_samples` peaked at
**247 982 of the 960 000 bound (25.8 %)**, so memory stayed bounded; `publishedFrameCount`
**3430 == 3430** `POST /frames → 200` server-side, so zero double count again; outbox 0–2 frames for
the whole healthy stretch.

***Then one dropped audio buffer ends the meeting in 29 seconds.*** Three independent clocks agree:
- **16:22:32.09** (m4mbp unified log, K2): `capture lane system failed: state=failed
  code=macos_buffer_overrun dropped=112 discontinuities=0` — pid 77860, at capture age **844 s**.
- **16:22:33** (server journal): the **first `POST /frames → 409`**, and the **last
  `POST /heartbeat → 200`** — 1682 heartbeats had gone out at 0.5 s, i.e. exactly up to this instant.
  57 × 409 follow in 28 s; no heartbeat follows at all.
- **16:23:01** (server journal, K3's line): `live helper terminal:
  session=6e4f280535424114baf7bb10f66c31f1 reason=helper_lease_expired lanes=none`. The view routes
  401 from age **874.8 s**, the client's own `status` reports `sessionRefusal: sessionDisowned` at
  875.9 s, and `POST /frames` answers **608 × 403** for the remaining 150 s because a release is
  one-way.

*The line that turns a lane hiccup into a dead meeting is `CaptureController.swift:413-417`:*
```swift
let published = try self.publishPendingFrames(configuration: configuration, onContention: .skip)
_ = try self.emitHealth(configuration: configuration)   // never reached when the publish throws
```
The comment directly above it states the right rule — *"a tick that finds the previous pass still
draining skips its publish turn, but it still emits health: the server's helper lease is what a
silent client loses"* — but that guarantee only covers **contention**. A publish that **throws**
propagates past `emitHealth` to the catch at `:421`, and because the wedged frame is retried and
refused identically on every later tick, the heartbeat stops **permanently**. 30 s later the helper
lease expires and the server correctly ends a meeting the client still believes is running. This is
the **third** instance of the same shape (J's four blockers, L1's `:403`): the heartbeat is coupled
to the publish path, so a non-fatal publish condition ends the meeting.
*The 409 is classified into the blind spot on purpose.* `CapturePumpFailure(error:)`
(`CaptureController.swift:150-167`) maps any `CaptureHTTPTransportError` to `transportUnavailable`,
and `CaptureSessionRefusal(error:)` **deliberately excludes 409** (`:179-182`, because the wire
overloads it for a closed session and an ordering conflict). Both decisions are defensible; together
they mean a permanently-wedged lane is reported as a transient network problem.
*Which 409 the server sent was left undetermined here and was **SETTLED in iteration 11** — it is
`LiveV2SessionTerminalError`, `"v2 system lane is failed."`, and **not** the
`LiveV2OutOfOrderFrameError` this block guessed at. Read the lane-refusal block below before using
any sentence in this paragraph.* Still true, and still the reason it took a probe: the access log
records only the status code and the client discards the body by G3's contract, so **neither host
records why a frame was refused**.

***The same chain ended F1.*** The journal still holds `live helper terminal:
session=de088f0510ec492082972365127cebee reason=helper_lease_expired lanes=none` at **15:53:55** —
exactly **30 s** after F1's own `macos_buffer_overrun` at 15:53:25.507. F1's canary stopped inside
that 30 s window, which is the only reason it looked like a live session at its last poll. So F1's
red zero-loss clause and F3's red soak are **one defect**, not two, and it is a different defect from
Phase L (there the pump never started; here it ran healthily for 14 minutes).

*The clause verdict, stated exactly.* **RED.** Capture did not remain active for 16 minutes.
"The same view authority works after minute 15" is **unproven, not disproven**: the token was
accepted continuously to **871.9 s (14.53 min)** and then refused because the *session* was gone —
25 s short of the 900 s that the retired fixed expiry would have used, so this run cannot discharge
that clause on real hardware. The 401 is **not** the old fixed expiry: it lands within 1 s of the
lease expiry and 28 s away from 900 s, and C1's deterministic nodes (60 virtual minutes, exact cap)
already prove the fixed clock is gone. "Clean stop immediately revokes it" is likewise unproven —
`stop` ran 150 s after the session had already been released (`revoke_latency_s=0.1`, but the
authority was refused before `stop`, not because of it).
*Everything else stayed clean:* both service MainPIDs (346453 / 301112) and `NRestarts=0` unmoved,
`live-runs` 0 entries, no `/tmp/mtd-live-*`, batch `/` and `/api/jobs` both 200 during the soak, the
served leaf hashed to the D2 pin **before** any authenticated request, pasteboard cleared to 0 bytes,
volume restored 45 → 31, and both TCC grants still `auth_value=2` after the app was quit.
*The app-owned latency report over 17 minutes* (evidence, not the Phase F procedure): committed p95
**9147.9 ms** (p50 1624.4, max 14437.0, n=358), render bound **1297.7 ms**, user-visible
**10445.5 ms**, `sufficientSamples` true, `timelineIntact` true, all disqualifier counters 0,
`fetchFailures` 607 — every one of those failures after the session died. A **third** independent
run at 9.1 s committed p95 (K5d 9089, F1 9053) on a fourth audio program.
*Reusable.* Driver `/tmp/ralph-f3-soak.sh` (m4mbp + MacStudio, sha256 `471e9a82…`), reducer
`/tmp/ralph-f3-analyze.py`, evidence `/tmp/ralph-f3/` on m4mbp and `/tmp/ralph-f3-evidence/` here.
Neither holds a secret. `log show` needs a **script file** on m4mbp — an inline `log show --predicate`
over `ssh` hits zsh's own `log` builtin and dies with `zsh:log:1: too many arguments`, printing
nothing, which reads exactly like an absent log line.

**The three Phase M decisions, taken and binding (new, run 20260728-181020 iteration 13).
READ THIS BEFORE WRITING ANY PART OF 53, 48 OR 50.** The fifth amendment required D-a/D-b/D-c to be
settled in writing before the patch. Full reasoning is in progress.txt under "Phase M decisions";
the rulings and the numbers behind them are here.

- **D-a. `macos_buffer_overrun` is a lane DEGRADATION, not a lane failure.** The general rule that
  decides it: *a lane failure means the lane can no longer produce audio; an event that loses some
  audio while the lane keeps producing is a degradation.* That rule partitions
  `NativeLaneFailureCode` cleanly and `bufferOverrun` is the only member on the degradation side —
  it is minted in exactly one place (`NativeAudioBuffers.swift:47-58`, a lane already holding
  `capacity` buffers) and is a statement about the **consumer**, not the device. *Zero-loss clause:*
  a dropped buffer never becomes a frame, so it is never *accepted* audio — an overrun is capture
  loss, not accepted-audio loss, and the clause holds. The report is the count, which already
  travels as `droppedFrames` / `dropped_frames` (`CaptureHTTPTransport.swift:395,415`).
  *What it buys:* the server needs **no change** — `_failed_lanes` keys on `state == "failed"`
  (`live_helper_failure.py:363-371`), so a degradation never reaches `_fail_lane`, never closes the
  lane, and never arms the 409 iteration 11 named. The chain breaks at step 1, the cheapest place.
  *What the patch must pay:* K2's log line fires only for `failed`
  (`CaptureController.swift:312-324`) and **both F1's and F3's diagnoses came off it** — an overrun
  must stay visible in the unified log as a degradation, or the cycle trades a dead meeting for a
  blind one. Three existing Swift assertions encode the old contract and must be changed
  **deliberately, citing this decision**: `CaptureControllerTests.swift:1507-1508`, the reducer
  table at `:2760`, and `:2710` — where a *health-mailbox* overflow reuses
  `.bufferOverrun(droppedBuffers: 1)` to mean "health facts were dropped". That overload is a
  different signal wearing the same fact and needs its own code, not the degradation's.
- **D-b. Inside one generation, no. Across a `stop`/`start`, yes — and that is K4's rule, not a new
  one.** With D-a applied every remaining failure code means the lane is not producing and cannot
  resume by itself, so an un-fail path would have to invent a recovery signal the source does not
  have; `recordFailure`'s stickiness stays. Across a restart the verdict names a session that no
  longer exists, exactly as K4 ruled for `sessionRefusal`. **`LiveV2Session` needs no un-fail
  path** — the amendment made that conditional on D-a, and with D-a the only lane the server ever
  closes is one that genuinely stopped producing.
- **D-c. Cap the decode, commit what came back, never abandon the span.** *Zero loss:* a capped span
  is still accepted and still committed with fewer words; abandoning it, or committing it empty,
  removes accepted audio from the transcript — which is the loss the clause forbids. *Speaker
  continuity:* a dropped span breaks the identity preparer's timeline, a shorter one does not.
  *Which cap:* a bound on **generated tokens derived from the span's own duration** — not a
  wall-clock deadline (non-deterministic, makes the same audio decode differently on a busy host,
  untestable here) and not a repetition heuristic in decoder space we do not control. It attacks the
  measured mechanism directly: both runaway spans were degenerate repeat loops emitting hundreds of
  fragments for 2.5 s of audio, i.e. far more tokens than the audio can contain. The constant must
  be **derived from the committed spans already in the F1/F3/canary evidence** (observed max
  tokens-per-second-of-audio for real speech, plus an explicit margin) and the derivation recorded —
  a tuning value, not a domain-contract value; the contract's 2.5 s `hard_cap_samples` is what it is
  derived *from*. A capped span publishes what the decoder returned, with the cap recorded on its
  event so truncation is visible rather than inferred (H1's treatment, one step along).
  *Not fixed by this:* the decode queue stays serial. The cap is chosen because it removes the
  measured cause; if a capped run still misses the gate, the plan's ordered remedies apply **then**.

**The heartbeat is uncoupled from the publish — candidates 53 and 48, one shape on two paths (new,
iteration 14; `[done]`). READ THIS BEFORE RE-RUNNING F1 OR F3.** Both red certification runs died of
this and nothing else: iteration 11 measured that after the lane-failed 409 *the peer lane still
returns 200 and a heartbeat still returns 200*, so the meeting was survivable and only the skipped
`emitHealth` ended it.
- **53, the tick.** `emitHealth` now runs in its **own** `do/catch`, after the publish's, so a
  publish that throws no longer jumps over it (`CaptureController.swift:404-437`). The publish's
  verdict is left standing rather than cleared — only a publish that *succeeds* says the transport
  recovered — so `pumpFailure` still reports the refused lane while the lease stays alive.
- **48, the start.** `let status = try emitHealth(…)` moved inside a `do/catch` that applies the
  **same rule the publish above it already applied**: retryable → degraded start (pump failure
  recorded, pump scheduled, status returned from `state.snapshot`), non-retryable → `source.stop` +
  `rollbackStart()` + rethrow. So a 403 on the start-time heartbeat can no longer leave both lanes
  hot with no pump, and `alreadyRunning` no longer blocks the next start.
- **The third caller now records a refusal.** One private `recordTransportVerdict(_:)` is called from
  all four request sites (start publish, start heartbeat, tick publish, tick heartbeat), and
  `rollbackStart()` **keeps** `sessionRefusal` while still clearing `pumpFailure` — `beginStart`
  clears it, so a verdict can never outlive the session id it names (K4's rule, unchanged). After an
  unwound start, `mtd-capture status` now answers `sessionDisowned` where it used to answer nothing.
*Red-before/green-after, three nodes, all in `CaptureControllerTests.swift`:* the F3 shape
(`ThrowingPublishStillEmitsTheHeartbeat…` — red: 1 heartbeat for 4 expected), the K5d wedge
(`StartHeartbeatTheServerRefusesUnwinds…` — red: lanes `capturing`, no refusal, second start
`alreadyRunning`), and the degraded start (`TransientStartHeartbeatFailure…` — red: `start` threw
503). Swift **151 → 154**, 0 failures. **Not fixed by this, and deliberately:** a lane the server has
permanently closed still retries its head frame once per tick. That costs one doomed request per 0.5 s
and the pump already isolates lanes (`CapturePublishPump.swift:110-124`), so the meeting continues on
the peer lane — with D-a landed, the server never closes an overrun lane at all.

**D-a is landed — an overrun is a degradation, and the client can finally say so (new,
iteration 15; `[done]`). READ THIS BEFORE RE-RUNNING F1 OR F3, WITH THE UNCOUPLING BLOCK.** D-a was
decided in iteration 13 and implemented here. The chain iteration 11 measured had four links; 53
broke the fourth, this breaks the **first**, and either alone keeps the meeting alive.
- **The vocabulary is partitioned, not renamed.** `NativeLaneFailureCode` (5 cases) means *the lane
  can no longer produce audio*; the new `NativeLaneDegradationCode` (2) means *it lost some and kept
  producing*. Two enums, so a degradation structurally cannot be minted where a failure is expected.
  `NativeLaneProjection` carries both; `reportedState(running:)` resolves failed → stopped →
  degraded → state, and `reportedCode` puts whichever verdict holds into the one wire code slot.
- **`degraded` is not a new word on the wire.** The server's `HELPER_STATES`
  (`live_helper_presence.py:10-14`) has always had it, `HelperLaneHealth` requires a `failure_code`
  only for `failed` while permitting it elsewhere, and ADR M04 already forbade failing a session for
  it. **The server needed no change and got none** — `moss_transcribe_diarize/` and `ops/` are still
  byte-identical to `main`, which is what keeps the offline probe's validity argument alive.
- **The second defect the reclassification exposed, and it is the one worth remembering.** The
  health mailbox *fenced itself shut* on the first overrun (`isTerminalOverrun`), because an overrun
  used to be the lane's last word. Left in place, a degraded lane would have gone **silent for the
  rest of the meeting while still producing audio** — losing the device failure that genuinely ends
  it. Measured in the red probe: after an overrun the lane reported `dropped=112` and
  `discontinuities=0` and never saw the `ioStoppedAbnormally` that followed; with the fence removed
  it reports `dropped=120`, `discontinuities=2`, `failed/macos_io_stopped_abnormally`.
  *The general lesson:* **a fence justified by "nothing after this matters" outlives the
  classification that justified it.** Re-classifying a fact means auditing everything that treated
  it as final.
- **The mailbox overflow stopped borrowing the overrun's name.** It appended
  `.bufferOverrun(droppedBuffers: 1)` — the audio code *and* the audio counter — for a loss of
  *health facts*. It is now `macos_health_facts_dropped` with `droppedFrames` untouched: facts and
  frames are different losses and must not share a number the PRD's accounting reads.
- **K2's log follows the condition.** `LaneFailureLoggingHealthAdapter` records a degradation as
  well as a failure (both live diagnoses were read off that line), still once per lane per
  generation, and the line's **verb comes from the state**: `capture lane system degraded:
  state=degraded code=macos_buffer_overrun dropped=149 …`. So the F1/F3 grep for
  `capture lane <lane> failed:` still matches failures only — **grep `capture lane ` in any future
  soak diagnosis**, not `failed`.
- **Stickiness, decided deliberately:** a degradation is first-cause-wins for the generation, like a
  failure, and `beginGeneration()` clears it (D-b's rule, unchanged). Un-degrading would need a
  "no drops for N ticks" threshold nothing has measured; `droppedFrames` carries the live count
  regardless.
*Red-before/green-after, both halves.* Probe A (pre-D-a reporting + the old mailbox fence, new
vocabulary kept so the tests still compile): **6 tests / 12 failures**, including the wire body
(`failed` vs `degraded`) and the swallowed later failure. Probe B (K2 filter back to `failed`-only):
the degradation logged **nothing**. Python: the new seam node flipped to `lane_state="failed"` reds
on `('failed', 'macos_buffer_overrun') != ('active', None)` — its negative control is the node above
it. Swift **154 → 158**, Python **598 → 599**, both suites 0 failures; the lane-refusal probe still
rc=0 (the server's failed-lane path is untouched and still permanent).
*What is NOT fixed by this, deliberately:* a lane that genuinely stops producing still fails, still
closes on the server, and still retries its head frame once per tick — 53's note applies unchanged.

**The decode is bounded — candidate 50 / D-c is landed, and the derivation is measured (new,
iteration 16; `[done]`). READ THIS BEFORE RE-RUNNING F1 OR F3, AND BEFORE TOUCHING THE TWO
CONSTANTS.** F1's latency tail was two spans out of 42; this is what stops them.
- **The bound that was actually in force was `VllmRunner.transcribe`'s own default.**
  `RunnerBoundedWavInference` passed **no** `max_new_tokens`, so every live span decoded under
  **2048**. Measured: F1's two runaways generated **2024** and **2019** tokens — they ran to that
  default and stopped there. The 8.5 s was not a slow decode, it was a *long* one.
- **The cap is affine in the span's own duration**, `68 + ceil(87 × duration_sec)`, so a 2.5 s
  span may generate **286** tokens instead of 2048 and a 0.5 s span **112**. Both terms are an
  observed maximum times an explicit margin of **4**: real speech never exceeded **54 tokens on a
  full 2.5 s span** (21.6 tokens per audio-second) and never exceeded **17 tokens on a span under
  0.5 s** — the fixed cost of the transcript's own syntax, which does not shrink with the audio,
  and the reason a pure rate would have starved short spans. All 76 real spans sit ≥ **4.88×**
  under their cap. Tuning values, not contract values; `hard_cap_samples` is what they derive from.
- ***How the tokens were counted, which is the reusable part.*** The committed transcripts of two
  independent runs (F1's 42 spans, the echo-free canary's 46) were tokenised **by the deployed
  decoder's own tokenizer**, through the resident vLLM's `/tokenize` endpoint on the host —
  read-only, no GPU work, no state touched. `POST http://127.0.0.1:8000/tokenize` with
  `{"model": "OpenMOSS-Team/MOSS-Transcribe-Diarize", "prompt": <text>, "add_special_tokens":
  false}` answers `{"count": n, …}`; the empty string calibrates to **0** either way, so there is
  no hidden template overhead in these numbers. Characters would have been a guess: the runaways
  are 1012 chars/s of audio against real speech's 44, but the ratio that decides a *token* budget
  is not the same number.
- **A capped span commits its words** (D-c), and the event says it was capped:
  `canonical_processed` now carries `canonical_decode_token_cap` and `canonical_decode_capped`
  beside the RTF. Truncation is stated rather than inferred — a shortened span and a quiet one are
  otherwise identical downstream.
- **A configured `max_new_tokens` may only tighten the derived cap** (`min`), never loosen it: the
  deployment that configures the runner cannot see the serial queue that makes one runaway the
  whole tail.
*Red-before/green-after, two probes, both semantic reverts with the file restored and re-hashed
(`aa481428…` / `a1bbcb82…` both ways).* Probe A — stop passing `max_new_tokens`:
`assert '2048' == '286'` on the wire field the product's own `_build_fields` builds, which is the
defect stated in one line. Probe B — drop the two event fields:
`KeyError: 'canonical_decode_token_cap'`. Python **599 → 602**, `test_live_pipeline_seams.py`
**53 → 56**, 0 failures.
*What is NOT fixed by this, deliberately:* the decode queue is still serial, and the latency
effect is **predicted, not measured** — at the runaways' own generation rate (2024 tokens in
8.49 s ≈ 238 tok/s) a fully capped 2.5 s span costs ~1.2 s instead of 8.5 s, which should take the
committed p95 from 9.05 s to near the 1.5 s median lag. F1 is what decides that. If a capped run
still misses the gate, *then* the plan's ordered remedies apply.
***The standing validity argument for the offline probes was spent here and RESTORED by M6c
(iteration 20).*** This was the first Phase M change under `moss_transcribe_diarize/`, so the
offline probes spoke for the **branch** rather than the deployed service from iteration 16 until the
redeploy. Since M6c all four checkouts hold `77e0014` and the branch's product source is identical
to `main`, so `live-lane-refusal-probe.py` / `live-hardcap-repro.py` speak for the deployed service
again. **The rule that outlives both states:** an offline probe speaks for the service only while
`git diff --name-only <deployed sha> HEAD -- ':!scripts/ralph-afk'` is empty — compare against the
**deployed** SHA, never against `main`, because between a merge and its redeploy those differ.

**The failed lane is in the suite — the Phase M coverage gap is closed (new, iteration 17;
`[done]`).** `tests/test_live_api.py:1055` failed the microphone lane and posted a **system** frame,
so the one path that ended F1 and F3 was covered only by the offline probe. Two nodes now close it,
both in `tests/test_live_api.py` and both semantically red-proved:
- **`…a_frame_on_the_lane_its_own_heartbeat_failed_is_refused_permanently_and_the_meeting_survives`**
  replays F3's sequence on the failed lane: healthy frame → a heartbeat reporting `system` failed
  (**200**, one failed lane is not terminal) → the next frame on **that** lane **409**
  `{"detail": "v2 system lane is failed."}` with **no** `failure` key, the identical retry 409 again,
  the **peer lane 200**, a **heartbeat after the refusal 200**, and the session still registered.
  Both halves are the point: the refusal is permanent *and* survivable, which is why the fix belonged
  in the client's tick (53) and not on the server.
- **`…a_degraded_lane_keeps_publishing_where_a_failed_lane_is_refused`** is D-a asserted on the wire:
  a `degraded` heartbeat is accepted and the frame on that lane returns **200**, `health` stays
  `active`, `failure_code` stays null.
*Red-before, by semantic revert, both files restored and re-hashed byte-identical
(`9b145d2e…` / `728f26ce…` both ways — the same hashes K5c recorded on the host).* Probe A deleted
`LiveV2Session.accept`'s `health != "active"` guard → node 1 `AssertionError: 200 != 409` while
node 2 stayed green (correct — it is about a lane that is never closed). Probe B made `_failed_lanes`
treat `degraded` as failed (with a code fallback, or the heartbeat 400s on the missing
`failure_code` before reaching the point) → node 2 `AssertionError: 403 != 200` with
`live helper terminal: … reason=helper_all_lanes_failed lane.system=macos_buffer_overrun
lane.microphone=macos_buffer_overrun` in the log — i.e. **without D-a the meeting dies exactly as it
did in K5d/F1/F3**, which is the strongest available statement that the reclassification is
load-bearing. Python **602 → 604**; the lane-refusal probe still rc=0.
*Product source untouched this iteration* — the diff against `main` is what candidate 50 already
made it, plus test files.

**The Phase M gate is green, and the certification ORDER is settled by precedent (new,
iteration 18). READ THIS BEFORE THE SIXTH MERGE.** Gate step (a) — the full local gate from the
Validation fence — is **GREEN at the feature tip `21a73ea`**, every line of it:
Swift **158 passed / 0 failures**, **0 `warning:` lines** across two builds into a *fresh* scratch
(the claim only means anything on a first build); Python **604 passed / 2 skipped / 368 subtests**
in 62.7 s, the two skips named as the pre-existing `test_large_upload.py:155,175` Python-3.10
contract and **not** Darwin skips; tracer **4 passed / 0 skips**; Phase A discriminator **10/10**;
`live-lane-refusal-probe.py` **rc=0**; all **seven** `live-hardcap-repro.py` cases rc=0; leak-scan
clean; `git status --porcelain` empty. Log `/tmp/ralph-i18-gate.log`, probe JSON
`/tmp/ralph-i18-lane-refusal.json`.
*Merge payload, reviewed at the same time:* exactly **10 files, +983/-51**, all inside the fifth
amendment's scope — `CaptureController.swift` (53+48), `NativeLaneHealth.swift` + `CaptureSecurity.
swift` (D-a, incl. the log verb coming from the state), `NativeDualCaptureSource.swift` (49),
`CaptureControllerTests.swift`, `live_adapters.py` + `live_coordinator.py` +
`live_service_runtime.py` (D-c), `test_live_api.py`, `test_live_pipeline_seams.py`. **No `ops/`,
no `macos/scripts/`, no doc, no `main`-only content.**

***The order, decided once and binding: gate → merge → publish + redeploy (+ Mac rebuild) → F1 and
F3.*** The fifth amendment's text lists F1/F3 *before* the merge. That order is physically
unreachable and the loop has already answered this exact question twice:
1. F1/F3 exercise the **deployed** server and the **installed** bundle. The server is detached at
   `fc7097d` and `/Applications/MOSSCapture.app` was built from `fc7097d` (K5c). **Neither carries
   any part of Phase M.** A run today would re-measure the code both red runs already died on.
2. Candidate 50's token cap is server-side only, so the latency clause — one of F1's two red
   sub-clauses — **cannot be measured at all** without a redeploy, and prd.md forbids deploying
   from a feature branch.
3. Building the Mac half from the feature branch would be exactly that forbidden deploy, *and*
   would certify a fixed client against an unfixed server.
4. **Precedent, not invention:** H4 and J5 hit the identical wording and ran gate → merge →
   redeploy → probe (progress.txt, candidate 42's J5 entry: *"the amendment lists the probes before
   the merge, but the branch's fixes are not on the host"*). J5d's green then landed at the merge
   SHA `6a540fe`, and K5d likewise at `fc7097d`.
**Nothing is weakened by this.** Both F1 and F3 green against the redeployed SHA is still the
acceptance evidence, and a red one is answered by the next amendment exactly as H4d's red was — the
merge buys the *ability to measure*, never the verdict.

**The sixth merge is made — `77e0014` (new, iteration 19). READ THIS BEFORE THE REDEPLOY.** Gate
step (b) of the fifth amendment, by the standing pre-merge procedure, both fences satisfied
honestly.
- **Fence 1, the history join, proven content-free BEFORE it was run.**
  `git merge-tree --write-tree main HEAD` returned **HEAD's own tree `64ad23d6…`**, so joining
  `main` could not bring content in. `git merge --no-ff main` → **`1b6a9f4`**, and afterwards
  `git diff --stat 79b52e4 HEAD` and `git diff --name-only 21a73ea HEAD -- ':!scripts/ralph-afk'`
  were **both empty**. Only then was `merge-base --is-ancestor main HEAD` honestly true.
- **Fence 2, `expected_main` advanced in-script** (`merge-keeper.sh:32`,
  `6a540fe…` → **`fc7097d…`**) with a paragraph citing the **fifth** amendment and naming all six
  items it authorizes — never the `RALPH_MERGE_MAIN_BEFORE` env override — and **committed first**
  (`4ac5d95`) so it became the feature tip the merge captured.
- **The merge**, run in the **background** per the standing lesson: `77e0014`, parents
  `fc7097d` (main) and `4ac5d95` (feature). Its own in-worktree gate, on the **merged** tree:
  Swift **158 passed / 0 failures**, Python **604 passed / 2 skipped / 368 subtests** in 64.4 s.
  The worktree cleaned itself up (`git worktree list` shows the primary only).
- **The tested tree IS the committed tree**, stated as a hash rather than assumed: merge tree and
  feature tree are both **`d2094369…`**, and `git diff --name-only 21a73ea 77e0014 --
  ':!scripts/ralph-afk'` is **empty** — the merged product source is byte-identical to what gate
  step (a) tested.
- **Payload against `main^1`:** exactly the reviewed **10 files, +983/-51** — `CaptureController.
  swift`, `NativeLaneHealth.swift`, `CaptureSecurity.swift`, `NativeDualCaptureSource.swift`,
  `CaptureControllerTests.swift`, `live_adapters.py`, `live_coordinator.py`,
  `live_service_runtime.py`, `test_live_api.py`, `test_live_pipeline_seams.py`. **No `ops/`, no
  `macos/scripts/`, no doc.** (The full `main^1 → main` diff also carries this loop's own
  `scripts/ralph-afk/` evidence, which is not product source.)
- **The guard is live again, rehearsed non-vacuously:** `RALPH_MERGE_DRY_RUN=1` now prints
  `ERROR: main moved from expected pre-merge SHA fc7097d…` and exits **1**. A seventh merge is
  refused until another amendment advances the line.
*What this did NOT do, and iteration 20 then did:* the merge was **local**. Gate step (c) — the
**K5c-shaped** redeploy — is what restored the four-way SHA. See the next block.

**M6c is deployed — all four checkouts at `77e0014`, and the deployment is proven by witness rather
than by SHA (new, iteration 20). READ THIS BEFORE F1 OR F3.** Gate step (c) of the fifth amendment,
in K5c's order: push → server checkout → admission check **under the new code** → restart → poll →
Mac checkout → rebuild → reinstall. Rollbacks pre-recorded and committed (`970a144`) before any host
was touched; nothing needed to be rolled back.
- **Four-way SHA GREEN 4/4** at `77e0014` — local `main`, `origin/main`, the server checkout, the
  m4mbp checkout. The push was a fast-forward `fc7097d..77e0014`, proven first, never forced.
- **The server's tree is the merge's own tree** `d2094369…` — the same hash gate step (a) tested at
  the feature tip, so the deployed tree needs no separate argument.
- **D-c is running, exercised rather than asserted.** Under the *service's* venv python on the host:
  `canonical_decode_token_cap(sample_count=40000)` → **286** and `(8000)` → **112**, exactly
  iteration 16's derived numbers, and `LiveServiceRuntime` carries both event fields. Manifest
  admission is **unchanged** (`available=True`, `failures=[]`, hash `61d97ffe…`), so D-c adds no
  admission constraint and breaks none.
- **The venv resolves the package FROM THE CHECKOUT**, measured, not assumed:
  `live_adapters.__file__` = `/mnt/d/Coding/…/moss_transcribe_diarize/app/live_adapters.py`. That is
  what makes "checkout + restart = new code" a fact. A non-editable venv would have restarted
  happily into the old code and mis-attributed every later measurement.
- Restart: MainPID **346453 → 350731**, `NRestarts=0`; `/live` 200 **9 s** after the restart
  (polled). Batch never restarted — `moss-web` 301112, `moss-vllm` 322117, both `NRestarts=0`, and
  `/` + `/api/jobs` 200. 0 tracebacks, `live-runs/` 0 entries, no `/tmp/mtd-live-*`.
- **The installed Mac product carries Phase M**, by a witness with a **control word** —
  `macos_health_facts_dropped` and `degraded` are **1 in the new install and 0 in the pre-M6c
  backup**, while `macos_buffer_overrun` is **1 in both**. Measured on the CLI *and* on
  `MOSSCaptureApp`, the binary that actually captures. The control is the point: 1-vs-0 alone proves
  the bytes changed; the 1-vs-1 beside it proves the grep works and the 0 is a real absence.
- **The DR is byte-identical across this rebuild for the fourth time**, `codesign --verify -R=` and
  `--verify --strict` both pass, G1's ATS block is still in the installed `Info.plist`, and **both
  TCC grants still hold `auth_value=2`** with the csreq decoding to that DR — measured read-only
  after the bundle inode moved `211995344 → 212080356`.
- **From m4mbp over the tailnet** — the exact path the PRD clause names — the served leaf hashes to
  the D2 pin `a35ca9fc…` **before** any request is trusted, and `/live` + `/api/live/descriptor` are
  **200**.
*Consequence for the offline probes:* they speak for the deployed service again, because the branch
tip's product source and `main` are identical and `main` is what all four hosts hold.
*Rollback strings this run created (the only copies of the `fc7097d` bytes — do not delete):*
`/Applications/MOSSCapture.app.backup-20260728T222244Z` and
`/Users/ga0/.local/bin/mtd-capture.backup-20260728T222244Z`.

**F1's re-run is blocked on a sleeping Mac — and the clause reduction now has a tool (new,
iteration 21). READ THIS BEFORE THE NEXT ATTEMPT AT GATE STEP (d).**
*The blocker, measured rather than inferred.* Setup ran: the app was launched fresh on m4mbp (pid
51512, both lanes `stopped`, `running:false`), a pairing code was minted on the server loopback and
consumed by `mtd-capture pair` (payload 113 bytes, `sessionID 8a6db4f6…`, device row **reused**, not
created), and `live-canary.sh` was copied over with matching sha256 `e88e4455…`. Then m4mbp went off
the network mid-setup and never came back inside the iteration: `ssh` timed out on every one of ~25
attempts over 12 minutes, ICMP 100 % loss, `nc -z 100.64.0.4 22` closed, `tailscale ping` "no reply",
and — the discriminating fact — the peer's **`rx` counter froze** at 162 594 700 while `tx` kept
climbing, i.e. our packets leave and nothing answers. **There is no second path:** MacStudio is
`192.168.68.36`, m4mbp is `192.168.1.240` on a different LAN with no ARP entry, so the tailnet is the
only route and Wake-on-LAN is unreachable. Nothing the loop can do wakes it; this is the same class
as the TCC clicks — a physical-host input.
*State left on m4mbp for the next iteration to clean up:* the app is **running** and the device is
**paired with a fresh bearer**. No capture was started, no lane is hot, the output was never muted
and the pasteboard was never written. K5d's rule still stands, so the next attempt must
`pkill -x MOSSCaptureApp`, relaunch fresh, and **re-pair** (this run's pairing code is single-use and
its 300 s life is long spent).
*What the iteration delivered instead, and it was the run's own missing instrument.*
`scripts/ralph-afk/live-canary-clauses.py` reduces a canary/F1 evidence directory to the
**certification clauses** — the question `live-canary-analyze.py` does not answer. Sections: poll
health with the first non-200; transcript growth; final snapshot incl. per-lane v2 health; the
accounting equality; decoder RTF **and D-c's token cap and capped-span count**; per-span commit lag
from the event stream; the latency report with its two components stated separately against the
run's gate; and the lane-health timeline printed **only where it changes**.
*Validated against three real directories rather than asserted:* on iteration 12's canary it
reproduces the recorded committed p95 **8342.697 ms** and user-visible **9702.2 ms** to the
millisecond and re-finds the two runaway spans (8.49 s / 8.35 s); on F1's directory it reproduces the
recorded decoder p95 RTF **0.706** and prints F1's red sub-clause 2 by itself — `system` goes
`failed`/`macos_buffer_overrun` at t+86.0 s with `failed_samples 8000`; on F3's directory it
**refuses** with a named reason, because that driver writes a compact projection whose second column
is not a status code. The old `/tmp/ralph-f1-analyze.py` could not read a canary run at all (hard-coded
directory, `T_MARKER_END`/`MARKER` keys the canary does not write), which is why this existed as a
gap.
*The invocation lesson, paid for once:* run the driver **`nohup`'d on m4mbp** and poll its log, never
as a foreground `ssh`. The link dropped three times during setup alone; a drop 40 s into a meeting
kills the driver mid-run and leaves the mute and the session behind.

**F3 has a repo driver now, and the reducer stopped passing two red runs (new, iteration 22).
READ THIS BEFORE THE SOAK HALF OF GATE STEP (d).** m4mbp was still unreachable for the whole
iteration (ssh timeout and 100 % ICMP loss on ~40 polls over 17 min), so the work was the soak's
own missing instrument — the same move iteration 21 made for the canary, applied to F3.
*Why the old driver could not be re-run as it stood.* `/tmp/ralph-f3-soak.sh` spoke its program
through the Mac's speakers, so it carries **exactly the echo confound candidate 51 removed** — and
the fifth amendment's gate requires that harness on **both** runs. It also wrote `snapshot.tsv` as a
positional jq projection, which `live-canary-clauses.py` refuses by name. And it lived only in
`/tmp` on two hosts.
*`scripts/ralph-afk/live-soak.sh`* is the canary's harness (output muted, topology before/after and
restored, the marker said alone ×3 at `-r 130`, `phases.tsv` naming each minute's intended lane)
plus the soak's own clauses: view-authority checks at `t0`, **the moment the token's age crosses
900 s**, after the soak, and after the stop. That third check is new and it is the point — F3's only
post-boundary check landed at age **1024 s**, 124 s late, which is why that run could not separate
"the authority expired" from "the session was already dead".
***The snapshot body is pruned, and the decision is measured, not tidy.*** F1's full body grew
**2796 → 18210 bytes across 42 committed spans** (~366 B/span, mean 10.3 KB/poll over 56 polls), so
a 412-span soak would reach ~150 KB/poll and ~**38 MB** of `snapshot.tsv` — written on the capture
Mac, during the run whose latency is being measured. The driver keeps the snapshot's **shape** and
replaces `committed[]` with its span ids. *Proven rather than asserted:* the **shipped** filter,
extracted from the script and applied to F1's 56 real bodies, gives **byte-identical reducer
output** at **564.5 → 102.7 KB (18.2 %)**, and the pruned body grows **32 B/span instead of 366**
(1020 → 2371 B), so a 412-span poll is ~14 KB and the whole file ~5 MB. `identity_snapshot` is the
other 700 B and is bounded by the 16-speaker contract, so it does not grow.
***Running the reducer on real directories found two false verdicts, which is the durable half.***
- **F1's directory returned `rc=0`.** Its recorded red sub-clause 2 — `system` goes
  `failed`/`macos_buffer_overrun` at t+86.0 s — was *printed* in the lane timeline and *decided* by
  nothing. Section 8 now reads that timeline as clauses and F1 reduces to **RED** from the evidence
  alone. Which transition is a fault comes from the shipped contracts, not taste: `failed` → red
  (D-a made an overrun a *degradation*, so a failed lane means it stopped producing),
  `degraded` → reported, `sessionRefusal` (K4) and `outboxDegradation` (B2) → red,
  `pumpFailure` → **reported, not red** (53 deliberately keeps the heartbeat alive through a
  failing publish).
- **F3's directory returned `rc=2` and threw away evidence the reducer understood.** The layout
  refusal is now **per section**, so F3 reduces to its recorded facts: lane failed **t+845.8 s**,
  `outboxDegradation overflowedLaneRetention` **t+865.9 s**, `sessionRefusal sessionDisowned`
  **t+875.9 s**, revoke latency **0.1 s** — and the "same authority after minute 15" clause comes
  out **UNPROVEN, not disproven**, automatically, because the session was already refused 148 s
  before the check. That distinction cost a careful human reading the first time; it is in the
  reducer now.
- **A refused layout can no longer exit 0.** `undecided` forces `rc=2`, so a half-read directory
  cannot be mistaken for a pass.
*Regression, stated because it is what makes the two new verdicts trustworthy:* the iteration-12
canary and F1 reduce **byte-identically** to the previous reducer through section 7, and the canary
— a clean meeting — gains **no** new red, so the section-8 clauses do not fire on a healthy run.

**D-c is MEASURED on the deployed service, and the cap is live-but-unexercised (new, iteration 23).
READ THIS BEFORE READING F1'S RE-RUN AS A VERDICT ON CANDIDATE 50.** m4mbp was unreachable for a
third iteration, so the reachable half of gate step (d) was taken: one `live-pipeline-probe.py` run
against the deployed `77e0014` from MacStudio over the tailnet, 120 s, `--lane-offset-ms system=137`,
device `ralph-i23-dc-probe-20260728T225905Z` (**revoked**; the only unrevoked device is still m4mbp's
`AB600574…`). Report `/tmp/i23-probe.json`.
*The instrument gap that was closed first, and it is the iteration-22 lesson in a second costume.*
The probe collected `canonical_decode_rtf` and **dropped** `canonical_decode_elapsed_sec`,
`canonical_decode_token_cap` and `canonical_decode_capped` — it predates D-c, so it **structurally
could not** have answered this question. *A reducer that prints a fault does not decide it
(iteration 22); a probe that never collects the field cannot measure it.* The probe now carries all
three plus a `decode` section, and it re-derives the expected cap by **importing the product's own
`canonical_decode_token_cap`** rather than restating the formula (fallback to the literal only when
the checkout is not importable; the report names which was used — `product-function` here).
Validated offline on six synthetic cases before the host run, including the two that matter: a
service with **no** cap on the wire reduces to `cap_present=0 / derivation_holds=False` rather than to
a pass, and a drifted cap **names its span** (`cap 2048, expected 286`).
- **The deployed pipeline is healthy end to end — the first real-audio exercise of the sixth merge.**
  240 ticks, 480 frames, `non_200_count` **0**, one TLS handshake, and
  `accepted == accounted == committed == 1 920 000` samples (exactly 120 s at 16 kHz). `status`
  `closed`, `terminal_failure` null, **4 attributed speakers** (S01–S04), **0 unattributed spans**.
  36 of 59 spans committed **empty** — H1's path firing 36 times with the accounting still balancing
  exactly, which is the strongest statement available that "commits empty, never terminal" holds at
  volume.
- **D-c is in force on real spans, and the derivation holds on the wire.** **58 of 58** spans carry
  `canonical_decode_token_cap`, every one equal to the product's own function for that span's
  duration, across **21 distinct values 89 … 286** — so the cap is genuinely per-span, not a
  constant that happens to be present. Iteration 20 only *called* the function on the host; this is
  the first time the number came back off the wire.
- ***But `capped_count` is 0, so the cap is DEPLOYED AND UNEXERCISED, and this run is NOT evidence
  that it fixes F1's tail.*** No span ran away, so nothing was truncated, so the missing 8.5 s tail
  **cannot be credited to the cap**. F1's runaway rate was 2 of 42; 0 of 58 here is ~5 % likely on
  that rate, so this is weak evidence the rate is lower on clean synthetic audio and **no** evidence
  about the cap's effect. F1 remains the run that decides candidate 50.
- **What the run does prove about the cap is its SAFETY, on content it was not derived from.** The
  23 committed spans with text tokenise (the host's own vLLM `/tokenize`, calibrating to 0 both ways)
  to **14–24 tokens** against caps of 89–286: **minimum headroom 7.64×**, median 13.0×, where
  iteration 16's derivation dataset had a minimum of 4.88×. **A cap that truncates real speech would
  be worse than the runaway it prevents**, and on a third independent dataset it does not.
- **The affine form's fixed term is load-bearing, measured rather than argued.** Tokens per
  audio-second is duration-dependent exactly as iteration 16 predicted: spans **≥ 2.0 s** peak at
  **9.60** tok/audio-s (well under the 21.6 the constant was derived from, 9.06× rate-term margin),
  while spans **< 1.0 s** reach **31.32** — the transcript's own syntax not shrinking with the audio.
  On the two sub-second spans a **pure rate** cap would have left only **2.79×** and 5.33× headroom
  where the affine cap leaves 7.64× and 9.87×. Do not "simplify" the cap to a rate.
- **The first decode of a session is warm-up, and certification must not read it as a runaway.**
  Span 0 took **1.689 s for 0.763 s** of audio (RTF 2.214) and returned **empty**; every one of the
  other 57 spans decoded in **≤ 0.456 s** (min 0.104, p50 0.207, p95 0.456). Decoder **RTF p95
  0.574 < 1** — green — and the `max` of 2.214 is that warm-up span alone. This matches the recorded
  "one pre-warm 2.5 s request took 3.851 s"; **pre-warm or discount span 0**, or a clean run reports
  a false tail.
*What this says nothing about, stated so the next reader does not borrow the number:* the Mac half —
outbox, pump, lane health — is untouched by this, and the probe's own committed p95 **2809 ms** /
user-visible **3954.7 ms** are a **different instrument on different audio** than F1's app-owned
9053 ms. They are not comparable and must not be quoted as an improvement.
*Host untouched:* `HEAD` still `77e0014`, `moss-live-web` MainPID **350731**, batch `moss-web`
**301112** / `moss-vllm` **322117**, all `NRestarts=0`; `live-runs` 0 entries, no `/tmp/mtd-live-*`,
**0** journal tracebacks, batch `/` still 200. Baselines `/tmp/i23-host-baseline.txt` and
`/tmp/i23-host-after.txt`.

**D-c's latency effect is MEASURED — a runaway costs 8.13 s uncapped and 1.07 s capped (new,
iteration 24). READ THIS BEFORE READING F1 AS THE VERDICT ON CANDIDATE 50.** m4mbp was unreachable a
fourth time, so the iteration took the half of candidate 50 that never needed the Mac. Iteration 23
left the cap **deployed, derivation-exact and safe but UNEXERCISED** (`capped_count` 0), so its
latency effect was still only predicted. `scripts/ralph-afk/decode-cap-latency-probe.py` induces the
runaway deliberately instead of waiting for one, on the deployed `77e0014` engine.
- **The paired measurement, same audio, same trigger, same real seam.** Both conditions run through
  the product's own `RunnerBoundedWavInference.transcribe_pcm` with a real `FrozenSpan` of the
  contract's 40000 samples; only `_token_cap` differs — **A** overridden to the 2048 that was
  actually in force before D-c (a semantic revert of D-c inside the probe), **B** the product's own
  `canonical_decode_token_cap`, imported not restated.

  | condition | tokens | wall median | RTF |
  | --- | --- | --- | --- |
  | control, no trigger | 49 | **0.198 s** | 0.081 |
  | **A pre-D-c 2048** | 2048 (3/3 hit) | **8.129 s** (8.036-8.192) | 3.277 |
  | **B deployed cap 286** | 286 (3/3 hit) | **1.074 s** (1.071-1.077) | **0.431** |

  **7.571x, 7.056 s off the head of the serial queue**, and a fully capped runaway no longer breaks
  the RTF gate either (0.431 < 1, where the runaway is 3.277).
- ***The reproduction is F1's own failure, within 4 %.*** F1's two runaways were 2024 / 2019 tokens
  at 8.49 / 8.29 s, RTF 3.398 / 3.318; condition A reproduces 2048 tokens at 8.13 s, RTF 3.277. That
  agreement is the evidence that the induced condition is the same condition, and it makes the
  measured generation rate **251.9 tok/s** — against the 238 tok/s iteration 16 predicted from F1's
  own spans, which predicted ~1.2 s for a capped span where **1.074 s** was measured. *The
  iteration-16 prediction was right.*
- **The queue argument, which is the part that reaches F1's p95.** This probe bounds the head of the
  serial queue, not the queue. But F1 committed 42 spans over 73.3 s, i.e. a mean span arrival of
  **1.745 s** — so an 8.13 s decode is **4.66x the arrival interval** and *necessarily* accumulates
  backlog (F1 measured exactly that: spans behind the runaways committed 4.9-8.3 s late), while a
  1.074 s decode is **below** the arrival interval and therefore cannot accumulate any. That is a
  structural statement, not an extrapolation.
- ***What this run does NOT establish, stated so the number is not over-read.*** (a) The **rate** of
  runaways is unmeasured — the trigger is deliberate, so this says nothing about how often a real
  meeting hits one. (b) The trigger is `temperature=2.0`, i.e. high-entropy sampling, **not** a
  natural repeat loop, and the survey below is why. (c) **D-c's "a capped span commits its words"
  half is NOT verified here:** this trigger's output is unparseable at *any* length, so the product
  reported 0 tokens and an empty transcript for the capped *and* the uncapped runs alike — there
  were no words to commit either way. F1's repeat loops were parseable fragments; that half of D-c
  still rests on the unit tests alone. What the empty answers *do* show is H1's path firing three
  more times without going terminal.
- **The trigger had to be measured, not assumed, and the first two guesses were wrong.** The
  endpoint's own `/openapi.json` has **no `ignore_eos` and no `min_tokens`**, so the loop must come
  from a sampling field. Surveyed at the pre-D-c bound on the same span (control 49 tokens):
  `repetition_penalty=0.5` → **0 tokens** (it *suppresses* generation, immediate EOS, 0.04 s);
  `frequency_penalty` -2.0/-1.0, `presence_penalty` -2.0, their combination, and
  `repetition_penalty=0.9` → **27 tokens**, i.e. all *shorten* the answer; `repetition_penalty=1.05`
  → 49, unchanged. Only **`temperature=2.0`** ran away. A probe that had assumed its trigger worked
  would have compared two identical empty decodes and reported a meaningless 1.0x.
*Host untouched, checked against a baseline taken first:* `HEAD` still `77e0014`; `moss-live-web`
**350731**, `moss-web` **301112**, `moss-vllm` **322117**, all `NRestarts=0`; `live-runs` 0 entries,
no `/tmp/mtd-live-*`, no probe scratch left, **0** tracebacks, batch `/` 200, and the device store
still **10 devices / 1 unrevoked** (m4mbp's) — this probe creates no device and no session. The four
`/tmp/*.wav` on the host are dated **2026-07-27**, a day before this run, and are the feasibility
probe's; the run's own span wav was deleted in the same invocation that wrote it.
*Reusable:* `python3 scripts/ralph-afk/decode-cap-latency-probe.py --wav <2.5 s span> --checkout
<deployed checkout> --extra-field temperature=2.0 --extra-field seed=<n> --repeats 3`, shipped to
the host on stdin and run under the service venv. `--survey --candidate 'label:field=value,...'`
re-answers the trigger question if the engine is ever replaced. Evidence `/tmp/i24-measure-raw.txt`,
`/tmp/i24-survey.log`, `/tmp/i24-host-baseline.txt`, `/tmp/i24-host-after.txt`.

**D-c's OTHER half is settled — a capped span commits its words, and F1's runaways had none
(new, iteration 25). READ THIS WITH THE TWO BLOCKS ABOVE BEFORE READING F1 AS THE VERDICT ON
CANDIDATE 50.** m4mbp was unreachable a fifth time. Iteration 24 measured what the cap *costs*
(8.129 s → 1.074 s) but recorded, as its limitation (c), that it could **not** verify the ruling's
other half: its `temperature=2.0` trigger was unparseable at *any* length, so capped and uncapped
alike committed empty and there were no words either way. That half rested on the unit tests.
`scripts/ralph-afk/decode-cap-truncation-probe.py` settles it on the deployed `77e0014`.
- ***The measurement is possible with no Mac and no engine run, and the licence is greedy
  decoding.*** `VllmRunner._build_fields` sends `temperature` 0.0 unless the caller asks for
  `decoding="sample"`, and the live path never does — so the token sequence a decode produces
  under a cap of N **is the N-token prefix** of the sequence the same decode produced under 2048.
  The cap changes when generation stops, not what it generates. So the transcript a capped decode
  would have returned is `detokenize(tokenize(<the recorded uncapped transcript>)[:cap])`, computed
  with the **deployed decoder's own tokenizer**.
- ***And the licence is verified rather than argued.*** Re-tokenising F1's two committed runaway
  transcripts returns **2024** and **2019** tokens — *exactly* the generated-token counts F1's own
  decode reported for those spans — and re-tokenising each truncation returns the same first 286
  ids. An offline reconstruction that reproduces the engine's own counter to the token is the
  reconstruction, not an approximation of it.
- **THE FINDING THAT CHANGES HOW F1 IS READ: F1's two runaways contain ZERO words.** Both parse to
  **127 segments of `[t][Sxx]...[t]`** — the literal text `...`, no alphanumeric character
  anywhere. The two spans that set F1's entire 9.05 s committed p95 bought **no transcript content
  at all**. So for the spans D-c was built for, "commits its words" was vacuous in both directions,
  and *nothing was ever at risk of being lost by capping them*.
- **At the real cap the span still commits, and never goes empty.** Truncated to 286 tokens, each
  runaway publishes **18 segments** with `empty_reason` **None** and identity status `prepared` —
  not H1's empty path, not a failure, not terminal.
- **A runaway that DOES hold words keeps them.** Built from the same run's own word-bearing
  fragments (1996 tokens, 105 segments, 1817 word chars), it commits **15 segments / 226 word
  chars** at the cap. *Stated honestly:* a degenerate loop repeats itself, so this shows the words
  survive truncation — it cannot show that no *distinct* content is lost, and no evidence available
  without a real runaway on real speech can.
- ***The general claim, which is the durable half: no cut point is terminal.*** Every character
  prefix of all three transcripts was classified — **9062 cuts, 0 terminal and 0 unclassified**.
  The only non-committing outcomes are the first 19/19/40 characters, before the first fragment
  closes, and those are `committed_empty` through H1's named `decoder_returned_unparseable_transcript`
  — the designed non-terminal answer. The token boundary is one cut out of thousands and the next
  runaway will not land on it, so the sweep is what makes this a property of the parse rather than
  a fact about two numbers.
*What "the real live path" means here, because reading the wrong seam would have answered a question
about code the meeting never runs:* the probe drives `LiveCoordinator.prepare_work_item` →
`_empty_transcript_reason` → `BoundedCausalIdentityPreparer.prepare` → `submit_prepared_work` →
`LiveSession`. It deliberately does **not** use `LiveProvider.decode_canonical` /
`_validated_segments`, which is the **batch** provider's seam — the live coordinator calls
`transcribe_pcm` directly and classifies the transcript itself.
*Limits, stated so the result is not over-read:* the decoder is stubbed to return the truncated
text (the engine is not re-run — the greedy-prefix argument plus the exact token agreement is what
licenses that), and `capped`/`token_cap` are set by the stub, which is harmless because the
coordinator only forwards them to the event and never classifies on them.
*Host untouched, checked line-by-line against a baseline taken first:* `HEAD` `77e0014`;
`moss-live-web` **350731**, `moss-web` **301112**, `moss-vllm` **322117**, all `NRestarts=0`;
`live-runs` 0; no `/tmp/mtd-live-*`; no probe scratch; `git status --porcelain` empty; device store
**10 / 1 unrevoked**; **0** tracebacks; batch `/` 200. The probe makes no TLS call, creates no
device and no session, and touches only the `/tokenize` and `/detokenize` routes.
*Reusable:* `--evidence-dir <canary or F1 dir>` or `--spans-json -`, `--tokenizer-url`,
`--synthesize-wordy-runaway <chars>`, `--sweep-stride`. Evidence `/tmp/i25-trunc-report.json`,
`/tmp/i25-trunc-raw.txt`, `/tmp/i25-host-baseline.txt`, `/tmp/i25-host-after.txt`.

**Candidate 49's mechanism was wrong in the record, and is now measured (new, iteration 13;
`[done]`).** The record said the lane failure "survives a stop/start inside one process" because
"`NativeLaneHealth` keeps `projection.failure`". **It does not** — `beginGeneration()`
(`NativeLaneHealth.swift:58-65`) resets every projection and `stop` invalidates the generation too.
The real mechanism is one line away: `NativeDualCaptureSource.start` cleared `reportedDroppedBuffers`
— the watermark of drops already turned into facts — while
`RealTimeNativeAudioBufferQueue.droppedBuffersByLane` is **cumulative for the life of the process and
never reset**. So the first `pendingFrames()` of the new generation read the whole process's drop
history back as fresh loss and failed the lane on the **first heartbeat**, before the new meeting had
dropped anything. Fixed by re-baselining the watermark against the queue instead of zeroing it;
red-before/green-after in
`testNativeDualCaptureSourceStartDoesNotReplayEarlierGenerationDrops` (red: `failed` /
`macos_buffer_overrun` / `droppedFrames 1` on a restart that dropped nothing).
*The general lesson, worth more than the fix:* **a watermark must be reset together with the counter
it watermarks** — resetting one alone is what replays history as news.

**The lanes are separated, and it corrects two things F1 concluded (new, run 20260728-181020
iteration 12). READ THIS BEFORE F2.** Session `c06fa7c5457c476487d48eca13454964`, label
`ralph-c51-20260728T210237Z`, 86.8 s of accepted audio on the real hosts at `fc7097d`, driven by the
new in-repo `scripts/ralph-afk/live-canary.sh` with `OUTPUT_MODE=muted`.

*The mechanism, and it is now measured rather than assumed.* A stock Mac has no way to route the
program away from the room — no `SwitchAudioSource`, no `sox`, no virtual device on m4mbp — so the
driver **mutes the system output** for the program. **The process tap is upstream of the output
mute**: with the room hearing nothing, the whole program still transcribed ("Good afternoon,
everyone.", "Begin weekly transcription status review.", "Thank you. Returning to the system
audio.", "That concludes the agenda."). Muting is therefore a valid, device-independent
lane-separation mechanism, and it is what F2 should use.

*The echo is gone, measured on the same instrument that found it.* **0 of 46 spans carry a repeated
fragment** (F1: 3 of 42, including "Good afternoon everyone." twice inside span 1), and the run
produced **49 fragments** where F1 produced **304** for a comparable program.

*The speaker-label clause is verified for the first time.* After the identity preparer settles, the
two program voices hold **stable, distinct labels across the whole meeting**: in the final program
phase — *after* the microphone lane had had its own 28-second turn — the labels are exactly
`S04 ×4` (voice A) and `S06 ×2` (voice B), with no new speaker invented.

***Correction 1, and it matters more than the fix.*** F1 blamed the echo for **16 canonical
speakers**. This echo-free run **also** reaches 16, saturating the `max_identity_speakers` bound at
**t+45.5 s** of an 89 s run; re-reducing F1's own evidence shows it saturated at **t+51.8 s**. The
driver is low-content fragments minting a canonical speaker each, mostly from the microphone lane's
ambient noise — not the echo. See candidate 55.

***Correction 2.*** The marker cross-check failed a **second** time, with a second word: `umbrella`
went the way of `pineapple`. Two words, two failures — a rare noun inside a fluent sentence is
reliably rewritten by the decoder's language model. The harness now says the marker **alone,
repeated three times at `-r 130`**; that change is written but **not yet exercised by a run**.

*What did NOT work, stated because it bounds what the harness can promise.* MacStudio's speaker at
volume 60 was supposed to give the microphone lane content of its own. `elephant` never appears.
The room window produced only filler (`S00 ×15` — J2's unattributed marker — plus four one-hit
labels): the mic lane is bound to **AirPods Pro over Bluetooth at 24 kHz**, not the built-in mic.
So the run separates the lanes as *program vs room* but the room is not yet a second speaker. An
external source that the capture Mac's own microphone can actually hear is still unfound.

*Topology is transient operator state and must be recorded every run.* This run found m4mbp's
default **input and output both** on AirPods Pro; F1 and F3 ran on the built-in speakers and
microphone. Output volume also moved 50 → 64 → 50 while the loop was working, and 238 bytes
appeared on the pasteboard after the driver had cleared it to 0 — **the operator was using the
machine during the run**. The driver now writes `topology-before.txt` / `topology-after.txt`.

*Clean meeting, and candidate 50 reproduces a fourth time.* No `macos_buffer_overrun`; both lanes
`capturing` throughout and `stopped` on a clean stop; `publishedFrameCount` 350 with the outbox
drained to 0; `sessionRefusal`, `pumpFailure`, `outboxDegradation` all null. Committed p95
**8342.7 ms**, user-visible **9705.3 ms** — a fourth independent run in the 8.3–9.1 s band
(K5d 9089, F1 9053, F3 9148).

**The 409 is NAMED, and the meeting was survivable (new, run 20260728-181020 iteration 11).
READ THIS BEFORE DESIGNING CANDIDATE 53'S FIX.** F3 left "which 409" undetermined and recorded
`LiveV2OutOfOrderFrameError` as likeliest. It is **not** that. Settled offline and deterministically
by `scripts/ralph-afk/live-lane-refusal-probe.py`, which drives the **real** `create_app` in-process
(the branch carries no product source, so its tree == `main` == the server checkout, all `fc7097d`
— re-verified this iteration) through F3's exact sequence and through the rival hypothesis beside it.

*The chain, and every link is a component behaving as designed.*
1. The Mac's `system` lane overruns. `NativeLaneHealth` classes `macos_buffer_overrun` as a lane
   **failure**, not a degradation (`NativeLaneHealth.swift:8,217-220`).
2. K1's projection carries that honestly into the **next heartbeat**. One failed lane is not
   terminal, so the heartbeat answers **200** — and then
   `LiveHelperFailureCoordinator` calls `_fail_lane` (`live_helper_failure.py:232`) →
   `LiveV2Session.fail_lane` (`live_v2_session.py:139-156`): the lane's retained frames are released
   into `failed_samples` and `lifecycle.health` becomes `failed`. **This is the client arming its own
   refusal**, and it is why F3's *last* heartbeat 200 and its *first* frame 409 share one second.
3. Every later `POST /frames` **on that lane** hits `LiveV2Session.accept`'s
   `if lifecycle.health != "active"` (`live_v2_session.py:99-103`) → `LiveV2SessionTerminalError` →
   `live_transport.py:262` → **HTTPException 409**, body exactly `{"detail": "v2 system lane is
   failed."}`.
4. `publishPendingFrames` throws, `emitHealth` at `CaptureController.swift:417` is skipped, the
   heartbeat stops, the 30 s lease expires — candidate 53.

*Measured, all rc=0 in one probe run:* the failed lane answers **409 three times in a row on the
identical retried frame** (permanent — `LiveV2Session` has no un-fail path, so the outbox's
retain-until-acked loop can never clear it); `failed_samples` 2 of 2 and `failure_code`
`macos_buffer_overrun` on `system` while `microphone` stays `health: active`; **the peer lane's next
frame returns 200**; **a heartbeat sent after the refusal returns 200** and the session stays
registered. So the meeting was survivable on one lane with the lease intact: *the only thing that
killed F3 was the skipped `emitHealth`.*

*The rival hypothesis, run beside it so the two are compared rather than argued.* A genuinely
skipped wire sequence answers a **different** 409: `{"detail": "expected v2 system frame sequence 1,
got 2.", "failure": {"code": "v2_out_of_order_frame", …}, "snapshot": …, "v2_session": …}` — and it
is **recoverable**: posting the awaited sequence afterwards returns 200. Two consequences.
(a) The two 409s are distinguishable on the wire *today*: the lane-failed one carries a bare
`detail` and **no** machine-readable `failure.code`. The client already receives the answer and
discards it by G3's contract, so candidate 54's "log it server-side" is one option and "stop
discarding it client-side" is another. (b) A sequence gap could never have been the cause anyway —
`CaptureFrameOutbox` stamps wire identity at admission and **a refused frame burns no sequence
number** (`CaptureOutbox.swift:116-120`), which is exactly the invariant that keeps the stream
gapless after lost audio.

*What this kills, and what it adds, for candidate 53's fix.* **Dead remedy:** "the client
resynchronises the lane sequence" — the refusal is not about sequence and no client-side
renumbering can reopen a lane the server has closed. **New question for whoever authorizes it,**
one level above candidate 53 and the same shape as L2's second question: should 0.5 s of dropped
capture audio close a lane for the rest of a meeting at all? Three components each behave
defensibly and the product of the three is a dead meeting; the cheapest single place to break the
chain is step 1 — an overrun with a dropped-buffer count is a *degradation*, not a *failure*.

*The coverage gap that let this ship, stated so it is closed deliberately:*
`tests/test_live_api.py:1055` fails the **microphone** lane and then posts a **system** frame,
asserting the *peer* lane survives. **Nothing in the suite posts a frame on the lane that failed.**
Same shape as every blocker in Phases H/J: the one path that ends the meeting is the untested one.

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

## Deployed reality — all four checkouts at `77e0014`

**Server (`ga0-alienware-rtx4070ti`, WSL Ubuntu, checkout `/mnt/d/Coding/MOSS-Transcribe-Diarize`).**
Detached at **`77e0014`** since M6c (run `20260728-181020` iteration 20); it was `fc7097d` (K5c),
`6a540fe` (J5c), `b817871` (H4c), `317df4d` (G5), `f9285d6` (D1). The checkout's own `main` ref is
still **`163e969`**, so `git -C /mnt/d/Coding/MOSS-Transcribe-Diarize checkout 163e969` is a complete
one-command rollback that moves nothing but `HEAD` — rehearsed for real and undone in F4a.
- **The venv is an editable install pointing at the checkout** (measured in M6c:
  `live_adapters.__file__` is under `/mnt/d/Coding/…`), which is why a restart picks up a checkout
  and why `git checkout` + `systemctl restart` is the whole redeploy.
- `moss-live-web.service`: installed (byte-identical to `ops/systemd/`), enabled, active, TLS on
  `0.0.0.0:7861`, **MainPID 350731**, `NRestarts=0`. `/live` answers 200 ~8-11 s after a restart —
  **poll for 200, never sample once**; a single early probe returns `000` and reads like a failure.
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
  *count* is not a signal; count unrevoked devices. Baseline copy:
  `live-auth.json.ralph-f0-backup-20260728T091927Z`, sha256 `9d306766…`.
- Windows host: portproxy `0.0.0.0:7861 → 172.30.115.123:7861` beside the untouched 7860 and 5100
  rows; firewall rule `MOSS-Transcribe-Diarize-Live` (Inbound/Allow/**Private** only); the sign-in
  scheduled task argument list ends `-RefreshOnly -IncludeLive`. `webrtcvad-wheels 2.0.14` and
  `onnxruntime 1.23.2` installed; WeSpeaker ONNX staged and hash-verified.
- **Remote-shell quoting.** Nested quoting through Windows conhost → `wsl.exe` → bash mangles inline
  scripts. Ship the script on **stdin** (`printf '%s\n' … | ssh … "wsl.exe -d Ubuntu -- bash -s"`).

**m4mbp (the capture Mac).** macOS 26.5.2, Xcode 26.5, Swift 6.3.3. Checkout
`/Users/ga0/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize`, reachable as `ga0@m4mbp`
with `BatchMode=yes`, **detached at `77e0014`** (tree `d2094369…`), clean.
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
  mtime `2026-07-28T18:22:32Z`. (K5c's `fc7097d` install was digest `267ada93…`, CLI `c11e89ff…`,
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

**The one class all of Phase J, L1 and candidates 50/53 belong to:** *a condition the design
contemplates is handled everywhere except the one path that ends (or degrades) the meeting.* Four
blockers in Phase H/J were this shape; L1 and 53 were the same shape and were fixed as one in
iteration 14; **50 and 55 are the two still unfixed.** Suspect this class first.

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
| **F1 canary / F3 soak** | **RED** — see the two blocks above. One defect, candidate 53. |
| **Phase M gate step (a)** | GREEN at **`21a73ea`** — Swift 158/0 (0 warnings, fresh scratch), Python 604+2/368, tracer 4/0 skips, 10/10, lane-refusal probe rc=0, 7/7 hard-cap cases, leak-scan clean, tree clean; payload 10 files / +983/-51 all in scope. |
| **M6 gate + merge #6** | Merge **`77e0014`**, parents `fc7097d` + feature tip `4ac5d95`; join `1b6a9f4` proven content-free first. In-worktree gate on the merged tree: Swift 158/0, Python 604+2/368 in 64.4 s. Merge tree == feature tree `d2094369…`. **Not server-only** (4 files under `macos/`), so step (c) is the K5c shape: restart **and** Mac rebuild+reinstall. Guard rehearsed: a seventh merge refuses. |
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
    pinned-TLS peer. It retired a large block of server risk (see the F0 block above for everything
    now proven, including "no raw audio is persisted" and the ~1280 ms render bound) and **found two
    blockers that would have destroyed F1 seconds after the operator's TCC clicks**. Off-list and
    justified in progress.txt: it is the only remaining work that could fail *downstream* of the one
    human step, and it needed no human. Re-runnable; the device revoke is mandatory after each run.
23b. **F0b — the offset probe run** `[done — iteration 10]`: one run with
    `--lane-offset-ms system=137 --lead-seconds 0` spent F0's open caveat and found blocker 3. The
    device was revoked, both batch units and the live unit kept their MainPIDs/NRestarts/timestamps,
    `live-runs/` is still 0 entries and no `/tmp/mtd-live-*` survives. See the H-diagnosis block.
24. **F1 — 60 s canary** per prd.md. `[RUN — RED — run 20260728-181020 iteration 8]`. See the F1
    block above. Green: continuously updating labelled transcript (42 spans, version 0 → 283),
    decoder p95 RTF **0.706**, zero double count (340 published == 340 accepted), run-time secret
    hygiene, no raw audio persisted. Red: **user-visible p95 10426 ms vs ≤ 4000 ms**, and **0.5 s of
    system-lane loss** to a mid-meeting `macos_buffer_overrun`. The diagnosis (candidate 50) is the
    part that matters; the label/marker clauses are confounded by the harness (candidate 51) and
    must be re-run, not re-argued. F1 is re-runnable end to end from
    `/tmp/ralph-f1-canary.sh` and costs no operator input.
25. **F2 — 300 s locked run** with 5 s interruption and the system-audio-denied variant.
    `[open — do NOT run before candidate 51; F1 proved the harness confounds the label clause, and a
    300 s run would spend five times the wall clock on the same confound]`
26. **F3 — 16-minute active-view soak**: capture and `/live` polling stay active with periodic
    two-lane audio; same authority works after minute 15; clean stop immediately revokes it.
    `[RUN — RED — run 20260728-181020 iteration 9]`. See the F3 block above. Green for 14 minutes:
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
    the mechanism below is WRONG, see the Phase M list and the correction block above]`. With no pump, the lanes overrun (`macos_buffer_overrun`,
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
    detail - it is what makes candidate 53's wedge permanent. See the lane-refusal block.

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
    `[done - run 20260728-181020 iteration 12; see "The lanes are separated" above]`. Fixed by
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

53. **A throwing publish stops the heartbeat, so one dropped audio buffer ends the meeting**
    `[done - iteration 14; the diagnosis below is kept, the fix record is in the Phase M list and
    the uncoupling block above; ROOT CAUSE of both red certification runs]`. Measured in F3 and re-read in F1's journal: an overrun on one
    lane makes the next `POST /frames` answer 409, `publishPendingFrames` throws at
    `CaptureController.swift:413`, `emitHealth` at `:417` is skipped, the same frame is refused on
    every retry so the heartbeat never resumes, and the 30 s helper lease ends the session. F3 died
    at minute 14.6; F1 died 30 s after its own overrun, inside the window its `stop` hid.
    *Shape of the fix, not a decision:* the tick's health emission must survive a failed publish the
    same way it already survives contention (the comment at `:410-412` states the rule the code only
    half implements) - and, separately, a lane whose frames are permanently refused must degrade
    (stop publishing that lane and report it) rather than block the pump forever. **Iteration 11
    named the refusal and it changes this list** (see the lane-refusal block): the 409 is
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

**D-a, D-b and D-c are TAKEN (iteration 13)** - see "The three Phase M decisions, taken and binding"
above for the rulings and progress.txt for the full reasoning. In one line each: an overrun is a
**degradation**, not a failure (so the server needs no change and the chain breaks at step 1); a
failed lane does **not** recover inside a generation but **always** does across a `stop`/`start`
(K4's rule), and `LiveV2Session` gains no un-fail path; a runaway decode is bounded by a
**duration-derived token cap** whose span still commits.

**D-a is IMPLEMENTED (iteration 15)** - `[done]`, see "D-a is landed" above. D-b needed no code (its
ruling was that `LiveV2Session` gains no un-fail path, and it has none). **D-c is IMPLEMENTED
(iteration 16)** - `[done]`, see "The decode is bounded" above. **All four authorized candidates,
all three decisions and the coverage gap have landed; what remains in Phase M is the gate alone.**

53. **[done - iteration 14]** The tick's `emitHealth` now has its own `do/catch` after the publish's,
    so a throwing publish cannot skip it; the publish's `pumpFailure` is left standing and only a
    successful publish clears it. See the uncoupling block above.
48. **[done - iteration 14, with 53 as one shape]** The start's `emitHealth` came under the same
    guard the publish above it already used: retryable -> degraded start with the pump scheduled,
    non-retryable -> `source.stop` + `rollbackStart()` + rethrow, and the refusal recorded either
    way. `rollbackStart()` now keeps `sessionRefusal` (cleared by `beginStart`), so a refused start
    is visible in `status` instead of silent.
49. **[done - iteration 13]** Not `NativeLaneHealth`'s projection, which `beginGeneration()` resets
    correctly. `NativeDualCaptureSource.start` zeroed the `reportedDroppedBuffers` watermark while
    the queue's per-lane drop counter is cumulative for the whole process, so the new generation's
    first drain replayed every historical drop as fresh loss and failed the lane on its first
    heartbeat. Now re-baselined against the queue; red-before/green-after. See the correction block
    above. **D-a still has to land** - this fix stops a *previous* generation's drops failing a
    lane; it does nothing about the current one's.
50. **[done - iteration 16]** Bounded per D-c: `canonical_decode_token_cap` =
    `68 + ceil(87 × duration_sec)`, each term an observed maximum times an explicit margin of 4,
    derived by tokenising F1's and the canary's committed spans with the deployed decoder's own
    tokenizer. The bound in force before this was `VllmRunner`'s 2048 default, which is exactly
    where both runaways stopped (2024 / 2019 tokens). A capped span commits its words and the
    `canonical_processed` event carries `canonical_decode_token_cap` / `canonical_decode_capped`.
    See "The decode is bounded" above. **DEPLOYED in iteration 20** — the host's own interpreter
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
    Mac. See "D-c's OTHER half is settled" above.
D-a. **[done - iteration 15]** `macos_buffer_overrun` is a lane degradation. Two code enums, a
    `degraded` state the server's contract already had, the mailbox's overrun fence removed (it
    would have silenced a still-producing lane), the mailbox overflow given its own code, and K2's
    log following the condition. Server unchanged. See "D-a is landed" above.
54. **[CLOSED - answered, not fixed]** The refusal reason is known. 53's fix **may** stop discarding
    the server's refusal detail where it must tell a permanent lane-failed 409 from a recoverable
    one; that is the only part of 54 in scope.

**Coverage gap - CLOSED in iteration 17.** `tests/test_live_api.py` now posts a frame on the lane
that **failed** (409, permanent, peer + lease survive) and on the lane that **degraded** (200,
health stays active), both red-proved by semantic revert of the two guards that decide them. See
"The failed lane is in the suite" above. **Nothing remains in Phase M except the gate.**

**Gate, in four steps. The order is decided — see "The Phase M gate is green" above for why the
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
  found in the installed binaries by a strings witness with a control word. See "M6c is deployed"
  above.
- **(d) F1 and F3, both required green** `[BLOCKED in iteration 21 - m4mbp is asleep/off the
  tailnet; setup completed, the meeting never ran. See "F1's re-run is blocked on a sleeping Mac".
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

55. **N1 - separate matching from enrollment.** The core defect: one threshold does both jobs, so a
    0.5 s fragment can overwrite a good prototype. A short span may be *labelled* against a
    prototype; it must never *become* one. Everything else in this phase depends on this split.
56. **N2 - duration-weighted centroid (strategy C).** Wire it through the `canonical_embedding` hook
    that already exists in `WeSpeakerLiveEvidenceProvider.__init__` and that
    `_identity_evidence_provider` never passes. O(1) memory and compute per span.
57. **N3 - raise the enrollment minimum to >= 2.0 s.** `identity_provider.min_segment_samples` is
    **not** a domain-contract value; the contractual 8000 is the *live frame size*, a different
    quantity sharing the number. Do not change the frame size. Treat 2.0 s as a lower bound - the
    supervisor's voices were synthetic TTS and cleaner than real humans.
58. **N4 - bounded bank (strategy D), only if measurement justifies it.** D and C were within 0.2%
    of each other; adopt D only if a prototype must demonstrably survive a bad patch.
59. **N5 - gate, merge, redeploy.** A tracked regression reproducing the duration curve that fails
    if the enrollment floor drops below the measured separation point; C must beat A on oracle
    alignment **and** same-speaker probe minimum on the real encoder; then F1 and F2 with candidate
    51's distinct-voice harness and the speaker-label clause **meaningfully verified**; then one
    merge, push, redeploy.

Keep the abstain path throughout: an ambiguous span stays unlabelled rather than guessing, and J2
already ruled that an abstain must not end the meeting.

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
