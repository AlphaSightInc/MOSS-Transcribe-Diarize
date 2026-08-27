# Account revocation generation prototype

## Structural question

How can re-allow restore the same Account without reviving workspace or Meeting authority created
before Account revoke?

## Hypothesis and falsifier

A monotonic Account authority generation is the minimum additional state. Revoke increments it;
owner-bound handles capture it; every read and mutation requires an enabled Account with the same
generation. A pre-revoke handle that reads or commits after revoke, including after re-allow,
falsifies the design.

## One command

```bash
uv run --frozen --extra dev pytest -q \
  tests/phase2/test_google_account_workspace.py::test_reallow_does_not_resurrect_pre_revoke_workspace
```

## Full measured state and verdict — 2026-08-27

Baseline without a generation: **FAIL** — the pre-revoke workspace created a new active Meeting
after revoke, explicit re-allow, and fresh same-`sub` sign-in.

With `accounts.authority_generation`: the stale workspace is rejected, while a workspace returned
by the fresh sign-in creates and reads one active Meeting. This exact sequence is retained as the
test above.
