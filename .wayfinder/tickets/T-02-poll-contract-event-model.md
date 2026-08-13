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

## Operator rulings recorded 2026-08-13 (ticket stays OPEN for the mechanical mapping)

Three of this ticket's questions are now settled by operator decision. The remaining work —
questions 1, 2, 3 and 6, the event/type mapping itself — is mechanical and needs no further
operator input.

**Q5, retro-sweep arrival — minimal effort.** No blocking, no dedicated finalization screen.
The adaptive poller already drops to 2 s in the finalizing/idle phase per C3, so this costs
nothing new: keep polling, let relabels land, drive the reference's existing `finalizing` flag.
Export stays available **at all times**, marked *provisional attribution* until finalization
lands. The user is never held hostage to the tab, and is never silently handed a transcript
whose speaker labels are about to change. Rationale: MVP feasibility is the near-term goal, so
buy correctness-of-disclosure rather than correctness-of-timing.

**Lane health — two meters plus one plain-language status line; everything else hidden.**
MOSS's per-lane accepted/failed/retained samples, device epoch, replay-prune watermark, stable
failure codes, queue depth, and 429 backpressure do **not** surface in the product UI. The two
meters are already required by the capture preflight, so they carry no extra design cost. The
status line renders plain language — "Meeting audio stopped", "Server catching up" — mapped from
the stable failure codes. Full diagnostics stay in `/live` (kept per T-09) and server logs, where
the operator already looks. This keeps C2's visual discipline without discarding the facts.

**Reload mid-capture — sessionStorage stash and reattach.** Stash session id + token in
`sessionStorage`; on load, attempt reattach and resume the poller from its existing cursors.
This is unusually cheap here because MOSS's `since_seq` / `since_version` cursors already make
resume a native operation rather than a new mechanism — the reason C3 called polling stronger
than the reference's cursor-less WS. Survives an accidental refresh; does not survive a tab
close. This also removes the orphaned-session concern from the map's *Not yet specified*: a
reattaching client reclaims its own decode slot instead of stranding it.

Open consequence for the mapping work: `sessionStorage` (not `localStorage`) is deliberate —
it dies with the tab, so a shared-token deployment does not leave capture authority sitting in
a browser profile indefinitely.
