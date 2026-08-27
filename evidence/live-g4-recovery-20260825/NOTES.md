# Live G4 recovery evidence — 2026-08-25

## A1 shared-normalizer prototype

**PASS.** The retained two-pass six-case matrix contains 122 full 10-second rolling proposals:
120 ordinary disjoint proposals and two copies of Jamie window 4. The producer-neutral rule is
authorized for implementation because:

- 120/120 ordinary proposals are byte-identical;
- 122/122 normalized proposals apply through `LiveSession.apply_text_revision`;
- zero observed words are dropped;
- WER and every recorded speaker score are non-regressing on all 12 reconstructed surfaces;
- Jamie window 4 moves the later start by exactly 2,720 samples, merges/drops zero, preserves
  24/24 words, clears `segments_out_of_order`, and applies in both retained passes.

Legacy TBSA decreases `.000236` on Jamie because the invalid 0.17-second double-owned text extent
is removed, reducing its time-coverage term by `.000674`; word accuracy and speaker metrics are
unchanged. The plan gates WER and speaker scores, so this is an expected validity correction, not
a hidden failure.

Command and raw record:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-policy-sweep-20260825/audit_rolling_normalization.py \
  --sweep evidence/live-policy-sweep-20260825 \
  --output evidence/live-g4-recovery-20260825/normalization-prototype.json
```

- Raw JSON SHA-256: `13c16f63546c7e7829148665ab4e96219bb41910d721bdad78f20724fb4876ac`
- Prototype script SHA-256: `b9e7c4e081d91f683986a5ece4946b61a5c86a9a8221e3319ee521cffe1a0be7`

The script hash changed only because A2 renamed the shared resolver to the producer-neutral
`resolve_segment_overlaps`; the retained raw JSON is unchanged.

## A4 production-class Jamie verifier

**PASS.** The production converger and session classes replayed cached Pass-A Jamie rolling
windows 0-4. All five proposals applied. Window 4 displaced exactly 2,720 samples, preserved
24/24 words, merged/dropped zero, and the accepted frontier queued window 5
`[800000,960000)`.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-policy-sweep-20260825/verify_jamie_rolling_recovery.py \
  --output evidence/live-g4-recovery-20260825/jamie-production-class-probe.json
```

- Raw JSON SHA-256: `58b73ae2cce44d2e879002646281d820c8241d61afbd31805633b64ba87800bf`
- Verifier SHA-256: `3905d506571336483d9d3131585589dbec2024e8c2084d3c82413347eb24955f`
