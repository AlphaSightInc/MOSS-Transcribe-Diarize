# Authlib 1.7.2 offline validation prototype

## Question

Can the exact Authlib 1.7.2 Starlette client configuration used by MOSS reject signed
OIDC failures locally, before any Account admission or callback token request?

## Hypothesis and falsifier

Authlib plus MOSS's explicit issuer, audience, state, nonce, and zero-leeway options accept only
the valid signed transaction. Acceptance of any malformed case below, or any outbound provider
request during the run, falsifies the design.

## One command

```bash
uv run --frozen --extra dev pytest -q -s \
  tests/phase2/test_google_account_workspace.py::test_authlib_172_offline_prototype_rejects_signed_claim_failures_before_admission
```

## Measured verdict — 2026-08-27

The absorbed deterministic prototype generated one local RSA key, installed only its
public JWK in the configured Authlib remote metadata, used Google's documented issuer values,
and made no HTTP requests.

| Case | Measured result |
| --- | --- |
| valid signed ID token | accepted, subject `offline-subject` |
| wrong signature | `BadSignatureError` |
| wrong issuer | `InvalidClaimError` |
| wrong audience | `InvalidClaimError` |
| multi-audience token with wrong `azp` | `InvalidClaimError` |
| expired token with `leeway=0` | `ExpiredTokenError` |
| wrong nonce | `InvalidClaimError` |
| empty Starlette session plus wrong state | `MismatchingStateError`, before token exchange |

`email_verified` is deliberately not an ID-token policy in this prototype. MOSS rejects it
separately at `AuthlibGoogleOidc.complete`, covered by the unverified callback test. The
prototype is retained as that deterministic Phase-2 test rather than a separate executable.
