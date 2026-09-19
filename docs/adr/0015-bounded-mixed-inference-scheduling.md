# ADR-0015: Reserve realtime decoder capacity from bulk settlement

- **Status:** Accepted for integration; real mixed-load confirmation pending a counted GPU lease
- **Date:** 2026-09-19
- **Scope:** two active Live meetings plus File, URL, and stopped-meeting finalization

## Context

One serial `LiveServiceRuntime` pump round-robins canonical items across Live meetings. File/URL
decoding and terminal finalization previously bypassed that pump and could call the same decoder
without a shared bound. A priority queue alone cannot preempt a long request already running.

The required behavior has four irreducible facts: ordered work per meeting, realtime capture versus
bulk settlement, non-preemptible decoder calls, and arrival/start/finish clocks. Scheduling must not
change request geometry, transcript words, or identity evidence.

The content-free prototype in
`prototypes/streaming-diarization/mixed-work-scheduler/` replays retained events from
`mono_javier_intro_50s` and `discussion_jamie_dimon_panel`. Sharing one serial slot with a
12-second background request produced 10.6–11.5 second p95 queue waits. Coalescing did not
materially improve that result and would change model context. A second Live pump produced a low
simulation result but does not describe production and initially violated per-meeting ordering.

## Decision

1. Keep one serial canonical Live pump across both admitted Live meetings.
2. Admit no more than two active Live meetings. Refuse the third before durable creation with a
   stable `live_capacity_full` response.
3. Put decoder calls through one process-local gate: at most two calls total and at most one bulk
   background call. Queued realtime capture precedes queued background work. Running calls remain
   non-preemptible.
4. Classify active Live canonical/rolling calls as realtime. Classify File, URL, and terminal
   finalization for a stopped meeting as background. Terminal settlement therefore cannot occupy
   both decoder slots while another meeting still records.
5. File/URL yields at the existing `WindowedRunner` decoder-call boundary. Cancellation fences the
   meeting key before joining its task, so no later queued window dispatches. Existing queued and
   running operator phases expose the wait.

## Falsifiers and evidence boundary

Reject this decision if a reachable test observes more than two calls, more than one background
call, a queued background call starting before queued Live, reordered or duplicated Live work, or
cancelled File work reaching the delegate. Also reject it if two stopped-meeting finalizers block
the remaining active meeting.

The asymmetric deterministic falsifier starts two 30-second settlement calls while Live continues:
the second settlement waits, 26 Live items dispatch during the first, and peak calls remain two.
Unit and product-seam tests cover priority, cancellation, visible state, third-meeting admission,
and the unchanged single-pump topology.

These checks prove policy, not provider throughput. The prototype's sub-second replay latency must
not be substituted for the retained real two-session baseline of 1.7–2.65 seconds. A counted mixed
monologue-plus-panel run must measure queue wait, processing time, pre-Stop backlog, File/URL
completion, asymmetric Stop, saved output, and peak provider concurrency before final qualification.

## Consequences

- One decoder slot remains available to realtime capture whenever only bulk work occupies the
  other. Two Live calls are permitted by the gate but cannot occur today because the canonical
  runtime deliberately has one pump.
- File/URL and terminal completion may take longer during sustained Live capture; their existing
  job state makes that delay visible.
- No new fairness weights, coalescing policy, retry layer, or second Live worker is introduced.
