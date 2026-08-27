# ADR-0009: Each Account owns one private Voiceprint bank

- **Status:** Accepted
- **Date:** 2026-08-27
- **Scope:** Phase-2 Wave-2 speaker identity

## Context

Phase-1 speaker identities are Meeting-local. Phase 2 needs durable recognition without treating a
display label as identity, sharing biometric derivatives across Accounts, or copying an unmeasured
threshold from a different encoder.

## Decision

One private server-side Voiceprint bank belongs to one Account. Opaque Voiceprint ID is identity;
labels are non-unique display text. The Account Speaker Identity module alone may match evidence,
manually name a Meeting Speaker, list Voiceprints, rename one, or delete one.

Manual naming during active capture enrolls the quality-gated album centroid at the existing 2.0 s
enrollment floor. Pending enrollment completes exactly once at the first eligible centroid. Matching
uses the production WeSpeaker encoder, clamped cosine similarity `>=0.46`, no runner-up margin,
at least 1.0 s eligible speech, and the L2-normalized arithmetic mean of samples. Otherwise it
abstains and retains `Speaker N`. Automatic matches never enroll.

Each Voiceprint records embedder identity and dimension. An incompatible entry alone becomes
`re-enrollment required`. Delete is by Voiceprint ID, removes samples and links, preserves historical
transcript labels, advances the Account-bank revision, and fences results captured under an older
revision before returning.

## Consequences

- Duplicate labels never select, merge, or update a Voiceprint.
- Rename propagates to linked active Meetings; stopped Meeting text stays recorded.
- The accepted evidence covers five speakers, two English recordings, and banks up to five;
  broader populations remain unmeasured.
