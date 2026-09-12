# G9 browser availability recheck

Current source at `3d1e2b8a` already calls `require_browser(p)` before the named optional test enters `probe.run`. Git history shows that guard in its introducing commit `53d2f0ca`; `76de3e25` adds the shared-selector regression. No duplicate guard or product change was necessary. The reported host failure cannot be attributed to current source without the failing staged source and traceback.

Added `tests/phase2/test_summary_browser_guard.py`: invoke all three real test entrypoints with executable discovery reporting `/missing/ms-playwright/chrome-headless-shell`; assert an explicit pytest skip containing that path and ensure no probe/server setup is entered. Combined with existing discovery tests and all three real-browser G9 tests: **8 passed**, no skips on MacStudio.

Audited `sync_playwright`, `async_playwright` and `chromium.launch` throughout tests: summary-provider paths, multi-file browser, canonical preview, timeout evidence, workspace geometry, locator sentinels, voiceprint latency and workspace reachability use the shared guard. Reference screenshot preparation resolves through `chrome_executable` to `require_browser`; standalone E2E resolves through `browser_executable` and emits explicit missing-browser evidence/exit 77. The wave1 qualification occurrence is a fake manager, not a browser launch. The summary-provider file is not in REQUIRED_PYTHON_TEST_FILES.

Ran `.venv/bin/python prototypes/client-configured-llm/final_browser_probe.py --output /tmp/moss-mixer-regression-20260911/final-summary-probe.json`: **exit 0**, **8/8 external checks**, all relay checks true. The probe itself starts an isolated app with a configured fake relay upstream, so relay models are present and the default provider is relay; the shared selector explicitly opens the external form. This is deterministic browser qualification, not a production-origin or real upstream test.

Evidence: [tests](../../evidence/summary-browser-guard-20260911/tests.txt), [probe](../../evidence/summary-browser-guard-20260911/probe.json). No host operations.
