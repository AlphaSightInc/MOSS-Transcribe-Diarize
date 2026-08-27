# ADR-0006: Account workspace makes cross-Account delivery unrepresentable

- **Status:** Accepted
- **Date:** 2026-08-27
- **Scope:** Phase-2 ownership and authorization

## Context

Phase 1 has one shared principal and global resource lookup. Phase 2 serves several known-team
Accounts, and disclosure of one Account's content to another is unacceptable. Route-by-route owner
checks would spread the central invariant across every caller.

## Decision

Each durable Meeting has exactly one Account owner. Authentication opens one Account workspace
whose interface is `list meetings`, `create meeting`, and `open meeting`; `open meeting` returns an
owner-bound Meeting handle. Every read, stream, mutation, download, background result, and
relationship crosses that interface. Routes never accept an `account_id`, repositories never expose
global owned-resource lookup, and resource identifiers or event cursors convey no authority.

Wrong-owner identifiers resolve as `404`; invalid or revoked Sign-in sessions resolve as `401`.
There is no product administrator content path, co-ownership, cross-Account sharing, legacy token,
view token, pairing/device grant, or compatibility mode.

## Consequences

- Same-Account devices share history and live observation through the same workspace.
- Operator status remains Operational metadata only; machine authority does not grant content access.
- The acceptance harness tests the workspace interface and every public route with two Accounts;
  code review alone cannot establish isolation.
