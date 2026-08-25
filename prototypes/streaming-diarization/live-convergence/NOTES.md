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

`run_paired_passes.sh` supersedes `run_paired_reacquisition.sh` from M1 onward: same four
sequential passes, plus the one discarded warm-up decode the campaign adopted after M0(d)
measured the decoder's cold-start flip. The M0(d) script is kept unchanged because it is that
milestone's reproducer.
