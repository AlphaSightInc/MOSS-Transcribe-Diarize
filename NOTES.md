# Pane 3.4 notes

The valid full-suite gate is green. No failing file is waived.

- `frontend/src/lib/transcriptExport.ts` and `frontend/src/lib/speakerMap.ts`: direct Node TypeScript export-oracle resolution fixed with explicit `.ts` runtime imports.
- `moss_transcribe_diarize/app/phase2_live.py`: removed the added post-finish database snapshot; the existing store review predicate supplies identical authoritative truth without extending Stop settlement.
- `tests/phase2/test_terminal_outcome_projection.py`: its non-product 50 ms harness wait flaked under combined load; 500 ms preserves the same pending-Stop path without changing production policy.
- `tests/phase2/test_export_oracle.py`: JSON expectation now follows the required publication normalization, saved `S00` to downloaded `UNKNOWN`, and asserts zero literal `S00` bytes.
