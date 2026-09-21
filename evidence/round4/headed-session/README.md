# Headed-session evidence index

- `browser-probe.json`: exact headed Chromium launch and loopback DOM receipt.
- `short-stack-run.json`, `short-stack-runtime-receipt.json`: reproducible local-stack refusal; no real decoder started.
- `s9-adam-frank-180s-source-rows.jsonl`: the selected retained 180-second source rows.
- `s9-adam-frank-180s-word-end-template.jsonl`: 531 rows requiring human word-end confirmation.
- `backend-suite.log`, `frontend-suite.log`, `frontend-typecheck.log`, `frontend-build.log`: required suite receipts.

All processes started by the probes bind loopback only and stop before their command returns.
