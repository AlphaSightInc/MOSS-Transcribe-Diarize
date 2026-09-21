# S17 raw-capture custody

**Verdict: READY, measurement still UNMEASURED.** S17 consumes I2's three native
diagnostic streams without reconstructing raw spans. No decoder request was made.

- I2 creates one `RawTerminalSpan` per parsed terminal span before overlap
  normalization. `finalize_lanes` retains those objects, creates the explicit
  raw-to-normalized mapping, and calls `record_diagnostics` with the raw, mapping,
  and normalized partition tuples.
- `TerminalLabelCapture.record_diagnostics` writes `raw_terminal_span`,
  `raw_to_normalized`, then `normalized_partition` JSONL rows. The sink comes only
  from `MOSS_TERMINAL_LABEL_CAPTURE`.
- S17 sets that same variable to `<out>/terminal-labels.jsonl` for the stack only,
  reads the rows appended during each case, and checks required fields, exact
  raw/mapping index equality, referenced partition existence, and the unchanged
  8,000-sample eligibility floor.
- The contained cross-label control retains raw `S02` even though normalization
  drops it and maps it to no partition. This is the required one-record-per-raw-span
  counterexample.
- Harness fix in this branch: absent or invalid raw custody writes a case receipt and
  run receipt with `status: INCOMPLETE`, then exits 2. It cannot become PASS or an
  identity FAIL.

Targeted gate: `30 passed` across `tools/qualify/test_bundle.py`,
`tests/test_terminal_label_capture.py`, and
`tests/test_p_f2f6_violating_controls.py` under SQLite 3.53.4.
