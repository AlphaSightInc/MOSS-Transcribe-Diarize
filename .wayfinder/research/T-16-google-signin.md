# T-16 research — Google sign-in for an allowlisted external app

Ticket: `.wayfinder/tickets/T-16-google-signin-allowlisted-external-app.md` (map-002-phase2-multiuser).
All sources retrieved **2026-08-26**. External research only; nothing was configured or tried — see the
"Unverified until tried" list at the end. "Documented" = quoted/paraphrased from the cited primary source;
"Reasoned" = inference from documented protocol mechanics, explicitly labeled.

## Verdict in one paragraph

Google OIDC fits premise C5 + C2 unusually well on paper. A sign-in-only app requesting only
`openid email profile` sits in a documented carve-out three times over: (1) no app verification is
mandatory for non-sensitive-only scopes; (2) even in **Testing** publishing status, users requesting only
these scopes "do not need to be in the trusted user list, they will not see a warning message, and their
authorizations will not expire after 7 days"; (3) the 7-day refresh-token expiry is moot twice — the same
scope subset is exempt, and a sign-in-only app never receives a refresh token at all because
`access_type` defaults to `online`. The redirect-URI rules require HTTPS and a public-suffix TLD but say
nothing about ports and nothing about public DNS resolvability, and no documented step has Google's
servers contacting the redirect URI — so `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/...`
with a self-signed cert is not documented to break anywhere Google touches; the browser is the only party
that validates the origin's cert. The sharpest open risks are console-acceptance of the exact URI string
(port + tailnet hostname) and whether "Publish app" demands app-domain links / Search Console domain
verification even for an unverified sign-in-only app — both resolvable only by configuring a real client.

---

## 1. OIDC flow fit (authorization-code flow for server-rendered FastAPI)

Primary source: https://developers.google.com/identity/openid-connect/openid-connect (retrieved 2026-08-26)
and Google's live discovery document https://accounts.google.com/.well-known/openid-configuration
(retrieved 2026-08-26).

**Endpoints** (discovery doc, live 2026-08-26):

| Field | Value |
|---|---|
| issuer | `https://accounts.google.com` |
| authorization_endpoint | `https://accounts.google.com/o/oauth2/v2/auth` |
| token_endpoint | `https://oauth2.googleapis.com/token` |
| userinfo_endpoint | `https://openidconnect.googleapis.com/v1/userinfo` |
| jwks_uri | `https://www.googleapis.com/oauth2/v3/certs` |
| revocation_endpoint | `https://oauth2.googleapis.com/revoke` |
| end_session_endpoint | **absent** — Google publishes no RP-initiated-logout endpoint |
| code_challenge_methods_supported | `S256`, `plain` (PKCE available) |
| id_token_signing_alg_values_supported | `RS256` only |

Documented: "Your application fetches the document, applies caching rules in the response, then retrieves
endpoint URIs from it as needed." (OIDC page.)

**Scopes.** Documented: "The scope parameter must begin with the `openid` value and then include the
`profile` value, the `email` value, or both." Minimal sign-in request: `openid email` (add `profile` for
display name/picture). (OIDC page.)

**Account key = `sub`, never email.** Documented, verbatim (OIDC page):
- "you **shouldn't** use the `email` field in the ID token as a unique identifier for a user."
- "Always use the `sub` field as it is unique to a Google Account even if the user changes their email
  address."

Consequence for premise C5: the server's admission check compares the ID token's `email` (with
`email_verified`) against the operator allowlist, but the persistent account key stored in MOSS must be
`sub`. Email is the policy input; `sub` is the identity.

**ID-token validation requirements.** Documented (OIDC page), five mandatory checks:
1. Signature — verify against certs from `jwks_uri`.
2. `iss` — must equal `https://accounts.google.com` **or** `accounts.google.com` (both are valid issuers).
3. `aud` — must match the app's client ID.
4. `exp` — must not have passed.
5. `nonce` — replay protection: "You should protect against replay attacks by presenting this value only
   once."

**JWKS caching.** Documented: "Since Google changes its public keys only infrequently, you can cache them
using the cache directives of the HTTP response and, in the vast majority of cases, perform local
validation much more efficiently than by using the `tokeninfo` endpoint." (OIDC page.)

**`state` / CSRF.** Documented: generate a random per-login `state`; "On the server, you must confirm that
the `state` received from Google matches the session token you created" — this "provides protection
against attacks such as cross-site request forgery." (OIDC page.)

**Token-exchange direction (matters for the tailnet origin).** Documented flow: the authorization code
arrives at the redirect URI via the *user's browser* (302 from Google); the app then makes an *outbound*
POST from the server to `https://oauth2.googleapis.com/token`. No inbound connection from Google to the
app appears anywhere in the documented flow. (OIDC page + web-server guide,
https://developers.google.com/identity/protocols/oauth2/web-server, retrieved 2026-08-26.)

---

## 2. External-app constraints (consent screen, publishing status, verification) — 2026 state

Primary sources, all retrieved 2026-08-26:
- Audience/publishing status: https://support.google.com/cloud/answer/15549945 (the consent-screen help
  now lives under the "Google Auth Platform" console pages — Branding / Audience / Clients; the old
  single consent-screen page https://support.google.com/cloud/answer/10311615 covers branding and defers
  publishing status to the Audience page)
- Verification overview: https://support.google.com/cloud/answer/13463073
- Unverified-apps warning: https://support.google.com/cloud/answer/7454865
- Token expiry: https://developers.google.com/identity/protocols/oauth2#expiration

**Testing status.** Documented (answer/15549945):
- "Projects configured with a publishing status of **Testing** are limited to up to 100 test users listed
  in the OAuth consent screen."
- "Authorizations by a test user will expire seven days from the time of consent."
- **The carve-out, verbatim:** "The only exception to this behavior is if your app requests a subset of
  the following: name, email address, and user profile (through the `userinfo.email, userinfo.profile,
  openid` scopes or their OpenID Connect equivalents). For such requests, **your users do not need to be
  in the trusted user list, they will not see a warning message, and their authorizations will not expire
  after 7 days.**"

Reading for this MVP: per the current doc, a sign-in-only external app satisfies premise C5 ("any Google
account authenticates") **even while left in Testing** — no 100-user listing, no warning interstitial, no
7-day re-consent. This is the single most consequential documented fact and also the one most worth
confirming empirically (see Unverified list) because it makes "publish to production" optional.

**7-day refresh-token expiry.** Documented (oauth2#expiration): "A Google Cloud Platform project with an
OAuth consent screen configured for an external user type and a publishing status of 'Testing' is issued
a refresh token expiring in 7 days, **unless the only OAuth scopes requested are a subset of name, email
address, and user profile**" (via `userinfo.email`, `userinfo.profile`, `openid` "or their OpenID Connect
equivalents"). Additionally moot for this app: refresh tokens are only issued when requested — see §6.
Other documented refresh-token facts (irrelevant to sign-in-only but recorded): limit of "100 refresh
tokens per Google Account per OAuth 2.0 client ID"; tokens die on user revocation, 6 months unused,
password change (Gmail scopes), cap exceeded, admin restriction.

**In production status.** Documented (answer/15549945):
- Publishing = pressing **Publish app**: "A project's publishing status is considered **In production**
  after selecting the **Publish app** button." Verification is required only "if it meets one or more of
  the OAuth verification criteria."
- Unverified-app warning: "Google will display an Unverified apps warning message if your project's OAuth
  clients request authorization of scopes considered **sensitive or restricted** before your project has
  completed verification for those scopes."
- 100-new-user cap: applies to "Apps that present the unverified app screen to users" — quota "100 new
  users in total, after the app presents the unverified app screen" (also answer/7454865).

**Verification requirement for sign-in-only scopes.** Documented (answer/13463073): "**If your app
utilizes only non-sensitive scopes, it is not mandatory for your app to complete the app verification
process.**" Optional lighter "brand-verification" exists solely to display a custom app name and logo on
the consent screen. Sensitive/restricted scopes are what force full verification ("Apps that request
access to scopes categorized as sensitive or restricted must complete Google's OAuth app verification").

**Are `openid` / `userinfo.email` / `userinfo.profile` non-sensitive?** No single page fetched today
carries an explicit label "openid = non-sensitive" (the scopes reference
https://developers.google.com/identity/protocols/oauth2/scopes marks sensitive scopes with an indicator
and states "Sensitive scopes require review by Google and have a _sensitive_ indicator on the Google
Cloud Console's OAuth consent screen configuration page"; the sign-in scopes carry no such marker in the
excerpt retrieved). The classification is however entailed by three independent official exemptions that
name exactly this scope subset (Testing carve-out; 7-day-expiry carve-out; verification exemption for
non-sensitive-only apps). **Reasoned, near-certain; the console shows the category authoritatively when
the scopes are added** — listed under Unverified.

**Net for the unverified-screen trap:** the unverified warning and the 100-user cap are documented as
attaching to *sensitive/restricted* scope requests only. A sign-in-only app is documented to show a plain
consent screen (project name unbranded unless brand-verified) with no warning and no cap, in both Testing
(per the carve-out) and In production.

---

## 3. Redirect-URI rules for `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/...`

Primary sources, retrieved 2026-08-26:
- Validation rules: https://developers.google.com/identity/protocols/oauth2/web-server#uri-validation
- Policy layer: https://developers.google.com/identity/protocols/oauth2/policies
- Consent-screen/authorized domains: https://support.google.com/cloud/answer/10311615

**The complete documented validation rules** (web-server#uri-validation, verbatim per rule):
- Scheme: "Redirect URIs must use the HTTPS scheme, not plain HTTP. Localhost URIs (including localhost
  IP address URIs) are exempt from this rule."
- Host: "Hosts cannot be raw IP addresses. Localhost IP addresses are exempted from this rule."
- Domain: "Host TLDs (Top Level Domains) must belong to the public suffix list."; "Host domains cannot be
  `googleusercontent.com`."; no URL-shortener domains unless owned.
- Userinfo: no userinfo subcomponent. Path: no path traversal (`/..`, `\..`, or encodings). Query: no
  open redirects. Fragment: no fragment component. Characters: no wildcard `*`, non-printable ASCII,
  invalid percent encodings, null characters.

**Ports.** The rules **do not mention ports at all** — an explicit port such as `:7861` is not prohibited
by any documented rule. (Documented absence; console acceptance of the literal string is Unverified.)

**Private/internal hostnames.** No rule requires the host to be publicly resolvable in DNS; the only
domain-shaped rules are the public-suffix-TLD rule and the two domain blocklists.
`ga0-alienware-rtx4070ti.tailnet.aisight.us` has TLD `us`, which is an ICANN TLD on the public suffix
list — the rule is satisfied (reasoned from the rule text + PSL membership of `us`; the rule tests the
TLD, not resolvability). Tailnet-private resolution is a browser-side concern only: the user's browser
must resolve the name (it does, on the tailnet via the `aisight.us` split-DNS/hosts arrangement) — Google
issues a 302 and never resolves the host itself (reasoned; see next point).

**Does Google ever fetch the redirect URI?** Not documented anywhere in the flow: the web-server guide
describes only (a) browser redirect to the URI carrying `code` and `state`, and (b) the app's outbound
token exchange. No server-side fetch, probe, or TLS validation of the redirect URI host is documented.
**Reasoned conclusion: the self-signed cert is invisible to Google.** The policies page adds only a
compliance statement — "OAuth 2.0 clients for web apps must use redirect URIs and JavaScript origins that
are compliant with Google's validation rules, including using the HTTPS scheme" and that URIs must "refer
to domains that you own, that you have been authorized to use... or that you have been explicitly given
license to use" (policy obligation, not a technical check documented as enforced).

**TLS-certificate validity.** No documented requirement that the redirect-URI host present a CA-trusted
certificate — the rules test the URI string's scheme, not the endpoint's cert. Browser-side, the user
must click through / pre-trust the self-signed cert to reach the app at all; once the origin loads, the
OAuth redirect back into the same origin is an ordinary top-level navigation (reasoned).

**Authorized-domains ordering trap.** Documented (answer/10311615): "**Add your Authorized Domains before
you add your redirect or origin URIs, your homepage URL, your terms of service URL, or your privacy
policy URL.**" So `aisight.us` must be entered as an authorized domain before the tailnet redirect URI
can be saved. On Search Console: the page says "If your app needs to go through verification, please go
to the **Google Search Console** to check if your domains are verified" and "If you have **verified the
domain** with Google, you can use any Top Private Domain as an Authorized Domain." **Ambiguous** whether
an unverified sign-in-only app can add `aisight.us` as an authorized domain *without* Search Console
verification — the doc ties the check to "needs to go through verification". Flagged Unverified. (If
required: `aisight.us` is operator-owned; DNS-record verification in Search Console is available and
one-time.)

**App-domain links.** Same page: homepage / privacy-policy / ToS links — "These links are required for
all external production apps" (in the branding context). Whether the **Publish app** button enforces them
for a sign-in-only app, and whether staying in Testing avoids them entirely, is Unverified. Staying in
Testing (viable per §2 carve-out) sidesteps the question.

---

## 4. Certificate options for the origin

Three paths; facts per path. Sources retrieved 2026-08-26.

### Path A — ACME DNS-01 on the public `aisight.us` zone (origin unchanged)

Source: https://letsencrypt.org/docs/challenge-types/ ; https://letsencrypt.org/docs/rate-limits/ ;
https://letsencrypt.org/docs/ct-logs/.

- Mechanism: client puts a TXT record at `_acme-challenge.<YOUR_DOMAIN>` ("your client will create a TXT
  record derived from that token and your account key, and put that record at
  `_acme-challenge.<YOUR_DOMAIN>`").
- Private hosts explicitly supported: "You can use this challenge to validate domain names whose
  webservers aren't exposed to the public internet." — exactly the tailnet case. HTTP-01 is ruled out:
  "The HTTP-01 challenge can only be done on port 80" on a publicly reachable server, and it cannot issue
  wildcards.
- Wildcards: "You can use this challenge to issue certificates containing wildcard domain names" — DNS-01
  is the only challenge that can (HTTP-01/TLS-ALPN-01 cannot).
- Operational requirement: API-automatable DNS for `aisight.us` ("Your DNS provider might not offer an
  API" is the listed con). Provider/API status for `aisight.us` is Unverified.
- Rate limits (2026-08-05 doc revision): "Up to 50 certificates can be issued per registered domain ...
  every 7 days"; "Up to 5 certificates can be issued per exact same set of identifiers every 7 days";
  "A single certificate can include up to 100 identifiers".
- **Certificate-transparency exposure.** Documented: "Let's Encrypt submits all certificates we issue to
  CT logs." Consequence (reasoned): a cert naming `ga0-alienware-rtx4070ti.tailnet.aisight.us` publishes
  that hostname permanently in public, searchable CT logs. A **wildcard `*.tailnet.aisight.us`** exposes
  only the wildcard label, keeping device names private — the standard privacy move for internal names
  under a public zone.
- Effect on OIDC/origin: none structural — origin string stays
  `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861`, redirect URI unchanged, browsers stop
  warning. Renewal automation (certbot/lego + DNS plugin, ~60–90-day cycle) must run somewhere with DNS
  API credentials (Unverified detail).

### Path B — Tailscale HTTPS cert on the `ts.net` name (origin changes)

Source: https://tailscale.com/kb/1153/enabling-https ; https://tailscale.com/docs/features/tailscale-serve.

- Names: **only** `machine-name.tailnet-name.ts.net`; custom domains like `aisight.us` are not supported.
- Prerequisites: MagicDNS enabled; "Enable HTTPS" toggled in admin DNS settings; explicit acknowledgment
  that machine names become public.
- Mechanism: Let's Encrypt via DNS-01 — "Tailscale creates a `*.ts.net` DNS TXT record for your nodes to
  complete their DNS-01 challenges"; private keys stay local ("Tailscale never sees them").
- **CT exposure, verbatim warning:** "Do not enable the HTTPS feature if any of your machine names contain
  sensitive information." and "The machine names are still published in the public ledger." Same CT
  exposure class as Path A single-name — here unavoidable (no wildcard option for your own device names).
- Renewal: `tailscale cert` output is **manually renewed** (daemon doesn't track it); `tailscale serve`
  "automatically provision[s] TLS certificates for your unique tailnet DNS name" and terminates TLS,
  reverse-proxying to a local port ("only `http://127.0.0.1` is supported for proxies") — i.e.
  serve → `127.0.0.1:7861` gives an auto-renewed HTTPS front on the ts.net name, tailnet-only (Funnel is
  the separate public option).
- Effect on OIDC: **origin and redirect URI change** to the ts.net name (TLD `net` — public-suffix rule
  satisfied). With serve, the natural origin is port 443; keeping `:7861` in the public URL would require
  serve on a custom port or the app presenting the ts.net cert itself (cert is name-bound, not
  port-bound — reasoned; untried). Also changes the "authorized domain": `ts.net` is Tailscale's domain,
  not operator-owned — interaction with Google's authorized-domains policy ("domains that you own ... or
  have been explicitly given license to use") is Unverified.

### Path C — keep the self-signed cert (status quo)

- Google-side: nothing documented breaks — URI-string validation only (HTTPS scheme satisfied); no
  documented fetch of the origin by Google (§3). Token exchange is outbound to Google over Google's own
  valid TLS. (Reasoned from documented flow.)
- Browser-side: every operator browser must trust/except the cert before and after the Google round-trip;
  the session cookie needs `Secure` semantics which self-signed HTTPS still provides once trusted.
- Cost: recurring browser warnings on new devices/profiles; no CT exposure at all (nothing is issued).

---

## 5. Maintained framework integrations (Python/FastAPI) and session practice

### Authlib — primary candidate

Source: PyPI JSON API `https://pypi.org/pypi/Authlib/json` fetched directly 2026-08-26 (curl; exact
values), plus https://pypi.org/project/Authlib/ and versioned docs
https://docs.authlib.org/en/v1.6.4/client/fastapi.html / `client/starlette.html`.

- Latest: **Authlib 1.7.2, uploaded 2026-05-06**. License **BSD-3-Clause** (PyPI also advertises an
  optional commercial license). `requires_python >=3.10`. Dependencies: `cryptography`,
  `joserfc>=1.6.0`.
- Cadence (from release JSON — active, two maintained lines): 1.6.8 (2026-02-14), 1.6.9 (2026-03-02),
  1.6.10 (2026-04-13), 1.6.11 (2026-04-16), 1.6.12 (2026-05-04) and 1.7.0 (2026-04-18), 1.7.1
  (2026-05-04), 1.7.2 (2026-05-06). Maintainer: lepture; repo https://github.com/authlib/authlib. Note:
  `authlib.jose` is being deprecated in favor of `joserfc` (now a hard dependency).
- FastAPI integration (documented, v1.6.4 docs — note: `docs.authlib.org/en/latest/` paths returned 404
  on 2026-08-26; use versioned URLs): FastAPI uses the Starlette client; requires
  `SessionMiddleware` to "save temporary code and state in session"; registration pattern:
  `oauth.register('google', client_id=..., client_secret=...,
  server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
  client_kwargs={'scope': 'openid profile email'})`; login route calls
  `await oauth.google.authorize_redirect(request, redirect_uri)`; callback calls
  `token = await oauth.google.authorize_access_token(request)` and — documented — "Authlib has called
  `.parse_id_token` automatically, we can get `userinfo` in the `token`". The docs do not spell out the
  claim-validation depth (iss/aud/exp/nonce) on that page — verify in code on 1.7.2 (Unverified list).

### Alternatives (pinned 2026-08-26 via PyPI JSON)

- **google-auth 2.57.0** (uploaded 2026-08-24; Apache 2.0; `>=3.10`) — Google's own library; provides ID
  token *verification* (`google.oauth2.id_token.verify_oauth2_token`) but no FastAPI flow helper; useful
  as the validation half of a hand-rolled flow.
- **fastapi-sso 0.21.1** (uploaded 2026-06-22; MIT; `>=3.10,<4.0`) — smaller third-party FastAPI SSO
  helper; less depth than Authlib.
- Host framework versions for compatibility pinning: **fastapi 0.141.1** (2026-07-29), **starlette 1.6.0**
  (2026-08-08), **itsdangerous 2.2.0** (2024-04-16, BSD).

### Session-cookie practice

Source: https://www.starlette.io/middleware/ (SessionMiddleware section), retrieved 2026-08-26.

- Starlette `SessionMiddleware`: "Adds **signed** cookie-based HTTP sessions. Session information is
  **readable but not modifiable**." Cookie is always `HttpOnly`. Defaults: cookie name `session`,
  `max_age` = 2 weeks, `same_site='lax'`, `https_only=False`, `path='/'`.
- Required hardening for this deployment (analysis): set `https_only=True` (Secure flag) on the HTTPS
  origin; keep `same_site='lax'` (a top-level GET redirect from accounts.google.com back to the callback
  still carries Lax cookies, which is what lets the session-stored `state`/`nonce` survive the
  round-trip — reasoned, listed Unverified as a behavior check); shrink `max_age` to bound
  allowlist-takedown latency (§6).
- **Signed cookie vs server-side session row** (analysis, no decision): the Starlette signed cookie is
  client-readable (claims like email/sub visible to the user — fine here, they're the user's own) and
  cannot be server-revoked before expiry; a server-side session row (opaque random ID in the cookie,
  session data in SQLite/redis) allows **immediate** takedown when an email leaves the allowlist and
  keeps nothing readable client-side. Either way Authlib only needs *some* `request.session` dict; the
  OAuth `state`/`nonce` live there only for the seconds between redirect-out and callback.
- CSRF: the OAuth callback is protected by `state` (documented Google requirement, §1); app-internal
  POSTs need the usual CSRF token or strict-SameSite treatment — standard practice, out of OIDC scope.

---

## 6. Lifecycle — logout, revocation, allowlist takedown, refresh needs

- **Refresh tokens: none needed, none received.** Documented
  (https://developers.google.com/identity/protocols/oauth2/web-server, retrieved 2026-08-26):
  `access_type` "Valid parameter values are `online`, **which is the default value**, and `offline`" and
  "the refresh token is **only returned if** your application set the `access_type` parameter to
  `offline`". A sign-in-only app that never sends `access_type=offline` holds no refresh token; the
  Testing 7-day rule is doubly inapplicable (also scope-exempt, §2). Confirms the ticket's "likely none".
- **Logout = app-local only.** Google's discovery document contains **no `end_session_endpoint`**
  (verified live 2026-08-26) — no RP-initiated logout; deleting the MOSS session (cookie or row) ends the
  app session while the user's google.com session persists. Re-visiting `/login` will typically silently
  re-authenticate (account-chooser at most) — expected OIDC behavior (reasoned).
- **Google-side revocation endpoint.** `https://oauth2.googleapis.com/revoke` (discovery doc +
  web-server guide: `POST https://oauth2.googleapis.com/revoke` with `token=` parameter; 200 on success).
  Optional for sign-in-only: the only Google artifacts held are a short-lived access token (discardable)
  and the ID token (not revocable — it simply expires). Users can additionally revoke the grant from
  their Google Account permissions page (well-known account-settings path; not captured verbatim from
  today's fetches — minor, Unverified as to exact URL wording).
- **Allowlist-removal takedown latency.** Entirely app-side: Google plays no role after login. Latency =
  min(session lifetime, allowlist re-check interval). Checking the allowlist per request (or per session
  refresh) against the stored email gives immediate takedown; a pure signed cookie without re-check gives
  takedown only at `max_age` expiry (default 2 weeks — shrink it). (Analysis.)
- **Google security events (optional, likely N/A).** Cross-Account Protection / RISC
  (https://developers.google.com/identity/protocols/risc, retrieved 2026-08-26) streams "cryptographically
  signed strings called security event tokens" (sessions revoked, account disabled, tokens revoked,
  credential changes) to a registered HTTPS endpoint, free, optional. **It requires a
  Google-reachable public webhook — incompatible with a tailnet-only deployment** unless a separate
  public receiver is stood up (reasoned). Note-only.

---

## 7. Fallback options (note only — no decision)

- **Tailscale identity headers** (https://tailscale.com/docs/features/tailscale-serve, retrieved
  2026-08-26): `tailscale serve` injects `Tailscale-User-Login` ("the requester's login name (for
  example, alice@example.com)"), `Tailscale-User-Name`, `Tailscale-User-Profile-Pic` for tailnet-origin
  traffic (not for tagged devices; also populated for accepted device-share users). Passwordless,
  no Google dependency, allowlist maps directly onto login names. Caveat, documented: backend must listen
  on localhost only — "any user that can call your service directly (rather than with the Serve URL)
  could trivially provide their own values for these HTTP headers." Forces the serve/ts.net front (Path
  B origin change).
- **Another public OIDC IdP** (e.g. Microsoft/GitHub) through the identical Authlib client path — swaps
  the consent-screen policy surface, keeps the no-password property.
- **Self-hosted IdP** (Keycloak, Authelia) — no external dependency, but the server then *does* operate a
  credential store, weakening the premise.
- **Local passwords** (argon2 via passlib) — contradicts the no-password-storage premise; last resort
  only.

---

## Unverified until tried

Nothing in this ticket was configured or executed. The following remain open until a real OAuth client is
created and exercised:

1. **Console accepts the exact redirect URI string** `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/auth/callback`
   — ports are undocumented (not prohibited) and the PSL rule is satisfied on paper, but acceptance of a
   port + deep tailnet subdomain is only provable in the Clients page.
2. **Authorized-domains gate**: whether adding `aisight.us` as an Authorized Domain (prerequisite for
   saving the redirect URI per answer/10311615) demands Search Console verification for an unverified
   sign-in-only app — docs tie the check to "needs to go through verification"; ambiguous.
3. **Testing-mode carve-out behaves as documented**: an arbitrary Google account (not on the test-user
   list) signs into a Testing-status app requesting only `openid email profile` with no warning and no
   7-day expiry. This is the linchpin fact; verify first.
4. **"Publish app" friction** for a sign-in-only app: whether homepage/privacy-policy/ToS links ("required
   for all external production apps") are enforced at publish time, and what the consent screen shows
   (plain project name vs any unverified wording) in production without brand verification.
5. **Google never contacts the redirect URI / origin** — undocumented rather than documented-negative;
   confirmed only by a successful end-to-end flow behind the tailnet with the self-signed cert.
6. **Authlib 1.7.2 `authorize_access_token` validation depth** — that iss/aud/exp/nonce are all enforced
   (docs confirm automatic ID-token parsing + `userinfo`, not the checklist) and that `email_verified` is
   surfaced.
7. **Session-cookie survival across the Google round-trip** with `SameSite=Lax` + `Secure` on the
   `:7861` origin (state/nonce retrieval at the callback), including on the browsers the operators
   actually use with a self-signed or newly-trusted cert.
8. **DNS-01 practicality on `aisight.us`**: which provider hosts the zone, whether it has an
   ACME-automatable API, and wildcard `*.tailnet.aisight.us` issuance + renewal automation.
9. **ts.net path details** (only if Path B is chosen): serving the ts.net cert on a non-443 port or the
   `:7861` app directly; Google's acceptance of a `ts.net` redirect URI given the authorized-domains
   ownership policy.
10. **Scope classification display**: the Cloud Console showing `openid` / `.../auth/userinfo.email` /
    `.../auth/userinfo.profile` as non-sensitive when added (entailed by three exemptions; never shown
    on a fetched page as a literal label).
11. **Starlette 1.6.0 / fastapi 0.141.1 / Authlib 1.7.2 compatibility** as an installed set (versions
    pinned today from PyPI; co-installation untested), incl. SessionMiddleware's `itsdangerous`
    requirement.
12. Exact user-facing Google Account permissions URL wording for self-service revocation (minor).

---

## Source index (all retrieved 2026-08-26)

| Topic | URL |
|---|---|
| Google OIDC guide (flow, sub, validation, JWKS, state) | https://developers.google.com/identity/openid-connect/openid-connect |
| Live discovery document (endpoints; no end_session) | https://accounts.google.com/.well-known/openid-configuration |
| Web-server flow (redirect-URI validation rules; access_type; revoke) | https://developers.google.com/identity/protocols/oauth2/web-server |
| OAuth policies (compliance layer) | https://developers.google.com/identity/protocols/oauth2/policies |
| Refresh-token expiry (7-day Testing rule + scope exemption) | https://developers.google.com/identity/protocols/oauth2#expiration |
| Audience / publishing status (100 test users; carve-out) | https://support.google.com/cloud/answer/15549945 |
| Consent screen / branding / authorized domains | https://support.google.com/cloud/answer/10311615 |
| Verification overview (non-sensitive exemption; brand verification) | https://support.google.com/cloud/answer/13463073 |
| Unverified-apps warning + 100-new-user cap | https://support.google.com/cloud/answer/7454865 |
| Scopes reference (sensitive indicator legend) | https://developers.google.com/identity/protocols/oauth2/scopes |
| Cross-Account Protection (RISC) | https://developers.google.com/identity/protocols/risc |
| Let's Encrypt challenge types (DNS-01, wildcard, private hosts) | https://letsencrypt.org/docs/challenge-types/ |
| Let's Encrypt rate limits | https://letsencrypt.org/docs/rate-limits/ |
| Let's Encrypt CT policy (all certs logged) | https://letsencrypt.org/docs/ct-logs/ |
| Tailscale HTTPS certs (ts.net only; CT warning; renewal) | https://tailscale.com/kb/1153/enabling-https |
| Tailscale serve (auto-TLS, 127.0.0.1 proxy, identity headers) | https://tailscale.com/docs/features/tailscale-serve |
| Authlib release metadata (1.7.2, BSD-3, deps, cadence) | https://pypi.org/pypi/Authlib/json |
| Authlib FastAPI/Starlette client docs (versioned) | https://docs.authlib.org/en/v1.6.4/client/fastapi.html |
| Starlette SessionMiddleware (signed cookie, defaults) | https://www.starlette.io/middleware/ |
| google-auth / fastapi-sso / starlette / fastapi versions | https://pypi.org/pypi/<pkg>/json |
