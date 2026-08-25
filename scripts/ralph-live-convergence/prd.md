# PRD - Live-mode convergence campaign (E0-E4, single autonomous run)

## Goal

> Close the live-vs-file quality gap of MOSS-Transcribe-Diarize live mode on real audio
> against golden transcripts, by executing ALL FIVE phases (E0-E4) of
> `docs/plans/live-mode-convergence-implementation-20260824.md` as rescoped by its
> **Appendix B** (owner decisions; Appendix B overrides everything). The mission is
> breakthrough live-mode accuracy - WER, TBSA, content recall, DER, speaker accuracy -
> converging toward paired file mode on the same audio. The plan document is the
> authoritative spec: every module boundary (§6), data contract (§7), phase procedure
> (§8-§12), test (§14), and risk/stop rule (§15) comes from it. Gate numbers come from
> the plan, Appendix B, the named measured prototypes, or the owner-directed prerelease
> amendments recorded in `progress.txt`; each derived gate names its source below.

## Acceptance bar

The loop is complete only when every milestone below holds, with evidence (commands run,
artifact paths, before/after metric deltas) recorded in progress.txt. Milestones are ordered;
always work the LOWEST unmet milestone. A milestone closes only when its gates pass in a fresh
run and its evidence file exists under `evidence/live-convergence-0824/M<n>-*/`.

- **M0 (plan E0 - measurement integrity):**
  (a) `verify_replay_roundtrip.py` exits 0; the two replay reconstructors preserve
  `label_revision_version` and `revised_transcript`; a field-complete asdict round-trip
  regression test is green in `tests/test_live_service_replay.py`.
  (b) Typed decode disposition reaches the trace (plan A0.2): unparseable text is no longer
  reported as `decoder_returned_no_transcript`.
  (c) Evaluator v2 prototype passes its self-tests (plan A0.3): self-score exactly 1.0; the
  60-second `"xx"` degenerate control scores zero lexical coverage and zero matched-word
  speaker credit; score invariant under same-speaker segment splits.
  (d) Paired baseline re-acquired with the checked-in drivers (trio + 5-minute case, two fresh
  same-provenance runs): file arms byte-identical to
  `prototypes/live-file-gap-baseline-20260824/`; fresh-vs-fresh live transcripts hash-identical;
  the 5-minute terminal snapshot now shows the revisions its `identity_finalized` event reports.
- **M1 (plan E1 - bounded salvage):** salvage decision table reproduced on plan §9.2's
  184-span corpus (saved WAVs plus spans reproduced by `run_all.sh`) plus constructed
  two-speaker hard-cap spans; the §9.1 O1-vs-O2 gating comparison run on that
  corpus (O1 hard-cap span + safe grammar + non-refusal text vs O2 safe grammar + recomputed
  WebRTC VAD speech ratio >= 0.5 + non-refusal text; prefer O1 if it matches O2 on the full
  corpus); production `classify_live_transcript` (plan M1) shipped with table-driven tests;
  parse -> render -> parse fixed point holds on every salvaged span; speaker identity
  preparation receives only intervals the salvager actually emitted; zero extra MOSS requests;
  no refusal boilerplate or digital-silence words published; paired rerun shows trio live
  WER <= .190 (P1v prototype projection .1885) with no per-case WER regression; file mode
  byte-identical.
- **M2 (plan E2 - rolling text convergence):** the first E2 step writes the accepted
  text-finalization ADR under `docs/adr/` from plan D1-D7 verbatim (Appendix B Q8); then the
  grid runs per §10.2-§10.3 (windows 10/5, 10/10,
  15/7.5, 15/10 x stitchers char/uniform/lexical, lex trio, reconciler truth-blind); cheapest
  arm passing gates selected; production rolling convergence shipped (plan M2/M3/M5 modules,
  snapshot fields of §7.3, events of §7.4, headless portal render/serialization test - the
  in-loop substitute for the attended browser E2E, which is a morning-review item). Exports
  stay on current commits until terminal/effective export tests pass, then switch export once
  in the same reviewed change (§10.5 step 7). The 5-minute soak (Appendix B's rescope of the
  30-minute soak) passes with bounded memory/queues. Gates on the
  trio, measured end-to-end through the deployed campaign-branch service: rolling WER <= .150
  mean AND < baseline live per case (baseline: bill .2614 / milei .1440 / keyu .1942); content
  recall >= .940 mean; correction-after-provisional p95 <= 6.0 s; single-session combined
  RTF < 1 with bounded queues (rescoped G7); 5-minute-case rolling WER <= .0985 (half the
  live-file gap at 5 min); exact sample accounting; file mode byte-identical.
- **M3 (plan E3 rescoped - witness-owned speaker authority, 2.5 s base only):** S1 (and S2
  only if S1 fails gates) per §11.1, embeddings strictly from witness-owned speaker intervals;
  gates: trio mean DER <= .1393 with no per-case regression vs baseline live (bill .2235 /
  milei .1945 / keyu .1112); trio mean speaker_accuracy >= .8437; 5-minute-case DER <= .0947;
  evaluator-v2 matched-word speaker accuracy reported; 9-clip
  `tests/test_live_identity_real_corpus.py` floor stays green (the runnable pytest floor over
  the `tests/live_identity_accuracy.py` harness that plan §11.2 names - both files exist, one
  mechanism, no conflict); no speaker collapse on two-speaker
  mixed windows; S00 duration does not increase; added WeSpeaker cost stays within the
  real-time budget - combined base + rolling MOSS + WeSpeaker processing RTF < 1 under the
  rescoped single-session G7 pacing, with G6 still green and refinement queue bounds intact
  (§11.2).
- **M4 (plan E4 rescoped - terminal convergence):** complete-tape retention per Appendix B
  Q10; async `finalization_status` lifecycle per §12.3; terminal pass through the existing
  150/120 `WindowedRunner` on trio + 3-minute (`lex_adam_frank`) + 5-minute cases; terminal
  WER within .010 absolute of the paired file arm per case (G8); terminal DER within .020
  absolute of the paired file arm per case (owner-directed prerelease companion to G8 for the
  speaker surface - §12.3 step 5 resolves terminal identities, so terminal speaker quality is
  gated, not just text); cold and warm model readiness reported separately (§12.2); accepted == accounted
  samples (G10); a terminal failure preserves and exports the rolling surface with explicit
  non-final status; file mode byte-identical.
- **M5 (evidence and record):** every milestone's T6-style evidence bundle exists under
  `evidence/live-convergence-0824/`; `docs/design-streaming-diarization.md` §7 gains a dated
  campaign verdict entry; the plan's §18 rows are annotated "gates passed <UTC timestamp>,
  awaiting morning sign-off"; a final `evidence/live-convergence-0824/CAMPAIGN_REPORT.md`
  states per-milestone before/after metrics against
  `prototypes/live-file-gap-baseline-20260824/`.

## Constraints

Non-negotiable, in addition to the rules in prompt.md:

- Appendix B of the plan overrides the plan body; this PRD encodes it. If PRD and plan
  conflict anywhere else, STOP on that item and record the conflict in progress.txt.
- **No test audio longer than 5 minutes.** Allowed corpora: the fully-referenced 1-minute
  trio, `calibration_diarization_3min/samples/lex_adam_frank`, `benchmark_5m/lex_keyu_jin`.
  Partial-reference `acquired_*` 1-minute samples are diagnostic-only, never in promotion
  denominators.
- One in-flight vLLM request per harness (`http://127.0.0.1:18000/v1`); greedy decoding only;
  never change the model, prompt (`inference_utils.DEFAULT_PROMPT`), or file-mode windowing.
  File-mode outputs must remain byte-identical - check after every production change.
- Preregistered gates are immutable mid-run: no tuning thresholds to pass, no adding arms
  beyond the grid, no timestamp padding (the evaluator-extent trap of plan §3.4). Reconcilers
  never read reference truth.
- Speaker embeddings must NEVER receive prefix/context/mixed-window audio - only
  witness-owned speaker intervals (plan D5).
- Local services: may restart the MacStudio `web_cli` (port 7861) and SSH tunnel using
  `scripts/g3-attended-session.sh` / `scripts/moss-vllm-tunnel.sh` patterns to deploy
  campaign-branch code; record every restart in progress.txt. NEVER mutate the 4070 Ti host;
  its vLLM endpoint is read-only infrastructure. Never push; never leave branch
  `ralph/live-convergence-0824`; never merge.
- Respect repo AGENTS.md: prototype-first with preregistered questions/gates, numbers over
  adjectives, no defensive scaffolding or feature-flag frameworks, scope limits.
- Appendix B §18 conditionally pre-authorizes every phase in this campaign. Do not wait for a
  signature between phases: pass the mechanical gates and write the evidence; morning review
  signs successful rows retroactively before merge. A hard gate failure leaves its row unsigned.
- New durable code follows plan §6 module boundaries and §7 contracts; tests per §14 tiers
  T1-T3 for whatever the milestone shipped. Throwaway experiments live under
  `prototypes/streaming-diarization/live-convergence/` (create it), never in module code.
- On a HARD gate failure (honest attempts exhausted, preregistered options spent): write the
  failure evidence + a `BLOCKED:` entry in progress.txt and context.md, then create the
  `.stop` file in this directory to end the campaign cleanly. Do not improvise compensating
  complexity (plan §15 stop conditions apply verbatim).

## Budget and stop

- The launcher argument sets the iteration budget; one logical change per iteration.
- Stop early only via the completion contract: acceptance bar met with evidence, or every
  remaining item blocked on input the loop cannot obtain, recorded in progress.txt.
- An ordinary external or transient blocker ends the iteration, not the loop: record it and the
  best next probe, then let a later iteration run that probe or another already-authorized
  candidate. A HARD gate failure is not an ordinary blocker; it follows the `.stop` rule above.
