#!/usr/bin/env bash
# Per-iteration environment sanity for the MOSS live-meeting loop.
#
# Deliberately LOCAL-ONLY: the engine reduces this to a single ok/failing signal,
# so transient LAN/tailnet or remote-host blips must not flip it. Host
# reachability is probed per candidate using the commands in context.md.
#
# Checks the things that would break *any* iteration:
#   - correct Python (3.12 pyenv, not /usr/bin/python3 at 3.9)
#   - pytest importable
#   - swift toolchain present (Mac client work)
#   - inside the expected git worktree
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

git rev-parse --is-inside-work-tree >/dev/null

python3 - <<'PY'
import sys
assert sys.version_info[:2] == (3, 12), f"python3 must be 3.12, got {sys.version.split()[0]}"
import pytest  # noqa: F401
PY

command -v swift >/dev/null

exit 0
