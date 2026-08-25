# Round 3 — Codex

## Scope reviewed

Plan-mode review of the sole target,
`docs/plans/live-mode-convergence-implementation-20260824.md`, after Claude Round 2. I read the
brief, session summary, Round 2, and full target in the required order. I edited only the target;
no production, test, or prototype code changed. No `VERIFY_CMD` is configured.

## Findings and evidence

### F1 — Claude's stale-clone correction had the right cause but the wrong terminal ref/date

**Moderate; corrected.** The MacStudio clone exists and is stale, as Claude found. Direct
`git log --all -1` shows its newest local ref is `origin/main` at `d0e2a068`, 2026-06-17—not
`origin/prod-hardening-0531` ending June 12. The header and V4 now record the exact local state;
the authoritative m4mbp evidence and its interpretation are unchanged.

### F2 — G5's denominator did not match both cited implementations

**Material; corrected.** `lane_current.py::_first_publication` returns only the first non-empty
span per case. `lane_rolling_terminal.py::_first_publication_latency` computes one value per
provisional observation. The plan had claimed an all-non-empty-span p95 while citing both as if
they implemented that aggregate. G5 now identifies the rolling-lane implementation as its source,
keeps `lane_current` as a session-start diagnostic, and requires the E3 harness to persist every
non-empty-span row before p95.

### F3 — E3, E4, and the optional multi-view phase lacked executable prototype contracts

**Material fidelity gap; corrected.** The brief requires exact phase commands/corpora/gates, but
only E0–E2 had runnable or proposed commands. The target now specifies proposed one-command
contracts for:

- `compare_speaker_authority.py`: S0/S1/S2, 1.0/2.5-second bases, production MOSS/VAD/WeSpeaker,
  exact interval/cache/RTF evidence;
- `compare_terminal_matrix.py`: exact 1/5/30/60-minute inputs, single-process concurrency,
  derived 60-minute transport-only fixture, paired file/terminal evidence;
- `compare_uncertainty_views.py`: none/targeted2/blanket5 with exact added-work accounting.

All are explicitly proposed/nonexistent; the plan still requires prototypes before production.
Every named input path exists. The acquired 30-minute and derived 60-minute arms are explicitly
excluded from lexical promotion denominators.

### F4 — Compute reuse, concurrency, and resource bounds were underspecified

**Material craft gap; corrected.** Current MOSS/vLLM exposes no cross-request audio-encoder or
decoder-state reuse; overlap redoes neural work. The plan now distinguishes reusable retained PCM,
completed witness outputs, and exact-interval speaker embeddings from non-reusable neural state.
S0–S2 share each MOSS witness decode. Rolling PCM is bounded to `2 × W` seconds per session
(request payload + newest-view ring; terminal tape separate), and the E2 prototype must print its
high-water mark.

G7 now requires one orchestration process to own both sessions, combined inference RTF `< 1`, no
dropped canonical commits, at most one queued-or-running refinement/session, and zero queues after
drain. Appendix A now distinguishes that deliberate concurrency bench from accidentally running
two independent harnesses.

### F5 — Optional multi-view and global stop language allowed wrong decisions

**Moderate; corrected.** Read-only m4mbp verification confirms the perturbation report's
4-of-5 mode was wrong 2/2 and all 20 Jamie live views merged the handoff. The optional phase now
routes plurality/near-consensus as uncertainty rather than authorizing majority voting, caps
targeted work at two extra views and 40% of blanket added work, and still requires equal-or-better
speaker quality. The global WER stop now applies to promoted rolling/final authority, while the
explicitly provisional one-second surface may be temporarily worse only behind G5, corrected
rolling gates, and owner acceptance.

## Verification

- Full target read; Markdown fences balanced; 21 unique H2 headings; required new contracts
  present — PASS.
- Stale June-12/prod-hardening claim absent; local newest ref independently measured — PASS.
- Remote LiveTranscribe REPORT.md directly confirms 4-of-5 wrong 2/2 and 20/20 Jamie merge —
  PASS via read-only SSH.
- Every corpus path named by E3/E4 exists — PASS.
- No quality/GPU benchmark rerun this round. Existing measured results remain accepted from the
  checked-in benches and prior rounds; new commands and thresholds remain proposed review items,
  not measured claims.

## Open review work

Claude should scrutinize the new prototype interfaces, the `2 × W` rolling-memory upper bound,
and the targeted-work `<= 40%` gate. Owner questions Q1–Q10 and every authorization row remain
open; this plan still authorizes review/prototypes only.
