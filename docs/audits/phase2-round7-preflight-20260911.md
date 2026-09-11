# Round 7 regression pre-flight

Audited 513c9d5f (round 5) through d98f9845 (proposed round 7), including ab6fdc3d,
76e58d16, f1f33168, 9fa8ee85, f484c635 and d98f9845. No host operations.

**No demonstrated new failure in a round-5 passing predicate. No production fix
justified by this audit.** This is not a prediction that round 7 passes. The known
Stop refusal remains unresolved, quality has not been measured with the stricter
capture locally, and several previously failing predicates will now reach checks
that round 5 never exercised.

Round-5 status source: the locally retained `scratchpad/issue10-round5.md`: deployed
8 pass / 11 fail, pre-admission 7 pass / 10 fail, zero unmeasured. Its complete failure
list and the wave-3 required predicate set determine the pass complement below;
individual passing raw observations were not available locally. The source's earlier
Stop-unification theory has been refuted and is not used here.

## Ranked risks

Ranking is qualitative exposure, not a measured probability. Separate newly strict
failures from regressions in formerly passing predicates.

**R1 — Highest exposure: quality_corpus, both layers, previously FAIL.** 9fa8ee85 waits
for canonical AND rolling work, raises after 30 seconds instead of sampling, rejects
event gaps, and requires finalization state `final`. A slow drain, lost event history,
or `failed`/`unavailable` terminal state now gives an explicit failure instead of a
mislabelled surface. The six-case probability is unmeasured locally; frozen identity
results cannot answer it. Do not relax these checks. The 30 seconds is a polling
budget, not a total transport bound: synchronous HTTP calls can take additional time.

A concrete conditional exposure: the Account adapter sends heartbeats during frame
ingress but not snapshot/event reads during settling. The helper lease is explicitly
configured (no CLI default); expiry interrupts capture. If the remaining lease is
shorter than the drain, waiting can encounter helper expiry. This omission predates
the patch, but waiting for rolling work increases exposure. The host's current lease
and drain times are uninspected, so no lease or heartbeat patch is made on speculation.

**R2 — Likely visual-difference exposure: transcript_pane_fidelity, both layers,
previously FAIL.** ab6fdc3d changes the speaker legend, adds row buttons, changes
continuation padding/margins and hides repeated metadata. These are inside the captured
transcript pane; the 2% pixel-difference and 1% largest-region limits are unchanged.
The nav/voice-bank section is outside the isolated pane and does not itself alter the
capture, but the transcript changes can. No current-versus-reference screenshot
measurement was run in this audit; no pixel failure is asserted. f484c635 fixes meeting
selection, not the previously observed reference/candidate preparation timeout or
potential visual mismatch. This is residual risk in an already-failing predicate.

**R3 — Lower, conditional risk to a previous PASS: zero_work_end, both layers.** A new
strict quality exception could contaminate later work if abort fails. Checked the
actual exception chain: SurfaceCaptureService raises ServiceReplayFailure;
run_service_replay catches it and invokes wrapper.abort, which directly delegates to
the Account adapter. Added two local production-replay tests: settle timeout and
nonfinal Stop both attempt abort and leave the session terminal, with no final capture.
This disproves an unconditional leak from the new exception. An HTTP abort failure
is still swallowed by the existing best-effort replay cleanup; zero_work_end remains
the failure detector. Such a failure was not reproduced and that code is unchanged.
Revocation is scheduled late and zero-work after cleanup, as before.

**R4 — Lower, newly reached paths: browser_final_summary and crash_recovery,
previously FAIL.** The fixes permit the real long-running summary/retry/load checks
and the actual forced-restart oracle to run. Round-5 results provide no evidence that
those later checks pass. This is increased coverage, not proof of a regression.
Crash restarts can interrupt cached live sessions, but the later observer predicate
creates a new A session, voiceprint tests create fresh sessions, and revocation creates
a new B session. Earlier passing identity/isolation/convergence checks execute before
the crash. No deterministic new failure was found in that ordering.

## All 36 predicate executions

D = deployed, P = pre-admission. PASS denotes the round-5 result inferred as described
above. “No new break found” is scoped to this diff, not a live requalification claim.

| Predicate | D / P round 5 | Delta and regression assessment |
| --- | --- | --- |
| installed_candidate_identity | PASS / PASS | Producer, evaluator and installation identity mechanics unchanged. Frontend/artifact bytes change legitimately with candidate; installer must package the new candidate as usual. No new break found. |
| zero_work_end | PASS / PASS | Producer and campaign cleanup unchanged. Newly strict failure paths tested; R3 is residual transport-dependent exposure. |
| cross_owner_matrix | PASS / PASS | Producer/API authority and owner-state digest unchanged. Nav has no role in its HTTP matrix. Its existing explicit live-title install is unchanged. No new break found. |
| sentinel_absence | FAIL / FAIL | Explicit audio-title install and exact readback repair missing setup; isolation scan unchanged. Rendered meeting selection now excludes fallback. No loosening. |
| same_account_convergence | PASS / not scheduled | Producer and compared owner HTTP snapshots unchanged; runs before restarts. No new break found. |
| browser_workspace_identity | PASS / PASS | Entire producer unchanged. Uses bootstrap/signed-in attributes, locks, cookies and APIs, not duplicated heading text. Bootstrap script unchanged; added nav/voice bank neither creates a second auth root nor sends initial voice-bank mutations. No new break found. |
| revocation_lifecycle | PASS / PASS | Producer, durable publication, account revocation, archive decoding and isolation checks unchanged. Fresh B live session, late execution; browser layout unused. No new break found. |
| meeting_modes_history_restart | FAIL / FAIL | Upload controls remain unique, added input label preserves name; Stop change is diagnostic only. Known non-200 Stop refusal remains unaddressed. |
| crash_recovery | FAIL / not scheduled | Correct durable revision field now reaches the crash oracle; R4. Missing/zero revisions and empty segments still reject before killing. |
| four_session_capacity | FAIL / FAIL | Reads actual kv_cache metric while requiring real finite usage; decoder, load and thresholds unchanged. Later load checks were not cleared by the prior absent-metric failure. |
| eight_session_overload | FAIL / FAIL | Same metric repair; overload/backpressure requirements unchanged. No passing baseline to protect. |
| quality_corpus | FAIL / FAIL | R1. Bounds, validator and identity policy unchanged; observations/diagnostics added. No claim that strict captures or speaker metrics pass. |
| audio_durability_download | FAIL / FAIL | Seekable ffprobe input repairs duration measurement; codec/duration/durability requirements remain. Still depends on the unresolved meeting_modes Stop path. |
| operator_control | FAIL / FAIL | Same ffprobe repair; operator controls unchanged. It is not established as a Stop-path symptom. |
| account_product_regression | FAIL / FAIL | Correct section order after voice-bank move; shared scoped opener fixes duplicate-card count; diagnostic now names observed count. Export title/roles unchanged by nav; real local browser verifies scoped history behavior. |
| transcript_pane_fidelity | FAIL / FAIL | Scoped opener repaired; R2 remains. Prior timeout is not proven fixed by locator repair. |
| voiceprint_production_rule | PASS / PASS | Calls the same fresh-embedding qualification bench and unchanged identity rule; no frontend dependence or bench/policy delta. No new break found. |
| voiceprint_workspace_behavior | PASS / PASS | API-only enrollment/rename/delete/recognition predicate, unchanged. Newly duplicated Name speaker buttons are not selected by this predicate. Voice bank still starts empty because frontend changes do not automatically enroll. No new break found. |
| browser_final_summary | FAIL / FAIL | Scoped meeting/Refresh/settings locators remove proven ambiguity without first/nth; later summary checks unchanged and previously unreached. R4. |

## Evidence and checks

- Inspected complete source diff; production application changes are workspace HTML
  and frontend only. Capture strictness lives in the shared measurement harness;
  the live runtime and identity implementation are unchanged.
- AST comparison confirms installed identity, zero-work, cross-owner, same-account,
  revocation, voiceprint producer methods, campaign cleanup, browser_workspace_identity,
  external_requirements and _validate_quality unchanged between the two audit endpoints.
- Followed actual scheduling in `phase2_acceptance_measure.measure_layer`, replay
  exception handling in `live_service_replay.run_service_replay`, and Account abort
  delegation. Strict capture exceptions do not bypass the existing abort attempt.
- Local shipped-DOM regression already exercises duplicate fallback cards, nav text,
  scoped meeting selection, Final summary visibility and dual Refresh buttons.
- `pytest tests/phase2/test_wave1_qualification.py tests/phase2/test_browser_workspace.py
  tests/phase2/test_acceptance_locator_sentinels.py tests/phase2/test_quality_surface_capture.py -q`:
  **138 passed**. Includes two new strict-capture/replay cleanup tests; no provider calls.
- The d98f9845 full-suite result remains 1,234 Python passed / 2 skipped /
  37 subtests passed, 155 frontend passed. This audit adds two passing tests only;
  it does not claim a new full-suite run or new host qualification.

## Decision

Preserve the stricter gates and the demonstrated fixes. No speculative production
change is warranted. Before consuming another full host run, use the already-running
round-6 retained evidence to resolve the Stop refusal and distinguish quality timeout,
event loss, failed finalization and genuine metric misses. That recommendation needs
no new decoder experiment or interruption of the current run. This audit alone cannot
clear those outstanding failures or establish that round 7 is admission-ready.
