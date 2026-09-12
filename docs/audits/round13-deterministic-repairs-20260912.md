# Round 13 deterministic test repairs — 2026-09-12

**Two test defects; no product-default or selector change.** The retained run at
`73236fcd` reports **1,600 passed + 37 subtests, two failed, two skipped**. The
reported 1,637 combines ordinary tests and subtests. Its trace explicitly launched
`/usr/bin/google-chrome`; the separate no-browser verification below simulates the
requested unavailable-browser environment rather than claiming that Chrome was
absent in this retained run.

Read-only source: `/tmp/moss-round13-retry-stage/result/raw/python.stdout` and
`python.stderr`. No host operations, decoder requests or existing-stack database
access. Browser experiments used separate temporary fixture databases and the same
SQLite-version seam as `tests/phase2/conftest.py`.

## F1 — timeout evidence screenshot assertion

Failing case:
`tests/phase2/test_browser_timeout_evidence.py::test_timeout_fields_raw_record_and_content_free_artifact[transcript_pane_fidelity-candidate.workspace-ready-selector-[data-boot="ready"]]`.
Two PNG strings differed at byte 36. That comparison conflates redaction with PNG
encoding and browser painting; it does not establish a content leak.

The test now checks the actual writer supplies `CONTENT_FREE_STYLE`, confirms
transparent text/text fill, no text shadow and hidden form values at each capture,
and verifies both real PNG dimensions are 400 by 300. Changed fixture text must
remain masked. No tolerance, hash or raw-image byte-equality gate is substituted.
The exact-byte check for copying an existing registered artifact remains valid and
unchanged. Production screenshot masking, boot/auth values and timeout stages are
unchanged.

## F2 — relay-default assertion before model discovery

Failing case:
`tests/phase2/test_summary_provider_paths.py::test_deployed_predicate_selects_external_when_relay_is_default`.
The fixture explicitly provides one relay model. Its expectation is correct after
catalog initialization; history readiness does not imply catalog readiness.

`FinalSummarySettings` initializes from browser settings, then asynchronously calls
`initializeRelaySettings`. That function selects relay for fresh settings only when
`/api/llm/models` returns models; an empty catalog leaves external selected. Existing
saved settings remain explicit choices. Neither `76de3e25` nor `53d2f0ca` changed
frontend defaults; they changed predicate/probe selection.

A real fixture-server/browser experiment held delivery of the actual model response:

| Fixture models | Models returned by endpoint | While response held | After response delivered |
|---:|---:|---|---|
| 1 | 1 | external | relay |
| 0 | 0 | external | external |

Thus this is a premature test assertion, not a fixture lacking its declared model
or a product regression. Both synchronous and asynchronous provider assertions now
use Playwright's retrying `to_have_value("relay")`, without selecting relay for the
test or weakening the expected value. The browser-free frontend suite additionally
checks delayed nonempty and empty catalogs. The shared external-provider selector
is unchanged and is still exercised after relay initialization.

## F3 — verification

Code/test commit: `139177d6`. Both repaired browser files pass locally with real
Chrome: **19 passed**. Frontend: **204 passed**, including both delayed-catalog cases.

Full suites then ran in a fresh detached worktree at integrated head `057a547c`,
including the history-observer repair `681d9239`, clean before and after. Its `.venv` and `node_modules` refer to the existing local test dependencies;
source and fixtures come from the detached checkout. `PLAYWRIGHT_BROWSERS_PATH`
points to an empty directory. An external `sitecustomize.py` hides only supported
system-browser file/command discovery; it does not alter pytest, skip handling or
the required-file policy. The real discovery function confirmed no executable.
`MOSS_LLM_UPSTREAMS` was set to a loopback fixture catalog (one model, no real relay).

- Full Python: **1,580 passed + 37 subtests, 25 skipped, zero failed**.
- Exact XML denominator: **1,642 collected, 1,617 executed/passed, 25 skipped,
  zero failed/unmeasured** (includes subtests).
- Skips: **23 optional missing-browser cases**, one unprovisioned operator identity
  corpus and one unprovisioned F-cert corpus.
- The production `_pytest_denominators` reducer found **all 24 required files** and
  all named required cases: **no required failure, skip or missing case**.
- Full frontend in the same clean worktree: **204 passed**.

Logs and XML stay outside git; the local scratch root is recorded in
`/tmp/moss-round13-hoststyle-root`. No content-bearing evidence is added. The follow-up
recording these integrated counts changes documentation only. This is local regression
verification, not a completed host qualification or preadmission.
