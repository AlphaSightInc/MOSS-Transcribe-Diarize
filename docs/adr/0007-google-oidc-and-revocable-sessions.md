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
Meetings before returning. Revoke also increments the Account's durable authority generation;
workspace and Meeting handles capture that generation, so re-allow plus fresh sign-in cannot revive
pre-revoke work. Every later request resolves session plus enabled Account from SQLite.

One in-process Account lifecycle module owns that ordering. Opaque counted gates cover Meeting
creation from before Sign-in-session resolution through Live binding or File/URL task registration.
Sign-out closes and drains only its Sign-in-session gate, runs the shared normal Live Stop for every
binding originated by that session, then revokes it; any Stop or durability failure reopens the gate
and retains the cookie/session. Accepted File/URL work is Account-owned and continues. Host Account
revoke closes and drains the Account-generation gate, synchronously fences every Live binding and
File task before awaiting any one settlement, quiesces transcript/audio work while captured handles
remain valid, recovers any residual active row through its fixed File/Live owner path, and disables
authority last only after a zero-active-row assertion. The Live fence cancels only an in-flight
SQLite transcript commit, whose transaction rollback is atomic; idle and terminal-settlement
workers receive a queued exit and are joined before authority changes. A failed revoke never
reopens that uncertain generation; startup recovery plus a fresh command is the retry boundary.

`mtd-admin` sends one bounded, content-free command to the running product's mode-`0600` Unix socket.
The socket adapter owns no policy and never opens SQLite. There is no second daemon, TCP listener,
admin webpage, or direct-database runtime revoke.

There is no password, invite token, shared bearer, refresh token, Headscale identity forwarding,
emergency bypass, or non-Google fallback. The production origin keeps explicit port `:7861` and uses
a browser-trusted Let's Encrypt certificate obtained through NS1 DNS-01.

## Consequences

- Google outage may block new sign-ins; existing MOSS sessions continue.
- Google-side logout or grant revocation does not revoke MOSS; MOSS sign-out and Account revoke do.
- Re-allowing an email requires fresh Google sign-in and restores only the same Google `sub` owner.

## Measured validation

The deterministic Authlib 1.7.2 prototype in
`prototypes/phase2-authlib-validation/NOTES.md` exercises the production claim options with a
local RSA key and JWK. It accepts one valid token and rejects bad signature, bad issuer,
a wrong audience even when `azp` matches, wrong authorized party, expiry with zero
leeway, nonce, and callback state before Account admission. `email_verified` is rejected at the
MOSS identity boundary. The prototype makes no provider request.

The Account authority-generation prototype in
`prototypes/phase2-account-revocation-generation/NOTES.md` reproduced the baseline failure: after
revoke, explicit re-allow, and fresh same-`sub` sign-in, a pre-revoke workspace created a new active
Meeting. With the generation fence, every pre-revoke list, open, snapshot, and create path is
rejected while the fresh workspace creates and reads an active Meeting.

The lifecycle ordering probe in `prototypes/phase2-account-lifecycle/` measured exact counted drain,
failed-create release, concurrent logout/revoke serialization, logout-failure authority retention,
late/stale generation fencing, reallow, and other-Account isolation. Production integration tests
then exercised the shared two-lane Stop, held Live/File results, fence-all-before-await, interrupted
audio cleanup, cancelled logout reopening, restart-after-failed-revoke, socket single ownership and
shutdown, and browser `401` capture teardown. These results accept the lifecycle module plus thin
Unix transport; no queue, retry framework, or second scheduler was needed.

The corrected probe also makes PASS depend on the exact logout-controlled Meeting IDs and their
durable `completed` states, so a no-op Stop fails. It measured metadata-identical
`available → partial` interruption, cleanup uncertainty remaining active/authorized until retry,
and a queued second publication committing nothing while the first settlement was held and failed.
The phase-policy probe also measured an idle queued exit without cancellation, a cancelled SQLite
commit with rollback and no durable version, and held terminal audio publishing exactly once before
Meeting completion, worker join, and authority disable. Production reproduced that held terminal
audio boundary through the shared Live adapter.
Production tests reproduced transient and persistent unregistered Live-create cleanup, restart
retry, File audio at the publish/finish boundary, the final zero-active assertion, and the same
synchronous publication fence.
