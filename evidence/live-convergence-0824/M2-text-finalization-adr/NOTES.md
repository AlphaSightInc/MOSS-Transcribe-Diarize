# M2 step 1 — the text-finalization ADR (plan E2's first step, Appendix B Q8)

**What this step is.** Appendix B Q8 of the convergence plan says: *"The text-finalization ADR is
accepted now. The campaign's first E2 step writes `docs/adr/` content from D1–D7 verbatim; no
further approval needed."* This bundle is that step. No measurement was required or performed; the
deliverable is a decision record and a mechanical check that it says what the owner accepted.

**Why the record has to exist before any E2 code.** Plan D7: ADR-0002's shipped L1 and proposed L2
identity sweeps *never re-run ASR*. E2 is the first phase that decodes the same audio a second
time in order to publish different words. Without its own record, word rewriting would arrive
through the identity sweep, and no reader of either document could tell which half applied to them.

## Deliverable

- `docs/adr/0005-live-text-finalization-authority.md` (270 lines).
  - D1–D7 quoted byte-for-byte from the plan, spliced mechanically rather than retyped.
  - One override recorded beside the verbatim text, not inside it: D6's last sentence ("Only E3 may
    promote one-second output") is superseded by Appendix B Q6, which deletes the one-second preview
    from scope. D6's operative half — do not move the 2.5 s cap while rolling text is being proved —
    stands and is now unconditional.
  - The authority D7 asks for, stated once: **two producers** (rolling converger over
    `[0, canonical_through_sample)`, terminal finalizer once per session), **one seam**
    (`LiveSession.apply_text_revision`), **seven validations**, **four snapshot fields**,
    **seven events**, **zero silent rewrites**.
  - An explicit "what this record does not authorize" section: no re-ASR inside an identity sweep,
    no redefinition of `revised_transcript` (label-only), no cap change, no evaluator-v2 promotion,
    no extra VAD/embedding phases, no tape-retention decision (Appendix B Q10 refines ADR-0003 and
    belongs there, recorded by the E4 step that implements it), and no authority to ship whatever
    E2 builds if its gates fail.

## Verification

`verify-verbatim.txt` — `verify_adr_text_finalization.py`, exit 0. It reads the plan for all three
instance facts rather than carrying them as constants: **which** decisions are required (parsed out
of the Appendix B Q8 row's own "D1–D7 verbatim" clause), **what** each says, and where each ends.
It then requires D1–D7 in the record as one contiguous byte-identical block appearing exactly once,
and requires every decision outside that range to be absent — so widening the record's scope fails
as loudly as narrowing it.

`mutations.txt` — five mutations, each applied to a copy under `/tmp`, each caught:

| # | Mutation | Caught by |
|---|---|---|
| M1 | one word changed inside the record's copy of D4 (`duplicated` → `duplicate`) | D4 verbatim + contiguous block |
| M2 | editor commentary inserted between D3 and D4 | contiguous block |
| M3 | D8 copied into the record (scope widened past D1–D7) | D8 excluded |
| M4 | D7 dropped from the record | D7 verbatim + contiguous block |
| M5 | the **plan's** Q8 clause widened to `D1–D8`, record untouched | D8 verbatim + contiguous block |

M5 is the one that matters most for the future: the check is symmetric, so a later amendment to the
plan's decisions fails this command until the record is amended too. The two cannot drift apart
silently.

`tree-status.txt` — the working tree after the change: one new ADR, one new verifier, this bundle.
**No file under `moss_transcribe_diarize/` was touched**, so the PRD's file-mode byte-identity check
has nothing to compare and is not claimed. The paired-rerun gates belong to the E2 arms, not to this
step.

`sha256.txt` — the record and the plan it quotes, so a later reader can tell whether either moved.

## What this step deliberately does not do

- It does not add a pointer to the new record from `docs/design-streaming-diarization.md`. That
  document gains a dated campaign verdict entry at **M5** (PRD), and the pointer goes in with it —
  one edit to that file, not two.
- It does not implement, prototype, or measure anything in §10.2's grid. The next E2 step is
  `compare_rolling_grid.py` over windows 10/5, 10/10, 15/7.5, 15/10 × stitchers char, uniform,
  lexical, reconciler truth-blind, selection by §10.4's cheapest-passing-arm rule.
