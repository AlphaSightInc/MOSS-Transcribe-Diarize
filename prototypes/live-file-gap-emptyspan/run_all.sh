#!/usr/bin/env bash
# One-command repro for the H3 empty-span investigation.
#   bash prototypes/live-file-gap-emptyspan/run_all.sh
# Requires: the vLLM endpoint at http://127.0.0.1:18000/v1 (request concurrency stays at 1).
set -euo pipefail
REPO=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize
PY="$REPO/.venv/bin/python"
cd "$REPO/prototypes/live-file-gap-emptyspan"

"$PY" d1_characterize.py   # locate + characterise every empty span in the baseline traces
"$PY" sim_spans.py         # gate G2: offline span simulator reproduces all 80 span boundaries
"$PY" d2_reproduce.py      # empty decodes reproduce deterministically; controls match baseline
"$PY" d3_explain.py        # raw decode (validation bypassed) + bounds sweep
"$PY" d4_ceiling.py        # gate G1 + recovery ceiling on the trio
"$PY" p1_provoke_3min.py   # provoke discards on the 3-minute tier (77 spans, ~1 min of GPU)
"$PY" p2_policies.py       # measure every recovery policy on every discarded span
"$PY" p3_project.py        # gate G5: project each policy onto the trio's published metrics
