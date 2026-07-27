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
#   - required source refs, fork remote, and authoritative plan available
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

git rev-parse --is-inside-work-tree >/dev/null
[[ "$(git remote get-url origin)" == \
  "https://github.com/AlphaSightInc/MOSS-Transcribe-Diarize.git" ]]
git cat-file -e af3ac3667393a0411616f52f76339eff01dc13e2^{commit}
git cat-file -e 67a27b88e5fab10dcb81ea28abd4628859ce33e8^{commit}

python3 - <<'PY'
import sys
assert sys.version_info[:2] == (3, 12), f"python3 must be 3.12, got {sys.version.split()[0]}"
import pytest  # noqa: F401
PY

command -v swift >/dev/null
git diff --check

plan="/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/docs/live-capture-gap-and-execution-plan-20260727.md"
[[ -r "$plan" ]]
grep -q '^\*\*Revision:\*\* 4 ' "$plan"
grep -q 'ga0-alienware-rtx4070ti' "$plan"
[[ -f "/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/.stop-after-current-role" ]]

exit 0
