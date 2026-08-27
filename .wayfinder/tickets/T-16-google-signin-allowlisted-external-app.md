---
id: T-16
map: map-002-phase2-multiuser
title: Google sign-in for an allowlisted external app — flow, framework, cert, lifecycle
type: research
status: closed
assignee: charting-research-20260826
blocked_by: []
---

## Question

Can Google OpenID Connect supply account authentication for this MVP without the server storing
passwords, under premise C5 (external OAuth app, any Google account authenticates, server admits
an operator email allowlist) and C2 (tailnet-only origin,
`https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861`, self-signed today)? Use **current
official documentation and primary sources only**; record exact versions and dates.

Surface:

- **OIDC flow fit** — authorization-code flow for a server-rendered FastAPI app: endpoints,
  `openid email profile` scopes, `sub` as the stable account key (not email), ID-token
  validation requirements.
- **External-app constraints** — consent screen, publishing status: what "Testing" vs
  "In production" means for an unverified external app in 2026 (user caps, 7-day refresh-token
  expiry in Testing, re-consent warnings), and whether sign-in-only scopes require verification.
- **Redirect URI rules** — can an external app register `https://…tailnet.aisight.us:7861/…`
  (private-resolution HTTPS host with explicit port)? Exact current rules on ports, private
  hosts, and TLS for redirect URIs; does the self-signed cert break the flow anywhere Google
  touches (it never fetches the redirect, but confirm) and what the browser-side requirements
  are.
- **Certificate options for the origin** — realistic paths to a browser-trusted cert on a
  tailnet name under `aisight.us` (DNS-01 ACME on the public zone, Tailscale cert on a
  `ts.net` name, keep self-signed) and what each changes for OIDC and for the existing
  `:7861` origin.
- **Maintained framework integrations** — current maintained Python libraries for OIDC in
  FastAPI (e.g. Authlib; note exact versions, licenses, release cadence), session-cookie
  practice (signed cookie vs server-side session row), CSRF/state/nonce handling.
- **Lifecycle** — logout, Google-side revocation, allowlist-removal takedown latency, token
  refresh needs for a sign-in-only app (likely none — confirm).
- **Fallback** — the minimal non-Google fallback if the operator ever requires one (note
  options only; no decision here).

Record findings in `.wayfinder/research/T-16-google-signin.md` with source URLs, retrieval
dates, exact quotas/limits, and an explicit "unverified until tried" list. This ticket informs
the decision ticket *Authentication decision*; it decides nothing itself.

## Resolution

Resolved 2026-08-26 by a charting-session research subagent (primary sources only, every claim
carrying URL + retrieval date). Full findings with the source register:
[`../research/T-16-google-signin.md`](../research/T-16-google-signin.md).

Verdict for *Authentication decision* (T-20): **Google OIDC fits premise C5+C2 unusually well
on paper.** A sign-in-only app requesting only `openid email profile` sits in a documented
carve-out three times over:

- **No app verification is mandatory** for non-sensitive-only scopes; even in **Testing**
  publishing status, users requesting only these scopes are documented as not needing the
  trusted-user list, seeing no warning, and not expiring after 7 days.
- **The 7-day refresh-token expiry is moot twice** — that scope subset is exempt, and a
  sign-in-only flow never receives a refresh token (`access_type` defaults to `online`).
- **Redirect-URI rules require HTTPS and a public-suffix TLD but document nothing about
  ports or public DNS resolvability**, and no documented step has Google's servers contacting
  the redirect URI — so `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/...` with a
  self-signed cert is not documented to break anywhere Google touches; only the browser
  validates the origin's cert.
- **Account key = `sub`** (documented verbatim: never email); email+`email_verified` is the
  allowlist policy input only. ID-token validation: signature via JWKS (cacheable), `iss`
  (two valid forms), `aud`, `exp`, `nonce`; `state` for CSRF. Google publishes **no
  RP-initiated-logout endpoint** — logout is app-side session destruction (+ optional token
  revocation endpoint).
- **Cert options**: ACME DNS-01 on the public `aisight.us` zone (CT logs expose the
  hostname), Tailscale HTTPS certs (ts.net names only — would change the origin), or keep
  self-signed (works for OIDC per above). Libraries: Authlib 1.7.2 (BSD-3) + Starlette
  SessionMiddleware as the maintained FastAPI path.

Sharpest open risks (resolvable only by configuring a real client, listed as "unverified
until tried" in the findings): console acceptance of the exact redirect-URI string
(port + tailnet hostname), and whether "Publish app" demands app-domain links / Search
Console domain verification even for an unverified sign-in-only app.
