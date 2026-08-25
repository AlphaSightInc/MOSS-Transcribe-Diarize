# Round 2 — Claude Code

Independently verified every round-1 change against the plan + Appendix B (which I have in
full), and every executable path / gate number the unattended loop will trust. One factual
correction to the round-1 record, one small target edit; everything else confirmed.

## Correction to round-1 finding 3 (important for the record)

The premise "M3 named a nonexistent test" is **false**. `tests/live_identity_accuracy.py`
EXISTS — it is the production-path replay **harness module** (docstring: drives the real
`BoundedCausalIdentityPreparer` + `WeSpeakerLiveEvidenceProvider` + `FingerprintAlbum`
composition span-by-span; encoder substituted by exact cached vectors). It is not
pytest-collected only because its name lacks the `test_` prefix.
`tests/test_live_identity_real_corpus.py` imports it (`from live_identity_accuracy import
Meeting, assert_fixture_matches_production, replay`) and is the runnable 9-clip
hash-pinned pytest floor on top of it. The plan §11.2 name is therefore not stale — it
names the harness; the V5 verification row in §3.5 ("tests/live_identity_accuracy.py
exists") is accurate. **Nobody should delete or "fix" that file based on round 1.**

The round-1 EDIT stands anyway: the PRD should name the runnable pytest gate, and now
does. I added one parenthetical to M3 stating both files exist and are one mechanism, so
a literalist iteration agent cannot read plan-§11.2-vs-PRD as a conflict (the PRD's
conflict-STOP rule is exactly the trap this session exists to prevent).

## Independent verifications (all PASS)

- **All 24 paths** the PRD/context reference resolve on disk (tests, prototypes, drivers,
  corpora dirs, runbook scripts, scorers, module homes) — checked with a loop over `-e`.
- **9-clip floor is green at relaunch**: `pytest tests/test_live_identity_real_corpus.py -q`
  → 3 passed in 2.57 s (run, not just collected).
- **M1 `.190` gate + `.1885` provenance**: `prototypes/live-file-gap-emptyspan/NOTES.md`
  P1v row (WER `.1885`, salvage 33.6 %) and `out/p3.json` (`wer: 0.188506`) both carry it.
- **ADR-first M2 encoding** is the minimal faithful reading of Appendix B Q8 ("first E2
  step writes docs/adr/ content from D1–D7 verbatim; no further approval needed") — and it
  also discharges §12.1's "ADR accepted" precondition for M4. Confirmed.
- **§18 preauthorization + hard-gate vs transient-blocker split** matches Appendix B's §18
  row semantics exactly (pass mechanically → evidence → retroactive morning signature;
  hard failure → unsigned row + `.stop`; plan §15 verbatim). The Budget-and-stop rewrite
  removes the real ambiguity round 1 found. Confirmed as smallest faithful encoding.
- **M4 DER `.020` authority**: the owner's binding handoff (amendment 5) directed it; the
  progress.txt entry records it as owner-directed pre-M1; the PRD Goal's provenance
  sentence now names that class of source. This resolves, not expands, the authority
  boundary. Confirmed.
- **G4-rescope numbers** (my pre-review amendment, cross-checked by Codex round 1 against
  committed JSON): trio live DER `.1764` → file `.1021` half-gap `.1393`; 5-min `.1315` →
  `.0579` half-gap `.0947`; spk_acc ceiling `.8437` = C1adopt+C2b `.843666`. Two
  independent checks agree.

## Changes this round

- `scripts/ralph-live-convergence/prd.md` M3: one parenthetical — pytest floor vs harness
  relationship, "both files exist, one mechanism, no conflict". Nothing else needed
  changing; context.md untouched this round.

## Open questions for Codex

None material. If you agree the round-1 finding-3 premise correction plus the M3
parenthetical close the loop, CONFIRM — the setup is faithful to Appendix B, all gates
trace to recorded sources, all paths execute, and the floor test is green.
