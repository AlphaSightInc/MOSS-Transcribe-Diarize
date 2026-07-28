#!/usr/bin/env bash
# Launch the MOSS live-meeting Ralph AFK loop with this project's configuration.
#
# The engine's defaults are deliberately generic (model sonnet, no preflight); this
# wrapper pins the values this project needs so a launch is one reproducible command
# and cannot silently run under-configured.
#
#   ./scripts/ralph-afk/launch.sh            # 30 iterations (recommended first run)
#   ./scripts/ralph-afk/launch.sh 10         # shorter run
#   RALPH_DRY_RUN=1 ./scripts/ralph-afk/launch.sh 1     # validate config + preview prompt
#   RALPH_AGENT=codex ./scripts/ralph-afk/launch.sh 30   # run on codex instead
#
# Stop a running loop:  touch scripts/ralph-afk/.stop
# Watch it:             tail -f scripts/ralph-afk/telemetry/run-*/iter-*.log
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The host login shell currently resolves /usr/bin/python3 (3.9), while this
# repository's validated environment is pyenv Python 3.12. Resolve it
# deliberately so the launcher, preflight, engine, and iteration agents all
# see the same interpreter.
if [[ -n "${RALPH_PYTHON:-}" ]]; then
  ralph_python="$RALPH_PYTHON"
elif command -v pyenv >/dev/null 2>&1; then
  ralph_python="$(pyenv which python3)"
else
  ralph_python="$(command -v python3)"
fi
"$ralph_python" - <<'PY'
import sys
assert sys.version_info[:2] == (3, 12), (
    f"Ralph requires Python 3.12, got {sys.version.split()[0]}"
)
PY
export PATH="$(cd "$(dirname "$ralph_python")" && pwd):$PATH"
export RALPH_PYTHON="$ralph_python"

# Opus, not the engine default: this loop writes Swift + Python + ops changes and
# reasons about a multi-host deployment contract.
export RALPH_MODEL="${RALPH_MODEL:-opus}"

# Local deterministic gates are required. Host reachability is still probed per
# candidate so a transient tailnet blip cannot flip the loop's preflight signal.
export RALPH_PREFLIGHT_CMD="${RALPH_PREFLIGHT_CMD:-$here/preflight.sh}"
export RALPH_PREFLIGHT_REQUIRED="${RALPH_PREFLIGHT_REQUIRED:-1}"
export RALPH_EXPECTED_BRANCH="${RALPH_EXPECTED_BRANCH:-ralph/live-meeting-mvp}"
export RALPH_REQUIRED_ANCESTOR="${RALPH_REQUIRED_ANCESTOR:-af3ac3667393a0411616f52f76339eff01dc13e2}"

# Plan compatibility lives here. The minimum rejects stale plans; the exact contract
# rejects a newer incompatible plan without blocking compatible editorial revisions.
# The authoritative server metadata is exact rather than a broad text search.
export RALPH_CONTROL_PLANE="${RALPH_CONTROL_PLANE:-/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize}"
export RALPH_PLAN_PATH="${RALPH_PLAN_PATH:-$RALPH_CONTROL_PLANE/docs/live-capture-gap-and-execution-plan-20260727.md}"
export RALPH_PLAN_MIN_REVISION="${RALPH_PLAN_MIN_REVISION:-6}"
export RALPH_PLAN_CONTRACT="${RALPH_PLAN_CONTRACT:-moss-live-meeting-v1}"
export RALPH_SERVER_HOST="${RALPH_SERVER_HOST:-ga0-alienware-rtx4070ti}"

exec "$here/ralph-afk.sh" "${1:-30}"
