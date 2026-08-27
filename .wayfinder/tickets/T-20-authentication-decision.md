---
id: T-20
map: map-002-phase2-multiuser
title: Authentication decision — Google OIDC with email allowlist, sessions, revocation, fallback
type: grilling
status: closed
assignee: codex-20260826
blocked_by: [T-16, T-19]
---

## Question

How exactly does a browser become an authenticated account, under C5 (external Google OAuth
app + operator email allowlist) and C2 (tailnet origin)?

Decide, with the operator, on the evidence of *Google sign-in for an allowlisted external app*
and the identity model from *Identity and isolation architecture*:

- **Flow and library** — the OIDC integration (library, exact version), callback route, state/
  nonce handling, and what happens on an authenticated-but-not-allowlisted Google account.
- **Allowlist mechanics** — where the operator maintains the email list (config file, DB table,
  admin surface), how removal takes effect, and whether `sub` is captured at first sign-in so a
  later email change cannot re-key the account.
- **Sign-in session** — cookie vs server-side session row, lifetime, idle expiry, logout,
  server-side revocation, and how the capture page's long-lived poller behaves across session
  expiry mid-meeting (must not kill a live capture silently).
- **Authentication UI** — the current Chrome UI already follows the single-user reference and
  its history panel is merely hidden. Add the minimal sign-in, sign-out, denied, and expired-
  session states without redesigning that UI; revealed history is Account-wide across devices.
- **Origin and certificate** — which cert path the MVP ships (per T-16's options) and the
  publishing status of the OAuth app (Testing vs In production) with its user-cap/expiry
  consequences accepted explicitly.
- **Fallback** — does the operator require a non-Google path (local password, invite token)?
  Default: no fallback in MVP; Google-only.
- **Sole auth path** — *Identity and isolation architecture* already rules that shared,
  pairing/device, and view tokens are deleted with no compatibility mode. Specify only the
  Google-backed Sign-in session path; cutover timing belongs to *Wave-1 boundary and Phase-1
  cutover*.

Resolution records the chosen flow, library+version, session lifecycle table, allowlist
procedure, and cert decision — decision-complete for the AFK builder.

## Resolution

Resolved with the operator on 2026-08-26.

### Google flow and sole authentication path

- The MVP is **Google-only**. There is no local password, invite token, Headscale-header,
  shared-token, pairing/device-token, view-token, or emergency-bypass path. A Google outage may
  prevent new sign-ins; existing MOSS Sign-in sessions continue.
- Reuse Google project `ragtest-497122` and its existing branding, but create a **separate Web
  OAuth client for MOSS**. Do not reuse Headscale's client ID or secret. Live inspection found
  Headscale v0.29.2 is itself a Google OIDC client in that project; it is not an identity broker.
- Use **Authlib 1.7.2** with the repository's FastAPI/Starlette stack and
  **itsdangerous 2.2.0** for the signed temporary login transaction. The authorization-code
  flow requests only `openid profile email`, uses PKCE `S256`, `state`, and `nonce`, leaves
  `access_type=online`, and sets `prompt=select_account`. No refresh token is requested; the
  callback's Google access token and ID token are discarded after verification.
- Routes are `GET /auth/google`, `GET /auth/google/callback`, `POST /auth/logout`, and
  `GET /api/auth/session`. The exact registered redirect URI is
  `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/auth/google/callback`.
- Authlib must reject a callback unless signature, `iss`, `aud`, `exp`, `state`, and `nonce`
  validate. MOSS additionally requires `email_verified=true`. The implementation's mandatory
  pre-production prototype proves those failure cases against Authlib 1.7.2 before the library
  reaches the production path; a failed case reopens this decision rather than adding a second
  silent validator.
- Leave the shared Google project's current Testing/In-production status unchanged. This app's
  sign-in-only scope subset is documented as exempt from Testing's test-user list, warning, and
  seven-day authorization expiry, so the inherited status does not change MOSS behavior.

### Exact-email allowlist and Account binding

- `account_allowlist` in the T-21 SQLite database is the sole admission policy. It stores the
  trimmed, lower-cased exact Google email, enabled state, and the Google `sub` it first bound.
  Do not canonicalize Gmail dots or `+` aliases and do not admit an entire domain.
- A local operator CLI owns the table: `mtd-admin accounts allow EMAIL`,
  `mtd-admin accounts revoke EMAIL`, and `mtd-admin accounts list`. There is no web-admin UI or
  config-file reload path.
- On first successful callback, an enabled unbound email binds to the verified Google `sub`,
  which becomes `AccountId`; then MOSS creates or re-enables that Account. A later email change
  never changes `AccountId`: the new exact email must first be allowed, and the matching `sub`
  reopens the same Account. An email already bound to another `sub` is denied and never transfers
  Meetings or artifacts.
- An authenticated but unallowlisted account creates neither Account nor Sign-in session. It
  clears the temporary login cookie and lands on the denied state.
- `accounts revoke` disables the allowlist row and Account and deletes every Sign-in-session row
  in one transaction. Every request resolves both the session row and enabled Account through
  SQLite; the next request therefore returns `401` without a cache/reload delay. Re-allowing the
  email requires a fresh Google sign-in and restores only the same `AccountId`.

### Cookies and server-side Sign-in sessions

- Authlib's `state` and `nonce` live only in a signed, Secure, HttpOnly, SameSite=Lax,
  Path=/ `__Host-moss_oauth` cookie. It lasts ten minutes and is cleared on callback, denial, or
  error.
- A successful callback creates a server-side `sign_in_sessions` row keyed by a
  `secrets.token_urlsafe(32)` opaque session ID. The browser receives only that value in
  `__Host-moss_session`, also Secure, HttpOnly, SameSite=Lax, Path=/, with no Domain attribute.
  No Google token, Account ID, email, or authority-bearing resource ID is stored in-browser.
- MOSS applies **no idle or absolute expiry** and the row has no expiry timestamp. Chrome limits
  persistent cookies to 400 days, so `/api/auth/session` refreshes the cookie to 400 days on
  each application bootstrap. Poll, frame, and event requests neither rewrite the cookie nor
  update SQLite. The session survives browser and server restarts; after 400 days without
  opening MOSS, or after clearing cookies, the user signs in again. There is no Remember-me UI.
- Google logout, password change, account-side OAuth revocation, or grant revocation does not
  revoke an existing MOSS session. MOSS sign-out and the operator CLI are the only MVP
  revocation paths; this is accepted for the known-team tailnet boundary.

| Event | Server and browser behavior |
|---|---|
| Successful Google callback | Create one session row; set the persistent opaque cookie; open Account history. |
| Ordinary authorized request | Resolve session plus enabled Account; open only its Account workspace. |
| Application bootstrap | Perform the same lookup and refresh the browser's 400-day cookie. |
| Sign out | Revoke only this row and clear both cookies; other devices for the Account continue. |
| Unknown/revoked session | Return `401`; never use a cached Meeting grant or identifier to reattach. |
| Operator revokes Account | Disable Account, revoke all rows, and terminally interrupt its active Meetings. |

### Capture behavior and UI

- The Sign-out control first performs normal Stop for the current page's active Meeting and
  waits until transcript/audio are durable; only then does it call logout. If Stop fails, the
  page remains signed in and shows the Stop error.
- Operator revocation terminates every active Meeting for the disabled Account, preserves the
  durable transcript/audio prefix, and marks it `interrupted`, never `completed`. On the next
  request, the browser receives `401`, stops local capture, and shows **Access revoked — partial
  meeting preserved**. Authentication failure never silently leaves the capture UI running.
- Add only four UI states: full-page **Sign in with Google**; **Account not allowed — use another
  Google account or contact the operator**; signed-in email/avatar plus **Sign out**; and the
  blocking revoked/interrupted state. Preserve the existing meeting UI and reveal Account-wide
  history after sign-in.

### Trusted certificate and deployment

- Keep the existing origin and explicit port. Replace its self-signed certificate with a
  Let's Encrypt certificate for exactly
  `ga0-alienware-rtx4070ti.tailnet.aisight.us`, obtained by **lego 5.3.1** through NS1 DNS-01.
  The `aisight.us` zone is live on NS1 and DNS-01 works without making the host public.
- Store the scoped NS1 API credential outside the repository and pass it to lego through
  `NS1_API_KEY_FILE`. Uvicorn continues loading certificate and key files through the existing
  live TLS settings. Automated renewal writes the replacement files; the service manager loads
  them only at a zero-live-Meeting restart, never by interrupting capture.
- Do not proxy MOSS through public Headscale/Caddy and do not change to a `ts.net` origin.
  Certificate-transparency publication of this already-named host is accepted.

### Implementation gates handed forward

Before Wave 1 is accepted, prove the Google console saves the exact redirect URI; one allowed
and one denied external Google account traverse the real callback; state/nonce tampering fails;
the persistent cookie survives a browser restart and a server restart; session and Account
revocation produce the lifecycle above; and a browser trusts the renewed certificate without an
interstitial. These are implementation/acceptance evidence, not remaining design decisions.
