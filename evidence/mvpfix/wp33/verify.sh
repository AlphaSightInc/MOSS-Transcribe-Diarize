#!/bin/sh
# Required regression/full/build checks; every failure stops verification.
set -eu
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp33-crossreview-fixes
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
mkdir -p .wp33/tmp
export TMPDIR="$PWD/.wp33/tmp"
"$PY" -c 'from pathlib import Path; import moss_transcribe_diarize as m; print(m.__file__); assert Path(m.__file__).resolve().is_relative_to(Path.cwd())' > evidence/mvpfix/wp33/fresh-import.txt
"$PY" evidence/mvpfix/wp33/replay-truncation.py > evidence/mvpfix/wp33/fresh-truncation.json
"$PY" evidence/mvpfix/wp33/replay-qualification.py > evidence/mvpfix/wp33/fresh-qualification.txt
node evidence/mvpfix/wp32/prototype-legacy.cjs > evidence/mvpfix/wp33/fresh-legacy.jsonl
"$PY" - <<'PY'
import json
from pathlib import Path
rows=[json.loads(line) for line in Path('evidence/mvpfix/wp33/fresh-legacy.jsonl').read_text().splitlines()]
exports=[row for row in rows if row['step']=='export']
assert len(exports)==5 and all(row['equal'] for row in exports)
assert next(row for row in exports if row['format']=='json')['headBytes']==497
PY
"$PY" prototypes/streaming-diarization/wp12-stop-identity/fault_controls.py --terminal-only > evidence/mvpfix/wp33/fresh-terminal-mutations.txt 2>&1
"$PY" - <<'PY'
from pathlib import Path
log=Path('evidence/mvpfix/wp33/fresh-terminal-mutations.txt').read_text()
assert '2 failed' in log and log.count('AssertionError') >= 2 and 'TypeError' not in log
PY
"$PY" -m pytest -q -p no:cacheprovider -p evidence.mvpfix.wp16.local_scratch tools/qualify/test_bundle.py > evidence/mvpfix/wp33/fresh-bundle-helpers.txt 2>&1
"$PY" -m pytest -q -rs -p no:cacheprovider -p evidence.mvpfix.wp16.local_scratch tests > evidence/mvpfix/wp33/fresh-python.txt 2>&1
npm --prefix frontend test -- --run --configLoader runner > evidence/mvpfix/wp33/fresh-frontend.txt 2>&1
npm --prefix frontend run typecheck > evidence/mvpfix/wp33/fresh-typecheck.txt 2>&1
npm --prefix frontend run build -- --configLoader runner > evidence/mvpfix/wp33/fresh-build.txt 2>&1
git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets > evidence/mvpfix/wp33/fresh-asset-parity.txt
bash scripts/check_verify_layout.sh > evidence/mvpfix/wp33/fresh-layout.txt
printf 'PASS\n' > evidence/mvpfix/wp33/fresh-status.txt
