# live-convergence — throwaway experiments for the E0–E4 campaign

Home for the campaign's prototypes (PRD: "Throwaway experiments live under
`prototypes/streaming-diarization/live-convergence/`, never in module code"). Nothing here is
imported by `moss_transcribe_diarize/`.

| file | question it answers | verdict |
|---|---|---|
| `replay_saved_decode_dispositions.py` | do the seven real lost decodes now report the ending that happened? | yes — `evidence/live-convergence-0824/M0b-decode-disposition/` |
| `probe_file_mode_decode_identity.py` | did the A0.2 change move file-mode decoder output? | no — same bundle |
| `evaluator_v2.py` + `compare_evaluators.py` + `cases.json` | can the campaign be scored on a lens a wider timestamp cannot move? | yes — `evidence/live-convergence-0824/M0c-evaluator-v2/` |

`cases.json` is the corpus contract: which saved hypotheses are scored, which corpus each is
scored against, which group's mean it joins, and the means the plan already published for them.
Instance values live there so the drivers stay general.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_evaluators.py --output /tmp/v2.json
```
