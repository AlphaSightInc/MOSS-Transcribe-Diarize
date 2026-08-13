#!/usr/bin/env bash
# Codex convenience launcher: identical to `RALPH_AGENT=codex ./ralph-afk.sh`.
# Kept for callers that launch ralph-afk-codex.sh by name; all logic, model
# defaults, and overrides (RALPH_CODEX_MODEL, RALPH_CODEX_REASONING_EFFORT)
# live in ralph-afk.sh.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export RALPH_AGENT=codex
exec "$SCRIPT_DIR/ralph-afk.sh" "$@"
