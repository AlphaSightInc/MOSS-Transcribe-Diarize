# Round 1 — Codex

Reviewed the two campaign targets for fidelity to
`docs/plans/live-mode-convergence-implementation-20260824.md`, especially Appendix B, and for
craft against the Ralph AFK template. I also checked the baseline result JSON, identity-lever
result JSON, empty-span verdict, current prompt/template, corpus paths, and executable test names.

## Findings and changes

1. **High — M2 could close without the accepted ADR.** Appendix B Q8 requires the first E2 step
   to write the text-finalization ADR from D1-D7 verbatim, but neither M2 acceptance nor the M2
   candidate required it. Added ADR-first ordering to `prd.md` and `context.md`.
2. **High — hard-gate stopping was ambiguous.** The PRD said both that a hard gate creates
   `.stop` and that a blocker never stops the loop and may be routed around. Distinguished an
   ordinary external/transient blocker from an exhausted HARD gate, and encoded Appendix B §18's
   phase preauthorization so the loop neither waits for intermediate signatures nor routes around
   a failed gate.
3. **Medium — M3 named a nonexistent test.** Replaced `tests/live_identity_accuracy.py` with
   `tests/test_live_identity_real_corpus.py`. Collection confirms its three tests include the
   exact-nine-hash-pinned-clips acceptance check.
4. **Medium — gate provenance could itself trigger a false conflict.** The PRD claimed every
   number came from the plan, but M1 `.190` comes from the measured P1v `.1885` projection and
   M4 DER `.020` is an owner-directed prerelease amendment. Corrected the provenance statement,
   named both sources, and annotated M4 the same way in context.
5. **Low — “184 saved spans” was operationally misleading.** Only part of the corpus is stored as
   WAVs; plan §9.2 defines the total as saved WAVs plus simulator-reproduced spans. Reworded M1 to
   preserve the 184-span gate while identifying how to reproduce it.

## Verification

No controller `VERIFY_CMD` was configured. Targeted read-only verification:

- `git diff --check -- scripts/ralph-live-convergence/prd.md scripts/ralph-live-convergence/context.md`
  — PASS.
- `.venv/bin/python -m pytest tests/test_live_identity_real_corpus.py --collect-only -q`
  — PASS, 3 tests collected.
- Checked exact baselines in the committed JSON: trio live WER `.261364/.144/.194245`, DER
  `.2235/.1945/.111167`; 5-minute live/file WER `.146375/.050616`, DER `.131533/.057933`.
  The PRD's rounded baselines and half-gap gates are correct.
- Checked `C1adopt+C2b` mean speaker accuracy from the identity result: `.843666...`, correctly
  rounded to the `.8437` gate.
- Current campaign `prompt.md` is byte-identical to the Ralph template prompt.

## Open review question

None. Claude should independently verify that the added ADR-first and hard-gate language is the
smallest faithful encoding of Appendix B, and that naming the owner-directed M4 DER gate resolves
rather than expands the PRD/plan authority boundary.
