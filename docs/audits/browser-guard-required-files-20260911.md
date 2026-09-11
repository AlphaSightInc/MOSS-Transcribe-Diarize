# Browser guard and required-file audit — 2026-09-11

**393 required tests passed; zero skips; all 24 required files covered.** Browser
resolution was patched to raise AssertionError if called throughout this run. No
required test requested a browser. No acceptance list/evaluator rule was relaxed.
The 393-case subset satisfies required-file/case checks; the overall denominator
must be evaluated using a full-suite report.

## Preserved coverage

- Shared `tests/phase2/browser_support.py`: selects executable system Chrome/Chromium,
  Playwright Chromium or installed headless shell. Explicit missing-executable skip
  lists searched paths. Present-browser launch failures and product failures still fail.
- Multi-file/URL ownership, independent outcomes, cleanup and durable meeting checks
  remain in the required file. Original form/browser assertions moved intact to
  `test_multi_file_url_browser.py`.
- Original desktop/mobile reachability checks moved to
  `test_workspace_reachability_browser.py`. Required reachability now checks actual
  workspace/API mounts, independent same-cookie reads, live transcript visibility,
  shared rename convergence and read-only retrieval. Synthetic runtime fixtures shared.
- Optional Torch export compatibility moved to `test_legacy_model_exports.py` so absent
  Torch cannot skip a required lifecycle case.
- All actual browser-launch paths under `tests/` use the shared guard, including the
  standalone screenshot utility. The new E2E harness uses the resolver and exit 77 for
  absence. The attended canary's fake launcher does not launch a browser.

## Measured checks

- Browser-forbidden required suite: **393 passed, 0 skipped**;
  `/tmp/moss-required-browser-audit.log`, `/tmp/moss-required-browser-free.xml`.
- Simulated missing executable: **17 passed, 6 browser-only skipped**;
  `/tmp/moss-missing-browser-tests.log`. Required multi-file API test completed.
- Real MacStudio Chrome plus guard regression tests: **14 passed, 0 skipped**;
  `/tmp/moss-browser-present-tests.log`.
- Split API/browser/lifecycle/legacy tests: **30 passed, 0 skipped**;
  `/tmp/moss-browser-split-tests.log`.

Static AST audit found no browser-launch/environmental-skip calls in these required
files; imported fixtures were also inspected. Runtime browser-forbidden execution
corroborates this. Mock-browser tests and evaluator strings mentioning skips do not
launch a browser or skip a test.

| Required file | Browser launch | Environmental skip |
|---|---|---|
| `tests/phase2/test_tls_renewal.py` | None | None |
| `tests/phase2/test_completion_qualification.py` | None | None |
| `tests/phase2/test_final_summary.py` | None | None |
| `tests/phase2/test_manual_speaker_voiceprints.py` | None | None |
| `tests/phase2/test_voiceprint_bank_operations.py` | None | None |
| `tests/phase2/test_voiceprint_matching.py` | None | None |
| `tests/phase2/test_acceptance_setup.py` | None | None |
| `tests/phase2/test_acceptance_journal.py` | None | None |
| `tests/phase2/test_attended_g7_canary.py` | None | None |
| `tests/phase2/test_atomic_cutover.py` | None | None |
| `tests/phase2/test_account_deployment_surface.py` | None | None |
| `tests/phase2/test_account_file_ingress.py` | None | None |
| `tests/phase2/test_file_mp3_artifact.py` | None | None |
| `tests/phase2/test_workspace_lifecycle.py` | None | None |
| `tests/phase2/test_browser_workspace.py` | None | None |
| `tests/phase2/test_legacy_surface_absence.py` | None | None |
| `tests/phase2/test_multi_file_url_meetings.py` | None | None |
| `tests/phase2/test_operator_status.py` | None | None |
| `tests/phase2/test_owner_bound_file_meeting.py` | None | None |
| `tests/phase2/test_owner_bound_live_meeting.py` | None | None |
| `tests/phase2/test_runner_composition.py` | None | None |
| `tests/phase2/test_shared_meeting_history.py` | None | None |
| `tests/phase2/test_wave1_qualification.py` | None | None |
| `tests/phase2/test_workspace_reachability.py` | None | None |

Full product suite: **1330 passed, 2 optional corpus skips, 37 subtests passed**.
`/tmp/moss-guard-full.xml` passes the unchanged `_pytest_denominators` evaluator with
all 24 required files and no evaluator errors, including the whole-suite count gate.
