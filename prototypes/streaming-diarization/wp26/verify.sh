#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/runs/wp26/tmp" npm_config_cache="$PWD/runs/wp26/npm-cache"
export WP26_EVIDENCE_DIR=evidence/mvpfix/wp26/fresh
mkdir -p "$TMPDIR" "$WP26_EVIDENCE_DIR"
WP26_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
{
  pwd
  git branch --show-current
  git rev-parse HEAD
  "$WP26_PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
} > "$WP26_EVIDENCE_DIR/shell.txt"
"$WP26_PY" -m pytest -q -ra -p no:cacheprovider -p evidence.mvpfix.wp26.local_scratch --basetemp=runs/wp26/fresh-tests tests > "$WP26_EVIDENCE_DIR/python-full.txt" 2>&1
npm --prefix frontend test -- --run --configLoader runner > "$WP26_EVIDENCE_DIR/frontend-full.txt" 2>&1
npm --prefix frontend run typecheck > "$WP26_EVIDENCE_DIR/typecheck.txt" 2>&1
npm --prefix frontend run build -- --configLoader runner > "$WP26_EVIDENCE_DIR/build.txt" 2>&1
bash prototypes/streaming-diarization/wp26/replay.sh --production > "$WP26_EVIDENCE_DIR/replay-state.jsonl" 2> "$WP26_EVIDENCE_DIR/replay-stderr.txt"
"$WP26_PY" prototypes/streaming-diarization/wp26/survey.py > "$WP26_EVIDENCE_DIR/survey.json"
"$WP26_PY" prototypes/streaming-diarization/wp26/audit.py "$WP26_EVIDENCE_DIR" > "$WP26_EVIDENCE_DIR/audit.json"
"$WP26_PY" - <<'PY'
from pathlib import Path
for path in Path('evidence/mvpfix/wp26/fresh').glob('*.txt'):
    path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()).rstrip()+'\n')
PY
git diff --check
git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets
if lsof -nP -iTCP:18126 -sTCP:LISTEN > "$WP26_EVIDENCE_DIR/listeners.txt"; then
  echo 'Own tunnel port is still occupied; investigate ownership, do not kill unrelated processes.' >&2
  exit 1
fi
