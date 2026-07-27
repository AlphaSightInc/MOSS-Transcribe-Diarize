#!/usr/bin/env bash
# Create the sole reviewed main merge in a temporary worktree while leaving the
# Ralph primary worktree on its feature branch for later evidence journaling.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

expected_feature="${RALPH_EXPECTED_BRANCH:-ralph/live-meeting-mvp}"
expected_main="${RALPH_MERGE_MAIN_BEFORE:-af3ac3667393a0411616f52f76339eff01dc13e2}"
merge_dry_run="${RALPH_MERGE_DRY_RUN:-0}"
[[ "$(git branch --show-current)" == "$expected_feature" ]] || {
  echo "ERROR: keeper merge must launch from $expected_feature" >&2
  exit 1
}
if [[ -n "$(git status --porcelain)" &&
      ! ( "$merge_dry_run" == "1" && "${RALPH_MERGE_ALLOW_DIRTY:-0}" == "1" ) ]]; then
  echo "ERROR: feature worktree must be clean before keeper merge" >&2
  exit 1
fi
[[ "$(git rev-parse main)" == "$expected_main" ]] || {
  echo "ERROR: main moved from expected pre-merge SHA $expected_main" >&2
  exit 1
}

feature_sha="$(git rev-parse HEAD)"
git merge-base --is-ancestor main "$feature_sha"

if [[ "$merge_dry_run" == "1" ]]; then
  printf 'Keeper merge dry-run: PASS feature=%s main_before=%s\n' \
    "$feature_sha" "$expected_main"
  exit 0
fi

merge_parent="$(mktemp -d)"
merge_worktree="$merge_parent/main"
cleanup() {
  if [[ -d "$merge_worktree" ]]; then
    if [[ -f "$merge_worktree/.git/MERGE_HEAD" ]] ||
       git -C "$merge_worktree" rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
      git -C "$merge_worktree" merge --abort >/dev/null 2>&1 || true
    fi
    git worktree remove --force "$merge_worktree" >/dev/null 2>&1 || true
  fi
  rmdir "$merge_parent" >/dev/null 2>&1 || true
}
trap cleanup EXIT

git worktree add --quiet "$merge_worktree" main
git -C "$merge_worktree" merge --no-ff --no-commit "$feature_sha"
(
  cd "$merge_worktree"
  # The executable products must be built explicitly: Package.swift's test targets
  # depend only on MOSSCaptureCore, so `swift test` never produces mtd-capture or
  # MOSSCaptureApp. tests/test_live_integration.py (and the A-034 tracer) execute the
  # real binaries and ERROR rather than skip when they are absent — verified in a
  # fresh worktree: 5 errors without these builds, 5 passed with them.
  swift build --package-path macos/MOSSCapture --product mtd-capture
  swift build --package-path macos/MOSSCapture --product MOSSCaptureApp
  swift test --package-path macos/MOSSCapture
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q -p no:cacheprovider
)
git -C "$merge_worktree" commit --no-verify -m \
  "merge: live meeting transcription MVP keeper"

merge_sha="$(git -C "$merge_worktree" rev-parse HEAD)"
[[ "$(git -C "$merge_worktree" rev-parse HEAD^2)" == "$feature_sha" ]]
printf 'Keeper merge: PASS feature=%s main=%s\n' "$feature_sha" "$merge_sha"
