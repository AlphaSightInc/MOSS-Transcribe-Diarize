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
- The owner-bound Live probe in `prototypes/phase2-live-owner-binding/` accepts the same deep seam
  for transient capture: every request resolves its Sign-in session and enabled Account, then enters
  an Account-partitioned in-memory registry carrying the original Meeting handle. The originating
  Sign-in session alone mutates; another same-Account session observes; foreign identifiers never
  reach runtime state. The registry stores state but grants no authority.
- The extended probe accepts one deep Live transport module with two real adapters. Legacy access
  and Phase-2 Account ownership vary only at five hooks: authorize, create, snapshot, events, and
  publication. The module owns frame parsing, v2 lane registries, mixing, tape, heartbeat, Stop,
  abort, error mapping, and capture-state release once. Both adapters produced identical accepted
  frame, out-of-order conflict, and Stop outcomes; held Phase-2 commits kept old snapshot/events
  public until durable release. A second route/protocol implementation is rejected.
- The signed-in workspace loads the existing two-lane Chrome capture client in Account-authority
  mode. It sends only the opaque Meeting ID plus the HttpOnly Sign-in cookie: no browser Account ID,
  shared bearer, view token, or durable capture grant is created. Reload retains observer reattach by
  Meeting ID, while the server arms the existing helper lease at creation so a lost first heartbeat
  or later heartbeat interrupts the original capture.
- `/` composes File, Live, then History in one document scroller. The embedded Live app keeps its
  viewport-height working area but does not own or hide the page scroll; real headless Chrome at
  desktop and mobile viewports must scroll History into view in that order.
- The serial URL probe in `prototypes/phase2-serial-url-acquisition/` accepts one transient source
  acquisition as the only additional primitive. Direct HTTP(S) media enforces declared and streamed
  2 GiB limits, a 30-second network-inactivity timeout, a 3,900-second total timeout, and five
  redirects. Redirect responses are manually streamed and closed unread; every next Location is
  revalidated as HTTP(S), avoiding HTTPX automatic redirect-body buffering. Known YouTube hosts use
  pinned `yt-dlp[default]` with `--no-playlist` semantics and
  explicit `bestaudio/best` stdout: Python enforces the strict byte ceiling while draining one
  `input.media`. The downloader runs in its own process group. An explicitly retained cleanup task
  absorbs repeated cancellation only until that group is quiescent, then removes partial output and
  propagates cancellation; acquisition-owner completion therefore implies no live downloader or
  orphaned cleanup task. Total deadlines use Python 3.10-compatible `asyncio.wait_for`. Direct HTML is
  rejected. The acquired path enters the
  same owner-carrying File task, while each item remains an independent Meeting and no batch
  identity exists. yt-dlp's manifest `--max-filesize`, parent-only kill, anonymous shielded cleanup,
  and automatic redirects were measured-rejected.
