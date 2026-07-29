# PRD - MOSS live meeting transcription MVP

## Goal

> Make a real meeting transcribable end to end: the MacBook `m4mbp` captures system audio and
> microphone as two independent lanes, streams them over pinned HTTPS across LAN or Tailscale to
> `ga0-alienware-rtx4070ti`, which transcribes and diarizes on CUDA, and a server-hosted `/live`
> page shows the transcript with speaker labels continuously — for meetings longer than 15
> minutes, surviving a 5-second network interruption without silently losing accepted audio.
>
> The authoritative plan, with measured evidence and the committed design decisions D1-D14, is
> `/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/docs/live-capture-gap-and-execution-plan-20260727.md`
> (current controlling revision). Read it before the first change of any work item. This PRD is
> the acceptance contract; that document is the design rationale.

## Acceptance bar

The loop is complete only when every point below holds, with evidence (commands run, artifacts
inspected, before/after deltas) recorded in progress.txt:

- **IDEA-044 compatibility checkpoint recorded before production supersession:** the accepted
  A-034 pairing/pinning/tracer mechanics plus app-owned handoff and explicit permission
  transitions reach the registered **10/10 and 16/16** controls and all eleven historical
  commands while changes remain inside the registered thirteen product/doc paths. Record that
  green commit in progress.txt; do not merge or push it yet.
- **Production client gate green:** the *built* `MOSSCaptureApp` and *built* `mtd-capture`
  complete real two-step pairing (`/api/live/pairing-codes` → `/api/live/pairings` →
  `/api/live/sessions`) against a real TLS server over real same-user UDS, with
  full-certificate pinning; the **app** (never the CLI) reads view authority and writes the
  pasteboard; microphone and system-audio permissions have explicit per-lane request → pending
  → granted-or-denied transitions; a denied lane emits a typed lane failure rather than staying
  absent; frames remain queued until acknowledged; and both lanes leave the Mac as 16 kHz mono
  with `capture_timestamp_ns` converted from Mach host ticks to real nanoseconds. Swift and
  Python suites are green and the Darwin real-process tracer passes with zero skips.
- **Server meeting-reliability gate green:** view authority is bound to the session lifecycle
  (active session only + 12 h absolute cap + immediate terminal/device/operator revoke) and a
  900-second fixed expiry is unreachable. Deterministic tests cover virtual 60-minute duration,
  exact cap and terminal/revocation boundaries, 5-second outage, ambiguous-success retry,
  duplicate retry, 429, and outbox overflow surfacing a typed degraded state.
- **One reviewed keeper merge:** only after all three gates above, merge
  `ralph/live-meeting-mvp` once into `main`, run the full post-merge suite, and record both the
  feature tip and merge SHA. All tracked deployment templates, manifest/TLS/pairing tools,
  Windows networking changes, Mac packaging/install scripts, app-owned latency probe, and docs
  must be reviewed before this merge. No intermediate merge and no tracked product work directly
  on `main`.
- **One exact SHA everywhere:** `git rev-parse HEAD` is identical for local `main`,
  `origin/main`, the server checkout at `/mnt/d/Coding/MOSS-Transcribe-Diarize`, and the m4mbp
  checkout; the value is recorded in progress.txt.
- **Live service answering:** from m4mbp, `https://100.64.0.8:7861/live` returns 200 and
  `https://100.64.0.8:7861/api/live/descriptor` returns 200 over pinned HTTPS.
- **Batch service unharmed:** `http://192.168.68.38:7860/` still returns 200 over plaintext and
  its job routes still work.
- **Signed app installed:** `/Applications/MOSSCapture.app` exists; `codesign -dv` reports
  identifier `com.alphasight.moss.capture`; the designated requirement names the project signing
  certificate leaf and is unchanged across a rebuild.
- **Permissions granted:** Microphone and System Audio Recording are granted on m4mbp and
  `mtd-capture status` reports both lanes active.
- **60-second canary passes:** two speakers plus identifiable system audio produce a
  continuously updating transcript with speaker labels in the browser; **user-visible p95 ≤ 4 s**
  measured by the plan's Phase F procedure (single-clock committed latency + analytic portal
  render bound + one human marker cross-check), with both components recorded separately;
  decoder p95 RTF < 1; both lanes accepted and accounted with zero loss and zero double count.
- **300-second locked certification passes:** simultaneous lanes, silence/mute, a 5-second
  network interruption, ambiguous retry, duplicate retry, two speakers, clean stop/drain — plus a
  separate mic-granted / system-audio-denied run that still produces transcript.
  **User-visible p95 ≤ 6 s** by the same Phase F procedure; decoder p95 RTF < 1; zero
  accepted-audio loss; outbox and memory bounded. A latency miss is answered by the plan's
  ordered remedies (2.0 s span cap, then 0.5 s poll interval), never by relaxing the gate.
- **16-minute active-view soak passes:** capture remains active with periodic accepted audio and
  `/live` polling; the same view authority works after minute 15, then clean stop immediately
  revokes it.
- **Secret hygiene proven:** no bearer token, device token, view token, or pairing payload
  appears in any CLI output, log, URL, telemetry file, or browser storage; no raw audio is
  persisted.
- **Rollback rehearsed and recorded:** live service disabled, server checkout reverted to
  `163e969`, and `http://192.168.68.38:7860/` still serving — then restored.

## Authorized amendment - 2026-07-28, one follow-up fix merge

The keeper merge `f9285d6` shipped a blocker that no gate could see: App Transport Security
rejects every pinned live connection the app makes, so no part of Phase F can run. Evidence is in
progress.txt under "Supervisor diagnosis - ATS blocks the signed app bundle".

The operator has therefore authorized **exactly one** follow-up fix cycle that may change tracked
product source after the keeper merge, strictly limited to:

- the ATS declaration that lets the pinned live transport work from an `.app` bundle,
- the pairing-payload whitespace defect,
- control-channel error classification and logging for unclassified failures,
- regression tests for all three, including a tracer case bound to a `100.64.0.0/10` address,
- and one further reviewed no-ff merge to `main` through `merge-keeper.sh`.

Everything else stays frozen. This authorization does not reopen general product work, does not
permit a third merge, and does not weaken any existing gate. After that merge the original
post-merge freeze resumes: only Ralph evidence may change on the feature branch.

## Second authorized amendment - 2026-07-28, server decode-seam fix cycle

The F0 probe drove the deployed live service through the whole pipeline from a real remote pinned
TLS peer and found the session dies within ~3 s of ordinary audio. Evidence is in progress.txt under
"F0 server-side live pipeline probe". Neither blocker is reachable by any existing gate: no test in
this repo puts the real VAD endpointer and a real decoder in one process.

The operator has therefore authorized a **second** follow-up fix cycle, again strictly limited:

- **Blocker 1** - `vllm_runner.py:245` `_validate_transcription_response` raises a bare
  `RuntimeError` for an empty parse, which escapes before `live_adapters.py:360-364` can classify it
  as the typed `LiveProviderError` that already exists for the identical condition. A span the
  decoder cannot parse must be **dropped or committed empty, never terminal**. Decide and record
  which, then implement it.
- **Blocker 2** - `live_session.py:237` `frozen span end must advance`, reached from the coordinator
  at `live_coordinator.py:128` / `:231`. Before concluding, rule the probe's identical per-lane
  `capture_timestamp_ns` in or out by re-running the probe with a per-lane offset; a real capture
  never produces identical lane timestamps.
- Regression tests that put the **real** `vllm_runner` validation seam under the live coordinator,
  including an empty transcript and a leading-silence span. The absence of that seam from the suite
  is the root cause and must be closed, not just the two symptoms.
- Re-running `scripts/ralph-afk/live-pipeline-probe.py` against the deployed service as the gate,
  plus one further reviewed no-ff merge to `main` through `merge-keeper.sh`, then redeploy so all
  four checkouts return to one exact SHA.

Everything else stays frozen. This does not reopen general product work, does not permit a further
merge beyond the one named here, and does not weaken any gate. Server-side fixes may touch
`moss_transcribe_diarize/` only where the two blockers and their tests require it. After that merge
the post-merge freeze resumes.

**Order matters:** do not spend the operator's TCC clicks until this cycle is deployed. E3 exists to
enable the canary, and the canary cannot pass on the current build.

## Third authorized amendment - 2026-07-28, the live path's terminal-failure policy

H4d's gate run proved the second cycle worked (tick 1 -> tick 8, 0 -> 1 committed spans) and found
a fourth blocker of the **same shape as the previous three**: a non-fatal condition on the live path
is treated as fatal. The operator has authorized settling that class once rather than one blocker
per cycle. Evidence is in progress.txt under the H4d gate run.

**The governing rule this cycle must implement:** on the live path, only a condition that makes the
session genuinely unable to continue may be terminal. Anything the design already contemplates -
a span the decoder cannot parse, an abstained identity preparation, a transient decoder failure -
must degrade, retry, or commit without labels, never end the meeting.

Scope, all of it inside `moss_transcribe_diarize/` and `tests/`:

- **Timestamp tolerance, decided once.** `live_identity.py:101-102` rejects `segment.end > duration`
  with no tolerance. Choose the tolerance deliberately, record the reasoning, and apply the same
  answer in **both** places - `BoundedCausalIdentityPreparer.prepare` and
  `LiveSession._canonical_validation_error` (`live_session.py:436-442`). Fixing one moves the
  failure instead of removing it.
- **Non-`prepared` preparations.** `live_session.py:449` admits only `status == "prepared"`, so an
  `abstain` - the *designed* outcome for ambiguous identity or exhausted speaker capacity
  (`live_identity.py:106,121,127`) - is terminal. Decide whether any non-`prepared` preparation may
  be terminal at all, and make design intent and implementation agree.
- **Candidate 36, in the same pass:** a transient decoder failure is terminal. Same shape, same
  path; settle it here rather than in a fourth cycle.
- **Diagnosability.** `reason` must reach the failure detail and the `canonical_processed` event. A
  typed refusal that discards the one word naming it is what forced a host-side probe to be built.
- **Real-seam regression coverage** in `tests/test_live_pipeline_seams.py` for each case: nothing in
  the repo currently puts the real decoder's timestamps under the real identity preparer.
- **Gate:** re-run **both** probes (`live-pipeline-probe.py` and the hard-cap repro) against the
  deployed service, requiring a run that survives its full plan with committed spans advancing and
  speaker labels present; full Swift/Python gate; then one further reviewed no-ff merge through
  `merge-keeper.sh` (advance `expected_main` in-script, never by CLI override), push, redeploy.

Everything else stays frozen; this permits exactly one further merge. After it the post-merge
freeze resumes. **Do not spend the operator's TCC clicks until this is deployed and the probe is
green** - a canary against a service that dies at the first 2.5 s of continuous speech would burn
the one input the loop cannot obtain.

Housekeeping, not on the critical path: m4mbp was powered off during H4d, so "one exact SHA
everywhere" is 3/4. When that host returns, `git fetch && git checkout <merge sha>` restores it -
no rebuild or reinstall is needed unless `macos/` changes.

## Fourth authorized amendment - 2026-07-28, lane observability

**The TCC grants are DONE.** `kTCCServiceAudioCapture` and `kTCCServiceMicrophone` both hold
`auth_value=2` for `com.alphasight.moss.capture`. E3 is closed; never ask the operator for those
clicks again.

With grants in place the canary still fails: `start` succeeds, the first heartbeat returns 200, the
server marks the session terminal and releases it, and every later request returns 403 while the
client still reports `running: true`. `_terminal_reason` fires only on `helper_failed` or all lanes
failed, and the Swift client never sends a top-level `"failed"`, so **both capture lanes are
reporting failed**. The failure code is recorded nowhere:

- `ControlChannelResponse.init(status:)` (`CaptureSecurity.swift:607`) drops `status.lanes`, so the
  response type has no lane data at all;
- the app logs only *unclassified* failures, and a typed lane failure is silent;
- the server's terminal path records a generic reason, skips `_fail_lane`, and logs neither.

This also means the PRD clause **"`mtd-capture status` reports both lanes active" is unimplementable
as shipped** - not failing, but impossible, because the data never reaches the response.

The operator has authorized one scoped cycle, inside `macos/`, `moss_transcribe_diarize/` and
`tests/`:

- **Surface lane state on the control channel.** Carry each lane's `lane`, `state` and
  `failureCode` through `ControlChannelResponse` so `mtd-capture status` can satisfy the PRD clause.
  Counts, states and typed codes only - never audio, never a token.
- **Log typed lane failures in the app**, alongside G3's unclassified-failure logging. A typed
  failure that ends a meeting must not be quieter than an unknown one.
- **Record the terminal reason and per-lane codes server-side** when a helper heartbeat turns a
  session terminal, so the journal names what killed it.
- **Surface a dead session to the client.** `running: true` while every request 403s is the same
  "known but not shown" defect; `status` must report that the session is gone.
- Regression coverage for each in `tests/test_live_pipeline_seams.py` and the Swift suite, red
  before and green after.
- **Gate:** full Swift/Python gate, then one further reviewed no-ff merge through
  `merge-keeper.sh` (advance `expected_main` in-script), push, redeploy, and re-run the probes.

Everything else stays frozen; exactly one further merge. **This cycle is diagnostic groundwork, not
the fix for the lane failure itself** - once `status` names the codes, the cause becomes a normal
candidate and may need its own authorization. Do not guess at the cause before reading the code.

## Fifth authorized amendment - 2026-07-28, survive a lane fault

Candidate 54 is **answered and closed** without any product change: the F3 killer 409 is
`{"detail": "v2 system lane is failed."}`, and the probe proved **the meeting was survivable** - the
peer lane's next frame returns 200 and a heartbeat sent after the refusal returns 200 with the
session still registered. *The only thing that killed F3 was the skipped `emitHealth`.*

The operator has authorized candidates **48, 49, 50 and 53** in one cycle.

**Governing rule, extending the third amendment's:** a fault on one lane must not end the meeting.
No publish failure may stop the heartbeat, and a transient resource condition must not permanently
disable a lane. The session ends only when it genuinely cannot continue.

Three decisions this cycle must make **explicitly, with the reasoning recorded before the patch**:

1. **Is `macos_buffer_overrun` a lane failure or a lane degradation?** `NativeLaneHealth.swift:8,
   217-220` classes it as a failure; `LiveV2Session` then has **no un-fail path**, so one dropped
   buffer disables that lane for the rest of the meeting. Weigh that against a degradation carrying
   a dropped-frame count. The PRD's zero-loss clause is about *accepted* audio; decide what an
   overrun means for it and say so.
2. **May a failed lane recover?** If an overrun stays a failure, decide whether `LiveV2Session`
   gains an un-fail path, and what evidence justifies it. If it becomes a degradation, say what
   still constitutes a genuine lane failure.
3. **What bounds a runaway decode (candidate 50)?** Two of 42 spans decoded at RTF 3.398/3.318 as
   degenerate repeat loops, and the serial queue turns each into the whole latency tail. Neither of
   the plan's ordered remedies attacks it. Choose - cap the decode, abandon the span, or commit it
   partial - and justify the choice against the PRD's zero-loss and speaker-continuity clauses.

Scope, inside `macos/`, `moss_transcribe_diarize/`, `ops/` only where required, and `tests/`:

- **53** - a throwing publish must not skip `emitHealth` (`CaptureController.swift:417`).
- **48 (L1)** - `emitHealth` at `CaptureController.swift:403` sits outside the `do/catch` at
  `:387-402` and before `scheduler.schedule` at `:404`; a failed start-time heartbeat leaves both
  lanes hot with no pump and no recorded refusal, and `alreadyRunning` then blocks recovery.
- **49 (L2)** - `NativeLaneHealth` keeps `projection.failure` across a stop/start inside one
  process. K4 already ruled that "a new session id is a new question"; apply the same argument or
  explain why it does not hold.
- **50** - bound the runaway decode per decision 3.
- Where 53's fix must tell a permanent lane-failed refusal from a recoverable one, it **may** stop
  discarding the server's refusal detail - the two 409s are already distinguishable on the wire.
  That is the only part of candidate 54 in scope; do not widen it further.
- **Close the coverage gap that let this ship:** `tests/test_live_api.py:1055` fails the microphone
  lane and then posts a *system* frame. Nothing in the suite posts a frame **on the lane that
  failed**. Add that, plus red-before/green-after nodes for each decision above.
- **Gate:** full Swift/Python gate; the lane-refusal probe; then **re-run the two red
  certification runs - F1 (60 s canary) and F3 (16-minute soak)** - and require both green, with
  candidate 51's harness fix in place so the label clause is meaningfully verified. Then one further
  reviewed no-ff merge through `merge-keeper.sh` (advance `expected_main` in-script), push, redeploy.

Exactly one further merge. After it the post-merge freeze resumes. **Never ask the operator for the
TCC clicks again** - both grants hold `auth_value=2` and survive rebuilds.

## Sixth authorized amendment - 2026-07-28, live speaker identity

**This overrides the out-of-scope entry for intermittent-speaker identity calibration.** Identity is
the project's purpose; the live path currently cannot do it. Authorized as **Phase N**, and
**sequenced after Phase M's gate** - identity quality cannot be certified on a meeting that dies at
minute 14.6, so 53/48/49/50 finish first.

### Measured evidence (supervisor prototype, real encoder, 2026-07-28)
`voxceleb_resnet152_LM.onnx` on the 4070Ti through the exact production frontend
(`speaker_identity.py:654-677`), four verified-distinct voices.

Same-speaker cosine by segment duration - **vs** cross-speaker max:

| segment | vs full utterance | same-speaker slice-to-slice | min | cross-speaker max |
|---|---|---|---|---|
| **0.5 s** (deployed `min_segment_samples` 8000) | 0.494 | **0.378** | **-0.119** | **0.360** |
| 2.0 s | 0.825 | 0.715 | 0.347 | 0.289 |
| 4.0 s | 0.938 | 0.886 | - | ~0.31 |
| 8.0 s | 0.980 | 0.956 | 0.912 | 0.313 |

At the deployed 0.5 s floor two genuine samples of the **same** speaker agree at **0.378** - below
the deployed `min_match_score` of 0.5 - while two **different** speakers reach **0.360**. The
distributions overlap; identity at 0.5 s is close to undefined. Separation appears at ~2 s.

Accumulation strategies over the same 2.5 s span stream, alignment with an oracle embedding of all
that speaker's audio:

| strategy | oracle alignment | behaviour | encoder wall |
|---|---|---|---|
| **A replace** (`live_provider_bundle.py:597`, today) | 0.770 | oscillates 0.95 -> **0.51** between spans | 2.66 s |
| **B re-embed 0..t** | 0.999 | monotone, but **quadratic** cost and the *worst* short-probe match (0.575) | 15.87 s |
| **C duration-weighted centroid** | **0.975** | smooth | 2.93 s |
| **D quality-gated bank (K=5)** | 0.973 | smooth | 2.87 s |

Encoder cost is linear at ~30 ms per audio-second, so B on a 16-minute four-speaker meeting is
~23 minutes of compute on a GPU the decoder already contends for. **Do not implement B.**

### Scope
- **The core fix is an asymmetry that does not exist today: matching is not enrollment.** One
  threshold currently does both jobs, which is why a 0.5 s fragment can overwrite a good prototype.
  A short span may be *labelled* against a prototype; it must never *become* one.
- Adopt **C**, a duration-weighted running centroid, wired through the `canonical_embedding` hook
  that already exists in `WeSpeakerLiveEvidenceProvider.__init__` and is never passed by
  `_identity_evidence_provider`. Add **D**'s bounded bank only if a prototype must survive a bad
  patch; justify it with measurement rather than taste.
- Raise the **enrollment** minimum to >= 2.0 s. Note carefully: `identity_provider.
  min_segment_samples` is **not** a domain-contract value - the contractual 8000 is the *live frame
  size*, a different quantity that happens to share the number. Do not change the frame size.
  `identity_config.min_match_score` / `min_match_margin` are likewise free, but changing them is a
  decision to record, not a knob to tune until green.
- Keep the abstain path: an ambiguous span must stay unlabelled rather than guess (J2 already ruled
  that an abstain must not end the meeting).

### Gate - measured, not asserted
- A tracked regression that reproduces the duration curve and fails if the enrollment floor is ever
  lowered below the measured separation point. The supervisor's `embed_measure.py` and
  `strategy_compare.py` are the starting shape; they live in the scratchpad, so port what is needed.
- Strategy C must beat A on oracle alignment **and** on same-speaker probe minimum, on the real
  encoder, with the numbers recorded.
- Then F1 and F2 with candidate 51's distinct-voice harness, and the **speaker-label clause
  meaningfully verified** rather than merely present.
- Then one further reviewed no-ff merge (advance `expected_main` in-script), push, redeploy.

**Honest limit of the evidence:** the supervisor's speakers were synthetic TTS voices, which are
cleaner and more separable than humans in a room. The shape of the curve and the ranking of
strategies will hold; the absolute numbers will be worse. Treat 2.0 s as a lower bound, not a
target, and say so if real audio disagrees.

## Seventh authorized amendment - 2026-07-28, a wall clock is not a duration

Candidate 56 is root-caused and the operator authorized the fix as scoped. **This is Phase P and it
comes first** - ahead of Phase N, and before F1 or F3 are re-run as a gate, because until it lands
every certification run dies at ~13 % per 32 s and cannot answer any clause.

**The defect.** `vllm_runner.py:111` computes `elapsed_sec = time.time() - started` on the **wall
clock**. `live_adapters.py:305` takes a correct `time.monotonic()` reading and uses it on the
empty-transcript branch at `:317`, then the success branch at `:344` **discards it** in favour of
the runner's wall-clock value. An NTP step backwards makes `elapsed` negative, which is treated as a
terminal failure: the session leaves `VIEWABLE_SESSION_STATUSES`, later polls 401 and frames answer
the closed-session 409. Five audio hypotheses failed before this was found because the cause was
never in the audio - it is an external periodic event on the host.

Scope, inside `moss_transcribe_diarize/` and `tests/`:

- **(a)** Use the monotonic reading already taken at `live_adapters.py:305` on the success branch at
  `:344`. The correct value is measured and thrown away twelve lines from where it is needed.
- **(b)** Rule **once** that untrustworthy timing metadata **degrades** - `elapsed`/RTF recorded
  null on `canonical_processed` - rather than ending the meeting. This is the third amendment's
  governing rule applied to the fifth instance of its class; state it as the general rule, not as a
  guard on this one field.
- **(c)** A real-seam regression in `tests/test_live_pipeline_seams.py` driving the coordinator with
  a runner whose result carries a **negative** `elapsed_sec` - red before, green after.
- **(d)** Note in the journal that this also repairs the PRD's **decoder p95 RTF** clause, which is
  measured from this same number and has therefore been unreliable in every prior run.

**Sweep the class, do not just patch the site.** Any other place that subtracts two `time.time()`
readings and treats the result as a duration is the same latent failure. Enumerate them; fix or
record each.

**Gate:** full Swift/Python; the seam regression; then one further reviewed no-ff merge through
`merge-keeper.sh` (advance `expected_main` in-script), push, redeploy. **Only then** re-run F1 and
F3 as the Phase M gate. Exactly one further merge; the freeze resumes after it.

**Not in scope, deliberately:** mandatory client-side retention of the 409 refusal body. The
supervisor scoped it as optional in the fifth amendment and it has now cost four cycles of not
knowing why a frame was refused; it remains the right fix and needs its own authorization. Do not
widen this cycle to include it.

## Phase N is SUPERSEDED by ADR-0002 - read this before starting it

`docs/adr/0002-two-tier-diarization-fingerprint-album.md` (Accepted 2026-07-29) and
`docs/design-streaming-diarization.md` are the **authoritative design** for live speaker identity.
They are the operator's own work, committed to this repo, with prototype gates A/B/C passed against
**LibriSpeech** meetings using the production embedder and production live semantics. The sixth
amendment's Phase N was written from a supervisor prototype using four synthetic TTS voices; where
the two disagree, **ADR-0002 wins on evidence**.

What the sixth amendment got right and keeps: replacement at
`live_provider_bundle.py` `_reconcile_committed_vectors` is the defect; the fix is injected through
the existing `canonical_embedding` hook so matcher, abstain and birth semantics are unchanged;
re-embedding 0..t is rejected on O(T^2) cost.

What it got **wrong or incomplete**, corrected here:

- **Parameters.** Use ADR-0002's measured starting values - `min_score` **0.35**, margin
  **0.1-0.2**, admission **1.0-2.0 s**, **k=10** exemplars, sweep every 60 s, merge threshold 0.70.
  The amendment's flat ">= 2.0 s enrollment floor" came from TTS voices; the album's top-k
  admission gate does the work that floor was compensating for.
- **Scope.** Phase N as written is the **album only**, which ADR-0002 explicitly classifies as
  implementation step 1 of 4 and as a **terminal-state failure if shipped alone**: without
  retrospective rewrites, live accuracy diverges from whole-file exactly as the sibling project's
  did at <80%. Do not treat a green album as the finished job.
- **Acceptance bar.** Not "the centroid stops drifting" but ADR-0002's: **>= 90-95% live speaker
  accuracy and demonstrated live->file convergence.** Production's latest-span overwrite measures
  66.4% mean against the album's 98.5%.
- **Implementation order** is ADR-0002's: album -> tape recorder -> sweep -> batch unification, each
  step independently shippable.

**Consequences the operator has accepted and the loop must honour:** the server will retain meeting
audio (~0.3 GB/hr, TTL configurable) - a deliberate change from prune-after-commit, so the PRD's
"no raw audio is persisted" clause must be re-read against ADR-0002 rather than enforced blindly;
the transcript becomes a living document with versioned label rewrites; matcher thresholds need
recalibration against album centroid statistics; sweeps must yield GPU to live spans (ONNX embedding
is CPU-capable, measured 332-343 ms/unit, ~7x headroom under the 2.5 s cadence).

**Open caveat carried from the ADR's own §7:** the prototypes used clean read speech with no overlap
or noise, and assumed in-span local diarization is correct. A real conversational recording is
required before production sign-off. This compounds with the measured hardware limit that m4mbp's
built-in microphone cannot hear a second voice across the room.

Phase N remains authorized. Take it in ADR-0002's shape, not the sixth amendment's.

## Ninth authorized amendment - 2026-07-29, the birth floor, the stop, the RTF gate, the cadence

The operator authorized **candidates 55, 60, 64 and the cadence fix** together. Read
`scripts/ralph-afk/authorization-request-55-60-65.md` **including its iteration-7 correction banner**
before starting: candidate 65 is **withdrawn entirely** - both the session-end sweep (19 corrections
on 31 spans) and the cadence sweep publish on the deployed service, and the two "it never runs"
readings were the loop's own blind instruments.

### (a) Candidate 55 - a birth must not be minted from audio the system refused to embed

Measured: **14 of F2's 16 and 13 of F3's 16 canonical speakers** were born from spans where no
segment cleared the 0.5 s evidence floor, so the encoder was never asked for a vector. F3 on the
deployed Phase N still shows **16 canonicals for 2 voices, saturated at t+138.1 s, 397 empty spans**.

**Decision taken by the operator on the supervisor's recommendation: option 1 - the birth floor sits
at the album's admission (1.0 s of embedded speech).** Predicted 16 -> 1-2 canonical speakers on
these two meetings. Record the reasoning before the patch as the fifth amendment's shape requires,
and state the two consequences explicitly:

- A genuinely new speaker whose first turn is short is **deferred, not lost**: the span publishes
  unattributed under `S00` (J2), the ledger retains it, and a sweep relabels it retrospectively.
  That is only acceptable because a sweep **demonstrably publishes** - which is now measured, and is
  the reason this option was chosen over the weaker "any embedded speech at all" floor.
- **ADR-0002's "birth semantics unchanged" is read as constraining the album, not as asserting that
  birth was correct as written.** The operator authorized 55 knowing it changes birth. If the loop
  finds evidence that reading is wrong, stop and say so rather than proceeding.

**Measured wrong, recorded so neither is re-proposed:** raising `max_speakers` (raises references per
voice and should make the sweep *more* inert), and lowering `min_segment_samples` so short turns
produce vectors (at 0.5 s same-speaker agreement is 0.378 against different-speaker 0.360 - the
distributions overlap). The second was the supervisor's own original recommendation and is wrong.

### (b) Candidate 64 - the decoder-RTF gate needs a definition, not a filter

F1 measured p95 RTF **2.365** carried entirely by **3 spans shorter than 0.1 s**, while the same
build measured **0.568 over 648 spans** on F3 and aggregate RTF **0.20**. Rule once, with the
derivation recorded: **state a minimum span duration below which RTF is not a meaningful ratio**
(fixed per-request overhead dominates), derive that bound from measurement rather than choosing it
to pass, and **always report the excluded count** alongside the p95 so an exclusion can never be
silent. A run whose exclusions are unreported does not answer the clause. Do **not** answer this by
filtering the reducer without stating the rule.

### (c) The cadence fix - both halves together, and the enforcing node is the durable part

Measured: `portalCycleSeconds` has three sites and **reaches no scheduling site**, so moving it moves
the reported number and no request rate. `pollDelayMs` has two sites and **0 hits under `macos/`**,
so moving it changes what a browser waits and the gated number by **0.0 ms**. They are causally
disconnected in both directions.

- Moving the Swift constant alone **relaxes the gate while looking like a remedy** - forbidden.
- Moving the server constant alone hands a human 500 ms the PRD number never records.
- **Move both, or neither.** Whatever is decided about the cadence value, ship the **enforcing node**
  that fails if the reported render bound and the actual poll schedule drift apart again. That node
  is the durable part of this item and is required regardless.

The gated fetch p95s are untouched by either constant: they are the app probe's own fetches at
`CaptureLatencyContract.pollInterval` 0.25 s (F3: 4001 samples over 1019.724 s = 0.2549 s implied).

### (d) Candidate 60 - a clean stop must reach the server

Correctly priced at last: the route works, the portal's Stop button calls it, and a stop through it
revoked view authority in 0 s. **The Mac client simply does not call it**, so `mtd-capture stop`
leaves view authority alive for up to the 30 s helper lease (measured 29.4 s / 29 s) and skips the
final sweep. A transport call after the final drain, with the fifth amendment's rule that a stop
which cannot reach the server must still stop locally. It buys neither convergence nor the
`identity_finalized` event - fix it on its own merits.

### Coverage this cycle must close

Nothing in the suite asserts **what a canonical speaker was born from**. Add a red-before /
green-after node per decision above, and one that fails if a birth can be minted from a span with no
embedded evidence. That gap is what let all of this ship green.

### Gate

Full Swift/Python; the accuracy harness showing the birth floor's effect on canonical count; then
**F1 and F3 re-run** - F1 is where the latency and RTF rulings are proven and F3 is where the
canonical count and the stop revoke are. Then one further reviewed no-ff merge through
`merge-keeper.sh` (advance `expected_main` in-script), push, redeploy. Exactly one merge; the freeze
resumes after it.

Out of scope: ADR-0002 step 4 (batch unification), now measured at **100 % for the album engine
against the shipped resolver's 80 %**, and worth its own authorization later.

## Constraints

Non-negotiable, in addition to the rules in prompt.md:

- **Domain-contract values.** These are part of the domain contract, not incidental constants,
  and must be implemented exactly rather than "generalized away": canonical live sample rate
  16000 Hz; lanes exactly `system` and `microphone`; live frame size 8000 samples (0.5 s); pump
  interval 0.5 s; `hard_cap_samples` 40000 (2.5 s); `min_silence_samples` 8000 (0.5 s);
  `max_retained_samples` 960000 (60 s); client outbox 15 s per lane; helper lease 30 s; view
  authority active-session-only; view absolute cap 12 h; batch port 7860 plaintext; live port
  7861 TLS; bundle id
  `com.alphasight.moss.capture`; app path `/Applications/MOSSCapture.app`.
- **Timestamp units are contractual.** `capture_timestamp_ns` is converted nanoseconds in one
  Mac host-time domain, never raw `hostTime`/`mHostTime` ticks. The app-owned latency probe may
  use view authority internally but must expose only aggregate timing evidence; the CLI never
  receives the token.
- **One writer.** This loop is the only autonomous writer on this repo. The governed
  `aisight-coding-loop` control plane must stay halted — its `.stop-after-current-role` sentinel
  must not be removed. Never invoke `scripts/promote-keeper.sh`, `scripts/revert-feature.sh`, or
  anything under the control plane's `scripts/`.
- **Do not touch `scripts/aisight-coding-loop/`.** It is an inert older loop bundle whose files
  have the same names as this one. Read and write only `scripts/ralph-afk/`.
- **The certificate pin deliberately bypasses PKI.** `PinnedCertificateURLSessionDelegate`
  compares the leaf SHA-256 and does not call `SecTrustEvaluate`. That is correct for an
  exact-leaf pin on a private tailnet. Do not add chain or hostname evaluation.
- **Never weaken security posture to make a step pass:** no disabling SIP or Gatekeeper, no
  global trust changes, no plaintext live transport, no widening the private-network peer
  allowlist, no public-internet exposure.
- **TCC cannot be scripted.** Microphone and System Audio Recording grants require physical GUI
  clicks on m4mbp. When the loop reaches that point it must record the exact click sequence in
  progress.txt as a blocker and move to another candidate — never retry, never attempt to write
  the TCC database.
- **Deploy only a reviewed SHA.** Push and deploy only after the relevant work item's gate is
  green and the one keeper merge is complete. Never deploy from a feature branch, never
  force-push.
- **Preserve the historical IDEA-044 checkpoint without making it the final production
  contract.** The registered eleven-command gate requires Keychain to remain the default and
  restricts product changes to thirteen paths. Run and record that gate before changing the
  production secret-store default, outbox, pacing, resampling, server authority, or ops. Those
  later authorized changes deliberately supersede the lab-only source/locality expectations;
  they require their own behavioral tests and full-suite gate. Never weaken or rewrite the
  historical controls to manufacture a green result.
- **Reversibility.** Every server or Mac mutation must have its rollback command recorded in
  progress.txt before it is applied.
- **Out of scope** (see plan D12): the RTX 4090, durable transcript persistence and export,
  speaker rename/merge, search, browser-initiated capture start, linking `/live` from the batch
  UI, a Windows client, Developer ID or notarization, provisional/partial decode, and
  intermittent-speaker identity calibration.

## Budget and stop

- The launcher argument sets the iteration budget; one logical change per iteration.
- `<promise>COMPLETE</promise>` is permitted only after the full acceptance bar is met.
- If every remaining item depends on input the loop cannot obtain (normally physical TCC clicks),
  record the exact blocker and emit `<promise>BLOCKED</promise>` instead. Blocked is not complete.
- A blocker ends the iteration, not the loop: record it, commit anything useful, and let the next
  iteration attack it or route around it.
