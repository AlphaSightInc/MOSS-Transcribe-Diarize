# M1 — bounded malformed-output salvage, shipped (plan §9.3)

Iteration 7 of run 20260825-042645-70858, 2026-08-25.

**What this milestone is.** Five of eighty trio spans were correct words the parser threw away
for one reason: the decoder stopped without writing its closing timestamp. The words were in the
answer; the grammar rejected the answer; the span committed empty. This ships the one module
that decides what such a span may publish, and wires the live decode seam through it.

## What shipped

| file | change |
| --- | --- |
| `app/live_endpoint.py` | `HARD_CAP_REASON` named beside the only code that emits it; the two literals replaced |
| `app/live_span_bounds.py` | `classify_live_transcript` + `LiveTranscriptOutcome` / `LiveTranscriptDisposition` |
| `app/live_adapters.py` | the `EmptyTranscriptionError` catch routes `exc.text` through the policy; `InferenceTranscript.salvage_disposition` |
| `app/live_coordinator.py` | `decode_salvage` / `canonical_decode_salvage` carried to the result |
| `app/live_service_runtime.py` | `canonical_decode_salvage` on the `canonical_processed` event |
| `tests/test_live_transcript_salvage.py` | the ten zero-parse decodes + five constructed spans, as a table |
| `tests/test_live_pipeline_seams.py` | four seam/runtime tests for the salvage path |

**The policy, in one paragraph.** A span whose decode parses to nothing is offered to
`classify_live_transcript` — but only when the decoder reported that it *produced* an answer the
grammar rejected (`EmptyTranscriptCause.UNPARSEABLE_TEXT`); a zero-token decode has no answer to
repair, whatever text arrived beside it. Absent *outer* bounds are supplied from the span's own
bounds. Adjacent chunks sharing a speaker with no timestamp between them are merged, losslessly.
An absent *interior* boundary is filled only from a timestamp the decoder actually emitted, and
two *different* speaker labels with nothing between them are refused whole — a guessed
cross-speaker boundary would hand the identity path an interval holding another voice (plan D5).
The completed transcript must survive parse → render → parse. Finally the gate: only a hard-cap
span may be salvaged.

## Two deliberate deviations from the plan's §6 sketch, both measured

1. **No `speech_ratio` parameter.** Plan §9.1 conditions it on choosing O2; iteration 6 measured
   O1 (`M1a-salvage-gate-comparison/`). Shipping a parameter with no reader would be scaffolding.
2. **No refusal-boilerplate phrase list.** Its marginal load over the 184-span corpus is zero:
   all six observed hallucinations sit on `leading_silence` freezes, which the gate refuses, and
   0 of 163 hard-cap spans produced one. A table of English apologies is a fact about one decoder
   in one language, which `AGENTS.md` rules out of general logic. The residual it accepts —
   boilerplate on a hard-cap span would publish — is stated in the module docstring and pinned by
   `test_the_gate_is_what_refuses_the_hallucinations_not_the_words`.

## Validation

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
      prototypes/streaming-diarization/live-convergence/verify_production_salvage.py

`corpus-reproduction.txt` — exit 0. The **production** module reproduces the adjudicated O1
column over all 184 corpus spans and all 5 constructed spans: 174 `parsed`, 2 `salvaged`, 8
`refused_gate`. (Six of those eight were `refused_boilerplate` in the prototype; production
refuses them for a fact about the span rather than about the sentence. Same decision.)

    .venv/bin/python -m pytest tests/ -q

1012 passed, 2 skipped, 386 subtests, 88 s. Targeted run in `pytest-targeted.txt` (108 passed).

**File mode byte-identical.** `probe_file_mode_decode_identity.py` against a HEAD worktree:
`file-mode-head.json` and `file-mode-worktree.json` share sha256
`ad381d8bd247e4a8ebe56240dfbc29c0b5a86ffb35a2fcb411c07bbd5b7707f2`. Expected by construction —
nothing on the file path was touched — and checked anyway, per the PRD.

**Mutations** (`mutations.txt`), five, all caught:

| # | mutation | caught by |
| --- | --- | --- |
| M1 | gate accepts every freeze reason | 11 tests, incl. the runtime trace test |
| M2 | interior boundary interpolated instead of refused | the three two/three-speaker rows |
| M3 | adjacent same-speaker chunks not merged | bill 02 loses its 8 words |
| M4 | salvage decision dropped on the publishing branch | the runtime trace test |
| M5 | zero-token decodes offered to salvage | the no-speech disposition tests |

## What is NOT closed

The **E1 exit gate** — the paired live/file rerun on the deployed service — has not run. The
service is still on the pre-M1 build. Protocol and gates are preregistered in
`PREREGISTRATION.md`, written before any measurement. Predicted: trio live WER `.1885`
(gate `<= .190`), moving on exactly one span (`lex_bill_ackman#02`, 8 words, `.2614 → .2273`),
milei and keyu unchanged.
