#!/bin/bash
# Full integration gate; a nonzero result blocks commit/fresh verification.
set -euo pipefail
cd "$(dirname "$0")/../../.."
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/.wp28runtime/tmp" npm_config_cache="$PWD/.wp28runtime/npm-cache"
export WP28_REAL_FIXTURES="$PWD/.wp28runtime"
WP28_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
WP28_OUT="evidence/mvpfix/wp28/${1:-initial}"
mkdir -p "$TMPDIR" "$WP28_OUT" runs/wp28
{
  pwd
  git branch --show-current
  git rev-parse HEAD
  "$WP28_PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
} > "$WP28_OUT/shell.txt"
"$WP28_PY" -m pytest -q -ra -p no:cacheprovider -p evidence.mvpfix.wp28.local_scratch --basetemp=runs/wp28/tests tests > "$WP28_OUT/python-full.txt" 2>&1
npm --prefix frontend test -- --run --configLoader runner > "$WP28_OUT/frontend-full.txt" 2>&1
"$WP28_PY" - "$WP28_OUT" <<'PY'
from pathlib import Path
import sys
for path in Path(sys.argv[1]).glob('*.txt'):
    path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()).rstrip()+'\n')
PY
git diff --check
bash scripts/check_verify_layout.sh
