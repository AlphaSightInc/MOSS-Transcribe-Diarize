---
id: T-01
map: map-001-phase1-chrome-client
title: Shared-token trust posture and client identity
type: grilling
status: closed
assignee: operator+claude
blocked_by: []
---

## Question

C5 drops pairing for Phase 1 in favour of one shared bearer token from server config.
What exactly does the server bind a live session's ownership to, and what security posture
are we stating?

The problem this ticket exists to resolve: the capture token currently resolves to a
**device principal**, and every frame/snapshot/events path checks
`session.owner_device_id == that device`. One shared token means every client resolves to
the *same* device, so:

- the measured cross-client isolation (`other snapshot=403`, two Chrome profiles) **is lost** —
  any client can read any other client's live transcript;
- C9 keys the Phase 2 voice bank on `device_id`, and there would be no per-client id to key on.

Resolve, at minimum:

1. Does Phase 1 accept a **single trust domain** — everyone holding the shared token is
   trusted to read every session — and state it as the posture? On a tailnet where the token
   is already shared, a client-asserted id buys no real confidentiality, so honesty about
   this may be better than a security-looking mechanism that is not one.
2. Or does the browser mint and store a **client-generated `device_id`** (uuid in
   `localStorage`, sent as a header) that the shared token authorizes but does not
   authenticate? This preserves session-routing semantics and gives Phase 2 its key at
   near-zero cost, but a malicious in-domain client could assert another's id.
3. What does `LiveAccessRegistry` actually have to change? The goal is the smallest possible
   diff, because its current form carries 15/15 gates and 33/33 killed mutations. Prefer a
   configuration mode over new authority logic.
4. Where does the view token go? Today it is session-scoped and read-only, minted by
   `bind_session`. Does a shared-token Phase 1 still mint per-session view tokens (and if so,
   does the browser ever need to see one), or does the capture token cover reads too?
5. What is the migration story to Phase 2 pairing — does the Phase 1 shape make pairing an
   additive re-enable, or a rewrite?

Ground truth: `moss_transcribe_diarize/app/live_auth.py`;
`docs/research-chrome-capture-mvp-2026-08-03.md` §"Why transcripts do not cross clients" and
§"Authentication/onboarding constraints" (note its warning that `localStorage` is
XSS-exposed and not equivalent to Keychain/DPAPI, and that the current server rejects
query-only tokens).

## Resolution

**Single trust domain, accepted and stated (operator, 2026-08-13).**

Phase 1 ships one shared bearer token from server config. Every client resolves to the same
device principal, so cross-session reads are permitted: any holder of the token can read any
session's transcript. The operator's ruling: *"it's fine, everyone on the LAN sees the
transcript."*

This is recorded as the **security posture**, not an oversight:

- The deployment is LAN/tailnet-only behind a guarded network boundary.
- The token is already shared, so a client-asserted `device_id` would provide no real
  confidentiality — it would look like security without being security. Rejected for that reason.
- `LiveAccessRegistry` therefore needs a *configuration mode*, not new authority logic. Keep its
  15/15 gates and 33/33 killed mutations intact; do not rewrite the authority path.

**Consequences that other tickets must honour:**

- The historical `403` cross-read isolation result **cannot** be a Phase 1 acceptance criterion.
  T-11 must restate its isolation gate accordingly rather than carrying forward a criterion this
  posture makes unsatisfiable.
- Phase 2's `device_id`-keyed voice bank (C9) has **no key** under this posture. Re-enabling
  pairing is a Phase 2 precondition for the bank, not an optional enhancement. Recorded on T-12.
- Sessions remain individually addressable by server-issued id; routing is unchanged. What is
  gone is *enforcement*, not addressing.
