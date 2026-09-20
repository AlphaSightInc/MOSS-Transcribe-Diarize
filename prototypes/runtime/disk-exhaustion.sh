#!/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PYTHON=/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python
SCRATCH=$(mktemp -d /private/tmp/moss-r4-enospc.XXXXXX)
IMAGE="$SCRATCH/runtime.sparsebundle"
MOUNT="$SCRATCH/mount"
mkdir -p "$MOUNT" "$ROOT/evidence/round4/runtime"
mounted=0
cleanup() {
  if [ "$mounted" -eq 1 ]; then
    hdiutil detach "$MOUNT" >/dev/null
  fi
}
trap cleanup EXIT
hdiutil create -size 640m -fs APFS -volname MOSS_R4_RUNTIME -type SPARSEBUNDLE "$IMAGE" >/dev/null
hdiutil attach -nobrowse -mountpoint "$MOUNT" "$IMAGE" >/dev/null
mounted=1
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT" "$PYTHON" \
  "$ROOT/prototypes/runtime/disk_exhaustion.py" "$MOUNT" \
  | tee "$ROOT/evidence/round4/runtime/disk-exhaustion.json"
hdiutil detach "$MOUNT" >/dev/null
mounted=0
if mount | /usr/bin/grep -F "$MOUNT" >/dev/null; then
  echo "disposable image is still mounted" >&2
  exit 1
fi
