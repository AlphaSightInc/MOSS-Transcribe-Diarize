# Live portal fetch-concurrency prototype

Question: on the deployed portal under a live, full-payload viewer load, does starting snapshot and
events fetches together reduce paired end-to-end browser cycle time without losing revision/event
monotonicity?

After connecting `agent-browser` to a live portal and setting the in-page-only
`window.__mossAuth`, `window.__mossOriginalFetch`, and `window.__mossBenchmarkSessionID` values:

```bash
agent-browser --session moss-c5 eval "$(tr '\n' ' ' < prototypes/live-portal-concurrency/probe.js)" --json
```

The probe alternates ordering across 30 serial/concurrent pairs. Every request asks for the full
snapshot and retained event window; this is intentionally a heavier viewer load than steady-state
incremental polling.
