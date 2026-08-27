---
id: T-19
map: map-002-phase2-multiuser
title: Identity and isolation architecture — structurally unrepresentable cross-user delivery
type: grilling
status: closed
assignee: codex-20260826
blocked_by: [T-18]
---

## Question

What is the identity model and authorization architecture that makes wrong-user transcript
delivery **structurally unrepresentable** (C6), not a route-handler convention?

Decide, with the operator, on the evidence of *MOSS multi-user-relevant current state*:

- **The identity lattice** — account (Google `sub`), browser/device, sign-in session, live
  capture session, capture stream, event cursor, transcript, audio artifact, voiceprint, LLM
  artifact: which identities exist, which are server-generated vs client-asserted (Phase-1's
  *Shared-token trust posture* ruled client-asserted `device_id` security theatre — does that
  ruling carry?), and the ownership edges between them.
- **The enforcement seam** — where authorization lives so no read/stream/download/delete path
  can address another account's artifact: e.g. owner-scoped repositories/handles where a route
  physically cannot query outside its account, vs per-route checks. Consult `/codebase-design`;
  prefer the deep-module seam.
- **Registry redesign** — today's process-local session registry and view grants vs
  account-scoped ownership; what survives, what is replaced; interaction with the dormant
  `Live access registry` (pairing-era) if T-18 finds it present.
- **Sharing** — is any cross-account visibility (operator/admin, meeting co-attendees) in the
  MVP, or is single-owner strict? Operator call; default strict.
- **Adversarial shape** — the concrete misuse cases acceptance will test (stolen session id,
  cursor replay across accounts, reattach after revocation), so *Phase-2 acceptance gates* can
  gate them.

Resolution names the identities, their owners, the enforcement seam, and the CONTEXT.md terms
to add. It does not pick the database (that is *Persistence decision*) nor the sign-in
mechanics (*Authentication decision*).

## Resolution

Resolved with the operator on 2026-08-26.

### Identity and ownership

- The deployment serves **many Accounts**. Each Meeting has **exactly one Account owner**;
  there is no co-ownership, cross-account sharing, or implicit operator content access.
- `AccountId` is the verified Google `sub`. Email is allowlist/display data, never identity.
  The server derives `AccountId`; no client may assert an owner.
- A server-generated, revocable **Sign-in session** proves one Access client acts for one
  Account. Browser/device identity carries no authority. Every valid device for the same
  Account sees the same Account history.
- A durable **Meeting** is the ownership root. Its transient Live session owns capture
  streams and its event stream; the Meeting owns its transcript, retained audio, and LLM
  outputs. A durable Voice profile belongs directly to one Account because it spans Meetings.
- Resource identifiers are locators only. Event cursors are positions inside an already
  authorized Meeting event stream; neither conveys identity or authority.

### Enforcement seam

Authentication opens one deep **Account workspace module**. Its small external interface is
`list meetings`, `create meeting`, and `open meeting`; `open meeting` returns an authorized
Meeting handle through which snapshot/events/control/transcript/audio/LLM/delete operations run.

Routes receive neither a global resource lookup nor a caller-supplied `account_id`. Persistent
repositories and the in-memory live registry remain hidden behind the Account workspace and
partition by Account. Background work carries the owner internally. An authenticated request
for another Account's identifier resolves as not found (`404`) before any content or mutation
path is reached. Invalid/revoked authentication resolves as `401`.

### Registry and UI disposition

- Delete the shared bearer, pairing/device token, and per-Meeting view-token paths. There is
  **no compatibility mode, feature flag, or legacy-token fallback**. `LiveAccessRegistry` is
  replaced by the account-partitioned runtime registry; that registry stores live state but
  grants no authority.
- Reattach uses the current Sign-in session plus Meeting identifier. No cached Meeting grant
  survives authentication revocation.
- Preserve the current reference-derived Chrome UI. Reveal its existing hidden history panel
  as the shared Account-history view. Add minimal authentication UI because the single-user
  reference project has none.
- Authorization is resolved on every request. Revoking one Sign-in session stops that client
  on its next request without affecting the Account's other devices; disabling the Account
  stops every Sign-in session without transferring its data.
- Operator observability is metadata-only. It cannot expose transcript, audio, Voice profile,
  or LLM content.

### Acceptance behaviors handed forward

1. Another Account's Meeting/artifact/job/Voice-profile identifier returns `404` and reveals
   nothing.
2. A cursor replayed with another Account's Meeting identifier returns `404`.
3. Cross-owner feed, stop, abort, rename, rerun, delete, and download attempts have no effect.
4. A revoked Sign-in session receives `401`; stored identifiers cannot reattach; another valid
   Sign-in session for the same Account continues.
5. Disabling an Account rejects all its Sign-in sessions and never transfers ownership.
6. Two devices signed into the same Account see identical history and live updates.
7. Every legacy token is rejected; no compatibility route exists.
8. Operator health surfaces expose metadata only, never owned content.

`CONTEXT.md` now defines Account, Account ID, Meeting owner, Meeting, Meeting artifact, Voice
profile, Sign-in session, Access client, Account history, Resource identifier, Event cursor,
and the transient Live session relationship. Database engine/schema and authentication-session
mechanics remain with their named downstream tickets.
