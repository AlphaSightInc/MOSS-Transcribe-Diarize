# WP18 fresh-context verification — FAIL; identity wiring hypothesis FALSIFIED

Fresh session supplied after the requested `/new`; no prior implementation-session context used.
Verified 2026-09-18, branch `mvpfix/wp18-file-identity`, tested commit
`cfc69b7e74b089a36fb612e3e6a4499db8c6738d` (implementation `82ab6d27`, base `d769b010`).
Initial tracked/untracked status clean; Python import resolved inside this worktree.
Executed every command in `VERIFY.md`, in order, with its exact environment and scratch
plugin. Added exit-code recording only. No live requests, tunnels, deployment inspection,
push, merge, rebase, shared-service changes, or writes outside this worktree.

**F1 — Overall verification FAIL.** The identity diagnosis reproduced, but the required
full Python suite did not meet the documented zero-failure gate. No exception or retry
is used to convert this result into PASS.

| Required check | Result | Observed evidence |
|---|---|---|
| Initial branch/SHA/status and local Python import | PASS | Requested branch and SHA; clean; checkout-local import |
| Full Python suite | **FAIL**, exit 1 | **1873 passed, 1 failed, 2 skipped, 37 subtests passed, 21 warnings; 138.52 s** |
| Full frontend suite | PASS, exit 0 | **244 passed / 27 files; 2.64 s** |
| Offline evidence verifier | PASS, exit 0 | **6/6 exact resolver comparisons**, elapsed times excluded; zero GPU calls |
| Verification-document layout | PASS, exit 0 | Documents under `docs/verify/wp18/` |
| `git diff --check` | PASS, exit 0 | No whitespace errors |
| Base-relative stat and specified product diff | PASS, exit 0 | Reviewed 31 files, 2217 insertions, 11 deletions before this result commit |
| Port 18118 listener check | PASS, expected exit 1 | `lsof` returned no listener/output |

The full commands are retained in `VERIFY.md`; raw invocation outputs remain ignored in
`.wp18runtime/fresh-{python,frontend,evidence,exit-codes}.log`. Compact committed evidence:
`evidence/mvpfix/wp18/fresh-summary.json`.

The sole failure was
`tests/phase2/test_owner_bound_live_meeting.py::test_helper_lease_loss_interrupts_without_client_terminal_request_and_never_resumes`.
At line 2091 the test sets a **0.03 s** lease; line 2096 calls `feed_two_lane_span`.
The first system frame (sequence 0) failed at line 474: **HTTP 409, expected 200**.
Captured product log: `reason=helper_lease_expired lanes=none`.
Thus lease expiry preceded the test's intended populated-transcript scenario. Scheduler
timing is a plausible explanation, not an established root cause or a waived failure.
The failing test has no diff from `d769b010`; that does not establish pre-existing failure.
No test, lease, policy, or product code changed during fresh verification.

**F2 — Wiring-only hypothesis FALSIFIED, reproducibly.** Question: can enabling the
existing voice-vector provider alone reconcile recurring voices? Minimum concepts are
window-local observations, acoustic evidence, overlap links, and canonical identities:
observations are not identities; acoustic evidence permits comparison; overlap links
record continuity; canonical identities are the output. Removing any loses either input,
evidence, continuity, or the result. Invariants: preserve all words/times, window ownership,
matching policy and lifecycle. Unknown: whether the existing album composes correctly
with file processing. Falsifier: duplicate identities persist with the provider available.
Tool decision: replay identical decoder outputs to isolate identity logic; perfect vectors
remove acoustic uncertainty; full suites expose integration regressions.

| Replay case | Disabled resolver / stitched | Enabled resolver / stitched | Reference voices |
|---|---|---|---|
| Perfect vectors, one voice × three windows | 3 / 3 | **3 / 3** | 1 |
| Perfect vectors, two voices × three windows | 6 / 6 | **6 / 6** | 2 |
| Real six-minute public corpus, three windows | 7 / 7 | **7 / 7** | 3 |

The real replay accepted two overlap links and zero embedding links; four recurring-voice
fragments remained, with zero false accepted edges in retained diagnostics. The enabled
pinned CPU provider reported available. Real same-voice cosine scores **0.994946–1** and
margins **−0.005054–0.005054** fail the unchanged **0.20** margin. Perfect-vector scores
are **1**, margins **0**. Equal resolver/stitch counts exclude ownership clipping as an
explanation for these retained failures. This does not certify transcription accuracy.

**F3 — Two unchanged identity defects, source-confirmed.**
`moss_transcribe_diarize/app/speaker_identity.py:1172` (`_tier_b_runner_up`, filtering at
1176) treats another occurrence of the same voice as a rival. Lines 385–391 subtract its
score and reject the resulting low margin. Three identical observations therefore compete
with one another instead of reinforcing one speaker.
`moss_transcribe_diarize/app/speaker_identity.py:726` (`_tier_b_evidence`) selects only
singleton components. A voice already linked across two overlapping windows cannot be
an embedding candidate for a later isolated return. This exclusion is directly verified
in source; the dedicated linked-then-return case remains a follow-on acceptance test.

**F4 — Recorded production File construction disables Tier B.**
`ops/account-web-launcher.sh:33` selects vLLM; `phase2_web_cli.py:143` calls the shared
file factory; `runner_composition.py:100` constructs `IdentityResolverConfig()` without
an encoder; `speaker_identity.py:24` defaults `tier_b_enabled=False`.
The live manifest is loaded by `phase2_web_cli.py:104` for the live runtime, not File.
Fresh constructor output reports `enabled=false`, `available=false`, `reason=disabled`.
Paths without a prefix above are under `moss_transcribe_diarize/app/`.
This is source plus local construction evidence, **not inspection of a deployed process**.
The conditional production-enabled/local-disabled 30-minute rerun is inapplicable.

**F5 — Independent truncation-notice fix verified: three cases passed in the full suite.**
`phase2_audio.py:289` captures only the measured FFmpeg incomplete-media warning as fixed
safe text. `phase2_file.py:505` preserves the speech decoder's output-cap metadata as a
notice, and line 509 carries notices through completion. Real FFmpeg plus a fake speech
decoder tests healthy/no notice, truncated MP3/notice, and output-cap/notice through
save/reopen (`tests/phase2/test_file_truncation_notice.py:15`). Private paths/raw stderr
do not enter saved notices. The retained 12 s MP3 and its 60%-byte prefix both decoded
successfully; the prefix yielded **7.1669375 s** and the warning. No warning is not proof
of complete media. Existing silence assertions remain intact; helper callers only adapt
to the added notices return value/keyword. No frontend source/assets changed.

**F6 — Retained live measurement, not fresh decoder activity.** Three serial decoder
requests through the prior session's own 18118 tunnel, at most one in flight, queues
running/waiting zero before each. Wall times **10.519330834 + 5.143499209 + 3.940289833 =
19.603119876 s**; output **1211 + 1211 + 901 = 3323 tokens**. Retained enabled resolver:
**16.700404417 s**. Fresh verification made **0/60** authorized live requests; it reused
local decoder caches and re-ran the pinned CPU encoder/resolver. Raw public audio and
decoder text remain ignored scratch, not committed.

Follow-on album-based File identity acceptance requirements (proposed, not implemented):

- **A1 — Repeat consistency:** perfect one-voice × three-window input must produce **1**
  identity; independent two-voice input **2**, at both resolver and stitched output. Keep
  every owned segment; relabel only. Reorder local speaker labels to expose label leakage.
- **A2 — Linked voice returns:** link a voice across two overlap windows, then return it
  after a gap without overlap. It must reuse that canonical identity; a distinct voice
  stays distinct. Preserve same-window cannot-link constraints and ambiguity abstention.
- **A3 — Real attribution:** run the production File composition on this six-minute
  three-voice fixture and the original 30-minute 31-identities/3-voices case. Require
  three truth-aligned identities, without wrong merges or missing segments; report
  reference-based attribution/fragmentation, not counts alone. No 31→3 claim exists now.
- **A4 — Album evidence and persistence:** test clean admission, short/ambiguous evidence,
  and leave-one-out retrospective reassignment using existing album rules; verify corrected
  identities through File completion, saved/reopened records and exports, with text/times
  unchanged. Prove the production constructor actually supplies the intended engine and
  that unavailable evidence is reported truthfully. No assumed drop-in compatibility.
- **A5 — Invariants and cost:** retain all existing quality bounds, matching/admission
  policies, readiness, two-Refresh sentinel, nine-key frames and lifecycle checks; measure
  encoder calls, retained evidence and runtime versus file length, without re-decoding
  earlier speech. Full Python/frontend suites must pass. Prototype and record the verdict
  before any production integration; separate authorization is required.

Limits/deviations: the requested fresh zero-failure gate failed and remains blocking.
Identity work stopped at falsification per COMMON; no identity repair shipped. Existing
state-printing bench replaces an interactive TUI and remains a reusable falsifier. The
scratch plugin confines test paths/sockets without changing assertions. Historical
`summary.json` declares `budget: 400`, inconsistent with this request's **60** cap and
COMMON's **200** default; it is not fresh authority. Actual retained usage is **3**, fresh
usage **0**, so neither count exceeds 60. Original metadata is preserved, discrepancy
reported. Build/typecheck omitted exactly as VERIFY directs for Python-only changes.

Historical failed attempts reviewed: initial malformed notice tests **3 failed**;
corrected pre-fix regression tests **2 failed / 1 passed**; focused suite **98 passed**;
first full suite **3 failed / 1871 passed** (internal tuple callers); corrected previous
full suite **1874 passed**, unlike this fresh run. Initial fake probe clipped ownership
intervals (resolver 3/6, stitched 1/2); corrected inputs produce resolver/stitch 3/3 and
6/6. Real measurements were unaffected. No historical success supersedes fresh failure.

This session adds only this result and `evidence/mvpfix/wp18/fresh-summary.json`, committed
locally. Product changes remain the two notice modules, three helper-test adaptations,
one new three-case test, and the previously committed bench/evidence/design note.
