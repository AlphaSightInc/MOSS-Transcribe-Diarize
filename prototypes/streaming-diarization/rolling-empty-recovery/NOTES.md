# Rolling nonzero-empty recovery policy

**THROWAWAY PROTOTYPE — lifecycle evidence only; no production policy change.**

## Contract

- **Structural question:** after a nonzero rolling window yields no usable transcript, does the
  current stop-on-empty policy preserve later base/terminal words without repeated rolling calls,
  including when Stop arrives immediately?
- **Minimum primitives:** nonzero PCM; rolling lane decoder; monotonic rolling converger; complete
  retained tape; terminal finalizer; session publication authority; saved-document projection.
  The first distinguishes silence skipping from model-empty output; the next two own the disable
  state; the tape/finalizer provide recovery authority; session/document prove user-visible words.
- **Invariants:** production state transitions and serializers; no GPU, model, encoder, threshold,
  or production edit; source words are fixed by deterministic decoder scripts; a rolling empty may
  stop refinement but must not erase the base suffix or prevent terminal replacement.
- **Assumptions/unknowns:** scripted empty/nonempty results prove lifecycle only. They do not show
  how often real quiet speech produces an empty response, whether a retry would recover words, or
  whether retries hallucinate.
- **Falsifier:** reject the current policy if it repeats rolling calls after the first empty, loses
  the base suffix, prevents terminal decode, refuses terminal publication, or omits terminal words
  from the saved-document projection.
- **Tool decision:** one offline script drives `decode_refinement`, `RollingTranscriptConverger`,
  `TerminalTranscriptFinalizer`, `LiveSession.apply_text_revision`, and `_transcript_document`.
  Existing tests cover digital-zero skip, exception isolation, and speechless terminal windows but
  not this complete nonzero-empty lifecycle.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
  prototypes/streaming-diarization/rolling-empty-recovery/probe.py
```

## Result

**KEEP current stop-on-empty policy; DEFER retry/re-enable design.** All six lifecycle assertions
passed across the three requested paths:

- **Nonzero empty → later speech:** the first 10 s nonzero window made one rolling call, returned
  no segments, named `lane_refinement_failed`, and moved rolling to `window_failed`. Two later
  10 s audio chunks produced zero plans and zero additional rolling calls. Existing base words
  remained visible. Stop made one terminal call and saved `terminal opening` plus
  `terminal later speech`.
- **Repeated empty responses:** under the current policy they are deliberately unreachable within
  one lane/session. After the first empty, two later scheduling attempts produced zero calls, so
  the provider cannot spend calls returning the same empty result repeatedly. Stop still finalized
  and saved both scripted terminal passages.
- **Stop immediately after empty:** the terminal plan retained `rolling_status=window_failed` and
  `windows_failed=1`; terminal ran once, publication applied, finalization became `final`, and both
  passages reached `_transcript_document`.

Every case used one rolling call and one terminal call. `results.json` records full state, status,
call counts, base words, and saved-document words.

This is deterministic lifecycle evidence only. It does not show that real quiet speech causes an
empty result, that retrying would recover speech, or that retrying would avoid hallucinations.
Without that acoustic benefit/safety evidence, a retry policy has not earned its extra calls or a
new recovery state. Production remains unchanged.

The first script attempt failed before measurement because its fixture omitted the session's
required stable-identity preparation. The fixture was corrected to use the production prepared
identity transaction; no policy or assertion changed.
