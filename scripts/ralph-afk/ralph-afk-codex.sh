#!/usr/bin/env bash
# Codex convenience launcher. Route through launch.sh so the project-specific
# Python, preflight, branch, ancestry, and clean-tree gates cannot be bypassed.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export RALPH_AGENT=codex
exec "$SCRIPT_DIR/launch.sh" "$@"
