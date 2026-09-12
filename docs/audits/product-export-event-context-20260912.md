# Round 14: preserve Playwright download event results

F1 — Confirmed harness defect. Round-14 deployed raw record retains `AttributeError` at `phase2_acceptance_browser.py:401:product_regression`. Extracted the supplied evidence archive to scratch, outside the repository. Export runs in a separate browser context after selecting `export_meeting_id`, not in the background observer page. The reload fix allowed execution to reach this older defect; blame locates the wrapper in `cf0dc398`, not `681d9239`.

F2 — `EvidencePage.invoke` wrapped every result whose operation started with `expect_`. `EvidenceExpectation.__enter__` calls invoke with that same operation, so the actual Playwright event info was wrapped again. `download.value` therefore accessed an EvidenceExpectation with no value attribute. Likewise, wrapping the None returned by __exit__ made it truthy and could suppress errors raised inside the context. Neither requires host-specific Chrome behavior or a missing download.

F3 — Minimal correction: wrap only the initial page context-factory call in `EvidencePage.__getattr__`. Preserve enter/exit return values verbatim while keeping timeout interception in invoke. No export selector, timeout, product behavior, identity policy, or gate threshold changed.

## Regression evidence

- Fake-page test reproduces the original defect before the fix: returned event info is an EvidenceExpectation instead of the original event object. It exercises `.value`, Download type, suggested extension, actual path and nonempty bytes, matching the product-regression consumer.
- Additional regression proves context-body assertions propagate instead of being swallowed.
- Real guarded Chromium test receives an actual Download through the evidence wrapper and verifies its extension and nonempty bytes. Existing missing-download test still retains timeout evidence.
- `python -m pytest tests/phase2/test_browser_timeout_evidence.py tests/phase2/test_round11_browser_fixes.py tests/phase2/test_wave1_qualification.py tests/phase2/test_acceptance_cleanup.py -q`: 208 passed. Two subsequently added focused tests: 2 passed. Total 210 distinct passing cases, no skips.

## Full predicate on own local stack

Baseline head `c8713799c8ae4987e6ac82456f0fc1c0a0e7b054` plus this wrapper fix. Fresh database/control paths under `/tmp/moss-round14-download`, HTTPS port 17863, relay configured, draft lane 1.0. Real corpus MP3 submitted through the UI into a newly created workspace; separate active live meeting created for the observer test. Exact `BrowserCampaign.product_regression` invoked, including `unfocused_driver`, headless Chromium and its three omitted background-throttling default flags. Only browser-context TLS verification bypassed for the loopback self-signed certificate; no host flags or assertions changed.

| Suite | Passed / executed |
|---|---|
| Desktop semantic accessibility | 6/6 |
| Active background observer, including genuine hidden polling and reload/reopen | 4/4 |
| Mobile reachability | 4/4 |
| History export: Markdown, plain text, JSON, SRT, VTT | 5/5 |

Total **19/19**, zero failed/skipped/unmeasured. Command: `.venv/bin/python /tmp/moss-round14-download/probe.py`; numeric results: `/tmp/moss-round14-download/product-result.json`. Temporary upload/download files and credential file cleaned; own active session aborted. No raw content or screenshot committed. User's 17861 database untouched; no host operations. This is local predicate verification, not a host admission claim.
