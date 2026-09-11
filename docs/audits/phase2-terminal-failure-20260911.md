# Failed terminal pass: mechanism and Stop boundary

Inspected current source after d98f9845/a187eaa7; no production changes, decoder calls,
or host operations. Round-6 evidence supplied by the operator is one failure message:
`final capture requires final terminal state; observed failed`.

**F1 — This proves a failed final pass, not failure of capture or every round-5 session.**
Live capture status and finalization status are separate. `LiveServiceRuntime.stop`
drains admitted work, stops rolling, sweeps identity, closes capture with exact sample
accounting, then schedules the terminal pass. `LiveSession.apply_text_revision` alone
sets `final`, after accepting a full-meeting replacement. An unsuccessful final pass
retains the already-published rolling surface. Account history can correctly remain
`completed` while finalization is `failed`; qualification now correctly refuses to
call that rolling output final. Round 5 permitted this state, but its macros do not
establish which or how many of its twelve sessions were affected. Round 6 fails fast;
the single message does not identify the case or twelve-session denominator.

## Paths to failed

| Path | Retained event discriminator | Applies to 50–180 second corpus? |
| --- | --- | --- |
| Runner raises inside TerminalTranscriptFinalizer.finalize | outcome=decode_failed; reason=exception class | Yes, any duration: transport/timeout/server error; invalid/empty model response; media processing failure; multiwindow runner failure |
| Runner returns but no usable nonempty, positive-duration segments survive parsing/clipping | outcome=no_transcript | Yes; text can be absent/unparseable or entirely outside the owned interval. VllmRunner normally catches empty/unparseable output earlier as EmptyTranscriptionError, yielding decode_failed instead |
| Exception outside the finalizer's guarded runner call | reason=finalizer_defect | Yes if an implementation/I/O defect occurs: tape operations other than the handled unavailable read, scratch/WAV creation, parsing/mapping/accounting. Runtime logs the traceback |
| Valid proposal arrives after a runtime terminal failure | reason=session_terminal | Possible if the session is aborted/fenced while the terminal work runs; requires corresponding terminal_failure evidence |
| Session refuses terminal text revision | refusal=<specific revision refusal> | Possible if extent/version/epoch/order invariants fail. The normal finalizer fixes source/start, clips segments and resolves overlaps, and Stop drains rolling before scheduling; those invariants make malformed proposals less likely, not an observed explanation |

Revision refusal checks live in `LiveSession._text_revision_refusal`: stale epoch or
text version, wrong source/full-surface start, non-advancing/beyond-committed interval,
out-of-interval/non-advancing/out-of-order segments. `already_finalized` cannot turn
an existing final surface into failed: note_finalization preserves `final`.

Missing/degraded/short tape, missing terminal plan and missing retained tape produce
`unavailable`, not the observed `failed`. No configured finalizer produces
`not_started`. Unmatched speakers publish unattributed segments; that alone does not
set failed. Token-cap metadata alone is not a terminal failure either.

Sources: `app/live_transcript_convergence.py` TerminalOutcome, finalize, _segments_of;
`app/live_service_runtime.py` _begin_terminal_locked, _run_terminal,
_publish_terminal_locked; `app/live_session.py` apply_text_revision,
_text_revision_refusal, note_finalization.

## Duration and provider boundary

The production web CLI passes the shared File runner to build_terminal_finalizer.
For vLLM, build_file_runner constructs WindowedRunner, rather than sending every
whole meeting directly to the bounded canonical decoder. Its production planner gives:

| Audio seconds | Provider audio windows in seconds |
| --- | --- |
| 50 | [0, 50] |
| 60 | [0, 60] |
| 90 | [0, 90] |
| 180 | [0, 150], [120, 180] |

Therefore 180 seconds alone does not establish an oversized single request. Longer
cases add window extraction, a second decode and stitching/identity-resolution seams.
Short cases still reach provider errors, no usable output and proposal failures.
Do not blame 180-second window stitching without the failed case ID: the frozen
manifest begins with 50-second mono_javier_intro_50s, but later cases could fail too.

VllmRunner raises EmptyTranscriptionError for zero generated tokens, empty text or
zero parsed segments. HTTP/connectivity errors produce RuntimeError or
TransientTranscriptionError. WindowedRunner can wrap a window failure in
WindowTranscriptionError. The finalizer retains only the class as reason to avoid
putting transcript-bearing exception text in public events. Current host configuration
and actual decoder response are uninspected.

## F2 — Failed finalization does not itself cause a non-200 Stop

New local tests exercise the real Account HTTP route, runtime and normal threaded
terminal scheduler with controlled provider output. In all three cases below:
Stop returns 200; the later snapshot is status=closed, finalization_status=failed,
terminal_failure=null; rolling text remains; owner history is completed.

- provider raises RuntimeError -> decode_failed;
- provider returns no terminal text -> no_transcript;
- finalizer throws ZeroDivisionError -> finalizer_defect.

A manually paused terminal scheduler was unsuitable for the HTTP test because the
Account publication barrier can wait for its terminal publication; switching to the
normal scheduler allowed the route to complete. No HTTP early-return guarantee is
inferred from the runtime's asynchronous scheduling.

Separately, existing local tests demonstrate Stop timing out with pending work,
before terminal finalization starts. HTTP Stop maps drain timeouts to 409,
backpressure to 429, and also rejects mixer/terminal/authority failures.
meeting_modes_history_restart passes no body; the transport applies its own default
deadline. Quality passes deadline=5 after its separate settle phase. These are not
identical probe conditions. The meeting-modes probe also reuses an earlier live ID
and waits for file/URL jobs before attempting Stop. Its actual refusal body is needed
to distinguish stale/expired capture from pending work or other failure.
audio_durability_download calls meeting_modes_history_restart when its seeded meeting
lists are absent, so those two identical messages can share that earlier probe failure.

A shared provider outage/latency problem could cause both types of failure through
different paths. It is not proven by finalization_status=failed. The tidy direct
causal hypothesis is rejected by the local HTTP tests; an underlying common cause
remains unknown.

## F3 — Evidence needed to name the actual cause

For the failing round-6 case, inspect the existing `terminal_finalization_failed`
event payload: outcome, reason, refusal, applied, end_sample, tape_samples,
window_count/completed_windows, generated_tokens, and decode_elapsed_sec. Also retain
the case ID and snapshot terminal_failure. For finalizer_defect, the existing
`moss_transcribe_diarize.live.terminal` warning traceback identifies the exception
(the logger name in source is the authority; no log was read here). For the other
predicates, retain the actual Stop HTTP status/refusal body. These are existing-run
evidence, not a request for another qualification run.

The strict collector's one-line error reports the terminal state, not its cause.
No specific production correction is unambiguous from that line alone. No fix made;
no bounds, identity policy, capture strictness or Stop semantics changed.

Validation:

    .venv/bin/python -m pytest tests/phase2/test_finalization_failure_stop_boundary.py tests/test_live_terminal_finalizer.py tests/test_live_terminal_lifecycle.py tests/phase2/test_runner_composition.py -q

49 passed, 19 subtests passed. Additional Stop-deadline selection: 2 passed.
Window-plan table above evaluated with production plan_windows, with no decoder.
