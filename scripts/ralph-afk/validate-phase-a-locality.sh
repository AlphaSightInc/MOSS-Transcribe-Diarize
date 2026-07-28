#!/usr/bin/env bash
# Phase-A-only locality gate. Later production phases intentionally widen scope.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

base=af3ac3667393a0411616f52f76339eff01dc13e2
bad=()
while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  case "$path" in
    .gitignore | \
    scripts/ralph-afk/* | \
    macos/MOSSCapture/Sources/MOSSCaptureCore/CaptureSecurity.swift | \
    macos/MOSSCapture/Sources/MOSSCaptureCore/CaptureHTTPTransport.swift | \
    macos/MOSSCapture/Sources/MOSSCaptureCore/CaptureCommandLine.swift | \
    macos/MOSSCapture/Sources/MOSSCaptureCore/MicrophoneCapture.swift | \
    macos/MOSSCapture/Sources/MOSSCaptureCore/SystemAudioTap.swift | \
    macos/MOSSCapture/Sources/MOSSCaptureCore/NativeDualCaptureSource.swift | \
    macos/MOSSCapture/Sources/MOSSCaptureApp/main.swift | \
    macos/MOSSCapture/Sources/MTDCaptureCLI/main.swift | \
    macos/MOSSCapture/Tests/MOSSCaptureCoreTests/CaptureControllerTests.swift | \
    macos/MOSSCapture/Tests/MTDCaptureCLITests/MTDCaptureCLITests.swift | \
    tests/test_macos_uds_tracer.py | \
    CONTEXT.md | \
    docs/adr/0001-live-v2-json-http-contract.md)
      ;;
    *)
      bad+=("$path")
      ;;
  esac
done < <(
  {
    git diff --name-only "$base" --
    git ls-files --others --exclude-standard
  } | LC_ALL=C sort -u
)

if (( ${#bad[@]} > 0 )); then
  printf 'Phase A locality violation: %s\n' "${bad[@]}" >&2
  exit 1
fi
printf 'Phase A locality: PASS\n'
