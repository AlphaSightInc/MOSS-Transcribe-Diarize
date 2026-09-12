# G9: explicit external provider and real relay scenario

The external-provider predicate timed out because configured relay models make the initial settings form show a model dropdown instead of a URL input. Both the deployed predicate and deterministic `final-summary-real-cors` probe now explicitly select **External HTTPS provider** before filling URL/model/key. A second stale assertion was corrected: external summaries now include `max_tokens >= 2048`, as required by the accepted thinking-model fix.

## Contract and verification

Question: does each selected provider path reach its intended transport and persist a validated summary? Primitives: browser provider selection, owner transcript, external HTTPS request or same-origin relay request, configured fake upstream, fresh summary attempt, durable result. Invariants: external secrets stay browser-owned; relay uses configured models and no ambient upstream credentials; the transcript belongs to the requesting owner; an older current summary cannot satisfy the new-attempt assertion. No model/identity/quality policy changed.

Falsifiers: filling the URL while relay is selected; an external request going through MOSS; a relay request bypassing MOSS; no observed fake-upstream delivery; a wrong-owner transcript; a non-current or stale persisted result. Real Chromium and real HTTP servers are necessary to catch the original conditional-form bug and to establish the browser/relay boundary without request interception.

## Tests and gate integration

- `tests/phase2/test_summary_provider_paths.py` opens the actual product with relay models present, verifies that the URL field is absent, then calls the deployed predicate's `configure_external_summary` helper and verifies the external form. Its second test runs both complete provider scenarios against fake upstreams. These optional browser tests use the shared executable guard and are not on REQUIRED_PYTHON_TEST_FILES.
- `prototypes/client-configured-llm/final_browser_probe.py` keeps its two-owner real-CORS checks, with relay configured from app creation. It then switches one browser to the relay, observes the same-origin POST and exactly one fake-upstream request, checks model/token floor/owner transcript/credential exclusion, and checks the fresh durable summary attempt.
- The deployed `browser_final_summary` predicate also runs this provider-path probe and retains `summary-provider-paths.json`; its validator now requires all six relay checks plus one upstream delivery. Removing or falsifying relay evidence fails G9.
- Existing real-clock retry, cancellation, trusted deployed HTTPS, owner isolation, and four-session capacity checks remain in the deployed predicate. The additional fake-upstream scenario uses a separate scratch application/database, loopback HTTP, and synthetic transcripts. It qualifies candidate relay code on the host; it does **not** claim the configured real tailnet models or deployed relay TLS were measured. Its external fake TLS exception remains explicitly labelled in the artifact.

## Local evidence

`evidence/g9-provider-paths-20260911.json`: **8/8 external checks**, **6/6 relay checks**, **1 fake relay upstream request**. Real Chromium; no browser request interception; no paid upstream. Focused regression/evaluator/timing tests: **16 passed**. Full-suite results appended after completion.

Reproduce: `.venv/bin/python prototypes/client-configured-llm/final_browser_probe.py --output /tmp/g9-provider-paths.json`. The script pins imports to its own checkout. The host predicate supplies its configured Chrome binary; standalone probes use the shared executable discovery. Original local stack, host services, and databases were not changed. Scratch command paths: MacStudio-local (not in repo).

Full validation: `.venv/bin/python -m pytest tests/ -q` — **1,393 passed, 2 optional corpus skips, 37 subtests passed**; `npm --prefix frontend test -- --run` — **201 passed across 23 files**. Host round 10 has not been run by this agent.

Final integration after rebase onto c07c5d46: **1,400 Python passed, 2 skipped, 37 subtests passed** (89.24s); frontend remains **201 passed** (no frontend changes in the rebase). The first integration run caught one stale three-argument `_admin_status_surfaces` test stub from the incoming operator-status change; updating it to the actual two-argument signature restored the full suite. No operator product behavior changed in this follow-up.
