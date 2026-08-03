#!/bin/bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
scratch=$(mktemp -d /tmp/moss-capture-layout-policy.XXXXXX)
trap 'test -n "$scratch" && test "${scratch#/tmp/moss-capture-layout-policy.}" != "$scratch" && rm -rf "$scratch"' EXIT

cp "$root/prototypes/capture-layout-policy/probe.swift" "$scratch/main.swift"

swiftc \
  "$root"/macos/MOSSCapture/Sources/MOSSCaptureCore/*.swift \
  "$scratch/main.swift" \
  -o "$scratch/probe"
"$scratch/probe"
