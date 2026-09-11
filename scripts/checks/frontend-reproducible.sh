#!/usr/bin/env bash
# CI check: the exact committed frontend must rebuild without changing the tree.
# Also attack the developer-worktree case: node_modules symlinked to a sibling.
set -euo pipefail
root=$(git -C "$(dirname "$0")/../.." rev-parse --show-toplevel)
revision=$(git -C "$root" rev-parse "${1:-HEAD}^{commit}")
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
git clone --quiet --no-local "$root" "$scratch/repo"
git -C "$scratch/repo" checkout --quiet --detach "$revision"
cd "$scratch/repo"
assert_clean() {
  status=$(git status --porcelain=v1 --untracked-files=all)
  if [ -n "$status" ]; then
    printf 'FAIL: frontend build changed committed source (%s)\n%s\n' "$1" "$status" >&2
    exit 1
  fi
  printf 'PASS: git status --porcelain empty (%s), SHA=%s\n' "$1" "$revision"
}
npm --prefix frontend ci
npm --prefix frontend run build
assert_clean local-dependencies
mkdir -p "$scratch/shared/frontend"
mv frontend/node_modules "$scratch/shared/frontend/node_modules"
ln -s "$scratch/shared/frontend/node_modules" frontend/node_modules
npm --prefix frontend run build
assert_clean symlinked-dependencies
