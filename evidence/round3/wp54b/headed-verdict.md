# WP54b headed arm verdict

- Verdict: **INCOMPLETE; rejected as visible-word evidence**.
- Population: one 300.0 s headed-Chromium Live session; 21 source intervals,
  916 reference words; API 150 state changes; DOM 138; observations 586.
- Decoder: 165 starts / 165 ends / 200 budget; peak active 1; no rejection.
- Shared GPU: before 0 running / 0 waiting; after 0 / 0. Success-total delta
  165 (164 stop, 1 length), matching the owned counted proxy.
- Terminality blocker: meeting `closed`, finalization `running`; zero retained
  terminal-completed/failed events. The harness had stopped on lifecycle closure.
- Semantic falsifier: flat ordered alignment crossed source intervals, yielding
  impossible repeated-occurrence credit (minimum about -293 s).
- Hidden tab: `document.hidden` true 0/586; behavior **UNMEASURED**.
- Corrective control: source-interval overlap is now mandatory; deterministic
  suite 8/8. Corrected headed arm is **UNMEASURED** because only 35 requests
  remain, insufficient for another 300 s session.
- No numerical visible-word target was selected; it remains `USER_DECISION`.
- Teardown: proxy, tunnel, stack stopped; ports 18311/19311/17831 free.
- Preflight attempts: two readiness probes received 401 before browser/session
  creation; both used 0 decoder requests and were torn down.
