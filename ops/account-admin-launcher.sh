#!/usr/bin/env bash
# Relocatable host-local control client for an immutable Account release.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
RUNTIME_DIR="$(cd "${SELF_DIR}/.." && pwd)"
exec "${RUNTIME_DIR}/bin/python" -m moss_transcribe_diarize.app.phase2_admin "$@"
