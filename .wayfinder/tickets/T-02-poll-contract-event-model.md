---
id: T-02
map: map-001-phase1-chrome-client
title: Poll contract — MOSS snapshot/events mapped onto the reference event model
type: grilling
status: open
assignee:
blocked_by: []
---

## Question

C3 keeps MOSS's polling and replaces the reference's `api/ws.ts` with a poller feeding the
identical `dispatchWsEvent()` seam. What is the exact contract that poller consumes and emits?

Resolve:

1. **Event mapping.** The reference `WsEvent` union has 9 members: `session_state`,
   `transcript_update`, `transcript_relabeled`, `refinement_complete`, `speaker_renamed`,
   `llm_status`, `llm_format_update`, `llm_summary_update`, `stop_progress`. MOSS's runtime
   emits a different vocabulary (`span_frozen`, `identity_finalized`, `identity_commit_failed`,
   `stop`, `stop_accounting_mismatch`, `aborted`, `failure`, plus identity revision counters).
   For each of the 9: does it map from existing MOSS payloads, need new server fields, or is
   it Phase 2 (the three `llm_*` members and `speaker_renamed` almost certainly are)? A
   member with no Phase 1 source must be explicitly declared unreachable, not left dangling
   in the type union.
2. **Transcript item shape.** Reference `TranscriptItem` vs what MOSS spans/identity actually
   produce. Which fields are real, which are synthesized, which are absent? This shape is
   consumed by `TranscriptPane`, `mergeTranscript`, `speakerMap`, `transcriptExport`,
   `transcriptSearch` — so getting it wrong ripples through the whole UI.
3. **Lifecycle mapping.** Reference `SessionLifecycle` + `CapturePhase` + `CaptureLaneCode`
   vs MOSS snapshot `status` / per-lane health / stable failure codes. MOSS has genuinely
   richer per-lane facts than the reference UI has places to show; decide what surfaces and
   what is dropped.
4. **The two cursors.** `/events?since_seq` and `/snapshot?since_version` advance
   independently. Define the poller's state machine: when each is called, how the adaptive
   250 ms / 2 s cadence is driven, when cursors advance (the existing `/live` portal advances
   only *after* render — keep that rule), and how a 404/409/terminal status is handled.
5. **Retro-sweep arrival.** ADR-0002's retrospective identity sweep relabels spans after the
   fact, and `identity_finalized` lands after stop. Which reference event carries this —
   `transcript_relabeled` or `refinement_complete` — and how long must the client keep
   polling after stop before it may stop?
6. **Idempotency.** The reference dispatches into signal state that assumes at-most-once
   delivery in places. Confirm replayed events (the whole point of the cursors) are safe, or
   name where dedupe is required.

Ground truth: `frontend/src/api/ws.ts` + `frontend/src/api/types.ts` (reference);
`moss_transcribe_diarize/app/live_transport.py` (`_snapshot_response`, `_snapshot_payload`,
`_v2_snapshot_payload`, `live_events`); `moss_transcribe_diarize/app/live_service_runtime.py`;
`moss_transcribe_diarize/app/live_portal.py` (the existing polling client, including its
render-then-advance discipline and bounded retry/cancellation/stop-drain/poll-timeout).
