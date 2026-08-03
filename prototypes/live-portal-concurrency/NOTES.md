# Verdict — 2026-08-03

`PASS`; the original full-window result is historical and the advancing-cursor v2 rerun is the
closure result.

The production `/live` page was driven in Chromium 150 against deployed `3232375` while a real
two-lane session was active. Thirty alternating serial/concurrent pairs fetched a full snapshot and
the full retained event window. All 120 route responses were HTTP 200; snapshot versions and event
sequences remained monotonic in both modes.

| Mode | p50 cycle | p95 cycle | max cycle |
| --- | ---: | ---: | ---: |
| serial | 23.9 ms | 33.3 ms | 521.8 ms |
| concurrent | 21.2 ms | 29.4 ms | 33.9 ms |

Concurrent p95 improved by 3.9 ms (11.7%). It also removed the serial sample's 521.8 ms maximum.
The absolute p95 win on this low-latency route was small, but positive and regression-free. The
served portal therefore starts both requests with `Promise.all`. The original app-side
`max(snapshot p95, events p95)` arithmetic is now superseded: v2 records each concurrent cycle's
`max(snapshot_i, events_i)` and the render bound uses p95 of that paired distribution. Poll cadence
stays 500 ms. A failed member aborts its concurrent sibling before scheduling retry, preventing a
stale request from overlapping the next cursor generation; the browser-contract suite pins this
path.

Raw browser result: `/tmp/moss-closure-3232375-evidence/c5-browser-concurrency.json`.

The v1 result established latency and HTTP success, but its all-zero cursors made monotonicity
vacuous. `probe.js` v2 therefore owns the closure claim: separate per-mode cursors, real
incremental advances, two reconnect-style resets, and replay coverage of each last-known cursor.

## V2 closure rerun — 2026-08-03

Chromium 150 ran 30 alternating pairs against deployed `efc3dab` during an active real two-lane
session. Both modes advanced snapshot and event cursors after their initial read; reset cycles 10
and 20 replayed every last-known cursor. All 120 requests returned 200 and
`cursorAndReplayErrors=[]`. Serial cycle p95 was 11.5 ms; concurrent p95 was 8.5 ms. The raw result
is archived in the control-plane F4b remediation evidence packet, not only under `/tmp`.
