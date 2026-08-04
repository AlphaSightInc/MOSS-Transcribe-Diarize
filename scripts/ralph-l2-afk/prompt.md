# Per-iteration procedure

1. Read the controlling plan and `prd.md` before work.
2. Perform only the next authorized A-step and one logical change.
3. Keep every changed path inside the contract allowlist.
4. Preserve raw JSON and a SHA-256 manifest for every measurement.
5. Append verdict plus one reproduction command to the applicable `NOTES.md`.
6. Commit the logical change; never push or merge.
7. End only with `<promise>COMPLETE</promise>` when all Campaign-A gates pass, or
   `<promise>BLOCKED</promise>` on a failed gate or required supervisor decision.
