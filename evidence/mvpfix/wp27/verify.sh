#!/bin/sh
set -eu
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp27-early-share
EVIDENCE="$PWD/evidence/mvpfix/wp27"
mkdir -p "$EVIDENCE/raw"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$EVIDENCE/raw"
WP27_PYTHON=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
"$WP27_PYTHON" -c 'import pathlib, moss_transcribe_diarize as m; p=pathlib.Path(m.__file__).resolve(); print(p); assert p.is_relative_to(pathlib.Path.cwd())' > "$EVIDENCE/fresh-origin.txt"
"$WP27_PYTHON" -m pytest -q -p no:cacheprovider tests > "$EVIDENCE/fresh-python-full.txt" 2>&1
npm --prefix frontend test -- --run > "$EVIDENCE/fresh-frontend-full.txt" 2>&1
npm --prefix frontend run typecheck > "$EVIDENCE/fresh-typecheck.txt" 2>&1
npm --prefix frontend run build > "$EVIDENCE/fresh-build.txt" 2>&1
git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets > "$EVIDENCE/fresh-assets-diff.txt"
git diff --check
"$WP27_PYTHON" -c 'import shutil; shutil.rmtree("evidence/mvpfix/wp27/raw")'
printf 'WP27 fresh verification commands passed. Read logs for exact counts.\n'
