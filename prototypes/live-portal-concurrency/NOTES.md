# Verdict — 2026-08-03

`PASS`, implement concurrent snapshot/events fetch.

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
served portal therefore starts both requests with `Promise.all`; the analytic app-side render bound
charges `max(snapshot p95, events p95)` rather than their obsolete serial sum. Poll cadence stays
500 ms. A failed member aborts its concurrent sibling before scheduling retry, preventing a stale
request from overlapping the next cursor generation; the browser-contract suite pins this path.

Raw browser result: `/tmp/moss-closure-3232375-evidence/c5-browser-concurrency.json`.
