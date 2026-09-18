# WP10 prototype verdict — where an all-zero span leaves the decode path

**Question.** Where in the live path can an all-zero / all-`silent` span be excluded from
decoding so that (a) no model request is made for digital silence, (b) every decoder-seam
contract is preserved (empty causes, salvage gate, token-cap accounting, failure vs nothing to
say, terminal `final`), (c) accounting/timeline/sequence continue, and (d) the identity path
births no speaker from it?

**Answer: candidate 1 — at dispatch, never inside a decode seam.** The predicate belongs to
the audio, the decision belongs to whoever is about to send it, and the decode seam must keep
reporting only what a runner said.

## The harness

Two halves, both real code, one command each:

* `run_candidates.sh` — checks out each candidate branch in this worktree and runs the five
  files holding the 19 regressed contracts plus WP3's two guard files.
* `falsify.py` — drives the real runtime, real coordinator, real `CompleteMixedTape` and the
  real identity-preparer seam with a runner that records and raises if it is ever asked to
  decode, and checks requirements R1–R8 (a–d above, plus WP3's "one nonzero sample among zeros
  still decodes"). Logs: `evidence/mvpfix/wp10/`.

## Measured matrix (2026-09-18)

| candidate | seam contracts (147) | WP3 guard tests | requirements |
|---|---|---|---|
| **1 — dispatch guard** (`mvpfix/wp10-zero-guard-seams`) | 146 pass, 1 pre-existing fail\* | 40/40 | **7/7** |
| 2 — mixer declares the span silent (`proto/wp10-c2-mixer`) | 146 pass, 1 pre-existing fail\* | 37/40 | 3/7 |
| 3 — guard inside the adapter, WP3 as merged (`proto/wp10-c3-adapter`) | **128 pass, 19 fail** | 40/40 | 7/7 |

\* `tests/phase2/test_draft_lane.py::test_reader_retires_draft_by_audio_boundary[multiple]`
fails on all three candidates and on the integrated branch with both WP3 guards reverted, so
it is not a zero-guard regression. Cause and fix below.

### Why candidate 3 (WP3 as merged) fails

`RunnerBoundedWavInference.transcribe_pcm` is the seam that turns a runner's answer into a
fact. A guard that returns before consulting the runner cannot produce any of those facts, and
the tests that pin them necessarily hand the seam PCM — written, as fixtures are, as zeros:

* `test_the_decode_seam_publishes_a_salvaged_span_and_says_that_it_salvaged_it` and
  `test_the_decode_seam_refuses_the_same_answer_on_a_span_frozen_for_silence` — M1 salvage
  never runs; the salvaged text and the refusal both disappear.
* `test_a_decoder_that_failed_is_not_a_span_with_nothing_to_say` and the eight
  `test_the_real_runner_decides_which_transport_failures_a_later_attempt_could_answer` cases —
  `DID NOT RAISE LiveProviderError`: a failure cannot be classified if nothing was attempted.
* `test_every_no_speech_answer_from_the_real_runner_publishes_nothing_and_says_which_it_was`
  and `test_a_decode_that_emitted_no_tokens_never_publishes_the_text_that_came_with_it` — all
  three empty causes flatten back into one unnamed empty.
* `test_the_live_decode_carries_its_duration_derived_cap_onto_the_wire` and
  `test_a_runner_result_whose_elapsed_sec_is_negative_never_reaches_the_span` — no cap, no
  elapsed, nothing on the wire.
* `test_a_rolling_window_is_never_offered_to_the_M1_salvage_gate`,
  `test_launcher_without_prompt_finalizer_builds_http_request`, and
  `ReplayTerminalFinalizationWaitTest::test_the_run_reports_the_terminal_surface_and_the_events_that_made_it`
  (`'failed' != 'final'`) — same cause at the rolling, launcher and terminal seams.

This is not a fixture problem. There is no PCM a fixture could use that both is silence and is
not: the guard makes the seam's whole contract conditional on the audio, and the seam's
contract is about the *answer*.

### Why candidate 2 (mixer marks the span `silent`) fails

Implemented for real on `proto/wp10-c2-mixer` (mixed `AudioFrame.silent`, silent ranges
recorded on the coordinator, a fully-silent span skipped before dispatch). It keeps every seam
contract — it never touches a seam — and still loses four of the seven requirements:

* **R1 fails.** An all-zero span only skips if a lane *declared* itself silent. A muted device
  that keeps streaming zeros, a lane that renders to zero for any other reason, and any
  replayed or synthesised zero audio all still reach the model. The measured harm is the
  audio, not the declaration.
* **R4, R5 fail.** The draft lane and the terminal pass have no frames to read a declaration
  from — the terminal pass reads a tape, not a stream — so both remain unguarded.
* **R6 fails.** With the adapter guard removed, an undeclared zero span decodes and publishes
  whatever the model invents; the span is accounted for but its words are fiction.

It is also the most invasive of the three: it puts a new field on `AudioFrame` and a new
interval ledger on the coordinator to carry a signal that `is_digital_silence` reads directly
off the bytes.

## What was implemented (candidate 1)

| piece | where |
|---|---|
| **`is_digital_silence(pcm)`** — the reusable predicate | `moss_transcribe_diarize/app/live_silence.py` |
| `DigitalSilenceGuardedInference` — `BoundedWavInference` wrapper answering `DIGITAL_SILENCE` | `app/live_adapters.py` |
| `bounded_live_inference(runner, *, max_samples, **kw)` — the one composition root all three deployed lanes build through | `app/live_provider_bundle.py` |
| `EmptyTranscriptCause.DIGITAL_SILENCE` → `empty_reason` `span_was_digital_silence` | `app/transcription_outcome.py`, `app/live_coordinator.py` |
| `CompleteMixedTape.has_signal`, read by the terminal pass through `_tape_holds_signal` | `app/live_tape.py`, `app/live_transcript_convergence.py` |

**The name WP1 should use: `moss_transcribe_diarize.app.live_silence.is_digital_silence`.**
A per-lane producer that builds its decoder through `live_provider_bundle.bounded_live_inference`
gets the guard for free and needs no predicate call of its own; one that decides earlier (for
example to skip staging a lane's span at all) should call `is_digital_silence` directly and
publish its own named empty reason, exactly as the canonical lane does — the predicate
deliberately carries no policy.

## Open items and judgement calls

1. **A meeting of pure digital silence reports `finalization_status: "failed"`.** It maps
   through the existing `TerminalOutcome.NO_TRANSCRIPT`, whose reader-facing word is `failed`.
   Nothing failed; the meeting simply held no audio. Fixing that means new vocabulary in a
   contract three surfaces read, which is out of WP10's scope. Carried over from WP3, flagged
   here for whoever owns `TerminalOutcome`.
2. **`test_reader_retires_draft_by_audio_boundary[multiple]`** — pre-existing on the integrated
   branch, unrelated to the zero guard (it fails with both WP3 guards reverted). The reader
   prefers `effective_transcript` over `committed` when the former is present, and the test's
   hand-built second snapshot set `committed` while leaving `effective_transcript` an empty
   list — a snapshot no session can emit, since the surface *is* the commit until a revision
   replaces it. Fixed by making the fixture self-consistent. If WP2's owner reads the
   precedence itself as the defect, the production question is whether a snapshot with
   committed words and an empty surface is reachable; it is not, because a span that commits
   words also contributes them to the surface.
3. **The draft lane counts a skipped decode as `published`.** `draft_stats` reports
   `started: 1, published: 1` for a digitally silent tick that published no draft. Pre-existing
   accounting noise in the draft lane, untouched here.

## Disposition

The prototype has answered its question; `run_candidates.sh`, `falsify.py` and the candidate
branches `proto/wp10-c2-mixer` / `proto/wp10-c3-adapter` are throwaway and should be deleted
with this directory once the verdict is accepted. The validated decision already lives in the
real code and in `tests/test_live_zero_span_dispatch.py`.
