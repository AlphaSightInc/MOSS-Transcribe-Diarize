# Locator-test browser availability

The round-7 failure was a missing executable, before any locator assertion ran.
`test_meeting_locator_ignores_server_fallback_and_nav` now checks the system Chrome/
Chromium paths used by the existing workspace-reachability test, plus Playwright's
installed Chromium executable. If none exists it explicitly skips with a reason.
When an executable exists, launch and assertion errors are not caught or suppressed.
The real mounted/fallback/nav ambiguity regression remains intact.

## Existing convention and remaining feature tests

At production base c93395fe, `test_workspace_reachability.py::_chrome` checks macOS
Chrome, `/usr/bin/google-chrome` and `/usr/bin/chromium`, and explicitly skips when
none exists. Its tests invoke the browser externally. The locator regression was
the only direct Playwright launch under `tests/phase2` at this base.

The staged feature branches add direct browser launches in
`test_canonical_preview.py`, `test_workspace_demo_geometry.py` (two viewports), and
`test_multi_file_url_meetings.py`. Those currently try macOS Chrome or Playwright's
default browser without an availability skip. Their local pass is not proof they
can run on the host without a browser. This patch changes the reported round-7
locator test only; it does not claim those feature tests are browser-independent.

## Validation

On local Chrome, the locator/sentinel module passes all 3 tests. With candidate
executable checks forced absent in an isolated pytest process, the locator test
reports 1 explicit skip and the reason, rather than a failure or a false pass.
The skip branch does not execute DOM assertions. The full combined staging result
is recorded separately after merging the two feature branches in scratch.
