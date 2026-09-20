#!/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PYTHON=/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python
mkdir -p "$ROOT/evidence/round4/runtime"
cd "$ROOT"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests \
  2>&1 | tee evidence/round4/runtime/backend-suite.log
