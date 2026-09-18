#!/bin/sh
# Audit witnesses only. A reproduced defect is a successful witness, not acceptance.
set -eu
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp32-final-crossreview
WP32_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
mkdir -p .wp32/fresh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/.wp32/fresh"
"$WP32_PY" -c 'import moss_transcribe_diarize as m; print(m.__file__)' > evidence/mvpfix/wp32/fresh-import.txt
node evidence/mvpfix/wp32/prototype-legacy.cjs > evidence/mvpfix/wp32/fresh-legacy.jsonl
"$WP32_PY" evidence/mvpfix/wp32/spec_probe.py > evidence/mvpfix/wp32/fresh-truncation.json
test ! -e frontend/src/components/WP32prototype.test.tsx
trap 'rm -f frontend/src/components/WP32prototype.test.tsx' EXIT HUP INT TERM
cp evidence/mvpfix/wp32/prototype-reset.test.tsx frontend/src/components/WP32prototype.test.tsx
npm --prefix frontend test -- --run --configLoader runner src/components/WP32prototype.test.tsx -t 'WP32 prototype' > evidence/mvpfix/wp32/fresh-reset.txt 2>&1
rm frontend/src/components/WP32prototype.test.tsx
trap - EXIT HUP INT TERM
"$WP32_PY" -m pytest -q -rs -p no:cacheprovider \
  tests/phase2/test_file_failure_reasons.py \
  tests/phase2/test_saved_speaker_naming.py \
  tests/phase2/test_accepted_stop_lease.py \
  tests/test_live_lane_decode.py \
  tests/test_file_resolver_performance.py \
  tests/phase2/test_runner_composition.py \
  tests/phase2/test_tls_preparation.py \
  > evidence/mvpfix/wp32/fresh-focused.txt 2>&1
printf '0\n' > evidence/mvpfix/wp32/fresh-probes-status.txt
printf 'Fresh audit witnesses completed; inspect source and all ten rows before verdict.\n'
