# Authlib 1.7.2 offline validation prototype

## Question

Can the exact Authlib 1.7.2 Starlette client configuration used by MOSS reject signed
OIDC failures locally, before any Account admission or callback token request?

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/moss-phase2-auth-only.NTprLU \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python \
  -m pytest -q -s tests/phase2/test_google_account_workspace.py
```

## Measured verdict — 2026-08-27

The absorbed deterministic prototype generated one local RSA key, installed only its
public JWK in the configured Authlib remote metadata, and made no HTTP requests.

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
