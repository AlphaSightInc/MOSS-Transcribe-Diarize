# Phase-2 shared Meeting-history prototype

## Contract

The one-command probe asks whether six primitives are sufficient for one Account history: durable
Meeting summaries, one active-first total order, derived browser query/date-group/selection state,
owner-bound rename with manual-title provenance, the existing active-Live observer, and refresh
reconciliation. The probe prints
each primitive's boundary and irreducibility, invariants, assumptions/unknowns, falsifier, and the
necessity plus rejection result for every experiment before printing transition state.

The smallest reference-compatible hierarchy is:

1. Active
2. Today
3. Yesterday
4. Earlier

The single Active section contains every active Meeting before any terminal Meeting, even when an
active Meeting is older than today's terminal work. Terminal Meetings reuse the reference's three
local-calendar date groups. Within every emitted group, `created_at_ms` descending is primary and
opaque Meeting ID descending under SQLite binary/ASCII code-point order is the deterministic
tie-break; the probe attacks it with mixed-case, underscore, and hyphen base64url IDs. Search filters title, mode, status,
and transcript text locally;
selection is a locator retained across refresh only while it remains in the Account-owned list;
the refreshed record replaces stale selected details. Neither grants authority. Day classification
uses the browser's local calendar: the probe demonstrates that the same two instants are
`Yesterday` in UTC and `Today` in America/New_York, making the time-zone boundary explicit.

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --frozen --extra dev python prototypes/phase2-shared-history/probe.py
```

## Verdict

**Accepted.** The full-state run produced mixed Live/upload/URL-origin File records across active,
completed, failed, and interrupted states. The one Active section placed a two-day-old active File
Meeting before today's terminal work. Same-time terminal records used the opaque-ID tie-break.
Case-insensitive transcript search selected only the URL sentinel without disturbing an independently
selected active Meeting.

Two same-Account snapshots diverged only until explicit refresh after an owner-handle rename; then
both carried `Customer URL review` with `manual` provenance, repaired stale selected details, and a
simulated restart retained the title/provenance and identical group order. Opening that Meeting from
another Account returned not-found, created no handle, and changed zero owner rows. Blank title is
rejected after trimming; no unmeasured length ceiling or durable history cursor is introduced.

Production should therefore deepen the existing seams rather than add a history repository:

- Account workspace list supplies the one durable active-first order.
- Owner-bound Meeting handle supplies rename.
- The browser derives search, local-day groups, and selection and reconciles on refresh.
- The existing cookie-authorized Live poller remains the only active observation path.

The production regression carries those measured boundaries through the actual TLS app and built
browser bundle: two isolated Chrome profiles receive distinct Sign-in sessions for one Account,
render the same active transcript read-only at desktop/mobile sizes, converge an owner rename after
explicit refresh, and lose observation rather than resuming capture on reload.

The design is rejected if production evidence finds any terminal-before-active result,
non-deterministic group order, same-Account non-convergence after refresh, restart title loss,
foreign mutation, or capture authority in the history observer.
