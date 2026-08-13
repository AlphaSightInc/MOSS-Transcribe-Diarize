---
id: T-12
map: map-001-phase1-chrome-client
title: Voice-bank persistence — Phase 2's store does not exist and Phase 1 does not create one
type: grilling
status: closed
assignee: claude
blocked_by: []
---

## Question

C9 keys the Phase 2 voice bank on `device_id`, and T-01 resolves what that key *is*. This
ticket resolves what it keys **into** — because, verified against the current tree, there is
nothing to key into, and nothing in Phase 1 creates it.

Filed by the night-ops supervisor (2026-08-12) as a trap, per the map's own convention of
recording traps as tickets rather than assumptions.

## Verified facts, not inferences

1. **The fingerprint album is per-session and in-memory.**
   `moss_transcribe_diarize/app/live_identity_album.py` is a 277-line pure data structure
   (`observe` / `reference` / `exemplars` / `speakers`). It contains no `Path`, no `json`, no
   write/save/persist of any kind. **The album dies with the session.**
2. **No embedding is ever written to disk anywhere in the product.** Grepping
   `json.dump|write_text|open(...,'w')|.save(` across `live_identity*.py` and
   `speaker_identity.py` returns zero hits. `live_identity_sweep.py` rewrites published
   *labels*, not vectors.
3. **There is no retained raw to re-derive vectors from either.** ADR-0003 retention is opt-in
   via `MOSS_LIVE_RETENTION_ROOT` (`ops/start-web.sh:85-92`), and production was deliberately
   deprovisioned on 2026-08-09 — verdict `PASS_EXACT_PRE_SPRINT_PROFILE_RESTORED`, retention
   flags 3→0, root removed.
4. **The one voiceprint-banking mechanism this project has built is unlanded.** Per-lane
   windowed extraction with the pinned production embedder, sealed as derived evidence and
   gating raw deletion, exists only on `ralph/dl2-postreview-rails` (`0983339`). Verified by
   symbol: `verify_vector_evidence`, `extract_session_vectors`,
   `initialize_controller_watchdog`, `authorize_vector_waiver` are **ABSENT from `main`
   (`2f5a83a`) and from production RC `fb83ba5`.**
5. **This was already flagged as needing policy, and deferred.** Production-readiness §7:
   "Decide cross-meeting persistent albums separately with explicit privacy/product policy."

**Therefore Phase 2's voice bank is not CRUD over an existing store.** It requires inventing
cross-session identity persistence — precisely the item previously deferred pending an explicit
privacy decision.

## Why this is worth a ticket now rather than in Phase 2's map

The DL2 capture sprint (2026-08-05→09) produced four speech specimens and then lost **every
acoustic asset**, because raw audio was deleted on a TTL before any vector was banked. That is
what left F2-A unrunnable and Gate 1 at one accepted case. Phase 1 ships two-lane capture at
**product** scale with no persistence and no retention. Unless something banks, this is the same
structural loss repeated — the difference is scale, not kind.

The cost asymmetry matters: banking at capture time is cheap; re-deriving a voiceprint after the
audio is gone is impossible.

## Resolve, at minimum

1. **Does Phase 1 bank anything at all, or does it knowingly discard?** Either is a legitimate
   answer — but it should be a decision on the record, not a side effect of no ticket owning it.
2. **Where would enrollment vectors come from?** Two real options with different costs:
   - **Live-album centroid at session end** — cheap, no retention, no new grant; but quality is
     whatever that session happened to give, and the duration-weighted centroid was tuned for
     within-session matching, not for cross-session enrollment.
   - **Post-session extraction from retained raw** (the `0983339` mechanism) — higher quality and
     re-derivable under a pinned embedder; but requires ADR-0003 retention ON, which reopens TTL,
     byte-cap, and consent, all of which production just deprovisioned.
3. **What is the privacy/consent posture for storing a person's voiceprint across meetings?**
   Materially different from storing transcripts, and different again for non-operator
   participants who never consented to enrollment. This is the deferred §7 policy item.
4. **Deletion / right-to-remove semantics** for a bank keyed on `device_id` — including what
   happens to a shared-token deployment where `device_id` is client-asserted (see T-01).
5. **Does landing D-7 (`0983339`) become a Phase 1 precondition?** If the live-album path is
   chosen instead, then D-7's rail is research-only and should be explicitly scoped that way so
   nobody assumes product coverage it does not provide.

## Non-goal

This does **not** ask to build the voice bank in Phase 1. It asks whether Phase 1 may ship
without deciding whether it is *discarding* the thing Phase 2 is specified to manage.

## Resolution

**Journal the vectors; do not build the bank. (Operator deferred to implementer, 2026-08-13.)**

Phase 1 **banks**, but the narrowest possible thing: at session end, write each speaker's
duration-weighted live-album centroid to a local append-only journal. It does **not** build
CRUD, enrollment, naming, matching, or any UI. Those stay Phase 2.

### Why bank rather than discard

The cost asymmetry decides it. Writing ~200 floats per speaker at stop is a single small writer
with no audio retention and no new grant. Re-deriving a voiceprint once the audio is gone is
impossible. The DL2 sprint already ran this experiment: raw audio hit a TTL before any vector was
banked, every acoustic asset was lost, and F2-A became unrunnable. Phase 1 ships capture at
product scale, so discarding repeats that loss at larger scale.

### What T-01 changed about this

T-01 accepted a single trust domain and rejected client-asserted `device_id`. **There is
therefore no per-client key in Phase 1.** C9's `device_id`-keyed bank cannot be built as
specified, and this ticket cannot pretend otherwise. Consequences:

- The Phase 1 artifact is a **session-keyed vector journal**, not a voice bank: append-only
  records of `{session_id, speaker_label, centroid, sample_seconds, embedder_id,
  embedder_state_sha, created_at, echo_mode}`.
- **Phase 2 must re-enable pairing before it can key or merge the journal into a real bank.**
  Recorded as a Phase 2 precondition, not an enhancement.
- Record `embedder_id` + `embedder_state_sha` on every row. Without the pinned-encoder identity,
  banked vectors are uncomparable after any embedder change and the journal is worthless.

### Retention posture — deliberately NOT inherited from ADR-0003

ADR-0003's opt-in retention governs **raw audio**: large, TTL'd, reconstructible into speech,
and deliberately deprovisioned in production on 2026-08-09. A derived centroid is a different
risk class — a few hundred floats, not invertible to intelligible audio. Conflating the two
would either lose the data (default-off, the exact failure this ticket warns about) or reopen
TTL/byte-cap/consent for no reason.

Ruling: **vector journaling defaults ON; raw-audio retention stays OFF.** State the distinction
explicitly in the ADR so no reviewer assumes ADR-0003's posture transfers.

### The limit of this ruling — flagged, not hidden

A speaker embedding is **biometric data**, materially different from a transcript. This ruling
is scoped to a LAN/tailnet deployment recording the operator's own meetings, consistent with
T-01's accepted posture. It is **not** a consent decision for participants who never agreed to
enrollment.

**Any rollout beyond the guarded LAN/tailnet requires an explicit consent and
deletion/right-to-remove decision before the journal ships.** That is the deferred
production-readiness §7 policy item and it remains open. Do not treat this resolution as having
closed it.

### Not in scope here

D-7 (`0983339` on `ralph/dl2-postreview-rails`) is **not** a Phase 1 precondition — the
live-album path is chosen instead. D-7's rail is therefore research-only and must be scoped that
way so nobody assumes product coverage it does not provide.
