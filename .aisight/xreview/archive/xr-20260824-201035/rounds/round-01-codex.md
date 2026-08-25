# Round 1 — Codex

## Scope reviewed

Plan-mode review of the sole target,
`docs/plans/live-mode-convergence-implementation-20260824.md`, on fidelity to the brief and on
technical craft. I edited no production code, tests, prototype code, or non-target project
document. There was no configured `VERIFY_CMD`.

## Findings and evidence

### F1 — The brief and target's LiveTranscribe refutation searched the wrong machine

**Material; corrected.** `/Users/gao/Desktop/AI_Projects/LiveTranscribe` does not exist on
MacStudio because the sibling project lives on `ga0@m4mbp` at
`/Users/ga0/Desktop/AI_Projects/LiveTranscribe`. Read-only SSH verification at HEAD
`6a8d0c1fafe8a1a8d6ea449036dd1ca330309d70` found:

- `RefinedLiveOverlayProductionWorkProvider.swift:320-360`: chunked-ASR candidate plus
  whole-file-ASR witness;
- `RefinedLiveOSFPartitionSelection.swift:166`: required view count 5;
- `RefinedLiveOSFProductionRequestBuilder.swift:197-213`: five phase offsets;
- `docs/adr/0029-refined-live-overlay-display-authority.md:316-323`: five matched A/B pairs,
  measured WER/TBSA/latency results;
- `docs/evidence/overlap-stability-perturbation-0806/REPORT.md:31-32`: all 20 live Jamie views
  merged the handoff and phase-VAD alone was insufficient.

The evidence exists, but its correct implication still supports the plan: dual-ASR overlay is a
different, display-only stack, while the five-phase result is negative for blanket VAD views.
Use overlapping MOSS witnesses as uncertainty evidence and prototype any extra work only on
disagreement regions.

### F2 — G5/G6 used the wrong clock and no denominator

**Material; corrected.** The target said both gates started when the request's last sample became
eligible. The actual prototype uses:

- first-word age: publication minus the first spoken-word audio start
  (`lane_current.py::_first_publication`,
  `lane_rolling_terminal.py::_first_publication_latency`);
- correction age: changed witness publication minus the provisional publication it replaces
  (`lane_rolling_terminal.py::_provisional_to_correction_latencies`).

The plan now makes G5 p95 over every non-empty provisional span in the primary trio and G6 p95
over every changed rolling-owned region. Eligibility-to-decode and browser-to-paint remain
separate diagnostics.

### F3 — Review gates had stale section references and no per-phase signoff surface

**Moderate; corrected.** D10 pointed to §§15/16 instead of §§17/18. Appendix A required each
phase's §18 row to be signed, but §18 had no phase rows. The references now resolve, and §18 has
an E0–E4 plus optional-multiview ledger. Initial authorization permits only its named phase.

### F4 — Baseline reacquisition allowed undefined “run noise”

**Moderate; corrected.** The plan now requires two same-provenance fresh runs, exact transcript
hash and metric agreement, and an explicit stop/provenance diagnosis if live differs from the
checked-in baseline. It no longer hides an unbounded difference behind “noise.” Partial
`acquired_*` references are explicitly diagnostic-only and cannot enter promotion aggregates.

## Changes made

- Corrected the header, V4 verification record, and §13 LiveTranscribe premise and transfer
  limits.
- Defined G5/G6 clocks and denominators from the implementation used by the measured prototype.
- Fixed D10 references; added the per-phase review/owner ledger required by Appendix A.
- Made baseline repeatability deterministic and promotion denominators explicit.

## Verification

- Plan structure: 1,314 lines, 21 unique H2 headings, balanced Markdown fences — PASS.
- Stale false-premise/noise/reference strings absent — PASS.
- Live deployed runbook endpoints during review: `127.0.0.1:18000/v1/models` and
  `https://127.0.0.1:7861/api/runtime` both answered — PASS.
- Remote LiveTranscribe source/evidence paths listed in F1 — PASS via read-only SSH.
- No full benchmark was rerun; V1–V3/V5 and measured quality values remain accepted from the
  prior pass and checked-in evidence, not newly measured in this round.

## Open review work

Claude should adversarially check this correction, especially the transfer boundary between RLO,
OSF, and joint-MOSS rolling witnesses. Owner decisions Q1–Q10 and all authorization rows remain
open; the plan still authorizes prototypes/review only.
