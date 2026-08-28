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
- The owner-task probe in `prototypes/phase2-owner-bound-file-task/` accepts the smallest reliable
  background seam: an application-owned strong-reference set retains coroutines that carry their
  original owner-bound Meeting handle. Browser detachment does not cancel accepted work, and a
  revoked handle cannot commit; no job identity or global Meeting lookup is introduced.
- The extended probe rejects cancel-and-delete shutdown: cancellation does not stop `to_thread`.
  The accepted seam shields and retains that runner task, fences its commit, waits for synchronous
  inference to quiesce, and only then removes source work and closes persistence. Startup first
  interrupts durable active Meetings, then removes children of the dedicated transient `file-work`
  root before admission. Cleanup failures are retrieved and logged without content.
- The serial URL probe in `prototypes/phase2-serial-url-acquisition/` accepts one transient source
  acquisition as the only additional primitive. Direct HTTP(S) media enforces declared and streamed
  2 GiB limits, a 30-second network-inactivity timeout, a 3,900-second total timeout, and five
  redirects. Known YouTube hosts use pinned `yt-dlp[default]` with `--no-playlist` semantics and
  explicit `bestaudio/best` stdout: Python enforces the strict byte ceiling while draining one
  `input.media`. The downloader runs in its own process group, which oversize, timeout, and cancel
  terminate before removing partial output. Direct HTML is rejected. The acquired path enters the
  same owner-carrying File task, while each item remains an independent Meeting and no batch
  identity exists. yt-dlp's manifest `--max-filesize` and parent-only kill were measured-rejected.
