# live-convergence — throwaway experiments for the E0–E4 campaign

Home for the campaign's prototypes (PRD: "Throwaway experiments live under
`prototypes/streaming-diarization/live-convergence/`, never in module code"). Nothing here is
imported by `moss_transcribe_diarize/`.

| file | question it answers | verdict |
|---|---|---|
| `replay_saved_decode_dispositions.py` | do the seven real lost decodes now report the ending that happened? | yes — `evidence/live-convergence-0824/M0b-decode-disposition/` |
| `probe_file_mode_decode_identity.py` | did the A0.2 change move file-mode decoder output? | no — same bundle |
| `evaluator_v2.py` + `compare_evaluators.py` + `cases.json` | can the campaign be scored on a lens a wider timestamp cannot move? | yes — `evidence/live-convergence-0824/M0c-evaluator-v2/` |
| `run_paired_reacquisition.sh` + `verify_paired_reacquisition.py` | do the M0(d) paired gates hold on campaign code? | 4 of 5 — G2 fails on the 5-minute case, `evidence/live-convergence-0824/M0d-paired-reacquisition/` |
| `probe_decode_determinism.py` | is the deployed vLLM decoder bit-reproducible for an identical greedy request? | no when cold, yes when warm — 12 requests gave 2 outputs after an idle gap, 1 output immediately after |
| `diff_live_runs.py` | where do two live runs of the same audio *first* disagree? | 5-minute case: one span (a decode flip); the other 51 are identity cascade |
| `salvage_gates.py` + `compare_salvage_gates.py` + `PREREGISTRATION-M1a.md` | plan §9.1: O1 (hard-cap freeze) or O2 (recomputed VAD ≥ 0.5) as the salvage gate? | **O1** — same words recovered, one fewer false word, no new state; `evidence/live-convergence-0824/M1a-salvage-gate-comparison/` |
| `verify_production_salvage.py` | does the shipped `classify_live_transcript` decide what §9.1 measured? | **yes** — 184 corpus spans + 5 constructed spans agree with the adjudicated O1 column; `evidence/live-convergence-0824/M1-salvage-production/` |
| `run_paired_passes.sh` + `verify_m1_exit.py` | does the M1 build clear the plan E1 exit gates on the deployed service? | 5 of 6 — G-M1-1 misses by .0023 on a pre-M1 decode flip; `evidence/live-convergence-0824/M1-e1-exit/` |
| `attribute_wer_delta.py` | which published segment is a WER delta actually made of? | measures each segment's cost by re-scoring without it — bill's salvage is worth −.034091, the S00 flip +.011363 |
| `verify_adr_text_finalization.py` | does the text-finalization ADR still quote the plan's decisions *verbatim*, as Appendix B Q8 required? | **yes** — D1–D7 byte-identical, one contiguous block, D8–D10 absent; `evidence/live-convergence-0824/M2-text-finalization-adr/` |

`cases.json` is the corpus contract: which saved hypotheses are scored, which corpus each is
scored against, which group's mean it joins, and the means the plan already published for them.
Instance values live there so the drivers stay general.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_evaluators.py --output /tmp/v2.json
```

```bash
# M0(d) paired re-acquisition: four sequential passes, then the gates
prototypes/streaming-diarization/live-convergence/run_paired_reacquisition.sh /tmp/m0d-$(date +%s)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_paired_reacquisition.py --fresh-root /tmp/m0d-<stamp>
```

`run_paired_reacquisition.sh` detaches deliberately: a measurement pass outlives the agent that
started it, and three earlier attempts died mid-run when their caller exited.

```bash
# plan §9.1 O1-vs-O2 salvage-gate comparison over the saved 184-span corpus (zero MOSS requests)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_salvage_gates.py --output /tmp/m1a.json

# does the SHIPPED classifier still decide what §9.1 measured? (exit 0 = yes; zero MOSS requests)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_production_salvage.py
```

```bash
# M1 (plan E1) exit: four warm-decoder passes against the running service, then the gates
prototypes/streaming-diarization/live-convergence/run_paired_passes.sh /tmp/m1-exit-<stamp>
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m1_exit.py --fresh-root /tmp/m1-exit-<stamp>

# what is a per-case WER delta made of? (re-scores the real hypothesis without a named segment)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/attribute_wer_delta.py \
  <hypothesis.jsonl> --case lex_bill_ackman --drop 49.75:50.0
```

```bash
# E2 step 1: is docs/adr/0005 still the plan's D1–D7 verbatim? (exit 0 = yes; no service, no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_adr_text_finalization.py
```

`verify_adr_text_finalization.py` reads the plan for every instance fact it needs — including
*which* decisions the record must carry, parsed out of the Appendix B Q8 row's own wording — so
amending the plan's decisions fails the check until the record is amended too. The check is
symmetric: quoting one decision too many fails exactly as loudly as quoting one too few.

`run_paired_passes.sh` supersedes `run_paired_reacquisition.sh` from M1 onward: same four
sequential passes, plus the one discarded warm-up decode the campaign adopted after M0(d)
measured the decoder's cold-start flip. The M0(d) script is kept unchanged because it is that
milestone's reproducer.

```bash
# E2 step 2: plan §10.2–§10.4 rolling grid — 4 geometries × 3 stitch policies × 3 runs
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_rolling_grid.py \
  --cases lex_bill_ackman,lex_javier_milei,lex_keyu_jin \
  --windows 10/5,10/10,15/7.5,15/10 --stitches char,uniform,lexical --runs 3 \
  --output /tmp/moss-rolling-grid.json
# ...replayed with NO GPU by pointing --cache-dir at the checked-in decodes:
#   --cache-dir evidence/live-convergence-0824/M2-rolling-grid/decode-cache
# five mutations, each caught by its own guard (also zero MOSS requests)
prototypes/streaming-diarization/live-convergence/mutate_rolling_grid.sh \
  evidence/live-convergence-0824/M2-rolling-grid/decode-cache /tmp/grid-mutations
```

`compare_rolling_grid.py` imports `prototypes/live-file-gap-context/proto_context_arms.py` as a
library — its decoder, disk cache, span loader, shared speaker timeline and scorer — instead of
rebuilding them, which is why its base control and its `10/5:char` arm reproduce that bench's
published `.19987` and `.128926` to every printed digit. Two things it adds are worth reusing:
`plan_windows` asserts the ownership regions **partition** `[0, duration]` (the literal `a2`
formula does not, once the final window is clamped, and the resulting double-publication is
invisible to a tail-vs-head duplicate screen); and `_TruthBlind` makes reading the reference raise
while an arm is being produced, so "the reconciler sees no reference" is enforced rather than
asserted. Verdict, gates and the three findings: `evidence/live-convergence-0824/M2-rolling-grid/`.

```bash
# E2 step 3a: does the SHIPPED converger reproduce the arm the grid selected? (no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_production_converger.py
# five mutations, in the production module itself, restored from a backup on exit
prototypes/streaming-diarization/live-convergence/mutate_production_converger.sh /tmp/converger-mutations
```

`verify_production_converger.py` is to M2 what `verify_production_salvage.py` is to M1: it drives
the production class — `RollingTranscriptConverger`'s own window planning, retention and parsing —
over the trio, decoding through `M2-rolling-grid/decode-cache`, and requires the result to equal
the grid's `10/10` column at 6 dp (trio WER `.131861`, recall `.943916`, `1.000×` added decode
audio, proposals tiling `[0, 60 s)` exactly). The decoder is handed a runner that raises, so a
cache miss is a failure rather than a fresh GPU call: a module that asks for a different decode
than the one that was measured cannot quietly pass. Verdict:
`evidence/live-convergence-0824/M2-converger-production/`.

```bash
# E2 step 3b: does the SHIPPED session authority publish that arm, and attribute it? (no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_session_text_authority.py
# five mutations, in `live_session.py` itself, restored from a backup on exit
prototypes/streaming-diarization/live-convergence/mutate_session_authority.sh /tmp/authority-mutations
```

`verify_session_text_authority.py` closes the loop the grid left open. The grid scored every arm
through `proto_context_arms.SpeakerTimeline` — an *external* relabelling step that presumed the
session would attribute rolling words from the base's own labels. This replays the baseline spans
through the real `LiveSession` publication path, feeds the production converger, applies each
proposal through `LiveSession.apply_text_revision`, and scores `snapshot().effective_transcript`.
The arm survives the trip (trio WER `.131861`, recall `.943916`) **and** the shipped projection
agrees with the measured timeline on 51 of 51 rolling segments. It also samples the surface after
every commit — 98 surfaces, 66 with a rolling prefix beside a provisional suffix — because plan
§5.1's ownership boundary is invisible at the end of a case, where six 10-second windows have
tiled the whole minute. Verdict: `evidence/live-convergence-0824/M2-session-authority/`.

```bash
# E2 step 3c: does the SHIPPED refinement queue schedule the witness without delaying the base? (no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_refinement_scheduling.py
# five mutations, in `live_arbiter.py` itself, restored from a backup on exit
prototypes/streaming-diarization/live-convergence/mutate_refinement_scheduling.sh /tmp/scheduling-mutations
```

`verify_refinement_scheduling.py` is the one driver here that puts **three sessions on one
arbiter**. Scheduling is a claim about ordering under contention, so it makes every unit of work
go through the real `InferenceArbiter` — the 2.5-second canonical spans as well as the 10-second
rolling windows — and then reads back what left the queue in what order: 98 dispatches, canonical
ahead of a waiting witness 14 times, a witness ahead of waiting canonical 0 times, with the arm
unchanged (trio WER `.131861`). It reuses `verify_session_text_authority.py` as a library
(`commit_span`, `label_of_canonical`) rather than restating the replay path. Appendix B deferred
the *two-session real-time stress*; this is the scheduling-correctness half, which costs no GPU.
One finding worth carrying: the converger's coalesce key is `rolling:<epoch>` and every session
starts at epoch 0, so the key identifies a session only because the runtime builds one arbiter per
session — the driver namespaces it and says so. Verdict:
`evidence/live-convergence-0824/M2-refinement-scheduling/`.
