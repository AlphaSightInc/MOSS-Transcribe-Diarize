---
id: T-22
map: map-002-phase2-multiuser
title: Biometric consent and voiceprint privacy boundary for a team deployment
type: grilling
status: closed
assignee: codex-20260826
blocked_by: [T-13]
---

## Question

What is the consent and privacy boundary for durable named voiceprints once the deployment
widens past the operator's own meetings to a team (C2)?

Phase-1's closed *Voice-bank persistence* ticket ruled session-end vector journaling ON for the
guarded tailnet and explicitly left consent **open** for any wider rollout — this is that
reckoning, now that the bank becomes durable, named, and shared-server. A voiceprint is
biometric data about a person who may not be a user at all (a meeting counterparty).

Decide, with the operator, informed by *LiveTranscribe voice bank internals* (what is actually
stored and how identifying it is):

- **Whose voices may be banked** — team members only (each consents at first sign-in)? Any
  meeting participant the account owner names? Explicitly not third parties?
- **Consent mechanics** — recorded where, shown when (first-run notice, per-meeting), and what
  "no consent" does to matching (never bank vs bank-but-unnamed vs discard vectors).
- **Deletion and right-to-remove** — who can delete a voiceprint (the named person? the account
  that created it? the operator?), and what deletion touches (vectors, names, past transcript
  labels).
- **Exposure surface** — voiceprints are per-account private, or shared across the team bank?
  (Design consequence lands in *Voice bank design*; the privacy ruling is made here.)
- **Retention** — do banked vectors expire; does the Phase-1 session-end journal inherit the
  same rules retroactively?

Resolution records the ruling as policy statements the spec and acceptance gates cite
verbatim. Jurisdictional legal review is out of scope; the operator rules for their own
deployment.

## Resolution

Resolved 2026-08-26 by operator grilling.

The Phase-2 MVP uses the following binding policy:

1. **Every voice bank is private to one authenticated user.** A durable Voiceprint and
   every vector sample in it belong to that user. No other user may list, read, match against,
   rename, update, or delete it. There is no team-shared bank.
2. **Any voice the user deliberately names is eligible.** The represented person need not be
   a MOSS user or meeting participant; the Voiceprint may represent a teammate, counterparty, or
   recorded-media speaker such as a YouTube or podcast host. MOSS does not require separate
   consent from the represented person.
3. **Manual naming is enrollment.** When the user manually names a session speaker, MOSS
   automatically creates or updates a Voiceprint in that user's bank. Unnamed session-speaker
   vectors are discarded at session end. An automatic match may rename a session speaker but
   does not itself persist another vector sample.
4. **The feature is always on.** MOSS shows no first-use or per-meeting consent prompt and
   provides no setting that disables Voiceprint learning or matching.
5. **Only the owning user may delete a Voiceprint.** Deletion removes its stored display name and
   all vector samples and immediately prevents further matching, including from an active
   session. It does not rewrite names already stored in historical transcripts. The operator
   has no Voiceprint-level deletion power.
6. **Voiceprints do not expire.** A Voiceprint remains until its owner deletes it or the owning
   account is deleted; account deletion removes the entire private voice bank.
7. **Phase 2 starts with empty voice banks.** It never reads or imports the session-keyed,
   unnamed Phase-1 vector journal. That legacy data has no compatibility guarantee and may be
   discarded; no cutover or migration plan is required. Only post-login manual naming creates
   Phase-2 Voiceprints.

The storage schema, matching thresholds, abstention behavior, sample aggregation, and
embedder-version handling remain owned by *Voice bank design*; they must preserve this policy.
