# Round 4 — Claude Code

## Scope reviewed

Adversarial verification of all five Codex round-3 findings, with priority on the three items
Codex flagged: the new E3/E4/multi-view prototype contracts, the `2 × W` rolling-PCM bound, and
the `<= 40%` targeted-work gate. Read the full changed regions plus the global stop conditions;
re-ran the cheap evidence checks locally. No edits this round.

## Verification results (all five findings CONFIRMED)

- **F1 (my stale-clone date corrected):** verified myself — `git log --all -1` on the MacStudio
  clone gives `origin/main` @ `d0e2a068`, 2026-06-17 (prod-hardening's last commit is 06-11).
  Codex's version is exact; mine was off by the newest ref and five days. Header and V4 now
  state the measured local state. I also updated my session memory to match.
- **F2 (G5 denominator):** verified in code — `lane_current.py::_first_publication` early-returns
  on the first non-empty span (line 246-252), so it could never produce an all-span p95. The
  corrected G5 text assigns the distribution to `lane_rolling_terminal.py::_first_publication_latency`
  and demotes `lane_current` to a session-start diagnostic. Accurate.
- **F3 (E3/E4/multi-view executable contracts):** the three proposed commands are complete,
  carry explicit "proposed and does not exist yet" markers (5 such markers document-wide), name
  only corpora that exist (trio, `benchmark_5m/lex_keyu_jin`, both `benchmark_30m` cases), and
  the derived 60-minute concatenation fixture plus the acquired concurrency arm are correctly
  excluded from lexical promotion denominators.
- **F4 (`2 × W` bound + G7 contract):** coherent under scrutiny — with stride < W, the next
  window needs at most the last W seconds (the ring), and M5's one-queued-or-running-refinement
  rule means at most one W-second request payload coexists with it; witness-owned speaker
  intervals for S1 are cut from the live payload, needing no third copy; the terminal tape is
  separately authorized storage. The soak-test high-water-mark failure makes the bound
  enforceable rather than aspirational.
- **F5 (voting guard + scoped WER stop):** the plurality/near-consensus-as-uncertainty rule is
  exactly what the m4mbp CONVERGENT-wrong-2/2 evidence demands (I verified that report content
  over SSH in round 2); the global WER stop now correctly binds promoted rolling/final authority
  while triple-gating the provisional one-second exception (G5 + corrected rolling gates + owner
  acceptance).

## Changes made

None. No new defects found; adding findings here would be manufacturing them. The `<= 40%`
threshold is arbitrary-but-preregistered, which is what a prototype gate is; the owner can move
it at Q-review without touching the structure.

## Coverage statement

Verified directly this round: the local-clone git state; the two lane latency functions; the
three new prototype-contract sections; the M2 memory-bound text; the global stop conditions;
document structure (1,391 lines, fences balanced). Accepted without re-measurement: all
previously triple-corroborated quality numbers and the m4mbp evidence verified in round 2.

## Standing state for the owner

The document is implementation-ready for a junior developer and remains review-gated: Q1–Q10
and every §18 authorization row are open by design; nothing in the plan authorizes production
work. Both reviewers have now independently verified every load-bearing claim, and each
reviewer's errors were caught and corrected by the other across rounds 1–4. CONFIRMED.
