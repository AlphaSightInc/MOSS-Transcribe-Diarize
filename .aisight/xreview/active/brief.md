# Brief — adversarial review of the ralph-live-convergence campaign setup (pre-relaunch)

## The user's request (binding, from docs/handoffs/handoff-8YIE4C.md)

> 1. Thoroughly update the ralph loop afk.
> 2. Then use adversarial review to review and finalize the ralph loop afk.

The named skill `/codex:adversarial-review` is not installed; the handoff explicitly
sanctions this xreview session as the equivalent. After this session converges, the
amendment is committed and the loop relaunches in tmux MOSS:2.1 with a 40-iteration
budget. So this review is the last gate before an unattended overnight campaign —
severity should be judged on "what would make the loop stall, STOP falsely, or pass a
milestone it should not".

## What just changed (the amendment set under review)

State: the loop is STOPPED (clean, run 20260825-030106-23237). M0a and M0b are CLOSED
and committed; the ladder resumes at M0c. No affected milestone (M1–M4) has started, so
amending their gates now is legitimate; M0 gates were NOT touched.

Six owner-directed pre-M1 amendments were just applied (full rationale in the new
progress.txt entry dated 2026-08-25 pre-relaunch):

1. Plan Appendix B §B.3 gained a **G4 rescope row** (file:
   `docs/plans/live-mode-convergence-implementation-20260824.md`, NOT in your edit
   targets — verify by reading; flag corrections in your round file for me to apply).
   Reason: Appendix B deleted the 1 s preview, which orphaned G4's comparator
   ("corrected 1 s within 2 points of corrected 2.5 s"); without the row, PRD M3 vs
   plan G4 is a false conflict and the PRD's own constraint ("if PRD and plan conflict
   anywhere else, STOP") would stop the campaign at M3.
2. prd.md M1 += §9.1 O1-vs-O2 gating comparison; §9.2 parse→render→parse fixed point;
   §9.2 "identity prep receives only salvager-emitted intervals".
3. prd.md M2 += §10.5 step-7 export-switch discipline; 5-minute soak (Appendix B's
   rescope of the 30-min soak); headless portal render/serialization test named as the
   in-loop substitute for the attended browser E2E (a morning-review item).
4. prd.md M3 += §11.2 WeSpeaker real-time budget (combined base + rolling + WeSpeaker
   RTF < 1 under rescoped single-session G7, G6 green, queue bounds intact).
5. prd.md M4 += terminal DER within .020 absolute of the paired file arm per case
   (mirrors G8's spirit; §12.3 step 5 resolves terminal identities but M4 gated only
   WER) and §12.2 cold/warm model-readiness reporting.
6. progress.txt: append-only amendment entry; context.md candidates 5/8 annotated
   (light touch only).

## Review scope

- **Fidelity axis**: the campaign setup files (your edit targets: prd.md, context.md)
  against `docs/plans/live-mode-convergence-implementation-20260824.md` **with Appendix
  B overriding the body** — is every Appendix B decision and every plan gate the loop
  must satisfy encoded, correctly numbered, and free of contradictions that would
  trigger the PRD's conflict-STOP rule? Are the amendment numbers right (derivations:
  half-gap recovery from `prototypes/live-file-gap-baseline-20260824/` numbers; identity
  ceiling from `prototypes/live-file-gap-identity/NOTES.md`)?
- **Craft axis**: against the ralph template's anti-drift rules
  (`~/Desktop/AI_Projects/AAgent/0.templates/ralph-loop-afk`, esp. its README/prompt.md):
  prd.md stays an acceptance bar (not a procedure dump), context.md readable in one
  sitting with a ranked candidate list, journal append-only, no gate weakening, no
  instance-specific hardcoding beyond the domain contract.

## Hard constraints on edits

- Edit targets only: `scripts/ralph-live-convergence/prd.md`,
  `scripts/ralph-live-convergence/context.md`. Anything wrong elsewhere (plan Appendix
  B row, progress.txt entry) → record in the round file; I apply it on my turn.
- progress.txt is append-only history; never rewrite it.
- Do NOT weaken or tune any gate number; closed milestones (M0a, M0b) are immutable.
- Appendix B overrides the plan body everywhere they differ.
- The loop relaunches immediately after convergence — prefer the smallest edit set
  that makes the setup safe to run unattended.
