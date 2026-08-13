---
id: T-02
map: map-001-phase1-chrome-client
title: Poll contract — MOSS snapshot/events mapped onto the reference event model
type: grilling
status: closed
assignee: claude
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

## Resolution (2026-08-13)

### Operator rulings this session

| Fork | Ruling |
|---|---|
| Live tail | **Parse the provisional string into segments and merge into the transcript list**, styled distinctly, marked stale when superseded. |
| Corrections | **Show corrected text silently.** No trace of the original in the UI. |
| `speaker_entity_id` | **Album canonical speaker id**, with the `Sxx` label as display text. |
| `prefix_hash` | **Carried in the contract, not verified** in Phase 1. |

### Q1 — the 9 reference events

Only **five** are reachable in Phase 1. The other four are declared unreachable rather than
left dangling in the type union; the poller must never synthesize them.

| Reference event | Phase 1 | Source |
|---|---|---|
| `session_state` | **reachable** | `/snapshot` → `LiveSnapshot.status` + `failure_reason`; `mode` is client-known |
| `transcript_update` | **reachable** | `/snapshot` → `committed[]` + `provisional`, `seq` from the event stream |
| `transcript_relabeled` | **reachable** | `label_revision_version` increment, or `revised_transcript` appearing; metadata `operation: "post_cluster_relabel"` |
| `refinement_complete` | **reachable** | `identity_finalized` event + its `identity_revision_*` counters |
| `stop_progress` | **reachable** | `stop` / stop-drain events. `llm_state` is **always null** in Phase 1 |
| `speaker_renamed` | **UNREACHABLE** | no rename endpoint exists; Phase 2 |
| `llm_status` | **UNREACHABLE** | no LLM layer; Phase 2 |
| `llm_format_update` | **UNREACHABLE** | no LLM layer; Phase 2 |
| `llm_summary_update` | **UNREACHABLE** | no LLM layer; Phase 2 |

MOSS's own vocabulary (`span_frozen`, `identity_commit`, `identity_finalized`,
`identity_commit_failed`, `stop`, `stop_accounting_mismatch`, `aborted`, `failure`) is
**internal**. It is consumed by the poller and never reaches `dispatchWsEvent()`.

### Q2 — `TranscriptItem` field mapping

One `CanonicalCommit` yields **many** items: its `transcript` is `[start][Sxx]text[end]` and
parses through `TranscriptStreamParser` into `TranscriptSegment(start, end, speaker, text)`.

| Field | Source |
|---|---|
| `start` / `end` | parsed segment times, offset by the span's `start_sample / sample_rate` if span-relative — **verify against a real span before implementing** |
| `text` | `revised_transcript ?? transcript`, parsed (silent-correction ruling) |
| `speaker` | `Sxx` label from the parse — display text |
| `speaker_entity_id` | **album canonical speaker id** from `LiveIdentitySnapshot.canonical_speakers` |
| `display_name` | Phase 1: equals `speaker`. Rename is Phase 2 |
| `state` | `provisional` (from the suffix) → `confirmed` (committed, sweep pending) → `final` (committed, finalization landed) |
| `provisional_stale` | true when the item's `ProvisionalSuffix.generation` has been superseded |
| `segment_id` | `f"{span_id}:{index}"`; provisional uses `f"prov:{generation}:{index}"` |
| `confidence` | `null` — MOSS exposes none |
| `refinement_status` | `online_preview` while provisional; `confirmed` once final. `tentative_refined` unused |
| `preview_speaker`, `deep_refinement_speaker`, `deep_refinement_changed` | **always null** — reference two-pass concepts with no MOSS analogue, and the silent-correction ruling forbids surfacing the changed flag |

**Stable keys are load-bearing.** Committed items key on `span_id:index`, which never moves.
Provisional items re-parse wholesale each generation, so they key on
`generation:index` and are expected to be replaced, not diffed. Without this the merged-list
ruling produces DOM churn on every provisional generation.

**Known consequence of combining the two rulings** (merged provisional list + silent
corrections): the list can rewrite from two independent causes. `provisional_stale` styling
covers the first; the second is silent by decision. Accepted deliberately for reference
fidelity — flagged here so it is not rediscovered as a bug.

### Q3 — lifecycle mapping, and a finding

`SessionLifecycle` maps from `LiveSnapshot.status` plus `failure_reason`.

**`CapturePhase` and `CaptureLaneCode` are now CLIENT-side facts, not server ones.** In the
reference the server owned capture and reported them; under C6 the browser owns capture. The
reference's lane codes are macOS-host-specific (`local_mic_start_timeout`, `unsafe_device`,
`system_audio_no_callbacks`) and are **dropped**. Phase 1 defines a browser vocabulary instead:
permission denied, surface supplied no audio track, track ended, sustained clipping, context
suspended. Per the lane-health ruling these render only as the single plain-language status
line; the raw codes never appear in the UI.

Everything MOSS knows that the UI does not show — per-lane accepted/failed/retained samples,
device epoch, replay-prune watermark, queue depth, 429 backpressure — stays in `/live` and logs.

### Q4 — the two cursors

- `/snapshot?since_version` is **authoritative state**: status, committed[], provisional,
  identity, `label_revision_version`. It is a full replacement, not a delta.
- `/events?since_seq` is **discrete happenings**: drives `stop_progress`,
  `refinement_complete`, and the relabel trigger.
- Cadence per C3: **250 ms while capturing, 2 s while finalizing/idle.**
- **Advance each cursor only after render** — the existing `/live` portal's discipline; keep it.
- Status handling: `404` session gone → terminal, clear reattach stash. `409` terminal → stop
  polling and surface. `429` on the frame path is **non-terminal backpressure** (retry, never
  terminal) — the legacy mono path's 429 *is* terminal, so Phase 1 must only ever send v2 lane
  frames.

### Q5 / lane health / reload

Settled earlier this session; see "Operator rulings recorded 2026-08-13" above.

### Q6 — idempotency

Replay-safe by construction: `/snapshot` is a **full state replacement keyed by `version`**, so
re-applying it is a no-op, and `/events` dedupes on `seq`. No client-side dedupe is required
beyond ignoring events with `seq <=` the last rendered one. This is why C3 called the cursors
stronger than the reference's cursor-less WS, and it is what makes the reattach ruling cheap.

### `prefix_hash`

Carried through the contract, **not verified** in Phase 1. Keeps the field available and adds no
failure mode the user cannot act on. Revisit if a Phase 2 durable transcript needs integrity proof.

## CORRECTION to Q3 (2026-08-13) — capture health is SERVER-authoritative

The Q3 ruling above said `CapturePhase` / `CaptureLaneCode` become client-side facts. **That is
superseded.** Operator constraint — minimize client-side *judgment* for cross-platform
consistency — plus an existing mechanism make server authority correct.

### The mechanism already exists and is tested

Built for the native macOS helper, and a browser client is simply another helper:

- `POST /api/live/sessions/{session_id}/heartbeat`, authorized action `"heartbeat"`
- `HelperHeartbeat`, schema `moss-live-helper-health.v1`: overall `state` plus per-lane
  `HelperLaneHealth { state, failure_code, ... }`. Validation is strict — a `failed` lane
  requires a non-empty `failure_code`.
- `HelperPresenceRegistry.observe()` → `HelperPresenceSnapshot`
- `LiveHelperFailureCoordinator.observe()` — **the server-side failure decision**
- `_helper_presence_payload()` already rides in the snapshot response

### The division of labour

| Observable only by the client | Observable only by the server |
|---|---|
| permission denied; picker cancelled; surface supplied no audio track; track `ended`; `AudioContext` suspended; sustained clipping | frame arrival/absence; sequence gaps; per-lane accepted/failed/retained accounting; silence across time; backpressure; whether the mixer can seal its frontier |

Neither is sufficient alone. The client cannot distinguish "my frames are not arriving"
(network) from "I am not sending" (capture dead). The server cannot distinguish permission
denied from not-yet-started from network loss — all three present as absence of frames.

**Ruling:** the client **reports** browser-only facts in the heartbeat and makes no judgment.
The server **fuses** them with its own frame facts, owns the vocabulary, and publishes one
`capture_phase` plus one plain-language status line in the snapshot. The client **renders** that
string. This is what the lane-health ruling (two meters + one status line) already implies.

### Consequences

1. The reference's macOS-specific `CaptureLaneCode` values are still dropped. The replacement
   vocabulary is **server-owned**, additive to `HelperLaneHealth.failure_code`, and shared by the
   native helper and the browser — not a separate browser-side enum.
2. **Sub-question for the capture-page spec (T-06):** do browser conditions fit the existing
   `HelperState` / `failure_code` vocabulary, or does it need additive extension? Extend
   additively; do not fork a parallel vocabulary.
3. **Trap — heartbeat cadence must not be timer-driven.** `live_helper_lease_seconds` is
   required config and abandonment is judged against it. A backgrounded tab throttles
   `setInterval` to as little as **once per minute**, which can trip the lease and kill a
   *healthy* session. Frame POSTs avoid this only because they are driven by worklet port
   messages (measured: hidden-tab p95 506.5 ms vs foreground 508.1 ms). **Heartbeats must ride
   the same worklet-driven path**, or the lease must exceed the worst-case throttle. Carry this
   into T-06 and into the Phase 1 acceptance gates.
4. Client logic reduces to: detect, name, report, render. No client-side state machine for
   capture health.
