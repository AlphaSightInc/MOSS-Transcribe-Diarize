#!/usr/bin/env bash
# Create the sole reviewed main merge in a temporary worktree while leaving the
# Ralph primary worktree on its feature branch for later evidence journaling.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

expected_feature="${RALPH_EXPECTED_BRANCH:-ralph/live-meeting-mvp}"
# Pre-merge SHA of the ONE merge this script is currently allowed to make. It was
# af3ac366… for the first keeper merge; the prd.md amendment of 2026-07-28 authorized
# exactly one follow-up fix merge (ATS declaration, pairing-payload trim, control-channel
# error classification, their regression tests), whose pre-merge main was the first merge
# commit f9285d6 and which landed as 317df4d. The SECOND prd.md amendment of 2026-07-28
# (server decode-seam fix cycle: H1 the empty-span decode contract, H2 the span-cap
# authority contract, H3 the webrtcvad framing contract, and the real-seam regression
# tests that close the gap none of them could be caught through) authorizes exactly one
# further merge, whose pre-merge main was therefore 317df4d and which landed as b817871.
# The THIRD prd.md amendment of 2026-07-28 (the live path's terminal-failure policy: J1
# the span-bound clamp answered once, J2 an unresolved identity publishing unattributed
# words, J3 a transient decoder failure retried then committed empty, J4 every refusal
# carrying the word that names it, and the real-seam coverage for each) authorizes exactly
# one further merge, whose pre-merge main was therefore b817871 and which landed as 6a540fe.
# The FOURTH prd.md amendment of 2026-07-28 (lane observability: K1 lane state carried on the
# control channel so `mtd-capture status` can name both lanes, K2 the app logging a typed lane
# failure as loudly as an unclassified one, K3 the server recording the terminal reason and the
# per-lane codes that caused it, K4 a released session reported gone instead of merely
# unreachable, and the real-seam regression coverage for each) authorizes exactly one further
# merge, whose pre-merge main is therefore 6a540fe. Advancing this default is a
# reviewable diff on purpose: a SIXTH merge still fails here, and a command-line
# RALPH_MERGE_MAIN_BEFORE override would leave no record of why the guard was passed.
expected_main="${RALPH_MERGE_MAIN_BEFORE:-6a540fe086cf819ba0e07a948da9fec0766202c3}"
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
# The merge must not drop content that exists only on main. As committed this was a bare
# command under `set -e`, so a false answer exited 1 printing nothing at all — and it is
# false by construction after any prior keeper merge, because that merge commit lives only
# on main. Join main into the feature branch first (an empty-diff history join when main
# carries no exclusive content) rather than loosening this check.
git merge-base --is-ancestor main "$feature_sha" || {
  echo "ERROR: main ($(git rev-parse main)) is not an ancestor of $feature_sha;" >&2
  echo "       merge main into $expected_feature first, then re-run" >&2
  exit 1
}

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
  # Build both executable products as explicit acceptance gates. Swift 6.3 currently
  # builds them incidentally during `swift test`, but the Python integration tests
  # execute the real binaries and error when they are absent; do not make the keeper
  # contract depend on incidental SwiftPM target-selection behavior.
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
