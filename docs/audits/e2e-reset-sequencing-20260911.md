# E2E reset sequencing repair

**Rows 13 and 14 PASS together with the committed harness implementation.** Both outage variants survive and finalize; all three subsequent same-tab meetings reach completed/final, remain in history, and export the correct current transcript. This targeted rerun closes the sequencing failure; it is a 2/2 rerun, not a new full 14/14 run.

The harness now records the last live meeting it created. Before Reset, when capture is stopping or terminal, it waits up to 30 seconds for both durable completion (snapshot closed/final OR history completed) and UI terminal. This uses row 14's existing terminal-wait budget. A timeout raises an assertion before Reset or new admission; the retained record names the previous meeting, last snapshot/history/UI states, deadline and failure reason. Each wait is preserved in network.jsonl; the latest also appears in row-N-before-reset.json. No product changes or assertion weakening.

Validation: **13 focused tests pass**, including delayed UI after either durable-completion signal and bounded failures when UI or durable completion never arrives. The browser run uses a fresh isolated local stack at port 17863, product head `3a641f06`, relay configured and draft lane 1.0 s, with the updated harness. Real corpus microphone and tab audio; no host operations or operator database access.

Run:

```sh
.venv/bin/python tests/e2e/verify_workspace.py \
  --base https://127.0.0.1:17863 --allow-local-self-signed \
  --corpus ~/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s \
  --rows 13,14 --output /tmp/moss-sequencing-20260911/e2e
```

[Results](../../evidence/e2e-reset-sequencing-20260911/results.json), [handoff evidence](../../evidence/e2e-reset-sequencing-20260911/network.jsonl), [tests](../../evidence/e2e-reset-sequencing-20260911/tests.txt). Screenshots, meeting records, exports and audio are retained alongside these files; browser cookies are excluded. Exit 0: `13:PASS | 14:PASS | total 2/2 PASS, 0 FAIL`.
