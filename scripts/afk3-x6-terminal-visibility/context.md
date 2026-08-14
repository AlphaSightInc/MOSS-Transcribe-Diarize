# Context — x6-terminal-visibility

Iteration 1 completed locally on `afk3/x6-terminal-visibility`.

## Implemented contract

- A `terminal_failure` projects `snapshot.session.status` to `"failed"` immediately; an explicit abort remains `"aborted"`. Snapshot readers can stop from one response without inferring state from events.
- `/events?since_seq` remains inclusive. `-1` means no event has rendered, so the portal fetches and renders `session_created` sequence 0 once, then advances only after render.

## Evidence and validation

- Committed probe sources: `tests/test_live_api.py::LiveApiTest::test_live_routes_are_runtime_backed_with_descriptor_events_and_backpressure` and `tests/test_live_portal.py::LivePortalRouteTest::test_live_portal_browser_contract_polls_renders_controls_and_stops`.
- Raw output: `evidence/phase1/x6-terminal-visibility/iteration-01-terminal-visibility.txt`.
- `dev` is already an ancestor of `HEAD` (`git rev-list --left-right --count HEAD...dev` → `6 0`), so no merge was needed before validation.
- Worktree validation must prefix `PYTHONPATH="$PWD"`: `.venv` is a symlink to the primary checkout's editable environment; without the prefix it imports the primary checkout rather than this worktree.
- Ticket gate: `89 passed, 1 warning, 331 subtests passed`.

## Remaining work

No implementation candidate remains. The branch is ready for the required independent review; do not merge or push `dev` from this worktree.
