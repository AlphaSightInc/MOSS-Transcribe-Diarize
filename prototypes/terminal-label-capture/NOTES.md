# Terminal-label capture on merged round-4 finalization

**Verdict: SUPPORTED.** The finalizer owns terminal-local partitions and their one
aggregate decision. With `MOSS_TERMINAL_LABEL_CAPTURE` set, the observer copies those
records to JSONL after they settle; without it, no sink or write exists.

- **Question.** Can a future S17 run retain native terminal partition evidence without
  changing publication?
- **Primitives.** Product `TerminalPartitionDecision`, its published spans, and an
  opt-in JSONL sink. The sink does not create partitions or decisions.
- **Invariant.** The serialized terminal proposal is byte-identical capture off/on,
  including a refused writer. The observer cannot change scores or identity policy.
- **Falsifier.** Different published bytes, a capture ID or decision different from the
  product record, or Keyu `0.017033` publishing Adam.
- **Measured controls.** The `0.27 s` (4,320-sample) `S02` span is ineligible; its
  shared partition's eligible Adam evidence scores `0.909091`. Keyu scores `0.017033`
  and abstains. `test_terminal_label_capture.py` compares each captured ID/decision and
  identity against `TerminalFinalization.terminal_partitions`.
