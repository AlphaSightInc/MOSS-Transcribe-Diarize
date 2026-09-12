# Round 15: async Playwright expectation protocol

`974b419d` correctly preserved synchronous event-info and exit values but exposed the shared EvidenceExpectation to AsyncEvidencePage without implementing the async context protocol. The summary probe's `async with page.expect_response(...)` therefore raised TypeError before submitting a summary.

Added `__aenter__` and `__aexit__`, awaiting the existing AsyncEvidencePage.invoke boundary. Event info and exit values are returned unchanged; async timeouts still retain evidence and re-raise the original exception. No product behavior, selectors, timing budgets, or admission criteria changed.

## Verification

Baseline current branch head `767965d7` plus this fix. Four fake-context cases failed with the exact missing-async-protocol TypeError before the change. They now verify shared sync/async `.value` shape, identity-preserving None/False/True exit returns, and propagation of consumer errors. Two additional cases verify timeout preservation at async enter and exit.

Ran the actual CLI:

```sh
.venv/bin/python prototypes/client-configured-llm/final_browser_probe.py --output /tmp/moss-round15-async/probe.json
```

**Exit 0**. The CLI starts its own fresh local Phase-2 app/database from this checkout, with `llm_upstreams` configured to its fake relay upstream. External HTTPS provider scenario: **8/8 checks true**, including real CORS preflight/POST, two owner-isolated durable results and no inference on reload. Relay scenario: **6/6 checks true**, one upstream request, correct model/token floor, same-origin request, owner-only transcript and durable result. Both scenarios run in real Chromium through AsyncEvidencePage. The probe's test-only TLS bypass is not production TLS qualification.

Requested suites: `tests/phase2/test_browser_timeout_evidence.py` and `tests/phase2/test_summary_provider_paths.py`; results recorded below. Existing browser availability guards remain intact. No host operations or access to the user's 17861 database. All probe servers and temporary state are managed and cleaned by the probe; retained output contains only diagnostic metadata.

Requested suites: **26 passed in 24.59 s**, no skips. Subsequently added async enter/exit timeout tests: **2 passed**. Total **28 distinct passing tests**.

Completeness follow-up: the fake AsyncEvidencePage test now yields a resolved Future and explicitly awaits `.value`, while retaining sync/async event identity checks. The old-artifact/new-attempt regression in `test_summary_provider_paths.py` now passes an AsyncEvidencePage to `regenerate_summary`, exactly as the deterministic CLI and G9 subprocess do. This removes its former raw-page coverage gap. No production change in this follow-up; the previously measured CLI exit 0 covers external and relay together.
