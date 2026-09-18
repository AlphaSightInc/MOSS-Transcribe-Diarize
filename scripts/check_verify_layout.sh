#!/usr/bin/env bash
# Root copies collide when work packages merge. Check tracked AND untracked files.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
failed=0
for name in VERIFY.md VERIFY-RESULT.md; do
  if [ -e "${root}/${name}" ] || [ -L "${root}/${name}" ] || git -C "${root}" ls-files --error-unmatch "${name}" >/dev/null 2>&1; then
    echo "FAIL: ${name} belongs under docs/verify/<wp>/" >&2
    failed=1
  fi
done
if [ "${failed}" -eq 0 ]; then echo 'PASS: verification documents are not at repository root'; fi
exit "${failed}"
