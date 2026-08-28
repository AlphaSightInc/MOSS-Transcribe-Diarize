#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SQLITE_PREFIX="$(cd "${RELEASE_ROOT}/../.." && pwd)/sqlite-3.53.4"
export LD_LIBRARY_PATH="${SQLITE_PREFIX}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
exec "${RELEASE_ROOT}/bin/python" -m moss_transcribe_diarize.app.phase2_cutover_cli "$@"
