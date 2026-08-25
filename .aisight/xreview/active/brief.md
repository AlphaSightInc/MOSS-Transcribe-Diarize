# Cross-review brief — live-mode convergence implementation plan

## User request (their words, condensed)

"Review codex's analysis and his assessment on your findings … independently verify and
validate his findings and hypothesis using /diagnose and /prototype — thoroughly scrutinize
and adversarial review his proposed plan docs/plans/live-mode-convergence-implementation-20260824.md.
Please make necessary changes and updates to the plan so that it's fully implementation ready
to a junior developer." This xreview session continues that: converge the plan document itself.

## Goal

`docs/plans/live-mode-convergence-implementation-20260824.md` is the deliverable. It must be
implementation-ready for a junior developer: every claim true and sourced, every phase
executable from the document alone (exact seams, commands, corpora, gates, baselines), and the
review-gate/authorization structure intact (§18 — the plan authorizes review and throwaway
prototypes only until signed).

## Document history both reviewers must respect

- Authored by Codex 2026-08-24 19:19 (sections 0–19, D1–D10, G1–G10, E0–E4, T1–T6, R1–R10,
  Q1–Q10).
- Second pass by Claude ~20:30 same day, after independent verification with /diagnose and
  /prototype. Changes: header verification note; §3.3 expanded (confirmed replay-adapter root
  cause, server `asdict` field-completeness, blast radius incl. the 5-minute cadence-sweep
  correction); new §3.5 verification record (V1–V5); §13 premise rewritten; §16 sweep-cadence
  bullet rescoped; exact seam anchors added to M1/M3/M5/M7, A0.1/A0.2, E1; gate operational
  definitions under §1.3; lexical stitcher pinned as E2 reference arm (§10.2); Q4 extended;
  Appendix A (runbook, code map, corpora, bench commands, definition of done).

## Settled by evidence — do not re-litigate without NEW on-disk evidence

1. **F7 / replay adapter (Codex was right, Claude's first read corrected):**
   `_live_snapshot_from_dict`/`_commit_from_dict` drop revision fields; server side is
   `asdict`-complete; the 5-minute run's cadence sweep applied 2 label revisions
   (`identity_finalized` event). Reproducer exits 1: `prototypes/live-file-roadmap-verification/verify_replay_roundtrip.py`.
2. **LiveTranscribe "five-phase / 20-view Jamie" (Claude's greps refute, twice):** no such
   experiment exists in /Users/gao/Desktop/AI_Projects/LiveTranscribe on HEAD or
   origin/prod-hardening-0531. §13's corrected premise stands unless a reviewer cites a real
   file path proving otherwise; the phase's conclusion (uncertainty-routed only) is unaffected.
3. Measured numbers in §3.1 (F1–F12) are triple-corroborated where shared (deployed baseline,
   live-file-gap-context bench, live-multiview-prototype); the `.129–.146` rolling range is a
   real stitcher difference, both truth-blind.

## Hard constraints

- Plan mode: edit ONLY the target document. Experiments go to scratch space.
- Keep the review-gate structure: nothing may convert this document into an implementation
  authorization; §17/§18 stay.
- Repo norms (AGENTS.md): numbers over adjectives; no defensive scaffolding, feature-flag
  frameworks, or corner-case obsession; pyramid style; expand jargon; keep reference codes
  (D/G/E/T/R/Q/V) stable.
- Junior-developer bar: a reader with repo access but no conversation context must be able to
  execute E0 end-to-end tomorrow. If a section fails that test, fix the section.
- Convergence: rank findings by impact, verify before asserting, CONFIRMED is a legitimate
  outcome.
