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
# merge, whose pre-merge main was therefore 6a540fe and which landed as fc7097d.
# The FIFTH prd.md amendment of 2026-07-28 (survive a lane fault: candidate 53 a throwing
# publish no longer skipping the tick's heartbeat, candidate 48 the start-time heartbeat coming
# under the same unwind guard as the publish above it, candidate 49 the dropped-buffer watermark
# re-baselined against the queue's cumulative counter instead of zeroed, candidate 50 / decision
# D-c the live decode bounded by a token cap derived from the span's own duration, decision D-a
# reclassifying macos_buffer_overrun as a lane DEGRADATION rather than a lane failure, and the
# closed coverage gap that posts a frame on the lane that failed) authorizes exactly one further
# merge, whose pre-merge main was therefore fc7097d and which landed as 77e0014.
# The SIXTH prd.md amendment of 2026-07-28 (live speaker identity, Phase N) also authorizes one
# merge, but it is explicitly sequenced AFTER Phase M's gate and is UNSPENT — no Phase N source
# exists on this branch, so it is not what advances this line.
# The SEVENTH prd.md amendment of 2026-07-28 (a wall clock is not a duration, Phase P: P1 the live
# decode measuring its own elapsed time on time.monotonic() instead of reading the runner's
# wall-clock elapsed_sec, P2 the general ruling that untrustworthy timing metadata DEGRADES to a
# null elapsed/RTF on canonical_processed rather than ending the meeting, P3 the real-seam
# regressions driving the coordinator with a negative elapsed_sec, and P4 the sweep of every other
# site that subtracted two time.time() readings and called the result a duration) authorizes
# exactly one further merge, whose pre-merge main was therefore 77e0014 and which landed as 42abc5a.
# The prd.md section "Phase N is SUPERSEDED by ADR-0002" (operator commit 0456177, 2026-07-29) is
# what advances this line now. It does not create a new fix cycle: it re-shapes the ALREADY
# AUTHORIZED Phase N of the sixth amendment into docs/adr/0002-two-tier-diarization-fingerprint-
# album.md's form ("Phase N remains authorized. Take it in ADR-0002's shape, not the sixth
# amendment's") and ends its "after Phase M's gate" sequencing, which Phase M's landed gate spent.
# The Phase N source now on this branch is ADR-0002 steps 1-3 — the fingerprint album replacing
# latest-span overwrite through the existing canonical_embedding hook (live_identity_album.py), the
# calibrated matcher pair the album is measured at carried into the deployment manifest, the
# retained-audio tape of ADR-0003 (live_tape.py, OFF unless a host declares a root), and the
# retrospective sweep that re-matches the album against retained evidence and rewrites already-
# published labels beside the transcript (live_identity_sweep.py). Its gate is ADR-0002's measured
# acceptance, green at 1e1cf3f: >= 90-95 % live speaker accuracy (93.44 % mean / 92.18 % min against
# overwrite's 72.02/55.68) and demonstrated live->file convergence (swept 99.26/98.48 with
# residual_corrections 0). It authorizes exactly one further merge, whose pre-merge main was
# therefore 42abc5a and which landed as 7a4f59c.
# The NINTH prd.md amendment of 2026-07-29 ("the birth floor, the stop, the RTF gate, the
# cadence", operator commits 6e3e4fe and bb8daad) is what advances this line now. Phase Q is
# four items and every one of them is on this branch: Q1 / candidate 55, a would-be birth
# deferred unless the evidence layer would enrol it, asked of the album by name so the birth
# floor and the album's admission gate are ONE number rather than two that agree today
# (live_identity.py, live_provider_bundle.py); Q2 / candidate 64, the decoder-RTF clause given
# a derived minimum span duration below which the ratio measures the decoder's fixed
# per-request cost, with the excluded count inside the verdict sentence — loop tooling only, no
# product source, so it is not in this payload at all; Q3 / candidate 71, the portal's poll
# cadence and the app's reported render bound moved together 1.0 s -> 0.5 s (the plan's own
# second ordered latency remedy) with an enforcing node in EACH language, because either
# constant moved alone changes a gated number or a reader's wait but never both; Q4 /
# candidate 60, the Mac client's clean stop reaching POST .../stop after its final drain, so
# view authority dies with the meeting instead of outliving it by the 30 s helper lease.
# Its gate is the amendment's own: full Swift/Python green at 73bbe42 (Swift 164 / 0 failures /
# 0 warnings on a fresh scratch, Python 810 passed / 2 skipped / 368 subtests, Darwin tracer 4
# with 0 skips), plus the accuracy harness showing the birth floor's effect on canonical count
# — 16 canonical speakers on all eight fixture meetings without it against 2,2,4,3,4,4,7,6 with
# it, for true k of 2,2,3,3,4,4,6,6, and live accuracy 93.44 % -> 99.13 %. F1 and F3 are the
# amendment's remaining gate half and they measure the DEPLOYED service and the INSTALLED app,
# so they follow this merge and its redeploy exactly as they did for Phases M, P and N; the
# PRD's "never deploy from a feature branch" constraint permits no other order. It authorizes
# exactly one further merge, whose pre-merge main is therefore 7a4f59c. Advancing this default
# is a reviewable diff on purpose: a TENTH merge still fails here, and a command-line
# RALPH_MERGE_MAIN_BEFORE override would leave no record of why the guard was passed.
# Advanced to 5111b36 for the stop-race fix the operator directed on 2026-07-29, after F3 on the
# deployed 5111b36 came back 7 GREEN / 1 RED with `sessionRefusal sessionDisowned` 1.7 s after a
# clean stop. That merge carries exactly two product files — CaptureController.swift and its tests —
# from a branch cut at this same SHA, deliberately excluding the feature branch's prototype and docs
# commits. An ELEVENTH merge still fails here.
# Advanced to fa0ff6a for the operator-authorized production closeout on 2026-07-29. Fresh gates
# exposed one test-only Swift concurrency warning plus a first-run permission heartbeat sending
# local-only `pending` to a wire contract that calls it `starting`. This merge fixes that boundary,
# keeps the denied lane survivable, and makes its environment-sensitive tests deterministic. A
# THIRTEENTH merge still fails here.
# Advanced to 6d55da7 after deployment found both production listeners restart-looping: WSL had
# moved to mirrored networking while the Windows sign-in task kept restoring NAT portproxy rows.
# This operator-authorized closeout makes that target-repo deployment tool mode-aware.
# Advanced to 60f7767 after the final F3 proof exposed an in-process second-meeting failure:
# AVAudioConverter remained at end-of-stream after the first clean stop. This production closeout
# gives each meeting fresh converters and per-session counters, and closes the browser-storage
# regression already measured green by the deployed probe.
# Advanced to 42bfc2a after the final-SHA F2 interruption exposed the pump leaving URLSession's
# 60-second default on frame and heartbeat requests. A measured 5.140-second drop filled the native
# system-audio queue before captured audio could reach the 15-second outbox. This closeout bounds
# both serial pump requests to one second and pins that policy at both HTTP seams.
# Advanced to b56ad39 after that bounded-turn deployment proved the 128-buffer raw queue was still
# too shallow: one 5.460-second F2 turn held all 128 system buffers and dropped 146 more. This
# closeout pairs the one-second request bounds with 1,024 buffers per lane, 3.7x the measured
# 274-buffer demand.
expected_main="${RALPH_MERGE_MAIN_BEFORE:-b56ad393fd18a5d19fe294252e704d6d8c043d2f}"
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
