# Context - MOSS live meeting transcription MVP

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

## Current state

Measured 2026-07-27 from MacStudio against the live hosts. Anchors are file:line on the feature
branch after the iteration-1 graft unless stated.

**Branch state.** Iteration 1 merged `acl/IDEA-044--A-034@67a27b8` into `ralph/live-meeting-mvp`
with `--no-ff` (conflict-free: A-034 branches from the same `af3ac36` and touches paths disjoint
from the Ralph scripts). Iteration 2 added the per-lane permission coordinator (A3); iteration 3
moved the portal handoff into the app (A2); iteration 4 rebuilt the tracer around the immutable
lab bundle (A4); iteration 5 made the file secret store the production default (B1); iteration 6
added the retained-until-ACK outbox (B2); iteration 7 added the 16 kHz/8000-sample wire format and
converted-nanosecond timestamps (B3); iteration 8 added the bounded concurrent transport (B4);
iteration 9 added the tracked Mac packaging/install tools (B5); iteration 10 recorded the Phase B
client gate (B6) and changed no product source; iteration 11 bound view authority to the session
lifecycle (C1); iteration 12 generated the retuned manifest bounds (C2); iteration 13 added the
tracked TLS-material and loopback-pairing tools (C3a); iteration 14 added the tracked two-service
deployment bundle (C3b); iteration 15 added the app-owned latency probe (C3c); iteration 16 ran the
final local gate and made the **one keeper merge** (C4); iteration 17 published it (D1),
iteration 18 finalized the host manifest and rotated the live TLS pair (D2), iteration 19
installed and started the live service plus its Windows forward (D3), iteration 20 aligned the
m4mbp checkout with the published SHA (E2a), iteration 21 created the signing identity there (E1),
and iteration 22 built, signed and installed the app there (E2b) — none of 17-22 changed a tracked
file. Iteration 23 recorded the E3 blocker. **The post-merge freeze is then reopened exactly once**
by the prd.md amendment of 2026-07-28: run `20260728-072601` iteration 1 landed G1 (the ATS
declaration plus its gates), iteration 2 landed G2 (the pairing-payload trim and the canonical
wire form) and iteration 3 landed G3 (control-channel failure classification and logging), so the
branch carries tracked product source again, strictly within the amendment's four items.
Iteration 4 re-ran the full client gate green and changed no tracked source (see the G4 gate block),
and iteration 5 made **the amendment's one authorized follow-up merge** (see the second-keeper-merge
block). The post-merge freeze has resumed: from `23aabe6` on, the feature branch may again carry only
`scripts/ralph-afk/*`. Iteration 6 published that merge to all four checkouts (G5), iteration 7
rebuilt and reinstalled the signed app on m4mbp (G6's automatable half), and iteration 8 rehearsed
and restored the server rollback (F4a); none of the three changed a tracked file, and the *product*
on the Mac now carries G1+G2+G3. Iteration 9 built the F0 server-side probe and found two
certification blockers; iteration 10 resolved F0's one open caveat and found a **third**, worse one
(see the F0 and H-diagnosis blocks). Neither 9 nor 10 changed a tracked file.
**The freeze is then reopened a second time** by the prd.md amendment of 2026-07-28 (server
decode-seam cycle): run `20260728-112922` iteration 1 landed H3 — the first tracked **server**
source change on this branch — so the branch now carries `moss_transcribe_diarize/` again, strictly
within that amendment's scope; iteration 2 landed H1 (the empty-span decode contract) and
iteration 3 landed H2 (the span-cap authority contract), which closes the last of F0's three
blockers. Iteration 4 ran the **H4 gate green** at `8b852f2`, reviewed the merge payload against the
amendment's scope and proved the deployed manifest still admits under H2's and H3's new refusals; it
changed no tracked file. Iteration 5 made **the second amendment's one authorized merge** at
`b817871` (see the third-keeper-merge block) and changed no tracked product source — only
`merge-keeper.sh`'s guard. **The post-merge freeze has resumed: from `9e0780a` on, the feature branch
may again carry only `scripts/ralph-afk/*`.** Iteration 6 published that merge and redeployed the
live service (H4c) — see the H4c redeploy block; it changed no tracked file, and **the deployed
service now carries H1/H2/H3**. Only H4's step (d), the probe, is open in Phase H.

**PRD acceptance scoreboard after iteration 6 of run 20260728-112922.** Green with evidence:
IDEA-044 checkpoint, production client gate, server meeting-reliability gate, the reviewed keeper
merge (plus both amendments' authorized follow-up merges), live service answering (re-measured after
the redeploy), batch service unharmed, signed app installed, **rollback rehearsed and recorded**.
**One exact SHA everywhere is 3/4 green at `b817871`** — local `main`, `origin/main` and the host
checkout all read it; **m4mbp is the only laggard and is offline** (`ssh`/`ping` both time out on
`m4mbp` and `m4mbp.local`), so its `git fetch && git checkout b817871` is the one mechanical step
left. No Mac rebuild is needed for it. Open: permissions granted, the 60 s canary, the 300 s
certification, the 16-minute soak, the run-time half of secret hygiene, and the final close.

**Those open items are no longer merely waiting on E3 — iterations 9 and 10 proved they cannot pass
on the deployed build at all, and that the deployed build fails *sooner* on realistic input than on
the probe's first-cut input.** See the F0 block and the H-diagnosis block below. The operator
decision those iterations waited on **arrived** (prd.md's second amendment), so the certification
path is now gated on Phase H itself: **all three blockers are fixed on the branch** (H3, H1, H2 in
run 20260728-112922 iterations 1, 2 and 3), and E3's physical TCC clicks stay unspent until **H4**
deploys the fixed SHA. Running E3 before that would burn the one irreducible human step against a
deployed service that still carries none of the three fixes.
Test totals on the branch: Swift **139 passed**
(67 → 81 → 92 → 95 → 98 → 106 → 116 → 121 → 131 → 132 → 134 → 139); Python **551 passed / 2 skipped / 368 subtests**
including `tests/test_live_pipeline_seams.py` **13 passed** (new in run 20260728-112922 iteration 1,
+5 in iteration 2, +3 in iteration 3),
`tests/test_macos_uds_tracer.py` **4 passed** (1 hung → 2 → 3 → 4),
`tests/test_macos_packaging_tools.py` **9 passed** (new in iteration 9),
`tests/test_live_manifest_finalizer.py` **17 passed** (new in iteration 12),
`tests/test_live_deployment_credentials.py` **14 passed** (new in iteration 13) and
`tests/test_live_service_deployment.py` **30 passed** (new in iteration 14).

**Phase B client gate: GREEN at `3fb5567` (iteration 10).** Product-tree SHA `3fb5567`; the
checkpoint commit adds only `scripts/ralph-afk/*`, so
`git diff --name-only 3fb5567 HEAD -- ':!scripts/ralph-afk'` is empty. Recorded: both Swift products
build from an empty scratch path in 8.7 s with **zero warnings**; `swift test` **121 passed /
0 failures**; `pytest tests` **466 passed / 2 skipped / 346 subtests** (the two skips are
`tests/test_large_upload.py`'s pre-existing Python-3.10 compatibility contract, not Darwin skips);
the Darwin tracer is **3 passed / 0 skips** *from a deleted lab bundle*, so the whole chain from no
bundle to a paired built app is proven cold; B1/B2/B3/B4 filters 5/10/11/5 passed; attempt-2
discriminator **10/10**; `leak-scan: clean`; and MacStudio is left with no
`~/Library/Application Support/MOSSCapture`, no `/Applications/MOSSCapture.app` and no
`moss-signing.keychain-db`. **Phase C is open.**

**Keeper merge: DONE at `f9285d6` (iteration 16).** Feature tip `f400d426…`, merge
`f9285d69ed7bcc592bb41b3dcdf29e3221968f44`, `main^1 = af3ac366…`, `main^2 = f400d426…`.
`git diff f400d42 f9285d6` is **empty** — main was untouched since the branch point, so every
number measured on the feature tip is also a measurement of the merge commit, and the merge
worktree re-ran the whole suite anyway. **Published in iteration 17 (D1)**: `origin/main` and the
server checkout are both `f9285d6`. From here the feature branch may only carry
`scripts/ralph-afk/*` evidence — **no tracked product source may change on it**. A defect found in
D/E/F needs a new branch and a decision, not a second keeper merge.
*The gate measured at `f400d426` (all on MacStudio, 2026-07-28):* both Swift products from an
**empty** scratch path, `MOSSCaptureApp` 8.0 s and `mtd-capture` 0.9 s, **zero warnings**;
`swift test` **131 passed / 0 failures**; `pytest tests` **536 passed / 2 skipped / 368 subtests**
in 51.9 s; tracer **3 passed / 0 skips**; attempt-2 discriminator **10/10**; `leak-scan: clean`.
*Gotcha found here:* `swift build --product A --product B` silently builds only **B**. The B6 and
C4 gates and `merge-keeper.sh` all use two separate invocations; never collapse them into one.

**G4 client gate: GREEN at `23dc163` (run 20260728-072601 iteration 4).** The amendment's fix cycle
re-measured on MacStudio 2026-07-28, tree clean before and after: both Swift products from an
**empty** scratch path in separate invocations (`mtd-capture` 8.48 s wall / 7.69 s build,
`MOSSCaptureApp` 0.92 s / 0.61 s), **zero warnings**; `swift test` **139 passed / 0 failures**;
`pytest tests` **537 passed / 2 skipped / 368 subtests** in 59.2 s — the two skips printed with
`-rs` are `tests/test_large_upload.py:155,175` "Python 3.10 compatibility contract", the same
pre-existing pair as every prior gate, **not** Darwin skips; tracer alone **4 passed / 0 skips** in
14.7 s; attempt-2 discriminator **10/10**; `leak-scan: clean`.
*The merge payload, reviewed against the amendment's four allowed items:* `git diff --stat main HEAD
-- ':!scripts/ralph-afk'` is exactly eight files, +864/-19 — `Resources/Info.plist` (G1),
`CaptureSecurity.swift` (G2 trim + wire form, G3 classifier), `MOSSCaptureApp/main.swift` and
`CaptureCommandLine.swift` (G3), and four test files (`CaptureControllerTests.swift`,
`MTDCaptureCLITests.swift`, `tests/test_macos_packaging_tools.py`,
`tests/test_macos_uds_tracer.py`). No `ops/`, no server source, no deployment template, nothing
outside the amendment. The only non-product paths in the diff are
`scripts/ralph-afk/{context.md,prd.md,progress.txt}`.

**Second keeper merge — the amendment's ONE authorized merge: DONE at `317df4d` (iteration 5).**
Feature tip `23aabe640cc39d16a996e7d48e4fdf297bf4f51e`, merge
`317df4d728b6765dbe365a3166158ba581299557`, `main^1 = f9285d6…` (the first merge),
`main^2 = 23aabe6…`. `git diff 23aabe6 317df4d` is **empty** and both trees are
`3b37815fd1ba68d83e8f2441f8d4d9a2778446a3`, so the merge commit carries exactly the feature tree.
Against the published `f9285d6` the whole delta is **12 files**: the amendment's eight (four Mac
client sources, four test files) plus `scripts/ralph-afk/{context,prd,progress,merge-keeper}`;
`git diff --name-only f9285d6 317df4d -- ':!macos' ':!scripts/ralph-afk' ':!tests/test_macos_*'` is
**empty**, i.e. the server tree is byte-identical, so publishing this SHA cannot change server
behavior and needs no service restart.
*The suite on the merged tree, measured inside the merge worktree:* `swift test` **139 passed /
0 failures**; `pytest tests` **537 passed / 2 skipped** in 67.3 s; `tests/test_macos_uds_tracer.py`
alone **4 passed / 0 skips** in 16.5 s. Both Swift products built there first, separate invocations.
**Not pushed** — `origin/main` is still `f9285d6`.

**Third keeper merge — the SECOND amendment's ONE authorized merge: DONE at `b817871` (run
20260728-112922 iteration 5).** Feature tip `9e0780a69ef8438fd1ece0e93652b4c461dd68d3`, merge
`b817871414fcc8f609c6f5eb2898ec2957c7768c`, `main^1 = 317df4d…` (the second merge),
`main^2 = 9e0780a…`. `git diff HEAD main` is **empty** and both trees are
`eb26fa9131fbf172125112c7f51e165935739399`, so the merge commit carries exactly the feature tree.
Against the published `317df4d` the whole delta is **21 files**: the H4a-reviewed fifteen (nine
`moss_transcribe_diarize/`, six tests, +917/-106) plus six `scripts/ralph-afk/*`
(`context`, `prd`, `progress`, `merge-keeper`, and the two probes `live-hardcap-repro.py` /
`live-pipeline-probe.py`). `git diff --name-only 317df4d b817871 -- macos ops docs LOCAL_DEPLOYMENT.md
CONTEXT.md` is **empty** — unlike the second merge, this one is *server-only*, so the deployed
service **does** change behavior and the redeploy in step (c) **does** need a
`moss-live-web.service` restart. No Mac rebuild is needed: `macos/` is byte-identical, so the app
installed on m4mbp in G6 is still current at this SHA.
*The suite on the merged tree, measured inside the merge worktree (the script's own gate):* both
Swift products built there first in separate invocations (`mtd-capture` 7.33 s, `MOSSCaptureApp`
0.63 s); `swift test` **139 passed / 0 failures**; `pytest tests` **551 passed / 2 skipped**.
The run completed in ~3 min with no stall — the iteration-5 hang of run `20260728-072601` did not
recur, and it stayed unexplained rather than diagnosed.
**Not pushed** — `origin/main` is still `317df4d`; publishing is H4 step (c).
*The guard is live and was rehearsed non-vacuously after the merge:* the same dry run now prints
`ERROR: main moved from expected pre-merge SHA 317df4d…`, rc=1, so a **fourth** merge is refused.

**H4c redeploy: DONE at `b817871` (run 20260728-112922 iteration 6).** `git push origin main`
fast-forwarded `317df4d..b817871` on the AlphaSight fork; the host checkout fetched and detached at
`b817871` (tree `eb26fa91…`, matching `git rev-parse b817871^{tree}` here, and
`sha256(live_session.py)` `b14eb43dacaa031e…` on both hosts — content parity proven independently of
git); `systemctl --user restart moss-live-web.service` replaced MainPID 336320 with **338545**,
`NRestarts=0`, `ActiveState=active`, and `/live` answered 200 **11 s** after the restart (a single
probe before ~10 s still returns 000 — poll, never one-shot). The batch unit was untouched:
`moss-web.service` MainPID stayed **301112** with `NRestarts=0`.
*Post-restart client checks from MacStudio:* served leaf still hashes to the D2 pin
`a35ca9fc…` (**so every paired Mac is intact**), `https://100.64.0.8:7861/live` 200,
`/api/live/descriptor` 200, `http://192.168.68.38:7860/` 200, `/api/jobs` 200, and plaintext
`http://100.64.0.8:7861/live` still dead (000, curl rc=52).
*Positive proof the deployed code carries the three fixes*, taken with the **service's own venv**
inside the deployed checkout rather than inferred from the SHA: `LiveSession.__init__` has no
`hard_cap_samples` parameter and no `_freeze_hard_cap_spans`, `LiveServiceRuntime.
_require_one_span_cap` exists (H2); `EmptyTranscriptionError` subclasses `RuntimeError` and
`LiveSession.submit_empty_canonical` exists (H1); `WebRtcSpeechProvider(vad=…, frame_samples=5808)`
is refused with `LiveProviderBundleAdmissionError: webrtc frame_samples must be one of [160, 320,
480] …` while 160 constructs and carries `_carried_voiced` (H3). The unit's journal after the
restart is clean: startup complete, no traceback, only the pre-existing onnxruntime GPU-discovery
warning.
*Gotcha for the next reader:* `/api/live/descriptor` reports `source_revision
f9285d69…`. That is a **manifest field** stamped by C2's finalizer at D2 time, not the running
code's revision — it does not move on redeploy and must never be used as the deployed-SHA check.
Use the four-way `git rev-parse` check plus the venv introspection above.

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

**Server meeting-reliability gate: GREEN at `f400d426` (iteration 16).** The PRD clause → node map
the C1 residue asked for, each clause run and passing:
| PRD clause | node |
| --- | --- |
| active-session-only authority | `test_view_authority_follows_the_session_lifecycle_without_an_explicit_release`, `test_view_authority_is_refused_until_a_session_lifecycle_is_bound` |
| virtual 60-minute duration | `test_view_authority_outlasts_the_retired_fifteen_minute_expiry` (0→60 min in 5-min subtests) |
| exact 12 h cap boundary | `test_view_authority_ends_exactly_at_the_absolute_cap_while_capture_continues` (cap−0.5 s ok, cap and cap+1 s refused, capture still authorized at cap+1 h) |
| terminal boundary | `test_clean_stop_immediately_revokes_view_authority`, `test_failed_stop_revokes_the_view_without_stranding_capture_authority` |
| device revoke | `test_device_ownership_revocation_and_session_release` |
| operator revoke | `test_operator_view_revocation_is_loopback_only_and_leaves_capture_running`, `…_and_keeps_capture_streaming` (route) |
| restart | `test_view_authority_does_not_survive_a_restart` |
| 900 s expiry unreachable | proven by absence: the only `VIEW_TTL` string in the tree is `test_…outlasts…`'s `assertFalse(hasattr(live_auth, "VIEW_TTL_SECONDS"))`, and no `900` literal exists in `live_auth.py` or `live_transport.py` |
| 5-second outage | Swift `testOutboxRetainsEveryFrameAcrossAFiveSecondOutageAndDeliversEachExactlyOnce` |
| ambiguous-success retry | Swift `testAmbiguousAnswerAndDuplicateRetryReuseTheOriginalLaneSequenceIdentity` |
| duplicate retry | server `test_v2_http_replays_prior_ack_and_keeps_lane_sequences_distinct` + the Swift node above |
| 429 | server `test_v2_http_maps_lane_capacity_to_429_without_mutating_or_sharing_capacity` + Swift `testTypedRetryPolicySeparatesTransientAnswersFromUnauthorizedOnesAndNeitherLosesAudio` |
| outbox overflow → typed degraded state | Swift `testOutboxOverflowKeepsSequencesGaplessAndReportsATypedDegradedState`, `testOneStalledLaneNeitherBlocksTheOtherLaneNorReattemptsItsWholeBacklog` |
Counts: view-authority slice **10 passed / 22 subtests**, device-revocation node **1 passed**,
server retry/429 pair **2 passed**, Swift reliability filter **5 passed**.

**IDEA-044 attempt-2 checkpoint: GREEN at `1ede498` (iteration 4).** Discriminators **10/10** and **16/16**;
all eleven registered commands plus `validate-phase-a-locality.sh` pass; tracer is 3 passed /
**0 Darwin skips**. That commit is the frozen historical evidence — do not try to reproduce
16/16 on the tip.

**Deliberate post-checkpoint delta (iteration 5, B1).** On the tip the attempt-2 discriminator is
still **10/10**, but `idea-044-real-uds-tracer/repro.py` is **14/16**: checks **09** and **15**
fail by design because they assert `keychain_still_default` and the `MOSS_CAPTURE_SECRET_STORE_PATH`
literal inside each `main.swift`. B1 removed both — the default is now the file store and the
env-key literal lives only in `CaptureSecretStoreSelection`. Their replacement evidence is
behavioral (see below). Never edit those control-plane scripts to recolor this.

**`validate-phase-a-locality.sh` is historical from iteration 6 on.** Its own header says later
production phases widen scope, and its allowlist is the thirteen registered A4 paths. It is
**green at the frozen checkpoint** — `git diff --name-only af3ac366 1ede498` is exactly that
allowlist — and it now fails on the tip on `CaptureController.swift` plus the new
`CaptureOutbox.swift`, `NativeLaneWireFormat.swift`, `CapturePublishPump.swift`, `macos/scripts/*`
and `tests/test_macos_packaging_tools.py`, which Phase B is authorized to add. Verify it against
`1ede498`, never against the tip, and do not add paths to the script.

**Lab bundle contract (new, iteration 4).** The tracer's one fixed path is
`macos/MOSSCapture/.build/idea044-lab/MOSSCapture.app` (gitignored via `macos/MOSSCapture/
.gitignore:1`), held under an exclusive `flock` on `install.lock` for the whole pytest process.
It is installed **once** — copy the built `MOSSCaptureApp`, write the product `Info.plist`
verbatim (identifier `com.alphasight.moss.capture`, both `NSAudioCaptureUsageDescription` and
`NSMicrophoneUsageDescription`), ad-hoc sign — and its identity is recorded in a sibling
`first-install-evidence.json` (`schema: idea044-lab-bundle-evidence.v1`): per-file inventory
hashes, `executable_sha256`, `bundle_sha256`, `designated_requirement`
(`designated => cdhash H"…"`), and the provenance `built_product` `{macho_uuid, sha256}`.
Every later node re-observes the bundle and asserts the recorded evidence *and* that the evidence
file's own inode/mtime/bytes did not move — so a rebuild at the same path is not continuity
proof. A reinstall happens only when the built product's Mach-O UUID or sha256 changes, and it
rewrites the evidence as a new first install. Everything else — certificate, server, port, UDS,
secret store, artifacts — stays per-test temporary. Ad-hoc signing means the cdhash is stable
across runs, so the lab bundle is the only surface on which real TCC continuity could later be
observed; that observation is still the E3 human step. Measured in iteration 10: deleting the whole
`idea044-lab` directory and re-running reproduces `bundle_sha256 990bc18f…`,
`executable_sha256 5b0f5c98…` and `designated => cdhash H"d01b39e2…"` byte for byte, so the identity
is a property of the built inputs, not of the surviving directory.

**Secret-store contract (new, iteration 5).** `CaptureSecretStoreSelection.makeDefault()` is the
only resolver and both composition roots call it with no arguments, so app and CLI cannot drift:
the path is `defaultPath(homeDirectory:)` = `~/Library/Application Support/MOSSCapture/secrets.json`,
overridden only by a non-empty `MOSS_CAPTURE_SECRET_STORE_PATH` (what the tracer uses). The
returned store is always `FileCaptureSecretStore`; `KeychainCaptureSecretStore` is dormant,
unreachable from either product, and no longer carries an access group. Construction is
side-effect free — `mtd-capture` printing usage must not create a directory in the user's home —
so the 0700 directory is materialized on first write. A save writes a fresh `O_EXCL` file at
exactly 0600, `fsync`s it, and `rename(2)`s it over the live path: readers never see a partial
document and the live path never exists wider than 0600. A widened *directory* is tightened on the
next save (it cannot expose a 0600 file); a widened *document* is refused with
`secretStorePathNotPrivate` (its bytes may already have been read). `validateFile` uses `lstat` and
demands a regular file, so a symlink planted at the path is rejected.

**Outbox contract (new, iteration 6).** `CaptureFrameOutbox` (`CaptureOutbox.swift`) sits between
`source.pendingFrames()` and `transport.publish`. It is the authority for **wire identity**: it
stamps the `(lane, sequence)` a frame keeps for every attempt, so the emitter's per-lane counter is
only a source-local production count. Capacity is **15 s of audio per lane**, measured from each
frame's own `sampleCount / sampleRate`, so it survives B3's rate/frame-size change unedited. Audio
is released **only** by `acknowledge(lane:sequence:)` after a 2xx publish; every failure — 429,
5xx, `URLError`, even a fatal 401 — leaves the frame queued. On overflow the outbox **refuses the
new frame** rather than evicting a retained one (evicting would leave a permanent hole in the
lane's sequence stream and the server rejects every later frame as out of order), counts it in
`refusedFrames`, sets sticky `degradation` (`overflowedLaneRetention` / `undeliverableFrame`, never
cleared by later success), and marks the next frame that lane admits `discontinuity = true`.
`reset()` runs on every `start`, because a new server session counts each lane from zero.
The pump flushes in **global admission order** and stalls only the failing lane (one head retry per
lane per tick, no backlog hammering); `CaptureStatus.outbox` and
`ControlChannelResponse.outboxRetainedFrames` / `.outboxDegradation` expose depth and the typed
degraded state. The `moss-live-helper-health.v1` heartbeat wire is untouched.
`CaptureFrameRetryPolicy` is the single classifier: 0/408 → `ambiguous`, 429 → `backpressure`,
5xx → `serverUnavailable`, the transient `URLError` set → `ambiguous`; 4xx, `missingCaptureBearer`,
`missingCertificatePin`, `secureConnectionFailed`, `cancelled` → not retryable.

**Wire-format contract (new, iteration 7).** `NativeLaneWireFormat.swift` holds everything that is
unsafe on a Core Audio callback thread, and `NativeLaneFrameEmitter` is the only caller.
`NativeLaneWireFormat.live` is the domain contract (16000 Hz, 8000 samples); the emitter takes it
plus a `MachHostTimeConverting` and a resampler factory, all defaulted, so the products get the
contract and tests can state a timebase. Per lane, `NativeLaneWireStream` runs: convert host ticks
→ ns; downmix to mono; resample through **one stateful `AVAudioConverter`** (identity short-circuit
when the device is already on the grid); coalesce into exact 8000-sample frames. Timestamps are
**re-derived from every buffer's own converted capture instant** (`pendingStartNS = capturedNS −
duration(pending)`), never accumulated from the frame cadence, so a meeting-length run tracks the
device clock instead of drifting; the cost is ≤ 1 wire sample (62.5 µs) of cadence jitter and a
fixed converter group delay measured at 0.67 ms. A frame is emitted **only** at full size; the
trailing partial leaves through `flush()`, which `NativeDualCaptureSource.stop` calls before
parking the tail for one last `pendingFrames()`, and `CaptureController.stop` now drains once after
stopping the source so that tail actually reaches the wire. An unusable capture instant — zero
ticks, `AVAudioTime` without `isHostTimeValid`, `AudioTimeStamp` without `.hostTimeValid` — makes
the buffer be **refused**, counted (`drainRejectedBufferCounts()` → a `.discontinuity` lane fact),
and the lane's next frame `discontinuity = true`. Never fabricate a timestamp. A device-timeline
gap beyond one wire sample, a `deviceEpoch` change, or a driver-flagged buffer breaks the timeline
the same way. `MachTimebaseHostTimeConverter` divides before multiplying and returns `nil` rather
than wrapping.

**Transport-pump contract (new, iteration 8).** `CapturePublishPump.swift` holds
`CaptureFramePublishPump`, the only thing that calls `transport.publish`. It bounds the transport
two independent ways. *Width*: one pre-created serial `DispatchQueue` per lane, so a lane has at
most one request in flight (its stream must arrive in sequence order) and the lanes run at the same
time; in-flight work is `CaptureLane.allCases.count`, never a function of backlog, meeting length or
tick count. A lane's first failure ends that lane for the pass only — the one-head-retry-per-tick
rule from B2 is unchanged — and the reported failure is chosen in lane order so it is deterministic.
*Time*: passes never overlap. `Contention.skip` (the periodic tick) gives up the turn; `.wait`
(start and stop) takes it after the running pass, because the meeting's final frames reach the wire
only through the stop's pass. Critically, the retained-frame list is read **inside** the pass, never
before it — a waiting caller that snapshotted first would re-send identities the running pass still
had in flight (found by the stop node, not by review). A skipped tick still emits health: a long
recovery drain must not read as a dead helper against the 30 s lease. `CapturePumpContract.interval`
= 0.5 s (was a 0.25 s literal in the app) — exactly one canonical wire frame per lane per tick.
`PinnedURLSessionCaptureHTTPClientProvider` now caches one `URLSessionCaptureHTTPClient` per pin and
`invalidate()`s a superseded one; before this every frame built a fresh ephemeral `URLSession`,
which re-handshook TLS twice a second per lane and leaked a session + pinning delegate per frame for
the whole meeting (a session retains its delegate until invalidated). The app builds **one**
provider and gives it to frames, heartbeat and pairing; `httpMaximumConnectionsPerHost` is lanes + 1.
Cross-lane publish *order* is now undefined by design — the server aligns lanes by capture
timestamp, and only per-lane order is contractual — so tests assert per lane
(`FakeCaptureTransportAdapter.publishedFrames(lane:)`).

**Packaging-tool contract (new, iteration 9).** `macos/scripts/` holds three tracked tools plus
`moss-tool-lib.sh`, which fixes one output discipline: `--dry-run` prints the ordered `plan:` and
the `rollback:` command and mutates nothing; the `rollback:` line is printed **before** the first
mutation; a re-run prints `unchanged:` instead of mutating; `evidence: key=value` lines carry the
observed facts and never a secret.
*`bootstrap-signing-identity.sh`* creates the dedicated `moss-signing.keychain-db` (random password
in a 0600 file), a self-signed `extendedKeyUsage=critical,codeSigning` certificate, imports it with
`-T /usr/bin/codesign`, sets the key partition list, appends the keychain to the user search list
keeping every existing entry, and accepts only if a scratch `codesign` run succeeds. It refuses the
login/System/default keychain outright.
*`build-app.sh`* composes and signs `MOSSCapture.app` plus `mtd-capture` into build output only
(it refuses an install location), derives the signing entitlements from the tracked file with
`keychain-access-groups` dropped, and reads the embedded entitlements, identifier and DR back out of
the signature with `codesign -d` — what was passed in is an input, not evidence. Identical inputs
give an identical bundle digest and DR, and a re-run over the same output re-signs nothing.
*`install-app.sh`* verifies the source signature/identifier/entitlements first, does **nothing** when
the installed bundle is already byte-identical (the inode and therefore the TCC grants survive),
moves a replaced bundle aside to `<installed>.backup-<utc>` instead of deleting it, reports loudly when the
new DR differs from the installed one (that is exactly when the human loses the grants), and
re-verifies the installed bundle's DR against the source.

**Signing mechanics — measured on MacStudio, iteration 9.** `codesign --keychain <kc> --sign <name>`
is accepted and **ignored**: with the identity only in `<kc>` it fails `no identity found`, while
`security find-identity <kc>` lists it as `CSSMERR_TP_NOT_TRUSTED`. The same command succeeds once
the keychain is in the **user keychain search list** (`security list-keychains -d user -s <existing…>
<kc>`) — no trust change, no `add-trusted-cert`, `find-identity -v -p codesigning` still reports 0
valid identities. So search-list membership, not the flag, is what makes an identity reachable, and
D7's DR claim reproduces here: two different binaries signed by that identity both get
`designated => identifier "…" and certificate leaf = H"421b…"`. `security delete-keychain` also
removes the search-list entry, so the recorded rollback is complete.

**View-authority contract (new, iteration 11).** View authority is **derived** from the live
session lifecycle, never mirrored from it. `attach_live_routes` wires
`LiveAccessRegistry.bind_session_lifecycle(_session_status)`, and `_view_for_digest` admits a view
token only when all four hold: the ownership entry exists, it is not operator-revoked, `now` is
below the 12 h absolute cap (`VIEW_ABSOLUTE_CAP_SECONDS`, stamped at `bind_session`), and the
lifecycle reports a status in `VIEWABLE_SESSION_STATUSES` = `{active, closing}`. The allowlist
fails closed: any status added later — and an **unwired** registry — grants nothing, so authority
that is not bound to a lifecycle does not exist. `VIEW_TTL_SECONDS` is deleted, not raised; a
900 s expiry is unreachable because no code carries it.
*The status a viewer must follow is not `session.status`.* A runtime terminal failure (a stop that
fails accounting, a helper lease expiry) refuses every later frame while
`snapshot.session.status` still reads `active`; `_session_status` therefore reports `failed`
whenever `snapshot.terminal_failure is not None`. That is the case the mirror could never cover:
the failed-stop path releases v2/mixer/presence but deliberately **not** the access entry, because
the capture client still has to be able to abort and clean up.
Operator revoke is `revoke_view` + loopback-only `DELETE /api/live/sessions/{id}/view`: it kills
the browser's authority and leaves capture streaming, and it is idempotent (second call → 404).
Sessions are still memory-only in the persisted state file, so a restart revokes every view while
paired devices survive.

**Manifest-bounds contract (new, iteration 12).** The deployed manifest's bounds are **generated**,
never hand-edited: `moss_transcribe_diarize/app/live_manifest_finalizer.py` holds the wire contract
(0.5 s/8000-sample frame, 1 s/16000-sample contract maximum, 0.5 s/8000-sample min silence, 15 s
client outbox → `LIVE_RECONNECT_BURST_SAMPLES` 240000 per lane) and `ops/finalize-live-provider-
manifest.py` is the thin tracked wrapper D2 runs from the deployed checkout (it inserts the repo
root on `sys.path` so the reviewed revision generates the file, not an installed copy). The three
bounds a deployment states are **required flags**, because the plan's latency remedy tunes the span
cap (40000 → 32000 → 24000); everything else is a checked relation, so a wrong flag is refused
rather than deployed: `frame_samples` must equal the client's 8000; `frame_samples ≤
max_frame_samples ≤ 16000`; `endpoint_config.hard_cap_samples` must **equal**
`bounds_config.hard_cap_samples` (the endpoint closes the span and `LiveSession` freezes it — a
divergence silently splits spans); `min_silence_samples` must be the contract 8000; the cap must be
a whole number of wire frames, exceed `min_silence_samples`, and fit `decoder_config.max_samples`;
retention must be a whole number of frames and hold a full reconnect burst **plus one open span**
(240000 + 40000 = 280000 ≤ 960000, i.e. 45 s spare). The 15 s outbox replays
`30 × 2 = 60` frames against the shared 256-entry ack window, so duplicate retries cannot hit
`LiveV2PrunedReplayError`. Hashes are regenerated from the retuned sections and never inherited
(inheriting them is caught at write time by the admission step, not only by tests); admission is
proven with the runtime's own readers (`_endpoint_config`, `_bounds`, `LiveServiceDescriptor`).
Output discipline matches B5: `--dry-run` prints `plan:`/`rollback:`/`evidence:` and writes nothing,
a re-run prints `unchanged:` without touching the inode, a differing file is moved to
`<output>.backup-<utc>` with the `rollback:` line printed before the write, and the provisional
input is never overwritten.
*Measured on the host 2026-07-27*: the staged provisional carries `frame_samples 4000`,
`hard_cap_samples 120000` in both sections, `max_retained_samples 480000`, `max_frame_samples
16000`, `decoder max_samples 120000`, `min_silence_samples 8000`, paddings 1600 — so every value
the finalizer does not set already satisfies the contract and D2 will not be refused. The test
fixture mirrors those exact values.

**WebRTC VAD framing contract (new, run 20260728-112922 iteration 1 / H3).** `WebRtcSpeechProvider`
tiles the **accepted-sample stream**, not each accepted range. The invariant is one sentence:
*webrtcvad is called only with exactly `frame_samples` of real contiguous audio, and never with
anything else.* Three consequences, each a node in `tests/test_live_pipeline_seams.py`.
1. *A tail that cannot fill a VAD frame is carried into the next `observe`, not padded and not
   dropped.* Padding would fabricate input to a detector; dropping would leave audio unexamined.
   The carry is PCM plus one bit (`_carried_voiced`), both per session — `speech_provider_factory()`
   is called once per session at `live_service_runtime.py:442`, so the state cannot leak across
   sessions.
2. *The coordinator still gets gap-free coverage of the accepted range now*
   (`live_coordinator._observe_endpoint` refuses anything else), so a carried tail is reported with
   the **last decided frame's** answer, `confidence=None` and `provider_reason`
   `webrtc_observation_carried` — it says what it is instead of pretending to be a decision. Silence
   is the answer before any frame has been decided. When the frame later completes, the samples that
   complete it get the real decision, so one VAD frame's audio can span two observations with
   different answers; that is a partition, not a contradiction.
3. *An illegal `frame_samples` is refused at construction*, so a manifest that would raise on
   **every** frame is refused at admission instead of at the first frame of a real meeting. Legal
   values are 10/20/30 ms — `{160, 320, 480}` at 16 kHz; the deployed manifest's 160 is unaffected.
The shipped aligned case is unchanged by construction: 8000 = 50 × 160, so the carry is always empty
and the observation stream is byte-identical to the pre-fix one (that control node passes *before and
after* the fix, which is what makes it a control).
*What this does not fix:* the classification seam that turned the bare `webrtcvad.Error` into
`kind=integrity, retryable=false`. That is shared with H1 and belongs to H1's iteration — the
session should not die on any bare provider exception, and now no longer has one to die on here.

**Empty-span decode contract (new, run 20260728-112922 iteration 2 / H1).** *The policy, decided and
recorded as the amendment required: a span the decoder cannot parse is **committed empty**, never
dropped and never terminal.* Dropping was ruled out by the session's own accounting rather than by
taste — `LiveSession.stop` waits for `committed_samples == accepted_samples` and
`live_service_runtime.stop` fails a stop whose accepted and accounted totals differ, and
`accounted_samples` **is** `committed_samples`, so a dropped span strands the session just as surely
as a terminal failure, only at the end of the meeting instead of the start. Committing empty keeps
the committed prefix contiguous, advances the prefix hash, prunes retained PCM, and publishes
nothing false.
Four moving parts, each the smallest thing that makes the rule true:
1. *The condition is typed at the runner.* `vllm_runner._validate_transcription_response` raises
   `EmptyTranscriptionError` (new leaf module `app/transcription_outcome.py`) for all three of its
   "the model produced nothing usable" cases. It subclasses `RuntimeError` and the messages are
   byte-identical, so **every batch caller is unchanged** — a batch job that returns no transcript
   for a submitted file must still fail closed.
2. *The live decode seam translates it.* `RunnerBoundedWavInference.transcribe_pcm` turns that one
   type into `InferenceTranscript(transcript="", generated_tokens=0)` with the measured wall time,
   so an empty span still carries an RTF figure instead of hiding from the gate.
3. *The rule is stated on the transcript, not on an exception type.*
   `live_coordinator._empty_transcript_reason` (replacing `_transcript_text`, which raised) answers
   `decoder_returned_no_transcript` / `decoder_returned_unparseable_transcript` / `None`, so a
   decoder that *returns* garbage without raising gets the same treatment as one that raises — the
   fix is not welded to vLLM. An empty span skips identity work entirely (nothing to relabel, no
   speaker observed) and commits through the new `LiveSession.submit_empty_canonical`, which leaves
   the identity snapshot version untouched. `CoordinatorWorkResult.empty_reason` reaches the
   `canonical_processed` event, so an empty span is visible rather than silent.
4. *A decoder that **failed** is still terminal, and now named.* The same seam wraps every other
   exception from `runner.transcribe` in `LiveProviderError` with the original as `__cause__`.
   That is the classification half H3 deferred: nothing crosses the decode seam unclassified, and
   committing a dead GPU's spans as silence — which a blanket catch would do — would render a whole
   meeting blank instead of saying why.
The portal now skips empty commits when joining rows, so accounted silence does not open blank gaps.
*Measured red/green (offline, MacStudio, no server):* restoring the five product files from `HEAD`
turns the five new nodes red and leaves the five H3 nodes green; the pre-fix failure is the
deployed signature exactly — `LiveServiceFailureRecord(kind=integrity, code='RuntimeError',
message='vLLM transcription returned zero parsed segments for …/span-0000.wav.', retryable=False)`.
The leading-silence span the node builds is `(0, 14400, "leading_silence")`, i.e. F0's
`frozen_until_sample 14400` reproduced from the deployed endpoint config
(`16000 − pre_speech_padding_samples`) rather than asserted.
*What this does not fix:* a **transient** decoder failure (one vLLM timeout, one reset socket) still
ends the meeting. That is honest classification, not a defect fixed here, but it is a real
reliability gap for the 300 s certification — recorded as a candidate, out of the amendment's scope.

**Span-cap authority contract (new, run 20260728-112922 iteration 3 / H2).** *One authority decides
where a span ends: the `EndpointPolicy`. `LiveSession` records the partition it is told and never
draws one.* Of the two readings the diagnosis offered, this is the first; the second (teach the
coordinator to honour `FrameAck.frozen_span_ids`) was rejected because it inverts the design — a
boundary decided by the session would then have to be pushed back into the policy to keep
`_open_start` in step, and the policy's own later span could still land *behind* the session's
cursor and be refused by the same `ValueError`.
Four parts:
1. *`LiveSession` loses `hard_cap_samples` entirely* — the constructor parameter, the attribute and
   `_freeze_hard_cap_spans`. `accept_frame` now freezes nothing and its ack carries
   `frozen_span_ids=()`; the ack the **client** sees is unaffected, because
   `live_service_runtime.accept_frame` has always rebuilt it from `result.frozen_spans` (the
   coordinator's). That rebuild is why the session's own spans were orphaned: frozen, never queued,
   never decoded, and the audio under them never transcribed.
2. *The lockstep invariant is now assertable:* `session.frozen_until_sample ==
   policy.open_start_sample` after every accepted frame. The seam node checks it every frame rather
   than only at the end.
3. *`bounds_config.hard_cap_samples` becomes a declaration rather than a mechanism, and is enforced
   as one.* `LiveServiceRuntime._require_one_span_cap` refuses to open a session unless the endpoint
   policy carries exactly the declared cap. Without it, removing the session's freezer would have
   silently turned a manifest with `bounds` capped and `endpoint` uncapped into a session with **no**
   cap at all, where one span grows until retention backpressures. C2's finalizer enforces the same
   equality at manifest-write time; this enforces it for a manifest that arrived any other way, and
   it caught a real fixture (`tests/test_live_provider_bundle.py`'s manifest declared the cap only in
   `endpoint_config`).
4. *The retired knob is refused, not ignored.* `live_replay.py` raises on a manifest carrying
   `session_hard_cap_samples`, because such a manifest was authored against a session that closed
   its own spans and would replay differently now.
*The only boundary the session still draws is `stop`'s tail flush*, and it cannot collide: it fires
only when `accepted > frozen_until`, i.e. only when nothing else closed the tail. On the runtime path
`stop_endpoint()` has already closed it, so it never fires there at all.
*Measured red/green (offline, MacStudio):* with `live_session.py` and `live_service_runtime.py`
restored from `HEAD` and the seam harness handed the cap the pre-fix session took, the three new
nodes are **red with the deployed signature** — `ValueError: frozen span end must advance.` at
`live_session.py:237`, for continuous speech *and* for opening silence — while the ten H3/H1 nodes
stay green; restored, sha256-verified, 13 pass. `live-hardcap-repro.py --frames 8` flipped
**rc=3 → rc=0**: it now survives 64000 accepted samples with `session_frozen_span_ids == [0] ==
coordinator_queued_span_ids`, so the orphan is closed in the same evidence line as the collision.
*Why no test could have caught it, restated for the next fixture author:* every harness in the repo
gave the policy a cap and the session none, so the deployed shape (both, equal, because C2 requires
it) existed nowhere. The runtime and API harnesses now declare both.

**H4 gate: GREEN at `8b852f2` (run 20260728-112922 iteration 4).** The second amendment's fix cycle
measured on MacStudio 2026-07-28, tree clean before and after; the checkpoint commit adds only
`scripts/ralph-afk/*`, so `git diff --name-only 8b852f2 HEAD -- ':!scripts/ralph-afk'` is empty.
Both Swift products from an **empty** scratch path in separate invocations (`mtd-capture` 9.08 s
wall / 8.08 s build, `MOSSCaptureApp` 0.95 s / 0.62 s), **zero warnings**; `swift test`
**139 passed / 0 failures** (unchanged — Phase H touched no Swift); `pytest tests`
**551 passed / 2 skipped / 368 subtests** in 59.7 s — the two skips printed with `-rs` are
`tests/test_large_upload.py:155,175` "Python 3.10 compatibility contract", the same pre-existing
pair as every prior gate, **not** Darwin skips; tracer alone **4 passed / 0 skips** in 14.7 s;
attempt-2 discriminator **10/10**; `leak-scan: clean`.
*The merge payload, reviewed against the second amendment's scope:* `git diff --stat main HEAD --
':!scripts/ralph-afk'` is exactly **15 files, +917/-106** — nine under `moss_transcribe_diarize/`
(`live_adapters`, `live_coordinator`, `live_portal`, `live_provider_bundle`,
`live_service_runtime`, `live_session`, the new leaf `transcription_outcome`, `vllm_runner`,
`live_replay`) and six test files (the new `tests/test_live_pipeline_seams.py` plus
`test_live_api`, `test_live_identity`, `test_live_provider_bundle`, `test_live_service_runtime`,
`test_live_session`). **No `macos/`, no `ops/`, no deployment template, no doc** — the whole delta
is the three blockers and their tests. The two least obvious entries are in scope by inspection:
`live_portal.py` is H1's six-line skip of empty commits when joining rows, and `live_replay.py` is
H2's refusal of the retired `session_hard_cap_samples` knob.
*Pre-redeploy check the redeploy depends on (read-only, on the host):* the deployed
`live-provider-manifest.json` carries `endpoint_config.hard_cap_samples == bounds_config.
hard_cap_samples == 40000`, so H2's new `_require_one_span_cap` admits it instead of refusing every
session; `speech_provider.frame_samples` is **160** (10 ms at 16 kHz), a legal webrtcvad length, so
H3's construction refusal admits it too; and the manifest carries no `session_hard_cap_samples`
anywhere. Verify all three again after any manifest change — each one now fails the service closed.

**Live-credential tool contract (new, iteration 13).** Two tracked tools share
`ops/moss-ops-lib.sh`, which carries B5's output discipline for the Linux side; the two libraries
are separate files because the primitives differ per host family, and
`test_ops_and_mac_tool_libraries_speak_one_output_vocabulary` compares their emitted lines byte for
byte so the vocabulary cannot drift.
*`generate-live-tls.sh`* mints `live.crt`/`live.key`. Names are **flags**, never constants: at least
one `--dns` and one `--ip`, addresses refused unless inside the networks `live_auth` admits
(IPv4-only, so the tool is narrower than the server, never wider), a name whose final label is
all digits refused as an address in the wrong flag, `--days` ≤ 825. It reads the generated file back
before installing anything — SAN set, `serverAuth`, key/certificate pairing, and the pin both as a
DER digest and as `x509 -fingerprint`, which must agree. **A re-run with the same names prints
`unchanged:` and rotates nothing**; that is a safety property, not tidiness, because the pin is what
every paired Mac stores and what the server embeds in every pairing payload. A name change, a CN
change, expiry inside `--min-remaining-days`, or a half-installed pair is **refused** unless
`--rotate` is passed, and a rotation moves both files aside to `<path>.backup-<utc>` with the
`rollback:` line printed before the first mutation. Key 0600, certificate 0644, directory 0700
created if absent and refused if group/world-writable.
*`live-pair.sh`* mints one payload from `POST /api/live/pairing-codes` and prints it **once** on its
own `payload:` line — no temp file, no log, no argv, no `set -x`; the body never leaves a shell
variable. It refuses any non-loopback or plaintext URL **before** sending anything (the mint route
is loopback-only by design), and it refuses to print the payload when the certificate digest the
*running service* embedded differs from the digest of the certificate file on disk — the
rotated-but-not-restarted case, which would otherwise surface as an unexplained pinning failure on
the Mac. `curl -k` on this hop is deliberate: the connection is to 127.0.0.1 and the certificate is
then verified by exact digest against the operator's own file.
The pin is the coupling: `evidence: pin=` equals `web_cli._certificate_sha256`, equals
`sha256(DER)` computed independently, and equals the leaf a real handshake with the generated pair
offers (measured by starting a TLS listener on it). Exchanging a minted payload needs a non-loopback
TLS peer and is already covered end to end by `tests/test_macos_uds_tracer.py`; D4 does it for real.

**Two-service deployment contract (new, iteration 14).** The live service is a **second systemd
unit**, never a mode of the batch one: `--live` hands the certificate to uvicorn
(`web_cli.py:197-202`), so TLS covers the whole listener and a live profile on 7860 would *replace*
the plaintext batch surface. `moss-web.service` and `moss-live-web.service` run the same
`ops/start-web.sh`; only the environment differs. The live unit loads `ops/moss.env` (optional,
shared vLLM tuning) then `ops/moss-live.env` (**mandatory**, no `-` prefix), so a missing profile
fails the unit instead of starting a second batch server. `ops/moss-live.env.example` is the
tracked template with `REPLACE_WITH_` paths; the filled-in `ops/moss-live.env` is gitignored,
and systemd expands nothing in an EnvironmentFile so every path must be absolute.
`start-web.sh` gained `MOSS_WEB_PORT` and `MOSS_RUNS_DIR`, both **required** under
`MOSS_LIVE_ENABLED=1` and both checked by relation: the port may not be the batch 7860 and the
runs dir may not be `<checkout>/runs`. They use `${VAR-default}`, not `${VAR:-default}`, so a
profile line that sets nothing is a typo to refuse rather than a request for the default. The
batch argv is unchanged — recorded literally in `tests/test_live_service_deployment.py` as the
contract the PRD's "batch service unharmed" clause rests on.
`install-services.sh` now carries B5's output discipline via `moss-ops-lib.sh`: it installs the
tracked units verbatim, prints `unchanged:` per unit that already matches, backs a replaced unit up
to `<unit>.backup-<utc>` with the `rollback:` line printed before the first mutation, and derives
its source from its own location (so it installs the checkout it lives in). `--with-live` is the
only way the live unit is installed, enabled or started, and it is refused before any mutation when
`ops/moss-live.env` is absent. It **never restarts a running service**: a changed unit file is
reported as `evidence: restart_required=<units>` because bouncing the batch service is a
deployment decision, not a side effect. `configure-windows-network.ps1` forwards a table of rows —
the 7860 row unconditional, the 7861 row (its own firewall rule name) added only under
`-IncludeLive`, which is also written into the sign-in scheduled task so a refresh forwards the
same ports. `LOCAL_DEPLOYMENT.md` documents the layout, the C2 finalizer, both C3a tools, and the
rule that the `payload:` line is never redirected to a file; a test asserts every operator-run
`ops/` tool is named in it (tools invoked only from a unit's `ExecStart`, and `*-lib.sh`, are
excluded).

**Latency-probe contract (new, iteration 15).** The Phase F number is measured inside the app,
because that is the only place the capture instants, the polling and the view authority are on one
clock — `LiveServiceEvent` carries no timestamp and the server cannot compare its clock with the
Mac's. `CaptureLatencyProbe.swift` holds three separable pieces. *`CaptureLatencySampler`* is the
arithmetic, with no clock and no network: it takes acknowledged-frame facts, lane states and
`(committed_samples, now)` readings, and produces the report. The mixer origin is **derived, not
assumed**: it is the maximum first capture instant over the lanes the mixer would still wait for
(`failureCode == nil && state != "stopped"`, mirroring the server's `active_lanes` minus failed
lanes at `live_mixer.py:139-169`), it resolves only once *every* such lane has produced audio, and it
then freezes — resolving early on one lane would anchor the whole measurement to the wrong instant.
16000 divides 1e9 exactly, so `committed_end_capture_ns = origin + committed × 62500` is exact and
the mapping adds no error of its own. The first reading is only a **baseline** (it has not been seen
to advance, so it says nothing about arrival time); after that, each advance is measured, and the
plan's four disqualifiers are counted separately rather than averaged away: `rejectedNegative`,
`rejectedClockRegression`, `rejectedAfterTimelineBreak`, and `timelineIntact`. A short frame taints
the timeline **only when the lane produces another frame after it** — the meeting's trailing partial
never gets a successor, so a clean stop is not a break. *`CaptureLatencyProbe`* is the IO half: it
loads server URL / session / view token from the same app-only store the handoff uses, fetches
`snapshot?since_version` then `events?since_seq` serially exactly as the portal does, times both, and
advances both cursors. The token is written to exactly one place — the `Authorization` header — and a
node asserts that by filtering *all* headers for it. Only `seq` is decoded from the events body, so
the transcript never enters the app's memory. `render_bound = 1000 ms + snapshot p95 + events p95`
and `user_visible = committed p95 + render_bound`; both components stay in the report, and the report
is numbers and flags only (no URL, no session id, no token), so it cannot leak by construction.
Percentiles are nearest-rank, so every quoted figure was actually observed.
*Default-off:* nothing polls and no view authority is read until `mtd-capture latency` asks for a
figure; `measure()` schedules only when capture is running and is idempotent; a poll that finds the
session stopped cancels itself; `stop` cancels the probe but leaves the aggregates readable.
`CaptureController` gained one optional `CaptureAcknowledgedFrameObserving` hook that fires **after**
`outbox.acknowledge`, so what the measurement anchors to is audio the server accepted; the hook is
handed lane/timestamp/rate/count/discontinuity — never a `CaptureFrame` — so the measurement path
structurally cannot reach PCM.

**ATS contract (new, run 20260728-072601 iteration 1 / G1).** `Resources/Info.plist` declares
`NSAppTransportSecurity = {NSAllowsArbitraryLoads: true}` and **nothing else** — declaring
`NSAllowsLocalNetworking` or either `NSAllowsArbitraryLoadsIn*` sibling makes the OS ignore
`NSAllowsArbitraryLoads`, which would silently restore the failure. Three shape gates hold it:
`MTDCaptureCLITests.testBundleDeclaresTheTransportExceptionThePinnedClientCannotWorkWithout`
(parses the plist, so the explanatory comment inside it cannot satisfy the assertion),
`test_macos_packaging_tools.py`'s composed-bundle node (what `build-app.sh` actually ships), and
`_first_install_lab_bundle` (refuses to install a lab bundle without it). Mutation-rehearsed: key
removed → 4 nodes fail; `NSAllowsLocalNetworking` added → the 2 exact-shape nodes fail.
*The exemption matrix, measured on MacStudio 2026-07-28 with one ad-hoc `.app`-bundled Swift probe
whose `URLSessionDelegate` accepts the leaf (26.5.1; m4mbp is 26.5.2 and answered identically):*
| destination | bare binary | in `.app` |
| --- | --- | --- |
| remote `100.64.0.8` (tailnet) | 200 | **-1200 / -9802** |
| remote `192.168.68.38` (LAN) | 200 | 200 |
| this host's own `100.64.0.1` | 200 | 200 |
| this host's own `192.168.68.36` | 200 | 200 |
Same bundle + the declaration → `100.64.0.8` answers **200**. So ATS applies only to a bundle, only
to a peer that is neither loopback nor RFC 1918, and it overrides a delegate that already accepted
the leaf.
**The consequence for testing is structural: no single-host test can gate this.** Every server the
tracer starts is on the tracer's host, so however the peer address is *written* the connection is
routed over loopback and exempted — `100.64.0.1` proves it directly. G4's premise (that binding
`100.64.0.0/10` would reproduce it) is therefore wrong, and the supervisor's inference that the
tracer's blind spot was the *address range* is only half of it: remote RFC 1918 is exempt too, so
even a second LAN host would not have caught this. The behavioral confirmation is m4mbp dialling
`https://100.64.0.8:7861` — a real remote tailnet peer — which is E3. Never re-add a node that
looks like an ATS gate but binds a local server; that is the exact shape of the test that let this
ship.
The CGNAT node the loop did build (`test_bundled_app_on_the_production_address_range_still_refuses_
an_unpinned_leaf`) proves the *other* half of the declaration's safety case: with ATS off the whole
trust decision is the pin's, so it pairs once honestly and then serves a leaf the payload's pin does
not describe and requires refusal. Non-vacuity rehearsed both ways.

**Pairing-payload contract (new, run 20260728-072601 iteration 2 / G2).** The payload is typed by a
human — paste, Return, Ctrl-D — so `CapturePairingPayload.init` treats surrounding whitespace as
punctuation of the *input*, not of the payload: it trims `.whitespacesAndNewlines` first, and only
then splits. Two consequences are contractual.
*The error now accuses the right thing.* Whitespace that survives the trim is **inside** a field, so
the guard refuses it as `invalidPairingPayload`; before this a wrapped or space-broken payload
reached the strict 64-hex check and came back as `invalidPinnedHash`, an error that sends the
operator to inspect the server's certificate for their own keystroke. Whitespace-only input is
`missingPairingPayload`, not `invalidPairingPayload`.
*What was parsed is what is sent.* `URLSessionCapturePairingExchangeAdapter.pair` used to validate
the parsed payload and then put the **raw stdin bytes** in the HTTP body
(`String(decoding: pairingPayload, as: UTF8.self)`), so the client validated one string and
transmitted another. It now sends `parsedPayload.wireRepresentation` =
`"mtd1.<secret>.<lowercased pin>"`. That mattered beyond tidiness: the server strips the pin field
(`live_auth._normalize_cert_sha256` → `.strip().lower()`) but not the prefix, so a trailing newline
would have been forgiven on the wire while a leading space would have come back as a 401 the app
reports only as `nonSuccessStatus(401)`. Lowercasing is safe because both sides normalize the pin;
the secret is `secrets.token_urlsafe(32)` (`[A-Za-z0-9_-]`, no dot, no whitespace), so trimming can
never eat a legitimate character. Canonicalization happens at exactly one place — the parse — and
the CLI still ships the raw bytes across the UDS unaltered.
Measured red/green: with the trim removed the tracer's real `mtd-capture pair` with a trailing
newline answers `exit=70 {"ok":false,"error":"invalidPairingPayload"}`; with the trim *and* the
internal-whitespace guard removed the same input reproduces the shipped signature
`invalidPinnedHash`; with the wire form reverted to the raw bytes the body assertion fails showing
`…aaaa\n` on the wire.

**Control-channel failure contract (new, run 20260728-072601 iteration 3 / G3).** A failure the
control channel cannot name now says *which* failure it is. `classifyControlError` replaces
`sanitizedControlError` and returns `(name, detail)`: the four typed families
(`CaptureSecurityError`, `CaptureControllerError`, `CaptureHTTPTransportError`,
`NativeCaptureError`) keep their exact `String(describing:)` names and get **no** detail — their
cases carry only what this process put in them, so the name is already the evidence — while
anything else keeps the bare `control_failed` it always had **plus** a
`ControlChannelErrorDetail`.
*The detail is a domain and integers, and that is the whole safety argument.* It is built from
`error as NSError`, so it needs no per-type list: `URLError`, `POSIXError` and a bare Swift struct
all answer, which is what makes it a backstop rather than another list the next unfamiliar error
falls off the end of. `underlyingCode` is `_kCFStreamErrorCodeKey` when non-zero, else
`NSUnderlyingError.code`, else **absent** — never zeroed, because zero is a code an error can
really have. Nothing else is copied out: a `URLError`'s `userInfo` carries
`NSURLErrorFailingURLStringErrorKey` and a localized message, and the mutation that replaced
`nsError.domain` with `nsError.description` put `https://100.64.0.8:7861/api/live/pairings` and the
whole SSL message on the wire — caught by the node's absence assertions.
*Logging.* `UnixDomainControlServer` takes an optional `ControlChannelFailureLogging` and calls it
**only** for a detail-bearing (i.e. unclassified) failure; `MOSSCaptureApp/main.swift` wires
`OSLogControlChannelFailureLog()` and the CLI has no control server at all. Unified logging is the
only place an `LSUIElement` app can leave a record — no window, and Launch Services gives it no
usable stderr. Read it with
`log show --predicate 'subsystem == "com.alphasight.moss.capture"' --last 30m`.
Everything the line marks `.public` is provably non-secret: the detail is numbers and a constant,
and the command word is reduced to `ControlChannelCommands.all` (the CLI's own vocabulary, now one
constant instead of two literals) or the literal `other`/`unknown`. An unrecognised command never
reaches this path — it throws the named `unknownCommand` — which is exactly why that guard is
structural rather than assumed.
*The signature this makes readable:* the tracer's real-process pin refusal is `control_failed` +
`{domain: NSURLErrorDomain, code: -999}` with **no** `underlyingCode` — -999 is
`NSURLErrorCancelled`, i.e. *this client* refused the leaf — whereas the ATS block G1 fixed is
-1200 with underlying -9802, i.e. the *OS* refused the connection. Same `control_failed` for both;
only the detail tells them apart, and that distinction is what nobody could make in E3.

**Handoff contract (new, iteration 3).** View authority is app-only. `ControlCommandDispatcher`
owns `case "handoff"` and an injected `CapturePortalHandoffAdapter`
(`CaptureSecurity.swift`); `MOSSCaptureApp/main.swift` is the only composition root that builds
`PasteboardCapturePortalHandoff`, so only the app reads `capture-view-token` and writes the
pasteboard (honouring `MOSS_CAPTURE_PASTEBOARD_NAME` in the *app* process). The CLI sends one
`ControlChannelRequest(command: "handoff")` and relays the response verbatim; `handoff` no longer
costs two round trips. The non-secret confirmation rides on `ControlChannelResponse` as
`viewAuthority` ("copied-to-pasteboard"), so `{ok, sessionID, portalURL, viewAuthority}` is the
whole wire answer. Missing authority → typed `portalHandoffUnavailable`; a pasteboard refusal →
typed `pasteboardUnavailable`; neither reaches stdout as anything but a sanitized error name.

**Feasibility — settled, do not re-litigate.**
- Warm 12-run decode p95: 7.5 s span → **0.241 s**; 2.5 s → **0.162 s**. One pre-warm
  2.5 s request took 3.851 s, so certification must warm the resident engine before timing.
  Output already carries `[t][S01]` speaker labels.
- Live decode reuses the **already-resident** vLLM engine (`web_cli.py:87-98`) → **no extra
  VRAM**. GPU free 1328 MiB of 16376 after the probe is not a blocker.
- Latest m4mbp → 4070Ti tailnet probe: ping avg **72 ms**, max **146 ms**. Treat callback cadence
  and tailnet latency as variable; no fixed request-rate assumption is valid.
- Uplink: 48 kHz lanes = 2.05 Mbit/s of base64 JSON; 16 kHz lanes = 0.68 Mbit/s.

**Confirmed defects.**
1. Pairing contract mismatch — client posts `/api/live/pair` expecting `{session_id,
   capture_bearer}`; server exposes only `pairing-codes` → `pairings` → `sessions`
   (`live_transport.py:114-173`) and returns the view token from session create.
   **Closed on the feature branch by the iteration-1 graft** — `URLSessionCapturePairingExchangeAdapter`
   now posts `/pairings` then `/sessions` (`CaptureSecurity.swift:823-890`).
2. No pinning on `main`. **Closed by the iteration-1 graft**:
   `PinnedCertificateURLSessionDelegate` + `FullCertificatePinValidator` +
   `PinnedURLSessionCaptureHTTPClientProvider` (`CaptureHTTPTransport.swift:65-118`); both
   product entrypoints build their HTTP clients from the stored pin.
3. Frame loss on any send failure — `queue.drain()` does `removeAll()`
   (`NativeAudioBuffers.swift:60-64`) and `publishPendingFrames` abandoned the current and all
   remaining drained frames on a throw. **Closed on the feature branch by iteration 6 (B2)**: the
   drained frames go straight into `CaptureFrameOutbox` and only an ack releases them. Two adjacent
   defects found and closed with it: (a) a publish throw inside `start` failed the start while
   leaving `state.running == true` with no pump task — a zombie capture; a retryable failure is now
   a degraded start and an unretryable one unwinds the source and rolls back; (b) a raw `URLError`
   (what a pinned `URLSession` throws on a real outage) typed as `CapturePumpFailure.unexpected`
   instead of `.transportUnavailable`.
4. Viewer expiry — `VIEW_TTL_SECONDS = 900` fixed at `bind_session`, no renewal. Reproduced:
   authorized at t=899, rejected at t=3600. **Closed on the feature branch by iteration 11 (C1)** —
   see the view-authority contract above. The adjacent defect found with it: a runtime terminal
   failure leaves `session.status == "active"`, so a status-only check would have kept the viewer
   alive on a dead session.
5. Unbounded callback-shaped blocking POSTs. **Closed on the feature branch by iterations 7 and 8**:
   B3 fixed emission at two 0.5 s frames per second per lane, and B4 bounded the transport — lanes
   concurrent with one request each, no overlapping pass, one pinned session per pin. A 15 s
   recovery backlog is 30 frames per lane drained on two threads (~2.2 s at the measured 146 ms max
   RTT) instead of 60 sequential round trips, and later ticks skip instead of piling on.
   `URLSessionCaptureHTTPClient.send` still blocks its lane thread on a semaphore; that is now the
   *definition* of one request in flight per lane, not an unbounded cost.
6. Secret store broken — code requested access group `com.alphasight.moss.capture.shared` while
   the entitlement declares `$(AppIdentifierPrefix)com.alphasight.moss.capture`; strings differ and
   a self-signed identity has no Team ID. Keychain writes also fail `-25308` from any non-GUI
   session. **Closed on the feature branch by iteration 5 (B1)**: the file store is the default,
   the Keychain store is dormant with no access group. The residue is **closed by iteration 9
   (B5)**: the tracked `Resources/MOSSCapture.entitlements` still declares `keychain-access-groups`
   with the unresolvable `$(AppIdentifierPrefix)` literal, deliberately, as documentation of intent
   for a future real Team ID — `build-app.sh` derives the *signing* entitlements from it with that
   key dropped and refuses to finish if the key reappears in the signature. Rehearsed: without the
   drop the literal really is embedded verbatim.
7. No client-side 16 kHz conversion — devices stayed at their native rate and the server mixer
   resampled by linear interpolation with no anti-alias filter (`live_mixer.py:305-327`).
   **Closed on the feature branch by iteration 7 (B3)**: both lanes leave the Mac at 16 kHz mono in
   exact 8000-sample frames, so the mixer grid is 1:1 and uplink drops to 0.68 Mbit/s. Measured
   duration conservation: 96×1024 at 48 kHz → exactly 32768 output samples; 129×1024 at 44.1 kHz →
   47926 vs 47925 ideal (one sample of ratio remainder).
8. Wire timestamps were mislabeled — raw `AVAudioTime.hostTime` / `AudioTimeStamp.mHostTime` ticks
   travelled as `capture_timestamp_ns`, collapsing the timeline by the 125/3 timebase.
   **Closed on the feature branch by iteration 7 (B3)** — see the wire-format contract above. The
   drivers still hand raw ticks to the queue on purpose; conversion happens off the callback thread
   and is source-gated by `testRealtimeCallbacksNeitherConvertHostTimeNorResample`.
9. **Undetermined microphone permission hung `start` forever** — **closed by iteration 2**.
   `MicrophoneCapture.start` used to throw only on `.denied` and let `.undetermined` fall through
   to `driver.currentInputDeviceID()`, whose `engine.inputNode` access blocks inside
   `AVAudioEngineImpl::UpdateInputNode` → `_dispatch_sync_f_slow` → `kevent_id` forever, because a
   non-GUI process cannot answer the TCC prompt. Every SwiftPM rebuild is ad-hoc signed with a new
   cdhash, so `.undetermined` is the *normal* state, not an edge case. `start` now requires
   `.granted` before touching the engine, and `NativeLanePermissionCoordinator` runs the explicit
   `AVCaptureDevice.requestAccess(for: .audio)` transition instead.

**Lane admission contract (new, iteration 2).** `NativeDualCaptureSource.start` never waits on a
user decision. Per lane: `.granted` → admit inline; `.denied` → typed lane failure; `.undetermined`
→ one `requestAccess` and lane state `pending`. The source is *running* only if at least one lane
is actually capturing; a pending lane joins the running capture when the answer grants it. When no
lane is capturing, `start` retires the permission generation (so a late grant cannot start capture
behind a failed start) and throws the pending lane's typed `permissionDenied`. System audio has no
preflight or request API, so its user-initiated recording start *is* the request
(`SystemAudioPermission`); it resolves synchronously and never sits pending. `stop` retires the
generation before teardown.

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

**Server state.** Deployed **`317df4d`** since iteration 6 of run 20260728-072601 (G5); it was
`f9285d6` from iteration 17 (D1) until then. **The PRD's "one exact SHA everywhere" clause is GREEN
at `317df4d728b6765dbe365a3166158ba581299557`** — local `main`, `origin/main` (via `ls-remote`), the
server checkout and the m4mbp checkout were all measured at that value in iteration 6. Both host
checkouts are **detached** on purpose: the server's local `main` ref is still `163e969` and m4mbp's
is still upstream `40cf854`, so
`git -C /mnt/d/Coding/MOSS-Transcribe-Diarize checkout 163e969` is a complete one-command rollback
that moves nothing but `HEAD` — **rehearsed for real and undone in iteration 8 (F4a)**, see the
rollback-rehearsal block below. Tree clean; `moss-vllm` MainPID 322117 and `moss-web` MainPID 301112
still `active` with `NRestarts=0` and `ActiveEnterTimestamp` 2026-07-26 22:05:29 / 2026-07-24
21:37:11 — **neither batch service has been restarted** by D1, D2, D3, G5 or F4a, and those four
values are what every later probe must still show.
*Why G5 needed no restart, measured rather than assumed:* the server-visible tree is byte-identical
across the two SHAs (`git diff --name-only f9285d6 317df4d -- ':!macos' ':!scripts/ralph-afk'
':!tests/test_macos_*'` is empty), and the tree objects differ only because the amendment's twelve
Mac/evidence files do (`815f23b0…` → `3b37815f…`).
*Known benign divergence left by G5:* `/api/live/descriptor` still reports
`source_revision f9285d69…`, because that string is baked into the manifest D2 generated and
`provider_manifest_hash 61d97ffe…` covers the file. It names an **ancestor** of the deployed SHA
whose server tree is byte-identical, so it still honestly describes the running code. Re-running the
finalizer to restamp it would rotate a file every paired client hashes, for no behavioral gain — do
not do it as a tidy-up; only as part of a deployment that has another reason to regenerate.
**The live service is up since D3 (iteration 19); its PID changed once, in F4a.**
`moss-live-web.service` is installed (byte-identical to `ops/systemd/`), `enabled`, `active`,
**MainPID 336320 since 2026-07-28 05:06:05** (it was 334346 since 00:50:29 until the iteration-8
rollback rehearsal disabled and re-enabled it), listening on `0.0.0.0:7861` **TLS**; `/live` and `/api/live/descriptor` both return 200 from
MacStudio *and from m4mbp*, and plaintext on 7861 gets nothing (`000`). The served leaf hashes to
the D2 pin on both hosts. `ops/moss-live.env` now exists on the host (untracked, `.gitignore:32`),
`MOSS_LIVE_ENABLED=0` stays in `ops/moss.env` and is overridden only by that profile.
`/mnt/d/Coding/MOSS-Transcribe-Diarize/live-runs` was created by the service.
`/api/live/descriptor` and `/live` are still 404 on 7860.

**`live-auth.json` now holds five devices, four of them inert (updated iteration 10).** The F0 probe
paired and revoked three `ralph-f0-probe-*` devices and iteration 10 added and revoked one
`ralph-h2-probe-20260728T094218Z`; only
`AB600574-FD93-4321-967E-652AB064A70B` (m4mbp, from the 03:10 attended pairing) is `revoked: false`.
Device *count* is therefore no longer a useful signal for D4 — check that entry's `paired_at`, or the
count of **unrevoked** devices. Baseline pre-copy: `live-auth.json.ralph-f0-backup-20260728T091927Z`,
sha256 `9d306766…`.

**A device is ALREADY paired — corrected in iteration 6, and it changes the E3/G6 premise.**
Context claimed until now that `live/live-auth.json` was absent and that D4 would create it. It is
**present**, 0600 on ext4, `{schema_version: 1, devices: 1}`, mtime **2026-07-28 03:10:15** — one
second after m4mbp's `~/Library/Application Support/MOSSCapture/secrets.json` (0600 in a 0700
directory, 469 bytes, 03:10:14). Both were written during the operator-attended diagnosis, by the
*unsigned* `.build/debug/MOSSCaptureApp`, which ATS does not restrict; the supervisor entry recorded
it ("one device pairing persisted to the Mac secret store by the unsigned build") but the two state
blocks were never corrected. The live journal since 02:00 agrees and is the independent witness:
**5** `POST /api/live/pairing-codes`, **2** `POST /api/live/pairings`, **2** `POST
/api/live/sessions`, 13 `GET /api/live/descriptor` — and **zero** frame posts, so no session has
ever received audio. (That journal is a uvicorn access log: paths only, no bodies, no token.)
*Four consequences, all measured or read out of the source this iteration:*
1. ~~**The two 03:10 sessions are still in memory.**~~ **Gone since iteration 8 (F4a).** The
   rollback rehearsal stopped and restarted the live service (MainPID 334346 → **336320**), and
   sessions are memory-only, so both died with the old process. `live-auth.json` came through the
   cycle with the **same inode (11374) and the same sha256 (`9d306766…`)**, so the *device* pairing
   is untouched — the durable/ephemeral split the view-authority contract asserts, now observed on
   the real host.
2. **They did not block anything, and their absence does not either.**
   `LiveServiceRuntime.create` (`live_service_runtime.py:430`) just
   inserts into `self._sessions`; there is no single-session refusal, so E3 can create a fresh
   session whether or not an old one is resident.
3. **m4mbp is no longer "unpaired", so `start` no longer fails closed** — and since F4a the session
   its store names is one the *server* has forgotten, so a bare `start` there now raises both TCC
   prompts and then fails on the wire instead of publishing anywhere. Either way the instruction is
   the same and now doubly so: **pair first**. The store holds
   `capture-bearer` (43), `capture-certificate-pin` (64), `capture-device-id` (36),
   `capture-server-url` (23 = `https://100.64.0.8:7861`), `capture-session-id` (32),
   `capture-view-token` (43) and `local-control-secret` (44). The supervisor entry's finding — that
   `captureConfiguration(from:)` throws `missingCaptureConfiguration` before
   `CaptureController.start` — was measured against an *empty* store and is now inapplicable on this
   host: a bare `start` resolves. Do not let an E3 run drift into that: pair first, so the fresh
   `pairings` → `sessions` exchange overwrites the session id and bearer, and the canary measures a
   session this app created.
4. **The paired device is why D4 is cheap now.** Device pairings persist; only the payload mint and
   the session are per-run. Nothing needs un-pairing, and `live-auth.json` existing is no longer the
   marker that D4 has run.
Windows: portproxy now carries `0.0.0.0:7861 → 172.30.115.123:7861` beside the untouched 7860 and
5100 rows, firewall rule `MOSS-Transcribe-Diarize-Live` (Inbound/Allow/**Private** only) beside
`…-Web`, and the sign-in scheduled task argument list now ends `-RefreshOnly -IncludeLive`.
`webrtcvad-wheels 2.0.14` and
`onnxruntime 1.23.2` installed with metadata; WeSpeaker ONNX staged and hash-verified.
*`~/.local/share/moss-transcribe-diarize/live/` after D2 (iteration 18):*
`live-provider-manifest.json` (0644, generated), `live-provider-manifest.provisional.json` (0600,
untouched, inode 665548), `live.crt` (0644) / `live.key` (0600) carrying all four SANs,
`live.crt.backup-20260728T044132Z` / `live.key.backup-20260728T044132Z` (the pre-rotation pair,
which is the recorded rollback), and `golden.wav`.
**The live pin is now `a35ca9fc4a0f5b32bf7da6dc2e03c1fa5b4ac60992f0ee49b6d5677d22b680ff`**
(was `2c88836b…`); that is the value D4's pairing payload carries and every Mac stores.
*The running batch process is still the `163e969` image* — `INDEX_HTML`/`FAVICON_SVG` are
module-level constants (`server.py:123-129`), so a checkout cannot change what an already-running
uvicorn serves. "Batch unharmed" therefore needs the *restart* proven separately, and iteration 17
did that without restarting anything: the deployed `ops/start-web.sh` sourced with the host's real
`ops/moss.env` derives exactly the recorded contract argv (`tests/test_live_service_deployment.py:
52-62`), port 7860, runs dir `<checkout>/runs`, **no live flag**. Re-run after D3 with the live
profile also sourced: the batch argv is byte-identical and the live argv is the complete
`--live …` form, so the two profiles really are one adapter.

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

**Mac state.** macOS 26.5.2, Xcode 26.5, Swift 6.3.3 (`swift-driver 1.148.6`).
**`/Applications/MOSSCapture.app` and `~/.local/bin/mtd-capture` exist since iteration 22 (E2b)** —
see the installed-app block below.
**`~/Library/Application Support/MOSSCapture/secrets.json` now exists** (corrected in iteration 6;
context previously claimed it was absent) — 0600 in a 0700 directory, written 2026-07-28 03:10:14 by
the *unsigned* debug build during the attended diagnosis. B1's mode contract therefore holds on the
real host, not only in tests. See the "A device is ALREADY paired" block above for its seven keys
and for why a bare `start` no longer fails closed here.
**The installed bundle carries G1+G2+G3 since iteration 7 of run 20260728-072601 (G6).** The
before/after pair that proves it, both measured on the real installed product:
`plutil -extract NSAppTransportSecurity xml1 -o - /Applications/MOSSCapture.app/Contents/Info.plist`
answered `No value at that key path` before and now prints exactly `NSAllowsArbitraryLoads` / `true`
and nothing else — the G1 shape, on the product. `CDHash 026836783c25f27e93c128214f717289864a680c`
→ **`2b51082c44a0e882f78a4b22d9e22e0a50bb6981`**, equal to the freshly built product's own CDHash;
CLI `f9d9e849…` → **`42c3593628f16ef81a778e039969e2a3ac73a74e`** (sha256 `08ba13fd…` →
`a901b4b3…`). The **designated requirement did not move** —
`identifier "com.alphasight.moss.capture" and certificate leaf = H"e118d874…"` — and
`codesign --verify -R=<that requirement>` now passes for bundle and CLI while a wrong-leaf variant is
refused, so DR satisfaction is proven positively and negatively rather than by string comparison.
*Note the `-R` syntax:* pass the requirement **without** the `designated => ` prefix `codesign -d -r-`
prints, or it fails `unexpected token: designated` and looks like a broken signature.
**The pre-G6 product is preserved, so the rollback is real rather than described:**
`/Applications/MOSSCapture.app.backup-20260728T085551Z` still verifies and still carries
`CDHash=026836…` with **no** `NSAppTransportSecurity` key, and
`/Users/ga0/.local/bin/mtd-capture.backup-20260728T085551Z` is still sha256 `08ba13fd…`.
SwiftPM is not byte-reproducible here, so those backups are the only route to those exact bytes.
**`moss-signing.keychain-db` exists since iteration 21 (E1)** — see the signing-identity block
below. Checkout is
`/Users/ga0/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize` (same relative path as
MacStudio), reachable as `ga0@m4mbp` with `BatchMode=yes`.
**Since iteration 6 of run 20260728-072601 (G5) it is detached at `317df4d`** — tree `3b37815f…`,
clean, 159 tracked files; it was `f9285d6`/`815f23b0…` from iteration 20 (E2a) until then. The four
G1/G2/G3 client sources plus `build-app.sh`/`install-app.sh` were re-verified by independent
`shasum -a 256` against MacStudio's blobs at `317df4d` — all six identical — and the reviewed
`macos/scripts/*` + `ops/*` tools are present with their exec bits intact
(the two `*-lib.sh` libraries are non-executable by design). Its `main` ref is deliberately
**untouched** at upstream `40cf854` still tracking `origin` = **OpenMOSS upstream**, and the fork
was added as a *second* remote `alphasight`; the complete rollback is therefore one
`git -C <checkout> checkout main` (rehearsed in iteration 20: it restores `40cf854`, branch `main`,
tree `ac0058f9…`, clean, `macos/scripts` gone), optionally followed by
`git remote remove alphasight`. The fork is fetchable from m4mbp **anonymously** —
`GIT_TERMINAL_PROMPT=0 git ls-remote` succeeds — so no credential lives on that host.
`.gitattributes` declares LFS filters for `*.bin/*.safetensors/*.pt/*.pth` but the reviewed tree
contains **zero** such files and neither host has `git-lfs`, so LFS is not in the picture.
Login keychain is **locked to SSH sessions** — `LiveTranscribe Local Dev` signing fails
`errSecInternalComponent`. A scripted self-signed identity in a dedicated keychain **does** sign
over SSH with a designated requirement that is byte-identical across rebuilds (plan D7).
`security find-identity -v -p codesigning` reports 0 valid identities for such a cert even though
`codesign` succeeds — never gate on `find-identity`. The exact mechanics are in the signing-mechanics
note above; `macos/scripts/bootstrap-signing-identity.sh` (iteration 9) implements them.

**Signing-identity state on m4mbp (new, iteration 21 / E1).** The dedicated keychain
`~/Library/Keychains/moss-signing.keychain-db` (0644) holds the self-signed identity
`MOSS Capture Local Signing` — RSA 2048 / sha256WithRSA, `CA:FALSE` critical, keyUsage critical
`digitalSignature`, EKU critical `codeSigning`, valid 2026-07-28 → 2036-07-25. Its password is a
random 32-byte base64 string in `~/.config/moss-capture/signing-keychain.password` (0600, in a 0700
directory). The keychain is the **fourth** entry of the user search list, after the three
pre-existing ones (`projectclerk-signing`, `login`, `openvpn`) — all preserved; the default keychain
is still `login.keychain-db`.
**The values E2b/E3 depend on:** `leaf_sha256
ef8fa54299d5774057287cf577f51d9a9a8410b4524ad67ce69b00b41021d4f2`, leaf SHA-1
`e118d874377746c4bd25beb8252bb84302b73e72`, and the designated requirement
`designated => identifier "com.alphasight.moss.capture" and certificate leaf =
H"e118d874377746c4bd25beb8252bb84302b73e72"`. Measured: that DR is byte-identical for two different
binaries and after re-signing changed bytes at the same path, while their `CDHash` values differ —
which is the PRD's "DR unchanged across a rebuild" property at the identity level (the app-bundle
level belongs to E2b). Contrast measured in the same session: ad-hoc signing gives
`designated => cdhash H"…" or cdhash H"…"`, different per binary.
*Three operational facts that decide later steps:*
1. **The identity is not reproducible.** The rollback was rehearsed for real and re-applied, and the
   fresh run minted a **new** key: leaf `8c99754e…` → `ef8fa542…`. Unlike the lab bundle, identity
   here is a property of a stored private key, not of the inputs. So after E2b installs and E3
   grants TCC, running `security delete-keychain` costs the human's grants. Rollback of E1 is free
   **only until E2b signs the installed bundle**.
2. **A fresh SSH session finds the keychain locked** — `security show-keychain-info` answers
   `User interaction is not allowed` and `codesign --sign` fails `errSecInternalComponent`, despite
   `set-keychain-settings` having disabled the auto-lock timeout; the unlock state is per security
   session. Not a defect: `build-app.sh:186-191` unlocks unconditionally from the password file
   before signing, and the bootstrap tool's own probe unlocks first. Any *ad-hoc* `codesign` run
   from a new SSH session must unlock first or it will look like a broken identity.
3. **No trust was added and none is needed.** `security find-identity -v -p codesigning` still lists
   only the pre-existing `LiveTranscribe Local Dev`, and the MOSS certificate appears in neither the
   user nor the admin trust-settings domain (the three certs that do carry user trust settings —
   `LiveTranscribe Local Dev`, `Ga0-Alienware-RTX4070Ti`, `Ga0-RTX4090` — are pre-existing and
   unrelated). Search-list membership alone makes the identity reachable, reproducing the
   iteration-9 MacStudio finding on m4mbp.

**Installed-app state on m4mbp (new, iteration 22 / E2b).** `/Applications/MOSSCapture.app`
(`drwxr-xr-x ga0:staff`, three files: `Contents/MacOS/MOSSCaptureApp`, `Contents/Info.plist`,
`Contents/_CodeSignature/CodeResources`) and `~/.local/bin/mtd-capture` (0755) are installed from
`macos/MOSSCapture/.build/product`, release configuration, signed by the E1 identity. Both verify
`codesign --verify --strict`; the bundle also "satisfies its Designated Requirement".
**The PRD's "Signed app installed" clause is GREEN**: the app exists, `codesign -dv` reports
`Identifier=com.alphasight.moss.capture`, and the DR is
`designated => identifier "com.alphasight.moss.capture" and certificate leaf =
H"e118d874377746c4bd25beb8252bb84302b73e72"` — that `H"…"` equals `shasum -a 1` of the E1
certificate's DER read independently out of the keychain. The CLI is a *separate* identifier,
`com.alphasight.moss.capture.cli`, signed by the same leaf. Embedded entitlements are exactly
`{com.apple.security.device.audio-input: true}`: `keychain-access-groups` is **absent** from the
signature while the tracked entitlements file still declares it, so B5's drop really fires on this
host. `TeamIdentifier=not set`, `flags=0x10000(runtime)`. Info.plist carries both usage strings.
*Three facts that decide E3 and any later rebuild:*
1. **SwiftPM release builds are not byte-reproducible on this host, but the DR is.** Two
   from-scratch builds of the identical checkout gave different `built_app_sha256`
   (`5bf01255…` → `ad83c0f8…` → build #3) and different `bundle_digest`, while the DR came out
   byte-identical every time. That is the PRD's "unchanged across a rebuild" property proven against
   a genuinely different binary rather than a tautology — and it is why the grants survive a rebuild:
   they key on the DR, not on the bytes. Corollary: `install-app.sh`'s byte-identical shortcut
   (which preserves the inode) will **not** fire after a rebuild, so a rebuild always takes the
   replacement path. That is fine, and it was rehearsed for real — see below.
2. **The replacement path is safe and was measured, not assumed.** Installing a rebuilt bundle over
   the installed one moved the previous install to `/Applications/MOSSCapture.app.backup-<utc>`
   (which still verifies and still carries the old CDHash), printed its `rollback:` line **before**
   the first mutation, and did **not** print the "designated requirement changes on install" warning
   — correctly, because only the bytes changed. Applying that printed rollback verbatim restored the
   previous bundle's exact CDHash. The same run also backs the **CLI** up to
   `<bin>/mtd-capture.backup-<utc>`; that file is not cleaned up by the tool, so a rebuild-install
   leaves one behind.
3. **`bin_dir_on_path=false` in the tool's evidence is an SSH artifact, not a defect.**
   `~/.local/bin` is absent from the non-interactive SSH `PATH`, which is what the tool observes, but
   `.zshrc` puts it on the human's interactive `PATH` — `zsh -lic 'command -v mtd-capture'` resolves
   to `/Users/ga0/.local/bin/mtd-capture`. So the default `--bin-dir` is right and **no shell profile
   was edited**; the loop just has to invoke the CLI by absolute path over SSH.
The installed CLI runs: `--help` prints the one-line usage (`rc=64`) and `status` answers
`{"ok":false}` (`rc=70`) with no helper running, emitting no path, token or secret. Neither call
created `~/Library/Application Support/MOSSCapture`, so B1's side-effect-free construction holds for
the *installed* binary too.

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
the whole 300 s available for pairing alone. **Derived from source, not yet observed** — E3 is what
confirms it; if the unpaired `start` behaves differently, fall back to the coupled sequence.

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

**F0 live-pipeline probe — the deployed pipeline dies in ~3 s (new, iteration 9). READ THIS BEFORE
PLANNING ANY PHASE-F WORK.** `scripts/ralph-afk/live-pipeline-probe.py` drives the deployed live
service through the whole path E3's canary needs, from MacStudio over the real pinned tailnet TLS
hop, with real two-speaker `say` audio and **no Mac and no TCC grant**. It is a Ralph evidence tool,
not product source. Three runs, each with a fresh single-use payload and a fresh device.

*Proven working on the real host for the first time:* remote pairing exchange (`scope=capture`,
43-char device token) and session create over a leaf pin the probe enforces itself (`CERT_NONE`, no
hostname check, DER sha256 == `a35ca9fc…`, **1 TLS handshake per run**); the running service admits
the C2 manifest (`sample_rate 16000`, `frame_samples 8000`,
`provider_manifest_hash 61d97ffe…` straight off `POST /sessions`); v2 lane ingress with the canonical
wire format on both lanes; the endpointer freezing spans and writing `/tmp/mtd-live-<rand>/span-*.wav`
for decode; C1 view authority (200 while viewable, **401** the instant the session leaves
`VIEWABLE_SESSION_STATUSES`, 401 after stop); and `DELETE /api/live/devices/{id}` releasing the
sessions it owns. **No raw audio is persisted** — after three runs `live-runs/` has 0 entries and
`/tmp/mtd-live-*` is gone. Timings: publish p95 **209-279 ms**, snapshot p95 **73-105 ms**, events
p95 **22-175 ms**, i.e. a ~1280 ms render bound leaving ~2.7 s of the 4 s canary budget. Committed
latency is **unmeasurable** here because nothing ever commits.

*Blocker 1 — a span with no speech makes the session terminal.* With 1.0 s of leading silence the
session went terminal on **span-0000**:
`vLLM transcription returned zero parsed segments for /tmp/mtd-live-…/span-0000.wav`,
`{kind: integrity, code: RuntimeError, retryable: false}`. Frames 409 thereafter, snapshot/events
401, `stop` 409. The span held no speech and that is measured, not inferred:
`frozen_until_sample 14400` (0.9 s) versus a first utterance at sample 16000 (1.0 s).
*Root path:* `vllm_runner.py:245` `_validate_transcription_response` raises a **bare `RuntimeError`**
when `parse_transcript(text)` is empty; it escapes before `live_adapters._validated_segments`
(`live_adapters.py:360-364`), which has a *typed* `LiveProviderError` for the identical condition,
can classify it. Unclassified → `integrity` → non-retryable → terminal. Every real meeting opens with
silence and contains silence between turns, so this ends the meeting almost immediately.
**Fixed on the branch by H1** (run 20260728-112922 iteration 2) — see the empty-span decode contract.
*One correction to the sentence above, found while fixing it:* `_validated_segments` is on
`LiveProvider.decode_canonical`, which the **runtime never builds** — the live decoder is
`RunnerBoundedWavInference` under `LiveCoordinator`, so the typed error it was "escaping before" was
never on the live path at all. The seam that needed the classification is the adapter, and that is
where it now lives.

*Blocker 2 — the endpointer can ask to freeze a non-advancing span.* With `--lead-seconds 0` the
session survived one tick longer (11 frames, `accepted_samples` 32000) and then answered **400
`frozen span end must advance.`** — `live_session.py:237`, `freeze_until` refusing
`end_sample <= self._frozen_until_sample`. Both call sites are the coordinator
(`live_coordinator.py:128` accept path, `:231` `_freeze_and_queue` used by `flush_endpoint`).
~~*Caveat a fix must resolve first:* the probe's two lanes carry identical `capture_timestamp_ns`.~~
**Spent in iteration 10 — the caveat was real and it was hiding a third, earlier blocker.** The
mechanism of blocker 2 is now named and reproduced offline, and lane timestamps have nothing to do
with it. See the H-diagnosis block below.

*Why every gate stayed green.* No test puts the **real** VAD endpointer and a **real** decoder in one
process: `tests/test_live_vad.py` drives the endpointer with a stub provider — it even asserts the
typed `LiveProviderError` the real path never reaches — and every decoder node is stubbed because
MacStudio has no GPU. The seam where they meet has only ever run on the deployed host, and both
blockers live in that seam. Do not "fix" this by loosening a gate; the missing thing is a node that
drives the coordinator through the real `vllm_runner` validation with an empty transcript.

*Probe usage (mint on the host, payload never on argv, never in a file):*
```bash
DEVICE_ID="ralph-f0-probe-$(date -u +%Y%m%dT%H%M%SZ)"
MINT='set -euo pipefail
cd /mnt/d/Coding/MOSS-Transcribe-Diarize
L="$HOME/.local/share/moss-transcribe-diarize/live"
out="$(ops/live-pair.sh --url https://127.0.0.1:7861 --cert "$L/live.crt")"
printf "%s" "$out" | sed -n "s/^payload: //p"'
PAYLOAD="$(printf '%s\n' "$MINT" | ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local \
  "wsl.exe -d Ubuntu -- bash -s" 2>/dev/null)"
printf '%s' "$PAYLOAD" | python3 scripts/ralph-afk/live-pipeline-probe.py \
  --host 100.64.0.8 --port 7861 --pin a35ca9fc4a0f5b32bf7da6dc2e03c1fa5b4ac60992f0ee49b6d5677d22b680ff \
  --device-id "$DEVICE_ID" --seconds 20 --lead-seconds 1.0 --report /tmp/moss-f0.json
```
Add `--lane-offset-ms system=137` (iteration 10) to break the degenerate shared-lane-origin input;
that is the flag that surfaces blocker 3, and any future run that wants to reach the endpointer at
all must **omit** it until blocker 3 is fixed.
`--fail-fast` is the default and must stay so: a terminal failure is sticky, so continuing only
buries the one response that explains it (the first run published for **7 minutes** past a dead
session and learned strictly less than the 2-second run that replaced it). Post-terminal 409s take
**6-8 s each** — unexplained, bounded to already-dead sessions, but it means a Mac outbox will back
up hard behind one.
**Mandatory rollback after every run**, on the host, loopback-only:
`curl -sk -X DELETE https://127.0.0.1:7861/api/live/devices/<device-id>`. It returns and releases the
sessions the device owns and needs no restart. It *marks* revoked rather than deleting, so
`live-auth.json` only grows; the three inert entries from iteration 9 are
`ralph-f0-probe-20260728T{091938,092856,093052}Z`. The m4mbp device
`AB600574-FD93-4321-967E-652AB064A70B` is untouched (`revoked: false`) and is the only one that
matters. A pre-copy of the baseline file is
`live-auth.json.ralph-f0-backup-20260728T091927Z` (sha256 `9d306766…`); restoring it costs a service
restart, so it is the deeper rollback, not the default.

**H-diagnosis — the three server blockers, all reproduced, two of them offline (new, iteration 10).
READ THIS WITH THE F0 BLOCK; it supersedes F0's open caveat.** Iteration 10 answered the one
question F0 left open (do the probe's identical lane timestamps explain blocker 2?) and the answer
changed the picture: **no, and relaxing that input exposes a third blocker that fires four times
sooner.** Two tools carry the evidence, both Ralph-only: `scripts/ralph-afk/live-hardcap-repro.py`
(new — offline, no server, no GPU, no network, ~0.4 s per case) and the existing
`live-pipeline-probe.py`, which gained `--lane-offset-ms LANE=MS`.

*The caveat is structurally irrelevant to blockers 2 and 3, and the repro prints the reason rather
than arguing it:* `live_session.AudioFrame` — the frame the mixer hands the coordinator — has fields
`sequence, pcm, sample_count, sample_rate` and **no timestamp field at all**. Lane capture
timestamps stop at the mixer. They decide *how many* mixed samples exist and *when*, never what the
coordinator does with them.

*Blocker 2 is a collision between two independent hard-cap freezers, and it is deterministic.*
`LiveSession.accept_frame` calls `self._freeze_hard_cap_spans()` **itself** (`live_session.py:198`,
`:353-359`) whenever `accepted - frozen_until >= hard_cap_samples`. The coordinator calls that same
`session.accept_frame` **first** (`live_coordinator.py:122`), *then* runs the endpoint policy, which
emits its own `hard_cap` span at the identical sample, and `freeze_until` refuses it because the
session already moved `_frozen_until_sample` there. So the session dies at the first stretch of
`hard_cap_samples` (40000 = **2.5 s**) of accepted audio that contains no endpoint — i.e. 2.5 s of
continuous speech, or 2.5 s of opening silence. Measured, deployed config, `--frames 8`:
continuous speech → `ValueError: frozen span end must advance.` at `accepted_samples=40000`;
pure silence → the same at the same sample; frame size 1000 instead of 8000 → the same at the same
sample (so it is not a frame-size artifact); a speech/silence pattern that endpoints every ≤ 2.5 s →
**survives**, because each endpoint span moves both cursors together. *Second defect visible in the
same output:* the span the session freezes by itself is never queued for decode —
`FrameAck.frozen_span_ids` is dropped on the floor by the coordinator and by
`live_service_runtime.py:477`, which reports only `result.frozen_spans`. So even without the
collision that audio would never be transcribed.
*Why no test could see it:* **every** harness in the repo gave the endpoint policy a hard cap and
the session none — `tests/test_live_coordinator.py:101` (`LiveSession(max_retained_samples=8000)`,
policy cap 4000), `tests/test_live_service_runtime.py:155,165` (`endpoint_config` 4000,
`bounds.hard_cap_samples=None`), `tests/test_live_api.py:209` (same shape, bounds default `None`).
`tests/test_live_session.py` exercised the session's cap in isolation, with no coordinator and no
policy. The two freezers therefore never coexisted anywhere except production — and C2
(iteration 12) *requires* them to be equal in a deployed manifest, so C2 is what guaranteed the
collision on the real host. **Fixed in iteration 3** — see the span-cap authority contract block;
the runtime and API harnesses now declare both caps, and the session has none to declare.

*Blocker 3 — an unaligned lane timestamp makes the mixed frame an illegal VAD frame, and the session
dies in ~1.1 s.* One probe run against the deployed service with `--lane-offset-ms system=137
--lead-seconds 0`: tick 0 both lanes 200, tick 1 system 200, tick 1 **microphone 500 Internal Server
Error**, `terminal_failure {kind: integrity, code: Error, message: "Error while processing frame",
retryable: false}`, `accepted_samples` **5808** — which is exactly 500 ms − 137 ms of audio. The host
traceback names it: `live_transport.py:221` → `live_mixer.py:112` → `live_service_runtime.py:465` →
`live_coordinator.py:122` → `live_provider_bundle.py:424` → `:643` →
**`webrtcvad.Error: Error while processing frame`**.
*Mechanism.* `LiveMixer._stage` sets `origin_ns = max(first capture_timestamp_ns over active lanes)`
and (non-final) `safe_end_ns = min(last sealed interval end)`, then
`sample_count = floor((safe_end − cursor) × 16000 / 1e9)` — an **arbitrary** integer once the lanes
are not aligned to each other on the frame grid. `WebRtcSpeechProvider.observe`
(`live_provider_bundle.py:417-434`) then chops that frame into `frame_samples` pieces with
`piece_samples = min(frame_samples, end − cursor)`, so the **trailing piece is short**; the deployed
`speech_provider` is `{kind: webrtc, frame_samples: 160, mode: 1}` and webrtcvad accepts only 10/20/30
ms (160/320/480 samples at 16 kHz). 5808 = 36×160 + **48** → raise. The exception is a bare
`webrtcvad.Error`, so — exactly like blocker 1 — it escapes typed classification, lands as
`kind=integrity, retryable=false`, and the session is terminal. Reproduced offline with the real
`WebRtcSpeechProvider` and a stand-in VAD that enforces only webrtcvad's documented length contract:
`--speech-provider webrtc --frame-samples 5808` → refused at the first frame with `got 48`; the
control `--frame-samples 8000` (8000 = 50×160) survives. **This is the normal case, not an edge
case:** two real capture devices never start on the same instant, so the Mac will produce unaligned
lanes on essentially every run. F0 could not find it because a single shared origin makes every mixed
frame exactly 8000 samples.
*Severity ordering for the fix cycle:* blocker 3 (≈1.1 s, any unaligned lanes) → blocker 1 (≈3 s, any
unparseable span) → blocker 2 (2.5 s, any endpoint-free stretch). All three are one-line-class
defects in server source and all three are `kind=integrity, retryable=false`, i.e. the session cannot
recover. **All three are fixed on this branch** (H3, run 20260728-112922 iteration 1; H1,
iteration 2; H2, iteration 3) — see Phase H. This whole block still describes the **deployed**
service, which is `317df4d` and carries none of the fixes.

**Gotcha — remote shell quoting.** Nested quoting through Windows conhost → `wsl.exe` → bash
fails ("The system cannot find the path specified"). Always pipe a script on stdin:
`ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local "wsl.exe -d Ubuntu -- bash -s" < script.sh`.
Binary transfer: embed a `base64 -d` heredoc in that script.

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
#     23dc163; iteration 4 of run 20260728-112922 re-ran it green at 8b852f2) --------------------
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
# Both fences were satisfied honestly (join first, then the in-script expected_main) and the guard
# is live again: the dry run below now REFUSES, which is the proof no third merge can slip through.
RALPH_MERGE_DRY_RUN=1 bash scripts/ralph-afk/merge-keeper.sh   # expect rc=1, "main moved from …"
# If a further merge is ever authorized, run the script in the BACKGROUND: a foreground timeout kill
# skips its EXIT trap and strands a worktree holding `main`, which then blocks the retry. Recover
# with: git -C <wt> merge --abort && git worktree remove --force <wt>

# --- D1: publish the reviewed merge --------------------------------------
# SPENT in iteration 17. `git push origin main` fast-forwarded 163e969..f9285d6 on the AlphaSight
# fork (118 commits) and the host is detached at f9285d6. The push is one-way - the PRD forbids
# force-push - so do not re-run any of this. `upstream` is OpenMOSS: never push there.
# Standing rollback for the host checkout, still valid until D3 changes the host:
#   git -C /mnt/d/Coding/MOSS-Transcribe-Diarize checkout 163e969
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
# Four-way SHA check — the PRD clause in full. GREEN at
# b817871414fcc8f609c6f5eb2898ec2957c7768c for local main + origin/main + the host since iteration 6
# of run 20260728-112922 (H4c); m4mbp still reads 317df4d because it was offline. It was fully green
# at 317df4d since G5, and at f9285d6 from iteration 20. Re-run it read-only any
# time — all four lines must print the same 40 hex characters:
git rev-parse main; git ls-remote origin refs/heads/main | cut -f1
printf '%s\n' 'cd /mnt/d/Coding/MOSS-Transcribe-Diarize && git rev-parse HEAD' |
  ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local "wsl.exe -d Ubuntu -- bash -s"
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
```

## Candidates

Strictly ordered by phase. Mark outcomes inline (`[done <commit>]`, `[dead: <why>]`) and prune
only after the durable result is in progress.txt.

### Phase A — preserve and close IDEA-044 before widening scope

1. **A1 — graft A-034's accepted mechanics** `[done — iteration 1, `--no-ff` merge of
   `acl/IDEA-044--A-034@67a27b8`]`: two-step pairing/session create,
   `PinnedCertificateURLSessionDelegate`, `FullCertificatePinValidator`, restart-safe authority
   persistence, environment-selected `FileCaptureSecretStore` (Keychain still the default with no
   `MOSS_CAPTURE_SECRET_STORE_PATH`), and `tests/test_macos_uds_tracer.py`. Grafted verbatim, not
   rewritten.
2. **A2 — app-owned UDS `handoff`** `[done — iteration 3]`: `case "handoff"` plus
   `CapturePortalHandoffAdapter`/`PasteboardCapturePortalHandoff` now live in
   `CaptureSecurity.swift` next to the dispatcher, injected only by `MOSSCaptureApp/main.swift`;
   `CaptureCommandLine.swift` sends `ControlChannelRequest(command: "handoff")` and keeps no
   view-token or pasteboard authority. Discriminator checks 1-4 green.
3. **A3 — explicit per-lane permission coordinator** `[done — iteration 2]`:
   `NativeLanePermissionCoordinator` in `NativeDualCaptureSource.swift`,
   `AVCaptureDevice.requestAccess(for: .audio)` in `MicrophoneCapture.swift`, and
   `SystemAudioPermission` in `SystemAudioTap.swift`. Discriminator checks 5-9 green; tracer
   `2 passed`.
4. **A4 — compatibility checkpoint** `[done — iteration 4]`: the tracer now installs one
   immutable lab bundle at the fixed path and re-asserts its first-install evidence across nodes;
   the eleven registered commands plus the locality script are all green at **10/10 / 16/16 /
   0 Darwin skips**. The SHA is recorded in progress.txt. **Not merged and not pushed** — the one
   keeper merge stays at C4. Residue: M38's *granted* dual-lane node still cannot run because no
   TCC grant exists on MacStudio; the tracer takes its typed-failure branch instead and the
   granted branch is exercised for real only at E3. That is a recorded gap in the mutation
   evidence, not a gate failure — the registered A4 gate does not require it.

### Phase B — production Mac reliability

**Gate opened by iteration 4's green A4 checkpoint.** From here the Phase-A source
discriminators are historical evidence: B1–B5 deliberately supersede the lab-only
source/locality expectations and need their own behavioral tests plus the full-suite gate. Never
edit the control-plane discriminator scripts to keep them green.

5. **B1 — production file secret store** `[done — iteration 5]`: `makeDefault()` returns a
   `FileCaptureSecretStore` at `~/Library/Application Support/MOSSCapture/secrets.json` for both
   products; 0700 directory, 0600 `O_EXCL`+`fsync`+`rename` replacement, no access group on the
   dormant Keychain store. The lab-default source assertions were replaced by behavioral nodes
   (see Validation); the control-plane discriminator was left untouched at 14/16.
6. **B2 — retained-until-ACK outbox** `[done — iteration 6]`: `CaptureFrameOutbox` holds 15 s of
   audio per lane keyed by the wire `(lane, sequence)` it stamps itself, retries the identical
   frame on timeout/429/5xx/ambiguous answers, releases only on an ack, and refuses new audio on
   overflow with a sticky typed degradation plus a discontinuity on the lane's next admitted frame.
   Eight behavioral nodes cover 5 s outage, ambiguous success, duplicate retry, 429/5xx/401,
   overflow, per-lane stall isolation, wire-sequence authority, and per-session numbering.
   The serial-flush residue this left is closed by iteration 8 (B4).
7. **B3 — 16 kHz mono conversion/coalescing + real nanosecond timestamps** `[done — iteration 7]`:
   `NativeLaneWireFormat.swift` + the rewritten `NativeLaneFrameEmitter` convert host ticks with
   `AudioConvertHostTimeToNanos`, run one stateful `AVAudioConverter` per lane, and coalesce exact
   8000-sample 16 kHz frames; the drivers still only copy and enqueue. Eleven nodes cover the
   injected 125/3 timebase, exact steady frames, 48/44.1 kHz duration conservation, one shared
   cross-lane time domain, a refused unusable capture instant, the terminal partial flush and its
   delivery through `CaptureController.stop`, a spliced gap, and the no-callback-DSP source gates.
   Residue for C2: the client now really does send 8000-sample 16 kHz frames, so the manifest
   bounds the server admits them against (`bounds_config.max_frame_samples`, `frame_samples`,
   `max_retained_samples` — read from the host provider manifest via
   `live_provider_bundle.py:269,912`) must be the retuned contract values before D-phase pairing.
   **Closed by iteration 12 (C2)**: the generator refuses any manifest the client's frames would
   not fit.
8. **B4 — bounded concurrent transport** `[done — iteration 8]`: `CaptureFramePublishPump`
   (`CapturePublishPump.swift`) is the only caller of `transport.publish`; one serial queue per
   lane makes in-flight work exactly the lane count, `Contention.skip`/`.wait` stops passes from
   overlapping, the app's pump interval is `CapturePumpContract.interval` (0.5 s, was 0.25 s), and
   `PinnedURLSessionCaptureHTTPClientProvider` keeps one pinned session per pin instead of one per
   request. Five behavioral nodes (see Validation); five mutation rehearsals recorded in
   progress.txt. Residue: `stop`'s final drain is unbounded in time — it waits for whatever pass is
   running plus its own. That is correct for the tail but means a stop during a full-window
   recovery can take seconds; if F2/F3 shows a slow stop, bound it with the stop deadline the
   `stop(deadline:)` signature already carries rather than by skipping the drain.
9. **B5 — tracked Mac packaging/install tools** `[done — iteration 9]`:
   `macos/scripts/{moss-tool-lib,bootstrap-signing-identity,build-app,install-app}.sh` with one
   dry-run/rollback-first/idempotent output discipline (see the packaging-tool contract above).
   Nine acceptance nodes run against scratch paths only; the suite creates no certificate,
   keychain, search-list entry or installed file. The signing incantation itself was proven for
   real once on MacStudio in a temp keychain and rolled back — `codesign --keychain` is ignored,
   search-list membership is what works. Residue for E2: `install-app.sh` defaults the CLI to
   `~/.local/bin` and reports `bin_dir_on_path`; if that is not on m4mbp's PATH, pass `--bin-dir`
   rather than editing a shell profile from the loop.
10. **B6 — client gate** `[done — iteration 10]`: green at product-tree `3fb5567` — see the Phase B
   client gate block above for the recorded numbers. The Phase-A source discriminators stayed at
   10/10 but are historical evidence, not final gates, after the deliberate B1–B5 production
   changes. Residue for C4: this gate is the *client* half; the keeper merge re-runs it plus the
   Phase C reliability tests on the merge commit.

### Phase C — server meeting reliability, then one merge

**Gate opened by iteration 10's green B6 checkpoint.** Server work may now start; the Mac client is
frozen except for defects the server work exposes and for C3c, whose probe is app-side by design
(iteration 15 added `CaptureLatencyProbe.swift` and one optional observer hook on
`CaptureController`; nothing on the capture or publish path changed).

11. **C1 — session-lifecycle view authority** `[done — iteration 11]`: `bind_session_lifecycle` +
    `VIEW_ABSOLUTE_CAP_SECONDS` + `revoke_view` and its loopback route (see the view-authority
    contract above). Nine nodes: virtual 60 minutes, the exact cap boundary with capture
    unaffected, five lifecycle statuses with ownership proven intact, fail-closed when unwired,
    operator revoke, restart, and three route-level nodes (clean stop → 401, failed stop → 401 with
    abort still possible, loopback-only operator revoke with capture still streaming). Four
    mutation rehearsals recorded in progress.txt. Residue for C4: the PRD's server gate also names
    5 s outage / ambiguous retry / duplicate retry / 429 / outbox overflow. Duplicate retry and 429
    already have server nodes (`test_v2_http_replays_prior_ack_and_keeps_lane_sequences_distinct`,
    `test_v2_http_maps_lane_capacity_to_429_without_mutating_or_sharing_capacity`); outage,
    ambiguous retry and outbox overflow are the B2 Swift nodes. The gate iteration must record that
    clause-to-node map rather than assume it.
12. **C2 — bounds retune** `[done — iteration 12]`: `live_manifest_finalizer.py` +
    `ops/finalize-live-provider-manifest.py` generate `hard_cap_samples=40000` (both sections),
    `max_retained_samples=960000`, `frame_samples=8000` with regenerated bundle hashes and refuse
    any combination the wire contract cannot carry — see the manifest-bounds contract above.
    Seventeen nodes; four mutation rehearsals recorded in progress.txt. Residue for C3: the tool is
    tracked but **undocumented** in `LOCAL_DEPLOYMENT.md`, which C3 owns; residue for D2: the host
    file must be finalized before the live service starts, and the source revision must be the
    40-hex merge SHA (the placeholder is refused).
13. **C3a — tracked TLS material and loopback pairing** `[done — iteration 13]`:
    `ops/{moss-ops-lib,generate-live-tls,live-pair}.sh` — see the live-credential tool contract
    above. Fourteen nodes; five mutation rehearsals recorded in progress.txt. No product source
    changed. Residue for C3b: both tools are **undocumented** in `LOCAL_DEPLOYMENT.md`, which C3b
    owns, and the doc must state the D2/D4 invocations and that the `payload:` line is never
    redirected to a file. Residue for D2: `--min-remaining-days` defaults to 30, so a host cert
    inside that window rotates only when `--rotate` is passed deliberately.
14. **C3b — tracked live service templates and networking** `[done — iteration 14]`:
    `ops/moss-live.env.example`, `ops/systemd/moss-live-web.service`, the `MOSS_WEB_PORT` /
    `MOSS_RUNS_DIR` overrides in `ops/start-web.sh`, `--with-live` in `ops/install-services.sh`,
    `-IncludeLive` in `ops/configure-windows-network.ps1`, and the `LOCAL_DEPLOYMENT.md` "Live
    service" section — see the two-service deployment contract above. Thirty nodes in
    `tests/test_live_service_deployment.py`; five mutation rehearsals recorded in progress.txt.
    No product source changed. The pre-existing
    `test_start_web_is_the_single_environment_adapter` was updated to the widened live contract
    (two new required variables, two new refusal checks), not weakened. Residue for D3: the host
    needs `ops/moss-live.env` created from the example with absolute paths *before*
    `install-services.sh --with-live`, and the batch service is not restarted by that tool —
    `evidence: restart_required=` names any unit whose file changed.
15. **C3c — app-owned latency probe** `[done — iteration 15]`:
    `CaptureLatencySampler` + `CaptureLatencyProbe` (`CaptureLatencyProbe.swift`), the
    `CaptureAcknowledgedFrameObserving` hook on `CaptureController`, the `latency` control command
    and `ControlChannelResponse.latency` — see the latency-probe contract above. Ten nodes; six
    mutation rehearsals recorded in progress.txt. No server source changed.
    Residue for F1/F2: the probe reports `sufficientSamples` only at the plan's twenty advances, so
    a canary must run long enough to produce them (at a 2.5 s span cap that is ~50 s of continuous
    speech); the human marker cross-check and the decoder RTF figure are still separate evidence the
    probe does not produce. Residue for E3: a lane left *pending* forever (a TCC prompt nobody
    answers) keeps the origin unresolved — the report says `mixerOriginResolved: false` rather than
    quoting a figure, which is the honest answer but means the canary needs both lanes settled
    (granted or denied) before it starts.
16. **C4 — final local gate and single keeper merge** `[done — iteration 16]`: gate green at
    `f400d426`, merge `f9285d6` — see the keeper-merge and server-reliability blocks above.
    The pre-merge review of every artifact the PRD names is recorded in progress.txt. Two review
    notes carried forward: (a) `build-app.sh` unlocks the signing keychain with
    `security unlock-keychain -p "$(cat …)"`, so the random keychain password is briefly visible in
    `ps` on a shared host — acceptable on single-user m4mbp, worth stating at E1 rather than
    silently accepting; (b) `.gitignore` now ignores `*.crt`, so a future tracked certificate
    fixture would need an explicit negation. **From here the feature branch carries only
    `scripts/ralph-afk/*`.**

### Phase D — publish and enable the 4070Ti

17. **D1 — publish reviewed `main`** `[done — iteration 17]`: `git push origin main` fast-forwarded
    `163e969..f9285d6` (118 commits) on the AlphaSight fork, and the host checkout is **detached**
    at `f9285d6` with its local `main` ref left at `163e969`, so the recorded rollback is one
    `git checkout 163e969`. Local `main`, `origin/main` and the host all read
    `f9285d69ed7bcc592bb41b3dcdf29e3221968f44`; the m4mbp leg of the PRD's "one exact SHA
    everywhere" clause is still open and belongs to E2. Batch service verified unharmed on four
    routes plus a restart-safety argv probe (see the server-state block). No service restarted.
    Residue for D2: the reviewed `ops/finalize-live-provider-manifest.py`, `generate-live-tls.sh`,
    `live-pair.sh` and `moss-ops-lib.sh` are now **on the host** and D2 runs them from that
    checkout, so `--source-revision "$(git rev-parse HEAD)"` there yields the 40-hex merge SHA the
    finalizer requires. Note the host is detached, so that command reads `HEAD`, not a branch.
18. **D2 — host manifest/TLS** `[done — iteration 18]`: the finalized manifest carries
    `source_revision f9285d69…`, `hard_cap_samples 40000` in **both** sections,
    `max_retained_samples 960000`, `frame_samples 8000` and regenerated hashes
    (`provider_manifest_hash 61d97ffe…`), and the runtime's own readers admit it with
    `available=True, failures=[]`. The certificate was **rotated** (the staged pair had no tailnet
    SAN) to CN `ga0-alienware-rtx4070ti.tailnet.aisight.us` with all four SANs, 825 days, cert 0644
    / key 0600; the new pin is `a35ca9fc4a0f5b32bf7da6dc2e03c1fa5b4ac60992f0ee49b6d5677d22b680ff`,
    agreed by four independent readers including a real TLS handshake. Both refusal and idempotence
    were proven for real on the host, not only in tests. Residue for D3: the finalizer must be run
    with the **deployment venv python** (see the open defect above), and `ops/moss-live.env` must
    point `MOSS_LIVE_TLS_CERT`/`_KEY` at the rotated pair. Residue for D4/E2: the pin the Mac stores
    is the new `a35ca9fc…`; any payload minted before 2026-07-28T04:41:32Z is dead.
19. **D3 — install reviewed live service/networking** `[done — iteration 19]`: host
    `ops/moss-live.env` written from the tracked example with literal absolute paths,
    `install-services.sh --with-live` installed/enabled/started `moss-live-web.service` (MainPID
    334346) leaving both batch units untouched (`unchanged:` ×2, same MainPIDs, `NRestarts=0`), and
    `configure-windows-network.ps1 -IncludeLive` added the 7861 portproxy row, the Private-profile
    firewall rule and the `-IncludeLive` sign-in task. `/live` and `/api/live/descriptor` return 200
    over pinned TLS **from m4mbp**, batch 7860 still 200, plaintext 7861 dead. The `--with-live`
    refusal and the installer's idempotence were both proven for real on the host. Residue for D4:
    the loopback mint route is what `ops/live-pair.sh` uses, so D4 runs on the host, never from
    MacStudio. (The "`live-auth.json` absent = nothing paired" marker this residue used to name is
    **spent** — the attended diagnosis paired a device at 03:10; see the "A device is ALREADY
    paired" block.)
20. **D4 — verify/pair** `[deferred by evidence — run immediately before the operator's pair command,
    which iteration 23 showed can come AFTER the TCC grants rather than in the same window]`:
    `live_auth.PAIRING_TTL_SECONDS = 300` (`live_auth.py:13`, stamped at
    `pairing-codes` time as `expires_at = now + PAIRING_TTL_SECONDS` and enforced at
    `live_auth.py:221`), so **a minted payload is dead five minutes later** — minting it before a
    built app exists on m4mbp would only burn it. Run it on the host (the mint route is
    loopback-only) as `ops/live-pair.sh --url https://127.0.0.1:7861 --cert <live.crt>` **once**,
    never redirecting the `payload:` line to a file, in the same five-minute window as the app's
    first `pair`. Then confirm no secret artifact was left (no payload in shell history, logs, argv
    or the journal) and that `live-auth.json`'s device count advanced (it already exists at 0600 on
    ext4 with `devices: 1` from the 03:10 attended pairing, so *appearance* is no longer the check —
    mtime and count are). Reachability is already recorded by D3/E2a/G5 and only needs re-asserting
    if the service is restarted. No tracked
    product/deployment edits after merge; only Ralph evidence may advance on the feature branch.

### Phase E — Mac install and human permission boundary

**E2 was split by evidence in iteration 20.** Its checkout half had to come first: every reviewed
tool E1 and E2b run (`macos/scripts/*`) simply did not exist on m4mbp, so "run the reviewed tool
there" was unreachable until the checkout carried it. It also closes a PRD acceptance clause on its
own, which no later step does.

20a. **E2a — align the m4mbp checkout with the published SHA** `[done — iteration 20]`: remote
    `alphasight` added beside the untouched OpenMOSS `origin`, `main` fetched, and the checkout
    detached at `f9285d6` (tree `815f23b0…`, clean, 159 files) with `main` left at `40cf854`. Six
    reviewed tool/source files hash identically to this host. Rollback rehearsed and re-applied. The
    PRD's four-way "one exact SHA everywhere" clause is green. `git-lfs` is absent on both hosts and
    the tree has no LFS-tracked file, so the `.gitattributes` filters are inert.
21. **E1 — run reviewed signing tool** `[done — iteration 21]`: `MOSS Capture Local Signing` exists
    in the dedicated `moss-signing.keychain-db` on m4mbp with leaf `ef8fa542…` and DR
    `identifier "com.alphasight.moss.capture" and certificate leaf = H"e118d874…"` — see the
    signing-identity block above. Validated by `codesign` only (DR identical across two different
    binaries and across a re-sign of changed bytes, CDHash differing), never by `find-identity`.
    Both keychain refusals and the idempotent re-run were proven for real on the host, and the
    rollback was rehearsed and re-applied. Residue for E2b: the identity is **not reproducible**, so
    from the moment E2b signs the installed bundle the E1 rollback is no longer free; and a new SSH
    session must unlock the keychain before any hand-run `codesign`.
22. **E2b — run reviewed build/install tools** `[done — iteration 22]`: release build (zero warnings,
    8.6 s from an empty scratch path), signed by the E1 identity, installed to
    `/Applications/MOSSCapture.app` + `~/.local/bin/mtd-capture` — see the installed-app block above.
    The PRD's "Signed app installed" clause is green, including *unchanged across a rebuild* proven
    against a byte-different rebuild. Both dry runs, the idempotent re-run of each tool, the
    first-install rollback and the replacement/backup rollback were all exercised for real on the
    host. C4 review note (a) observed and measured: `build-app.sh` does put the keychain password on
    argv, and after the run `ps`, both shell histories, `~/Library/Logs`, the build output and the
    installed artifacts all contain zero occurrences of it. `--bin-dir` was **not** needed (see
    fact 3 above). Residue for E3, **superseded by the attended diagnosis**: this used to say
    "nothing is paired and `~/Library/Application Support/MOSSCapture` does not exist yet". The store
    exists since 2026-07-28 03:10 and a device is paired — see the "A device is ALREADY paired"
    block. `mtd-capture status` still answers `{"ok":false}` until the app is running.
23. **E3 — TCC human step** `[BLOCKED on the operator — and DO NOT SPEND IT YET: H1 and H2 still
    stand between the clicks and any transcript, and the deployed service does not yet carry H3]`:
    the only irreducible human step in the whole loop. **F0 proved the canary it exists to enable
    cannot pass on the deployed build** (see the F0 block), so asking for the clicks now buys a
    session that dies in about three seconds. Correct order is: authorize H1/H2 → fix and gate →
    deploy → *then* E3. The runbook below stays valid and needs no rework. The exact click sequence, the exact
    commands and the read-only verification are in progress.txt iteration 23 and in the three new
    contract blocks above (TCC-verification, E3 command surface, prompt order). Summary of what
    iteration 23 changed about it:
    - ~~**Grants no longer have to happen inside D4's 300 s window.** An unpaired `start` still
      raises both prompts.~~ **REFUTED by the attended diagnosis** — iteration 23 flagged this one
      "derived from source, not yet observed", and observation killed it:
      `captureConfiguration(from:)` (`CaptureSecurity.swift:847-862`) throws
      `missingCaptureConfiguration` *before* `CaptureController.start` runs, so an unpaired `start`
      never reaches the source and never raises a prompt. **The order is pair → start → clicks.**
      Note the separate iteration-6 finding that m4mbp is no longer unpaired at all, so a bare
      `start` there now resolves against a stale session instead of failing — pair first anyway.
    - **Order is System Audio Recording first, Microphone second**, fixed by
      `NativeDualCaptureSource.swift:191-192`; only the first can block the control channel.
    - **Verification is read-only and scriptable** — two `sqlite3`/`csreq` queries, no TCC write.
    Never touch the TCC DB, never retry autonomously. Continue only after the operator confirms both
    grants. Both lanes must settle (granted or denied) before any canary starts — a lane left
    *pending* by an unanswered prompt leaves the latency probe's mixer origin unresolved (C3c
    residue).

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
24. **F1 — 60 s canary** per prd.md. `[blocked on E3 **and** on H1/H2/H3 — it cannot pass on the
    deployed build]`
25. **F2 — 300 s locked run** with 5 s interruption and the system-audio-denied variant.
    `[blocked on E3 and H1/H2/H3]`
26. **F3 — 16-minute active-view soak**: capture and `/live` polling stay active with periodic
    two-lane audio; same authority works after minute 15; clean stop immediately revokes it.
    `[blocked on E3 and H1/H2/H3]`
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

### Phase G - authorized post-merge fix cycle (2026-07-28)

Opened by the prd.md amendment of the same date, after E3 proved the merged app cannot reach the
live server at all. Scope is exactly these four items; nothing else may touch tracked source.

26. **G1 - ATS declaration for the pinned live transport** `[done - iteration 1 of run
    20260728-072601]`: `macos/MOSSCapture/Resources/Info.plist` now carries
    `NSAppTransportSecurity = {NSAllowsArbitraryLoads: true}` and nothing else - see the ATS
    contract block above for the exemption matrix measured on MacStudio, the three shape gates,
    and why no single-host test can be the behavioral gate. Chosen over a host-scoped
    `NSExceptionDomains` entry because the exact-leaf pin is the security control here by
    deliberate design (prd.md "The certificate pin deliberately bypasses PKI"), every connection
    the app makes comes from the pinned provider, and a scoped exception would bake one
    deployment's hostname into the shipped product. Do not add chain or hostname evaluation.
    Residue for the G4 merge: the fix is proven by probe on MacStudio and by shape gates in the
    suite; the *product* path is confirmed only when the rebuilt app on m4mbp pairs against
    `https://100.64.0.8:7861` (E3), so E2b must be re-run there after the merge.
27. **G2 - trim the pairing payload** `[done - iteration 2 of run 20260728-072601]`:
    `CapturePairingPayload.init` trims `.whitespacesAndNewlines` before splitting, refuses
    whitespace *inside* a field as `invalidPairingPayload` instead of letting it reach the hex
    check, and the exchange adapter now sends `wireRepresentation` rather than the raw stdin bytes -
    see the pairing-payload contract above. The strict 64-hex check is unchanged. Two Swift nodes
    plus the tracer's second real pairing (fed `payload + b"\n"`); three mutation rehearsals
    recorded in progress.txt, one of which reproduces the shipped `invalidPinnedHash` exactly.
    Residue for G4: nothing - this item needs no host work; the fix ships to m4mbp with the same
    E2b re-run G1 already requires.
28. **G3 - classify and log control-channel failures** `[done - iteration 3 of run
    20260728-072601]`: `classifyControlError` + `ControlChannelErrorDetail` +
    `ControlChannelFailureLogging` / `OSLogControlChannelFailureLog`, wired in
    `MOSSCaptureApp/main.swift` - see the control-channel failure contract above. Five Swift nodes
    plus the tracer's real-process pin refusal strengthened in place; four mutation rehearsals
    recorded in progress.txt, one of which puts the failing URL and the SSL message on the wire.
    `ControlChannelCommands.all` replaces the CLI's duplicate command literal so the log's public
    vocabulary and the CLI's accepted set cannot drift.
    Residue for G4: nothing new - it ships to m4mbp with the same E2b re-run G1 already requires,
    and the `log show` predicate above is what E3 reads if the rebuilt app still fails.
29. **G4 - regression tests, then one further reviewed merge.** Tests must fail before each fix and
    pass after. The `100.64.0.0/10` tracer case this item asked for is **done** (iteration 1 of run
    20260728-072601) - but measurement showed it cannot be the ATS gate, because a server this
    tracer starts is always reached over loopback. See the ATS contract block; the node it became
    proves the pin instead, and the declaration is gated by shape in three places. G2's regression
    tests are **done** (iteration 2) and G3's are **done** (iteration 3), red/green rehearsed for
    both. **The client-gate half is `[done - iteration 4 of run 20260728-072601]`** - green at
    product tree `23dc163`, numbers in the G4 gate block above, and the merge payload reviewed
    against the amendment's four items (eight files, every one of them Mac client source or a
    regression test; no `ops/`, no server source). Iteration 4 also measured the fence and found
    **two** blocking conditions rather than the one the prior iteration flagged, the second of which
    exits 1 printing nothing; both, and the honest route through each, are in the two-fence block
    above and staged as commands in Validation.
    **The merge half is `[done - iteration 5 of run 20260728-072601]`** - join `502a49a`, fence edit
    `23aabe6`, merge `317df4d`, all recorded in the second-keeper-merge block above. **G4 is
    closed and the amendment is spent: no third merge, and the post-merge freeze has resumed.**

30. **G5 - republish the authorized merge to all four checkouts** `[done - iteration 6 of run
    20260728-072601]`: `git push origin main` fast-forwarded `f9285d6..317df4d` on the AlphaSight
    fork, then both host checkouts moved to the same SHA, detached, each behind a HEAD-and-clean
    fence. **The PRD's "one exact SHA everywhere" clause is GREEN at `317df4d`** — see the four-way
    check in Validation and the server-state block. No service was restarted and none needed to be
    (the server tree is byte-identical across the two SHAs); both batch units and the live unit kept
    their MainPIDs, `NRestarts=0` and their original `ActiveEnterTimestamp`s. Cross-host content was
    proven by independent `shasum -a 256` of the six files that matter, not by `git status`.
    Residue for G6: the checkout carries G1+G2+G3 but the **installed** bundle does not — its
    `Info.plist` has no `NSAppTransportSecurity` key at all (measured), so the rebuild is the only
    thing left between the fix and the product.
31. **G6 - re-run E2b on m4mbp so the installed app carries G1+G2+G3** `[build/install half done -
    iteration 7 of run 20260728-072601; the operator's half is E3 and still BLOCKED]`.
    - **Done and proven.** `build-app.sh --configuration release` (7 s wall, zero warnings, both
      products) then `install-app.sh` took the **replacement** path exactly as predicted, printed
      each `rollback:` line before its mutation, created
      `/Applications/MOSSCapture.app.backup-20260728T085551Z` and
      `mtd-capture.backup-20260728T085551Z`, and printed **no** DR-change warning. The DR stayed
      `identifier "com.alphasight.moss.capture" and certificate leaf = H"e118d874…"`. The
      `plutil -extract` before/after and the CDHash pair are in the Mac-state block above. A second
      `install-app.sh` printed two `unchanged:` lines, `backup_bundle=none`, and left the inode
      (`211648186`) untouched — so the idempotent shortcut fires on the *installed* product, not only
      in tests.
    - **Still open, and it is E3, not G6:** the corrected order is D4 mint → `pair` → `start` → the
      two GUI clicks. All of it needs the human at the keyboard.
    - **Pair before start**, for a reason that outlives the ATS fix: the store on m4mbp already holds
      a complete configuration from the 03:10 unsigned-build pairing, so a bare `start` would no
      longer fail closed — it would publish into a stale session. See the "A device is ALREADY
      paired" block.
    - If the rebuilt app still fails, read
      `log show --predicate 'subsystem == "com.alphasight.moss.capture"' --last 30m` - G3 exists so
      that this failure has a name, and the -1200/-9802 vs -999 distinction is in the
      control-channel failure contract above. That log is now reachable for the first time: the
      installed product is the first build to carry `OSLogControlChannelFailureLog`.

### Phase H - authorized server decode-seam fix cycle (2026-07-28, second amendment)

Opened by the second prd.md amendment after F0 proved the deployed pipeline dies within ~3 s of
ordinary audio. Every blocker is server-side and downstream of the operator's TCC clicks, which is
why F0 was worth pulling ahead of E3. Scope is exactly these items.

**Naming, stated once because two sections used to disagree.** H1/H2/H3 are F0 blockers 1/2/3;
H4 is gate/merge/redeploy. The amendment's third bullet ("close the seam the suite cannot reach")
is not a separate item — it is a *requirement on each fix's regression test*, and it now has a home:
`tests/test_live_pipeline_seams.py`, where both sides of a seam are the product class and only the
genuinely off-host part (the native `webrtcvad` wheel, the GPU runner) is a stand-in.
**Order: H3 -> H1 -> H2**, the order the deployed build actually fails in (~1.1 s -> ~3 s -> 2.5 s).
All three were reproduced before the cycle opened, two of them offline in under a second (see the
H-diagnosis block and the repro commands in Validation), so none was waiting on diagnosis.
**All three are now fixed on the branch; H4 is the only open item.**

32. **H1 - a span the decoder cannot parse must never be terminal**
    `[done - run 20260728-112922 iteration 2]`. Policy decided and recorded: **commit the span
    empty** (dropping is unimplementable against the session's accepted/accounted equality). The
    typed `EmptyTranscriptionError` now names the condition at `vllm_runner`, the decode seam
    translates it into an empty transcript, the coordinator commits it through
    `LiveSession.submit_empty_canonical`, and every *other* decoder exception is wrapped as
    `LiveProviderError` so nothing crosses the seam unclassified - the classification half H3
    deferred. Five nodes in `tests/test_live_pipeline_seams.py` drive the **real** `vllm_runner`
    validation under the real coordinator (only the HTTP hop is a stand-in), including F0's own
    leading-silence span and a pure-silence meeting that stops with exact accounting. Red/green
    rehearsed; H2's offline repro is bit-for-bit unchanged by it. See the empty-span decode contract
    block above.
    *Left open by it, deliberately:* a transient decoder failure is still terminal - candidate 36.
33. **H2 - two independent hard-cap freezers collide** `[done - run 20260728-112922 iteration 3]`.
    Resolved by the first of the two readings: the endpoint policy is the single authority and
    `LiveSession` no longer partitions audio at all - the `hard_cap_samples` parameter, the attribute
    and `_freeze_hard_cap_spans` are gone, so the collision and the orphan (spans the session froze
    itself were never queued for decode) are both closed by the same removal.
    `LiveServiceRuntime._require_one_span_cap` keeps `bounds_config.hard_cap_samples` meaningful by
    refusing a session whose policy does not carry exactly the declared cap; without it the removal
    would have silently uncapped a `bounds`-only manifest. Three nodes in
    `tests/test_live_pipeline_seams.py` give one real session and one real policy the *same* deployed
    cap - the shape no harness in the repo had - and assert the lockstep invariant
    `frozen_until_sample == open_start_sample` every frame. Red/green rehearsed against the pre-fix
    files; `live-hardcap-repro.py --frames 8` flipped rc=3 -> rc=0. See the span-cap authority
    contract block above.
    The amendment's "rule the identical per-lane `capture_timestamp_ns` in or out" instruction was
    **spent** before the fix: iteration 10 ruled it out structurally (`live_session.AudioFrame` has
    no timestamp field) and the offset probe run it mandated is what found blocker 3.
34. **H3 - a mixed frame that is not a whole number of VAD frames kills the session**
    `[done - run 20260728-112922 iteration 1]`. `WebRtcSpeechProvider` now tiles the accepted-sample
    stream instead of each accepted range, so webrtcvad is only ever handed exactly `frame_samples`
    of real audio, and an illegal manifest `frame_samples` is refused at construction - see the
    WebRTC VAD framing contract block above. Five nodes in `tests/test_live_pipeline_seams.py`;
    red/green rehearsed by restoring the pre-fix file (4 failed / 1 passed before, 5 passed after,
    the survivor being the aligned 8000-sample control). The offline repro flipped rc=3 -> rc=0 for
    `--speech-provider webrtc --frame-samples 5808` while every blocker-2 case is unchanged.
    *Scope justification, since the amendment names only blockers 1 and 2:* blocker 3 was produced
    by the amendment's own Blocker-2 instruction to re-run the probe with a per-lane offset, it is
    the same classification seam the amendment opens the cycle over, and the amendment's gate
    (a probe run that survives its full plan) is unreachable while it stands - it fires ~1.1 s in,
    before blockers 1 and 2 are even approached. Nothing else was touched.
    *Not closed by it:* the classification seam - carried into H1 above.
35. **H4 - gate, merge, redeploy.** Four steps, in this order, because the amendment's gate (a probe
    run that survives its full plan) can only be observed against a service that carries the fixes.
    a. *Gate* `[done - run 20260728-112922 iteration 4]`. Full Swift/Python gate green at `8b852f2`
       (139 / 551+2 / tracer 4 / 10/10 / leak-scan clean), merge payload reviewed as exactly the
       three blockers and their tests, deployed manifest proven to admit under both new refusals.
       See the H4 gate block above.
    b. *Merge* `[done - run 20260728-112922 iteration 5]`. `b817871`, feature tip `9e0780a`,
       `main^1 = 317df4d`, `main^2 = 9e0780a`, trees identical, delta exactly the fifteen reviewed
       files plus `scripts/ralph-afk/*`. The guard now refuses a fourth merge. See the
       third-keeper-merge block above. **The freeze has resumed** - tracked product source may not
       change on this branch again without a further amendment.
    c. *Publish and redeploy* `[done except m4mbp - run 20260728-112922 iteration 6]`. Pushed
       fast-forward `317df4d..b817871`, host checkout moved, `moss-live-web.service` restarted
       (mandatory here because this merge is server-only), pin/live/batch/plaintext checks all as
       expected, and the deployed code proven to carry H1/H2/H3 by introspection under the
       service's own venv. See the H4c redeploy block. **Left open: the m4mbp checkout**, which was
       offline all iteration (`ssh` and `ping` both time out). When it is up:
       `git -C /Users/ga0/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize fetch origin
       main && … checkout b817871…`, then re-run the four-way SHA check. **No rebuild and no
       reinstall** - `macos/` is byte-identical to `317df4d`, and reinstalling would reset the
       bundle inode for nothing.
    d. *Probe* `[open - next]` - the amendment's actual gate, and now unblocked: the deployed
       service carries all three fixes. Re-run `live-pipeline-probe.py` against it and require a run
       that survives its full plan with committed samples advancing. Only after that is E3 worth the
       operator's clicks. Expect the probe's own recorded rollbacks (iteration 10 of run
       20260728-072601) to still apply; it is loopback-mint + remote-pinned-TLS, mutating nothing
       except one pairing that `DELETE /api/live/devices/{id}` revokes.

36. **A transient decoder failure ends the meeting** `[open; out of the amendment's scope, do not
    start without authorization]`. One vLLM timeout or one reset socket is now a named
    `LiveProviderError` and still terminal for the whole session (`live_service_runtime`
    `_process_in_flight_item` -> `_fail`). For a 300 s certification over a tailnet that is a real
    reliability gap, and the honest fix is a bounded per-span retry plus a typed degraded state -
    *not* committing the span empty, which would render a dead GPU as a blank meeting. Nothing in
    F0 observed this; it is a gap review found while fixing H1, and it needs its own decision.

Useful F0 facts for this cycle: healthy request timings are 4-280 ms while post-terminal 409s took
**6-8 s each**, so a dead session will back the Mac's outbox up hard - worth a look while fixing H1.
Three terminal sessions did not restart or destabilise any service, so the failure is per-session.
`live-runs/` stayed empty and `/tmp/mtd-live-*` was cleaned up, which is real evidence for the PRD's
"no raw audio is persisted" clause. Device revocation (`DELETE /api/live/devices/{id}`, loopback
only) is a complete no-restart rollback for a pairing but marks rather than deletes.

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
