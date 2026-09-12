# Round 13: ephemeral history observer reload

F1 — Harness expectation error, reproduced on candidate `73236fcdb683f766088a065f7ca80db795ac3618`. Both retained round-13 failures reach `background.reload-observer`; its selector was `[data-observer-mode="read-only"]`. The page is booted because reload succeeds. `ControlPanel.tsx`'s `observeHistoryMeeting` intentionally creates an ephemeral poller without `saveSessionReattach`. Its mount logic only automatically reattaches a saved originating capture session. `ControlPanel.test.tsx`, “opens an active history Meeting as an ephemeral Account observer”, explicitly checks empty session storage and idle after remount. This is not host-specific rendering failure or background polling failure. The predicate brings the page to front before reload.

F2 — Retained screenshot inspected after extraction outside the repository. It is content-masked and cannot establish observer state by itself. Source plus real browser reproduction establishes the missing state; no inference from obscured text is needed.

F3 — Fix `_reload_history_observer` in `phase2_acceptance_browser.py`: reload, wait for history ready and idle, reopen the identical owned meeting from history, require read-only/viewing and absence of Stop and finalize. Automatic originating-capture reattachment remains covered by existing UI tests. No product changes. The predicate still requires genuine hidden visibility and completed requests issued after hidden entry; its 2.5-second observation and existing selector timeouts are unchanged.

## Local falsification and verification

Own fresh HTTPS stack on port 17863, isolated state, current candidate source, relay configured and draft lane 1.0. User's 17861 database untouched. Chromium 153.0.8010.37, `unfocused_driver`, headless, same predicate omissions of `--disable-background-timer-throttling`, `--disable-backgrounding-occluded-windows`, `--disable-renderer-backgrounding`.

- Real compiled workspace, newly created meeting: genuine hidden state; **4 completed post-hidden requests in 2.504 seconds**.
- Foreground then reload: **idle**, saved reattachment absent. Old read-only selector times out (reproduction uses a 1-second bound; production timeout unchanged).
- Corrected predicate helper: reload and reopen same meeting; **read-only PASS**, Stop absent. Own meeting aborted after probe.
- `python -m pytest tests/phase2/test_round11_browser_fixes.py -q`: **4 passed**, including actual hidden polling and a new reload-order/ownership-negative regression.
- `npm test -- src/components/ControlPanel.test.tsx`: **11 passed**, including ephemeral history remount and originating capture reattachment.

Local reproduction command: `.venv/bin/python /tmp/moss-round13-observer-reload/probe.py`. Scratch script and numeric results remain there; no audio, transcript or screenshot committed. This verifies the failed boundary on macOS Chromium with the predicate's flags, not a new host admission run.
