# Round 6 terminal finalization: code mechanism and evidence retention

The candidate does **not** send the 600-second tape as one decoder request. The terminal
pass does use much larger windows than live decoding, but those requests are bounded at
150 seconds. The retained `WindowTranscriptionError` type is insufficient to establish
which decoder or validation condition failed. No finalizer behavior is changed here.

## Code path (unchanged between round-six 9fa8ee85 and base 887e76a0)

1. `app/phase2_web_cli.py:_build_file_runner` constructs the runner also supplied to
   `_build_live_runtime_factory` / `build_terminal_finalizer`.
2. `app/runner_composition.py:build_file_runner`, for the deployed `backend=vllm`, returns
   `WindowedRunner(VllmRunner(...))`. The terminal finalizer receives this wrapped runner;
   Live's causal decoder is a separate runner.
3. `app/live_service_runtime.py:stop` drains live work, records `session_closed`, then
   `_begin_terminal_locked` records `terminal_finalization_started` and schedules
   `_run_terminal` outside the Stop request's clock.
4. `app/live_transcript_convergence.py:TerminalTranscriptFinalizer.finalize` reads tape
   `[0, plan.end_sample)`, writes a whole-meeting WAV, and calls the wrapped runner.
   Tape capacity is bounded by the provider manifest: round six allowed 19,200,000 PCM16
   bytes, or 600 seconds at 16 kHz mono. Missing tape coverage is refused separately.
5. `app/windowed_transcription.py:WindowedRunner.transcribe` probes WAV duration and uses
   `plan_windows`: 150-second windows, 120-second stride. A 600-second recording produces
   `[0,150]`, `[120,270]`, `[240,390]`, `[360,510]`, `[480,600]` seconds. Each window is
   extracted separately and sent through the delegate. A recording at most 120 seconds
   takes the single-window shortcut and is submitted directly, still below the cap.
6. `app/vllm_runner.py:VllmRunner` sends each window to `/v1/audio/transcriptions`.
   The captured round-six configuration uses `http://127.0.0.1:8000/v1`, max length 16384,
   max new tokens 12000. These bounds do not prove successful output on every window.

## What can raise WindowTranscriptionError

`WindowedRunner._transcribe_windows` wraps any extraction/delegate exception with the
window index and interval. A decoder exception can include HTTP/transport failure or the
VllmRunner's rejection of zero generated tokens, empty text, or unparseable text.

The window runner also raises directly for zero generated tokens, empty transcript text,
or zero parsed segments. Stitching rejects an empty segment list. Checkpoint validation
has related errors, but terminal finalization does not supply a checkpoint directory.
A token-cap hit is marked `possibly_truncated`; it is not by itself this exception.

The finalizer catches the exception and records `outcome=decode_failed` and only its class
name as `reason`, deliberately excluding potentially sensitive exception text. Therefore
round-six `reason=WindowTranscriptionError` does not identify the failed window or inner
cause. Larger-window failure remains plausible, not proved. The one-request 600-second
hypothesis is ruled out by the deployed composition.

A failed terminal finalization leaves the rolling surface in place and sets
`finalization_status=failed`; it does not itself make previously accepted live decoding
unsuccessful. Qualification requiring a genuine final surface still correctly fails.

## Evidence changes

- Runtime records a content-free `stop_requested` event and monotonic timestamps for
  Stop/closed/terminal/abort events, using the existing runtime clock.
- Capacity projections retain session ID, event sequence, snapshot version, timestamp,
  refusal/submission-refusal fields, and Stop/closed/terminal lifecycle events alongside
  canonical and rolling decode records. Failure messages and transcript payloads are omitted.
- Quality replay writes a registered `quality/pass-N/CASE/terminal-diagnostics.json` in a
  `finally` block, including on replay or final-capture refusal. It projects status-only
  trace evidence and reads the remaining service events before cleanup. Event-read failures
  retain only their type. Existing artifact copying preserves this JSON before the runner
  deletes its measurement workspace. No raw traces, snapshots, audio or credentials are copied.
- A retention test exercises replay failure, copies the registered artifact, deletes the
  campaign directory, and verifies that diagnostics survive while transcript/credential
  sentinel strings do not. Runtime tests verify Stop → closed → finalization-started →
  finalization-failed ordering, timestamps and projected identity/refusal fields.

Validation: 219 tests passed across the three acceptance/runtime/replay files and three
terminal lifecycle/finalizer/boundary files (plus their subtests). No host operations,
cutover, service restart, admission, qualification run, gate change or identity-policy change.
