# Human-audit attestation — Q1: 1m-acquired-jamie-dimon (2026-08-04)

Auditor: operator (direct listening). Reference under audit: `benchmark_diarization_1min/samples/acquired_jamie_dimon/reference.jsonl`, SHA-256 `325c83712849262ebe7c6e513a9be495d6d6bf5230e70f174243f66ee691e01d`. Cross-check instrument: blind fresh ASR at deployed `9089b332` (human-audit-asr packet).

Operator statement (verbatim intent): all highlighted difference words confirmed as actually
spoken, EXCEPT "Jason" (machine's rendering; not confirmable). Timing-only lines: texts
confirmed correct; exact timestamps not confirmable by ear but within range; speaking speed
confirmed genuinely fast.

## Supervisor disposition (delegated authority)

1. **Golden text: UNCHANGED — no v2 file needed.** No line claims absent text; line 7's
   "Chase, and" is confirmed spoken; machine's "Jason." is an ASR mishearing of it.
2. **Timestamps: ACCEPTED.** All 5 high-word-rate flags adjudicated as genuine fast speech +
   coarse timestamp granularity. No retiming.
3. **Missing passages (machine-heard, operator-confirmed spoken): documented as sparse
   coverage, benign.** Verified by interval geometry: every confirmed passage lies in a gap
   between scored reference windows (2.9–15.4 s, 29.4–44.5 s, 58–60 s); none overlaps a
   scored window, so grading is unaffected. (Machine speaker labels were NOT used as
   evidence — the ASR over-birthed 4 labels for 3 speakers.)
4. **Case status: HUMAN-AUDITED — promotable** from exploratory to acceptance-eligible at
   the next corpus-manifest revision (batched with the other Q outcomes, one keeper cycle).
