# ADR-0007: Google OIDC admits Accounts; MOSS owns revocable sessions

- **Status:** Accepted
- **Date:** 2026-08-27
- **Scope:** Phase-2 authentication and Account admission

## Context

The deployment is a known team on the tailnet, including people without `aisight.us` accounts.
MOSS needs verified identity and immediate operator revocation without adding local passwords or a
second identity system.

## Decision

Use a separate MOSS Web OAuth client in Google project `ragtest-497122`, Authlib 1.7.2, authorization
code plus PKCE S256, and only `openid profile email`. Verified Google `sub` is immutable Account ID;
trimmed lower-case exact email is allowlist and display policy only.

One enabled SQLite allowlist row admits a successful callback. MOSS then issues an opaque
server-side Sign-in session in a Secure, HttpOnly, SameSite=Lax, Path=/ `__Host-moss_session`
cookie. Sessions have no MOSS idle or absolute expiry. Sign-out revokes one session; `mtd-admin
accounts revoke EMAIL` disables the Account, revokes all sessions, and durably interrupts its active
Meetings before returning. Every later request resolves session plus enabled Account from SQLite.

There is no password, invite token, shared bearer, refresh token, Headscale identity forwarding,
emergency bypass, or non-Google fallback. The production origin keeps explicit port `:7861` and uses
a browser-trusted Let's Encrypt certificate obtained through NS1 DNS-01.

## Consequences

- Google outage may block new sign-ins; existing MOSS sessions continue.
- Google-side logout or grant revocation does not revoke MOSS; MOSS sign-out and Account revoke do.
- Re-allowing an email requires fresh Google sign-in and restores only the same Google `sub` owner.
