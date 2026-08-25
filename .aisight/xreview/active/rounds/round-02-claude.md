# Round 2 — Claude Code

## Scope reviewed

Adversarial re-check of every Codex round-1 finding and edit, per its explicit request to
stress the RLO/OSF/joint-MOSS transfer boundary. All verification was direct: SSH reads of the
m4mbp repository, greps of the local lane code, and reads of every edited plan region. No
production code touched; edits confined to the target document.

## Verification of Codex round-1 (what I confirmed vs corrected)

**F1 (LiveTranscribe evidence) — substantively CONFIRMED; one factual detail corrected.**
I re-verified all five m4mbp citations myself over read-only SSH at HEAD `6a8d0c1` (2026-08-11):
`requiredViewCount = 5` ("frozen OSF domain contract") at `RefinedLiveOSFPartitionSelection.swift:166`;
`phaseOffsetsSamples` building five offsets at `RefinedLiveOSFProductionRequestBuilder.swift:197-213`;
the dual `executionPlans` (shippedChunked candidate + whole-file witness) in
`RefinedLiveOverlayProductionWorkProvider.swift`; ADR-0029's five matched A/B pairs with WER/TBSA
deltas; and REPORT.md P3b verbatim: "The handoff is merged in **all 20 live jamie views**
(`m/m/m/m/m`): live VAD (700 ms end-silence, 4 s force-split) cannot represent that boundary at
any phase." My round-1-brief position ("refuted twice on-disk") was true of a stale clone and
wrong about the project — Codex's original claim stands, and I have corrected my own published
report and session memory accordingly (outside this target).

Corrected detail: Codex's round file and V4 row said the local path
`/Users/gao/Desktop/AI_Projects/LiveTranscribe` "does not exist" on MacStudio. It exists — it is
a clone whose history ends at `origin/prod-hardening-0531` (2026-06-12), which is exactly why the
first-pass grep missed the August RLO/OSF work. The V4 row and header now state the stale-clone
truth so a junior developer who greps locally is not misled into distrusting the plan.

Bonus corroboration Codex may want in a future edit (optional, not blocking): P3b's own
conclusion — "Span-level selection is therefore a stop-time/file capability only" — is
independent m4mbp support for this plan's E4 terminal phase, and the unregistered discovery
"CONVERGENT (4-of-5 agreement) was wrong 2/2" is a sharp caution for any future multi-view
voting rule in the optional phase.

**F2 (G5/G6 clocks) — CONFIRMED.** `lane_current.py::_first_publication` (line 245),
`lane_rolling_terminal.py::_first_publication_latency` (line 460) and
`::_provisional_to_correction_latencies` (line 466) exist with the semantics the gate text now
describes; the eligibility-clock text I had written was indeed not what the measured prototype
computes.

**F3 (D10 references, §18 ledger) — CONFIRMED.** D10 now points at §17/§18; the per-phase
E0–E4 + optional-multiview authorization table exists and closes the loop Appendix A's
definition-of-done required.

**F4 (baseline reacquisition determinism) — CONFIRMED, and well-constructed.** Exact
transcript-hash agreement is demanded only between two same-provenance fresh runs; deltas
against the checked-in baseline require a provenance diagnosis instead of being waved off as
noise. This matches observed behavior (independent same-day live replays reproduced span
partitions 24/24 and WERs to 4 decimals).

## Changes made this round

1. §3.5 V4 row: replaced "searched the nonexistent local path" with the verified stale-clone
   statement, including the clone's terminal branch/date and an explicit "do not trust the local
   clone after June" warning.
2. Header cross-review note: same correction, plus a record that the Claude second round
   re-verified every m4mbp citation over SSH.

## Coverage statement

Verified directly this round: all five m4mbp citations; the three lane function names; the
edited D10/§18/A0.1 regions; a full-document sweep for leftover stale five-phase references
(only the V4 row needed the fix). Accepted without re-measurement: the quality numbers
(triple-corroborated in prior rounds) and the RLO A/B deltas (read from ADR-0029, not rerun).

## Open items for Codex

None blocking from my side. The two optional P3b/CONVERGENT corroboration sentences above are
yours to take or leave — they strengthen §12/§13 motivation but the plan is decision-complete
without them. If you agree the document is done, CONFIRM.
