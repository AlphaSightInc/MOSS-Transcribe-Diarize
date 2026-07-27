#!/usr/bin/env bash
# Per-iteration environment sanity for the MOSS live-meeting loop.
#
# Deliberately LOCAL-ONLY: the engine reduces this to a single ok/failing signal,
# so transient LAN/tailnet or remote-host blips must not flip it. Host
# reachability is probed per candidate using the commands in context.md.
#
# Preflight is MANDATORY (launch.sh sets RALPH_PREFLIGHT_REQUIRED=1), so every
# check here must be a durable environment fact. Never add code-style, coverage,
# or work-in-progress checks: a cosmetic failure would halt an unattended run.
#
# Checks the things that would break *any* iteration:
#   - correct Python (3.12 pyenv, not /usr/bin/python3 at 3.9)
#   - pytest importable
#   - swift toolchain present (Mac client work)
#   - inside the expected git worktree, with the fork remote and both source refs
#   - the authoritative plan is readable and not older than this bundle expects
#   - the governed control-plane loop is still halted (one-writer rule)
#
# Run it by hand to see which check failed; the engine discards this output.
set -euo pipefail

die() { echo "preflight: $*" >&2; exit 1; }

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git worktree: $repo_root"

origin_url="$(git remote get-url origin 2>/dev/null || true)"
[[ "$origin_url" == *"AlphaSightInc/MOSS-Transcribe-Diarize"* ]] \
  || die "origin must be the AlphaSight fork, got: ${origin_url:-<none>}"

# Both source refs the plan depends on: the reviewed base and the A-034 graft source.
git cat-file -e af3ac3667393a0411616f52f76339eff01dc13e2^{commit} 2>/dev/null \
  || die "base commit af3ac36 is missing from this repo"
git cat-file -e 67a27b88e5fab10dcb81ea28abd4628859ce33e8^{commit} 2>/dev/null \
  || die "A-034 graft source 67a27b8 is missing from this repo"

python3 - <<'PY' || die "python3 must be pyenv 3.12 with pytest importable (launch.sh resolves it)"
import sys
assert sys.version_info[:2] == (3, 12), f"python3 must be 3.12, got {sys.version.split()[0]}"
import pytest  # noqa: F401
PY

command -v swift >/dev/null 2>&1 || die "swift toolchain not on PATH"

control_plane="${RALPH_CONTROL_PLANE:-/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize}"
plan="${RALPH_PLAN_PATH:-$control_plane/docs/live-capture-gap-and-execution-plan-20260727.md}"
min_revision="${RALPH_PLAN_MIN_REVISION:-5}"

[[ -r "$plan" ]] || die "authoritative plan is not readable: $plan"

# Gate on "at least the revision this bundle was written against", never on one
# exact revision: the plan is expected to keep being revised, and an equality
# check would hard-block every launch the moment it legitimately advances.
revision="$(sed -n 's/^\*\*Revision:\*\* \([0-9][0-9]*\).*/\1/p' "$plan" | head -n 1)"
[[ -n "$revision" ]] || die "cannot parse '**Revision:** <n>' from $plan"
(( revision >= min_revision )) \
  || die "plan revision $revision is older than the required minimum $min_revision"

grep -q 'ga0-alienware-rtx4070ti' "$plan" \
  || die "plan does not target ga0-alienware-rtx4070ti; refusing to run against a retargeted plan"

# One-writer rule: the governed aisight-coding-loop must stay halted while Ralph owns this repo.
[[ -f "$control_plane/.stop-after-current-role" ]] \
  || die "governed loop sentinel .stop-after-current-role is gone; two autonomous writers would collide"

exit 0
