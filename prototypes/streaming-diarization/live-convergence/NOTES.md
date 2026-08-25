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
