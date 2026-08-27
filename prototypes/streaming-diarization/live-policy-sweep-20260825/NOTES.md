# Live policy and peer sweep notes

## Question

Which of shipped `10/10`, `15/10` lexical plus speaker-map, or `15/10` stable-anchor gives the
best pre-Stop speaker-attributed transcript on diverse real speech, and how do fresh actual-live
peer runs compare?

## Verdict

Measured on 6 fully referenced real clips, two MOSS passes (12 accuracy observations plus one
retained RTF-failure replacement), and one fresh six-case LiveTranscribe pass.

- Stable-anchor won aggregate 15/10 accuracy: macro WER `.1059` vs lexical `.1084`, TBSA `.8903`
  vs `.8885`, DER `.1507` vs `.1535`.
- Lexical is the recommended next research default: it captured 94% of stable-anchor's WER gain
  over drained current 10/10, while selected words were available 2.00 seconds earlier on average
  (`6.04` vs `8.05`). Stable-anchor remains the multi-speaker accuracy challenger.
- Current drained 10/10 macro WER was `.1445`; MOSS post-Stop was `.0951`.
- Fresh LiveTranscribe pre-/post-Stop macro WER was `.1536`/`.1812`. ProjectClerk was unmeasured:
  its packaged binary lacked Screen Recording/System Audio permission and captured zero buffers.
- No promotion: 10/10 differential reproduced only `4/12`; canonical p95 RTF failed at `1.06971`
  and `2.4403`; both Jamie sessions entered `pcm_evicted` after five rolling windows.

Full decision and denominators: `evidence/live-policy-sweep-20260825/REPORT.md`.
Production remains unchanged.

## G4 rolling-normalization prototype — 2026-08-25

**Question:** Can the terminal overlap rule safely become producer-neutral and normalize rolling
proposals before `LiveSession` validation?

**Command:**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-policy-sweep-20260825/audit_rolling_normalization.py \
  --sweep evidence/live-policy-sweep-20260825 \
  --output evidence/live-g4-recovery-20260825/normalization-prototype.json
```

**Verdict: PASS.** Across both retained passes, all 122 full 10-second proposals were audited.
The 120 ordinary disjoint proposals were byte-identical after normalization. Both changed
proposals were Jamie window 4: each displaced the second segment by exactly 2,720 samples,
merged/dropped zero, preserved 24/24 words, changed the real session result from
`segments_out_of_order` to applied, and left WER, DER, reference-speech DER, text-speaker
accuracy, speaker accuracy, and matched-word speaker accuracy unchanged. Removing the illegal
0.17-second double-owned extent reduced legacy TBSA by `.000236` through text coverage only;
that is reported, not hidden, and is not a regression in the plan's WER/speaker-score gate.

Raw evidence SHA-256:
`13c16f63546c7e7829148665ab4e96219bb41910d721bdad78f20724fb4876ac`.

The post-A2 producer-neutral prototype script SHA-256 is
`b9e7c4e081d91f683986a5ece4946b61a5c86a9a8221e3319ee521cffe1a0be7`; the raw evidence is
unchanged by the resolver rename.

## G4 cached production-class verifier — 2026-08-25

**Verdict: PASS.** The production converger and real session seam applied cached Pass-A Jamie
windows 0-4. Window 4 displaced exactly 2,720 samples, preserved 24/24 words, merged/dropped
zero, and the accepted frontier queued window 5 `[800000,960000)`.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-policy-sweep-20260825/verify_jamie_rolling_recovery.py \
  --output evidence/live-g4-recovery-20260825/jamie-production-class-probe.json
```

Raw JSON SHA-256:
`58b73ae2cce44d2e879002646281d820c8241d61afbd31805633b64ba87800bf`.

## Goal 2 causal 15/10 lexical prototype — 2026-08-25

**Question:** Can the saved batch 15-second-window / 10-second-stride lexical rule become a
causal, append-only publisher through the production `LiveSession` seam?

```bash
.venv/bin/python \
  prototypes/streaming-diarization/live-policy-sweep-20260825/verify_causal_15_10.py \
  --output evidence/live-15-10-lexical-20260825/causal-prototype.json
```

**Verdict: FAIL — STOP BEFORE IMPLEMENTATION.** The truth-blind replay enumerated all 112 saved
15/10 decodes across both six-case passes (1,239.987 audio-seconds). It reconstructed the saved
batch lexical content and settled speaker projection exactly in 12/12 case-runs, proving that it
tested the frozen rule rather than a substitute. But causal ownership failed in 12/12 case-runs:

- 46 unmatched selected words straddled the accepted frontier, across 46 windows;
- 24 additional selected words were wholly behind the frontier, across 18 windows;
- the real session seam refused the first invalid proposal in every case-run as
  `segment_outside_owned_interval` (12/12);
- 42 aligned/dropped straddlers safely remained with the earlier owner; they are not failures;
- the frozen comparator commit and prefix hash stayed unchanged in 12/12 case-runs.

Moving an unmatched word to the frontier would invent a timestamp boundary; retaining its decoded
start would rewrite prior authority. Neither is pre-authorized or measured. Plan B1 therefore
requires the stop: B2 production code, deployment, and the B4 ABBA campaign were not entered.

Authoritative evidence SHA-256:
`fd1ab4d8db9b2b4293dca8bd004fa9a744c078ceb296136a3c7783b4a954300a`.
Prototype script SHA-256:
`a8de0d459663de3eb17212437b94030ca877f91b0198f8cea516deee8c64eac6`.
`causal-prototype-incomplete-run.json` is a preserved development run that stopped enumeration at
the first failure per case; it is superseded by the authoritative full-denominator file above.
