# Browser timeout evidence and stronger readiness

**Timeouts remain failures at their original deadlines.** The three requested predicates now retain structured wait evidence before closing their pages, including reference-page preparation and the G9 async subprocess. No product UI/runtime, identity policy, quality bound, pixel threshold, or host configuration changed. The reported host failures were not rerun or claimed fixed here.

## F1 — What survives in the failed predicate's raw record

`raw.browser_timeout` contains the predicate, semantic stage, operation, exact selector chain or JavaScript function text (`target`), page URL, and all current values of `data-auth-state`, `data-boot`, and `data-history-boot`. An absent attribute is an empty list. Function arguments, fill values, DOM text, browser call logs, and subprocess output are not retained.

The diagnostic adapter forwards Page/Locator calls unchanged, catching both explicit waits and auto-waits such as `Locator.fill`, clicks and screenshots. Event waits such as `expect_download` are captured at context exit. The selector is Playwright's actual selector chain; locator spelling is not reconstructed from a truncated error message. No passed timeout/default is replaced. Reference and candidate stages are separate; fidelity distinguishes before-extraction and after-settle readiness.

The callback registers only the resulting diagnostic JSON and redacted PNG in the campaign's explicit safe-artifact set. The existing raw collector copies them under `artifacts/browser-timeouts/`; the raw record names that screenshot path. The G9 subprocess writes the same reduced evidence into the campaign directory, and the parent carries it into the failed G9 raw record even though the outer exception is `CalledProcessError`. Cleanup errors retain an underlying timeout's evidence rather than erasing it.

Screenshots preserve layout boxes/colors but hide all text, form controls/values, generated text, background images and media surfaces. They are **content-free layout diagnostics**, not the fidelity comparison images. The normal fidelity screenshots/exemptions are unchanged. The redaction is applied only during diagnostic capture, after failure; no successful predicate sees a modified page. Files are mode 0600. If the page or screenshot is unavailable, retain the original timeout and a typed collection error with a null screenshot; never fabricate an image or replace the original failure. Diagnostic screenshot collection has a separate two-second ceiling, not an extended predicate wait.

Implementation: `phase2_browser_evidence.py`, the two predicates in `phase2_acceptance_browser.py`, `phase2_acceptance_summary.py`, `tests/reference_ui_screenshot_diff.py`, and `final_browser_probe.py`. `_failure_details` now preserves the explicit timeout fields alongside its existing sanitized first-line error and operation location.

## F2 — Fidelity now requires the right surface twice

Shared `wait_for_final_tail` requires the fixture tail in a `.utt[data-state="final"] .utt-text` under `#tr-body`, with **zero `.utt[data-state="provisional"]` rows**. Both live preview and draft render with that provisional state; there is no separate DOM draft state. Apply the wait before extracting `#app > .app`, then again after fonts/frame/transition settling and before photographing `#transcript-panel`. The standalone reference comparison uses the same candidate readiness check.

This strengthens proof; it is not a diagnosis that drafts caused the earlier failure. The deployed fidelity caller already chooses a durable completed/interrupted meeting, not an active draft stream. Reference readiness still waits for its own boot and `.main`. The exact failing stage will now be visible. Pixel thresholds, masks/exemptions, fixture text and reference identity remain unchanged.

## F3 — Foreground traffic could satisfy the old background check

The old callback counted every matching `requestfinished` from before clicking the active meeting onward. A test feeds one foreground completion and a second request issued in foreground but completed after hiding: **old count 2, corrected count 0**. A request issued and completed after entering hidden state increments the new count to 1.

The corrected observer arms only after the existing hidden-state wait succeeds, records requests on `request`, and counts completion only for those same requests. The observation duration remains **2.5 seconds**. `page.wait_for_timeout(2500)` replaces `time.sleep(2.5)` so synchronous Playwright can dispatch the completion events during that interval. The hidden-state assertion, read-only/reload checks and pass requirement remain intact. Focus emulation is not changed or bypassed; a failure to enter hidden state still fails, now with the exact function recorded.

## Validation

- Real Chromium tests deliberately time out each predicate's diagnostic boundary, a reference boot wait, summary URL-field auto-wait, an async summary wait, and a download-event wait; original timeout types are preserved.
- Raw metadata survives `_failure_details`, cleanup exceptions, and the subprocess bridge. Registered PNG/JSON files survive the actual safe-artifact copy function and the screenshot path resolves in raw evidence.
- Replacing private transcript text and input secrets with different values produces **identical redacted PNG bytes**. Neither fill values nor fixture arguments enter diagnostic JSON.
- Readiness rejects provisional-only text, confirmed-only text, and a preview introduced after initial final readiness; it passes once the final tail is present without provisional rows.
- Existing sync/async external-provider and relay browser tests remain passing. Optional browser tests retain the shared executable guard; no required file gained an environmental skip.

Final checks:

```sh
.venv/bin/python -m pytest tests/phase2/test_browser_timeout_evidence.py tests/phase2/test_summary_provider_paths.py -q
.venv/bin/python -m pytest tests/ -q
```

Focused: **15 passed, zero skips**. Full Python: **1,447 passed, 2 existing skips, 37 subtests passed**, 103.36 seconds. The earlier full run before the final async/cleanup/download regressions was 1,443 passed; the final count above supersedes it. Retained output: [focused tests](../../evidence/browser-timeout-evidence-20260911/focused-tests.txt), [full suite](../../evidence/browser-timeout-evidence-20260911/python-suite.txt). No frontend source/bundle changed, so no frontend rebuild was required. No host operations or changes to the operator's running stack/database.
