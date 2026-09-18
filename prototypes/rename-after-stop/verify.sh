#!/bin/bash
set -euo pipefail
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp9-rename-identity
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/.wp9runtime/tmp"
mkdir -p "$TMPDIR"
py=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
out=evidence/mvpfix/wp9
"$py" -c 'from pathlib import Path; import moss_transcribe_diarize as m; print(m.__file__); assert Path(m.__file__).resolve().is_relative_to(Path.cwd())' | tee "$out/fresh-import.log"
"$py" prototypes/rename-after-stop/run.py --output "$out/fresh-prototype.json" > "$out/fresh-prototype.log" 2>&1
tail -1 "$out/fresh-prototype.log"
"$py" -c 'import json; rows=json.load(open("evidence/mvpfix/wp9/fresh-prototype.json")); assert len(rows)==5 and all(r["status"]==200 and r["meeting"]==r["history"] for r in rows)'
"$py" prototypes/rename-after-stop/silence.py | tee "$out/fresh-silence.json"
"$py" -m pytest -q -p no:cacheprovider --basetemp="$PWD/.wp9runtime/fresh-pytest" tests/phase2/test_saved_speaker_naming.py tests/phase2/test_manual_speaker_voiceprints.py tests/phase2/test_wp9_silence_birth.py 2>&1 | tee "$out/fresh-python.log"
npm --prefix frontend test -- --run > "$out/fresh-frontend.log" 2>&1
tail -6 "$out/fresh-frontend.log"
npm --prefix frontend run typecheck 2>&1 | tee "$out/fresh-typecheck.log"
npm --prefix frontend run build 2>&1 | tee "$out/fresh-build.log"
# Reproduce known original integration failures, never disguise them as passing tests.
set +e
"$py" -m pytest -q -p no:cacheprovider --tb=short --basetemp="$PWD/.wp9runtime/fresh-baseline" 'tests/phase2/test_draft_lane.py::test_reader_retires_draft_by_audio_boundary[multiple]' tests/phase2/test_runner_composition.py::test_launcher_without_prompt_finalizer_builds_http_request tests/phase2/test_export_oracle.py > "$out/fresh-known-failures.log" 2>&1
integration_exit=$?
set -e
printf 'Known integration failure command exit: %s\n' "$integration_exit"
tail -1 "$out/fresh-known-failures.log"
test "$integration_exit" -eq 1
git diff --check
