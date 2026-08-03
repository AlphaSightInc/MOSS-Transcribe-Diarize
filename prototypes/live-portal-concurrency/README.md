# Live portal fetch-concurrency prototype

Question: on the deployed portal under a live viewer load, does starting snapshot and events
fetches together reduce paired end-to-end browser cycle time without losing revision/event cursor
coverage through incremental polling and reconnect/reset replay?

After connecting `agent-browser` to a live portal and setting the in-page-only
`window.__mossAuth`, `window.__mossOriginalFetch`, and `window.__mossBenchmarkSessionID` values:

```bash
agent-browser --session moss-c5 eval "$(tr '\n' ' ' < prototypes/live-portal-concurrency/probe.js)" --json
```

The probe keeps independent serial and concurrent cursors, alternates ordering across 30 pairs,
waits between pairs so a live session can advance, and resets both cursors at cycles 10 and 20.
It fails if either mode does not observe post-initial advances, sees an event gap or version
regression, or cannot replay its last-known snapshot/event cursor after a reset.
