# Rolling eviction recovery — 2026-09-11

Question: can an admitted rolling window survive a 16.5-second wait while live PCM
outgrows the 20-second rolling ring? The current round-9 path says pcm_evicted and
never decodes the first window. Minimum primitives: immutable queued window,
contiguous rolling prefix, bounded ring, existing complete audio tape. Do not change
geometry, scheduling priority, identity, or memory capacity. Never read past the
committed audio boundary or publish after abort. No reader means explicit failure,
not invented audio or a jump to newest speech.

Hypothesis: the complete tape already retained for finalization can recover exactly
the next committed ten-second interval. Falsifiers: missing/skipped interval, changed
PCM, increased ring bound, revival of a true decoder failure, or late publication.

```sh
.venv/bin/python prototypes/streaming-diarization/rolling-eviction-recovery/prototype.py
```

The prototype loads candidate logic into a disposable module from pinned 323f1222;
it does not edit production source. It feeds 17.5 seconds, queues the first window,
then feeds another 16.5 seconds before dispatch. Frames have distinct PCM to check
exact payload custody. `results.json` records:

- Baseline: pcm_evicted, one planned window, zero decoded/applied windows.
- Candidate: rolling, three contiguous windows through 30 seconds; one tape read
  for [10,20) seconds; every payload matches the original frames exactly.
- Ring peak and limit both **320,000 samples** in both arms. The original immutable
  request is separate; complete tape is existing bounded deployment retention.

Verdict: absorb the bounded tape read into the existing converger/coordinator seam.
Do not re-plan newest audio: that skips the missing prefix and changes authority.
The runtime regression repeats the 16.5-second queue wait on the real arbiter path;
canonical work is still dispatched first. Tests cover exact PCM, unavailable tape,
no tape, true rolling decode failure, abort before dispatch and abort during a
recovered-window decode. This establishes plumbing, not improved live WER/DER.
