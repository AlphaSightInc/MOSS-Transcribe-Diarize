# Per-iteration procedure

1. Read the controlling plan and `prd.md`.
2. Perform only the next authorized L1 step and one logical change.
3. Keep every changed path inside the contract allowlist.
4. Preserve raw JSON and a SHA-256 manifest for every measurement.
5. Append verdict plus one reproduction command to `NOTES.md`.
6. Commit the logical change; never push or merge.
7. End with `<promise>COMPLETE</promise>` only on complete gates, or
   `<promise>BLOCKED</promise>` on gate failure or required supervisor review.
