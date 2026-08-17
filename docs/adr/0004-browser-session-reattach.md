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
