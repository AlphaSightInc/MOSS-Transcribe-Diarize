#!/bin/bash
set -eu
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp3-capture-guards
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/evidence/mvpfix/wp3/tmp"
mkdir -p "$TMPDIR"
wp3_python=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
"$wp3_python" -c 'import pathlib, moss_transcribe_diarize as m; print(m.__file__); assert pathlib.Path(m.__file__).resolve().is_relative_to(pathlib.Path.cwd())'
"$wp3_python" -m pytest -q -p no:cacheprovider --basetemp=evidence/mvpfix/wp3/tmp/fresh tests/test_live_capture_guard.py tests/test_live_mixer.py tests/test_live_session.py tests/test_live_session_v2.py tests/test_live_vad.py tests/test_live_terminal_finalizer.py tests/phase2/test_owner_bound_live_meeting.py tests/phase2/test_wave1_qualification.py tests/test_live_service_runtime.py tests/test_live_terminal_lifecycle.py tests/test_live_terminal_tape.py tests/test_live_transcript_convergence.py tests/phase2/test_pre_stop_terminal_boundary.py
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets
"$wp3_python" - <<'PY'
import ast, pathlib, subprocess
p=pathlib.Path('scripts/attended-echo')
ast.parse((p/'measure.py').read_text())
s=(p/'capture.html').read_text().split('<script type="module">')[1].split('</script>')[0]
r=subprocess.run(['node','--check','--input-type=module'],input=s,text=True,capture_output=True)
assert r.returncode==0,r.stderr
print('Attended kit Python/JavaScript syntax: PASS; physical recording UNMEASURED')
PY
git diff --check
