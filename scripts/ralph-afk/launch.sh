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

# Opus, not the engine default: this loop writes Swift + Python + ops changes and
# reasons about a multi-host deployment contract.
export RALPH_MODEL="${RALPH_MODEL:-opus}"

# Local toolchain sanity only; host reachability is probed per candidate so a
# transient tailnet blip cannot flip the loop's preflight signal.
export RALPH_PREFLIGHT_CMD="${RALPH_PREFLIGHT_CMD:-$here/preflight.sh}"
export RALPH_PREFLIGHT_REQUIRED="${RALPH_PREFLIGHT_REQUIRED:-0}"

exec "$here/ralph-afk.sh" "${1:-30}"
