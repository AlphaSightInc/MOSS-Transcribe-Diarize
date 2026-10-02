# ADR-0004: Browser reload reattaches transcript view, not capture authority

- **Status:** Accepted
- **Date:** 2026-08-17
- **Scope:** Phase 1 live browser reload behavior and terminal viewer authorization

## Context

G6 requires reload mid-capture to reattach from `sessionStorage`. Browser media tracks and the
capture bearer cannot be safely reconstructed after reload. Storing capture authority would enlarge
the credential exposure, while revoking all view access at terminal prevents a reattached browser
from learning why the session ended.

## Decision

1. Persist only `{sessionId, viewToken}` in tab-scoped `sessionStorage`; never persist the capture
   bearer.
2. Reload closes local media resources without sending server Stop, then starts the existing
   read-only snapshot/event poller with the saved view token.
3. The UI explicitly states that transcript viewing was reattached and browser capture stopped.
4. Clean terminal state, failed reattach, explicit detach, and reset clear the saved record.
5. View tokens retain their existing absolute expiry and operator/device revocation. While a session
   is `active` or `closing`, existing scoped view actions remain available. Once `closed`, `failed`,
   or `aborted`, the token may read only snapshot and events; stop and abort are forbidden.
6. Unknown lifecycle states fail closed. Capture ownership remains available to the capture
   principal for cleanup.

## Consequences

- Reload does not silently terminate a server session or store write authority.
- A reattached tab can render the terminal transcript and server-authored failure reason.
- Browser capture itself is not resumed; the operator must start a new capture session.
- Terminal transcript visibility lasts only within the session-scoped token's existing security
  bounds.

## 2026-09-18 — Accepted Stop ends helper-lease authority (WP15)

An authorized Stop which successfully closes capture transfers completion to the
server. Release the helper failure coordinator before awaiting the raw work drain;
retain all other capture registries until their existing teardown. Later helper
silence, failed heartbeats, or request cancellation cannot interrupt that Stop.
A Stop refused for unconsumed frames has not transferred this authority. A lease
expiry that already interrupted capture before Stop remains an interruption.

The Stop `deadline` bounds only the caller's wait. HTTP 202 `stop_in_progress`
means server work continues; it does not mean final or failed. Terminal decoding
failure keeps the committed transcript and explicit failed finalization status.
The durable meeting can be `completed` with failed refinement; these are distinct
fields, not a claim that decoding succeeded.

The browser sends its final stopped heartbeat, requests Stop, then closes local
media. The five-second UI wait is followed by read-only polling, not heartbeats.
No continuing browser presence is required once Stop is accepted. Closing a tab
before Stop reaches acceptance still leaves the capture lease in charge.

Measured basis: `prototypes/stop-lease/NOTES.md` and
`evidence/mvpfix/wp15/`: baseline held-drain departure/outage interruption;
fixed virtual 30-second lease ordering, genuine failure, cancelled request,
45-second wall-clock drain and 90-second wall-clock terminal refinement.
No change to the lease duration, wait deadlines, inference, or identity policy.

## 2026-10-02 — P74 browser capture handoff (U1–U4)

The Phase-2 browser contract supersedes the earlier view-only reload decision:
**U1** reload/reopen within the lease may automatically resume the same Meeting
with stored capture settings. A 409 `capture_page_alive` includes `retry_after_ms`;
the browser retries automatically for up to 8 s before becoming a viewer if the
old writer keeps heartbeating. **U2** missing time remains silence and closed
`capture_interruptions` intervals, with `sample_rate` beside them in the snapshot
`session` and saved document top level. Open gaps are not listed. The browser renders
`([HH:MM:SS-HH:MM:SS] Recording Interrupted)`. **U3** the 120 s lease is unchanged;
expiry, server restart, closing and accepted Stop cannot reopen capture. **U4**
only the originating browser Sign-in session may resume; the replaced page is
a viewer, fenced on frames, heartbeat, Stop and Abort. This server package
implements the handshake and durable metadata; browser restoration and all
transcript exports are a separate package. No server export endpoint or new
renderer; existing Python subtitle exports stay unchanged. Tab audio still needs
Chrome's picker
where gesture-free capture is refused; microphone capture need not wait for it.
No queued audio is recovered. Accepted Stop retains its server-owned outcome.
