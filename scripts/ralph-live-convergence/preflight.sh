#!/usr/bin/env bash
# Campaign preflight: stack + branch sanity. Status is injected into each iteration's
# prompt (RALPH_PREFLIGHT_REQUIRED=0: agents see failures and may repair the LOCAL
# stack per Appendix B grants; the 4070 Ti host is never touched).
set -u
ok=0
branch="$(git -C "$(dirname "${BASH_SOURCE[0]}")/../.." branch --show-current 2>/dev/null)"
if [[ "$branch" != "ralph/live-convergence-0824" ]]; then
  echo "PREFLIGHT FAIL: on branch '$branch', expected ralph/live-convergence-0824"
  ok=1
fi
if curl -fsS --max-time 6 http://127.0.0.1:18000/v1/models >/dev/null 2>&1; then
  echo "PREFLIGHT OK: vLLM tunnel (127.0.0.1:18000)"
else
  echo "PREFLIGHT FAIL: vLLM tunnel down (scripts/moss-vllm-tunnel.sh may restart it; 4070Ti host itself is off-limits)"
  ok=1
fi
if curl -fskS --max-time 6 https://127.0.0.1:7861/api/runtime >/dev/null 2>&1; then
  echo "PREFLIGHT OK: dev backend (https://127.0.0.1:7861)"
else
  echo "PREFLIGHT FAIL: dev backend down (restart allowed per Appendix B; record it in progress.txt)"
  ok=1
fi
exit "$ok"
