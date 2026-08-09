# DL2/F2-A hour-10 decision packet

Deadline: 2026-08-06 07:50 ET. This packet is required even if capture or audit is incomplete.

## Captured and retained safely

Fill: session IDs/shapes/durations, lane/tape verification, bytes captured vs 2 GiB, derived hashes, raw deletion state, failures.

## Audited

Fill: operator attestation per session, LISTEN rows resolved, unresolved questions, acceptance eligibility.

## Measured

Fill: F2-A status (`NOT_RUN`, `PRELIMINARY-SMALL-N`, or gate verdict), frozen spec/split hashes, arm metrics, compute, raw evidence hashes. Never report a gain without raw evidence.

## Safety and integrity

Fill: TTL compliance, services before/after, both-lane proofs, no TCC/volume/service/manifest mutation, program cap ledger, remaining raw paths and deletion deadlines.

## Decision

Choose one with evidence: continue capture/audit; freeze and run a larger F2-A campaign; product-stage candidate justified; or BLOCKED with the missing evidence named.
