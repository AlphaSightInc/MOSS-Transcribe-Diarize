# M0b — the trace says what the decoder did (2026-08-25)

**Question.** When a live span publishes nothing, does the trace name the ending that actually
happened?

**Answer: no, until this change.** Every one of the three endings arrived at the coordinator as
`transcript=""`, so all three were reported as `decoder_returned_no_transcript` — including the
spans where MOSS emitted real words that the parser rejected. `decoder_returned_unparseable_
transcript` existed in `live_coordinator.py` and was unreachable.

## What the seven real lost decodes report now

`dispositions.json` — the raw decodes the deployed service returned during the 2026-08-24
paired baseline (`prototypes/live-file-gap-emptyspan/out/d3.json`), each pushed back through
the production seam with only the socket replaced (`VllmRunner.transcribe` →
`RunnerBoundedWavInference` → the coordinator's naming).

| | before | after |
|---|---|---|
| reason reported | `decoder_returned_no_transcript` ×7 | `decoder_returned_unparseable_transcript` ×7 |
| generated tokens reported | 0 ×7 | the decode's own count (13–24), all 7 preserved |
| transcript published | `""` ×7 | `""` ×7 — **unchanged** |

The publishing policy did not move: these spans still commit empty. Only the observation
survives, which is the whole of A0.2. Deciding to *keep* those words is E1/M1 and is gated
separately.

Reproduce:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/replay_saved_decode_dispositions.py \
  --output evidence/live-convergence-0824/M0b-decode-disposition/dispositions.json
```

## Where the fix sits

- `app/transcription_outcome.py` — `EmptyTranscriptCause` (`no_generated_tokens` / `empty_text`
  / `unparseable_text`); `EmptyTranscriptionError` carries the cause, the raw answer and the
  token count as attributes. Same type, same message, so no batch caller changes.
- `app/vllm_runner.py` — each of the three raises names which condition it was.
- `app/live_adapters.py` — the catch that flattened everything now keeps `empty_cause` and the
  real token count on `InferenceTranscript`. **The raw words stay on the exception**: telemetry
  never receives them (A0.2's "do not log raw words"), and M1's salvage policy is the one
  caller entitled to read them at this seam.
- `app/live_coordinator.py` — `_decode_empty_reason` believes a decoder that reports its cause
  and falls back to reading the transcript for one that does not, so scripted adapters, replay
  and the deployed runner all get the same vocabulary. `canonical_decode_generated_tokens` rides
  on `CoordinatorWorkResult`.
- `app/live_service_runtime.py` — `canonical_decode_generated_tokens` on `canonical_processed`.

Two causes deliberately share one trace name: a decode that emitted no tokens and one that
emitted only whitespace both returned no transcript. The token count on the same event is what
separates them — that is why the count had to travel, not just the name.

## Tests are tripwires, not restatements

`mutation-check.txt` — five separate mutations of the shipped behavior, each run against
`tests/test_live_pipeline_seams.py` + `tests/test_vllm_runner.py`:

| mutation | caught |
|---|---|
| adapter drops `empty_cause` | 2 failed |
| adapter reports `generated_tokens=0` again | 2 failed |
| coordinator ignores the reported cause | 2 failed |
| runner labels unparseable text as empty text | 3 failed |
| event drops `canonical_decode_generated_tokens` | 1 failed |

Control green before and after (68 passed). `test_every_cause_a_decode_can_report_has_a_name_in_
the_trace` asserts the cause→reason map is exhaustive over the enum, so a fourth ending cannot be
added without being named.

## File mode is unchanged

`file-mode-decoder-head.json` vs `file-mode-decoder-campaign.json` — the same six canned answers
(three good, three no-speech) through `VllmRunner.transcribe`, run once against a `git worktree`
of HEAD and once against the campaign tree, `elapsed_sec` excluded as a measurement of the
process rather than of the code:

```bash
diff /tmp/decode-identity-head.json /tmp/decode-identity-working.json   # identical
```

Identical, including the messages of all three rejections. The file pipeline's other modules
(`windowed_transcription.py`, `inference_utils.py`, prompt) are untouched by this diff, so the
byte-identity obligation is met at the only seam this change reaches. The service-level file-arm
re-check is M0d's, after the deployed service is restarted onto the campaign branch.

## Full suite

`.venv/bin/python -m pytest tests/ -q` → 979 passed, 2 skipped, 386 subtests (88 s).

## What this does not do

It does not distinguish a **refusal** from any other unparseable answer — the observed
`"I'm sorry, I can't assist with that request."` is `unparseable_text` here, correctly, because
recognising refusal boilerplate is `classify_live_transcript`'s job (plan §6 M1: "callers must
not repeat those rules"). M1 adds the refusal verdict on top of this vocabulary rather than
beside it.
