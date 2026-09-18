#!/bin/bash
# Execute only in the actual new chat. Identity-equality failure blocks handoff.
set -euo pipefail
cd "$(dirname "$0")/../../.."
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/.wp28runtime/tmp"
WP28_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
mkdir -p "$TMPDIR" evidence/mvpfix/wp28/fresh
"$WP28_PY" - <<'PY'
import json, os
from pathlib import Path
previous=json.loads(Path('evidence/mvpfix/wp28/environment.json').read_text())
current=os.environ.get('CODEX_THREAD_ID')
assert current and current != previous['implementation_thread'], 'Actual fresh chat required; a fresh shell is insufficient'
Path('evidence/mvpfix/wp28/fresh/context.json').write_text(json.dumps(dict(implementation_thread=previous['implementation_thread'],verification_thread=current,pane=os.environ.get('TMUX_PANE')),indent=2)+'\n')
PY
bash prototypes/streaming-diarization/wp28-file-resolver-perf/suites.sh fresh
"$WP28_PY" prototypes/streaming-diarization/wp28-file-resolver-perf/probe.py --serial --arm fresh-serial > evidence/mvpfix/wp28/fresh/serial-stdout.jsonl
"$WP28_PY" prototypes/streaming-diarization/wp28-file-resolver-perf/probe.py --arm fresh-production > evidence/mvpfix/wp28/fresh/production-stdout.jsonl
"$WP28_PY" - <<'PY'
import json
from pathlib import Path
root=Path('evidence/mvpfix/wp28'); rows=[]
for minutes in (6,30):
    before=json.loads((root/f'fresh-serial-{minutes}.json').read_text())
    after=json.loads((root/f'fresh-production-{minutes}.json').read_text())
    assert before['byte_identical'] and after['byte_identical']
    assert before['counts']==after['counts']
    assert before['seconds']==after['seconds']
    assert after['times']['resolver']<before['times']['resolver'], 'No wall-time improvement in this run'
    rows.append(dict(minutes=minutes,windows=after['windows'],before_seconds=before['times']['resolver'],after_seconds=after['times']['resolver'],speedup=before['times']['resolver']/after['times']['resolver'],byte_identical=True,intervals=after['counts']['intervals']))
(root/'fresh/summary.json').write_text(json.dumps(dict(status='PASS',comparisons=rows,decoder_requests=0),indent=2)+'\n')
PY
git diff --check
bash scripts/check_verify_layout.sh
