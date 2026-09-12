# Deterministic summary probe: shared external-provider selection

**F1 — Current-head baseline passes.** Before this change, the exact `final_browser_probe.py` command returned 0 locally with `MOSS_LLM_UPSTREAMS` set: external 8/8, all relay checks true. Commit `53d2f0ca` had already added explicit external selection to this probe. Therefore the reported round-10 returncode 1 is not reproduced and cannot be attributed to the missing selector on current head. Host stderr/staged source would be needed to identify that failure; no host operations were performed.

**F2 — Selection cannot drift between callers.** Both the synchronous `configure_external_summary` predicate and asynchronous deterministic probe now call `select_external_summary_provider` from `phase2_acceptance_summary.py`. The probe awaits its result. Provider field and external option are defined once. No product behavior, lane contract or required-file guard changed.

**F3 — Real browser regression passes.** A fresh local Phase-2 fixture instance starts with relay models; the test observes Provider=relay and zero external URL fields, invokes the exact probe helper, then fills and reads the external URL. The existing synchronous predicate regression and full real cross-origin fake-provider/relay regression also pass: **3 passed, no skips**.

Run from the repository root:

```sh
MOSS_LLM_UPSTREAMS='[{"name":"selection-regression","base_url":"http://127.0.0.1:1/v1","models":["relay-default"]}]' \
  .venv/bin/python prototypes/client-configured-llm/final_browser_probe.py \
  --output /tmp/moss-operator-smoke-20260911/probe-after.json
.venv/bin/python -m pytest tests/phase2/test_summary_provider_paths.py -q
```

Post-change command: **returncode 0, external 8/8, all relay checks true, one relay upstream request**. Before/after JSON and test output are retained in `evidence/summary-probe-selection-20260911/`.

The deterministic probe creates its own local stack and scratch SQLite database, configures a real HTTP fake relay upstream explicitly, and uses synthetic transcripts; it does not connect to port 17861 or inject state into a running operator workspace. Its separate HTTPS fake external provider uses test-only self-signed TLS bypass, as before. This proves selection and CORS/relay behavior, not production TLS trust or host qualification. No actual model or decoder was called.
