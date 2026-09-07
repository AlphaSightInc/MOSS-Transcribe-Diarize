#!/usr/bin/env bash
# Qualification tooling only; never replace the host's system Node or live services.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/moss-ops-lib.sh"
require_cmd curl tar getent
LINUX_USER_DIR="$(getent passwd "$(id -un)" | cut -d: -f6)"
RUNTIME_ROOT="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize"
NODE_DIST=node-v24.20.0-linux-x64
NODE_PREFIX="${RUNTIME_ROOT}/${NODE_DIST}"
if [ -x "${NODE_PREFIX}/bin/node" ]; then
  [ "$("${NODE_PREFIX}/bin/node" --version)" = v24.20.0 ] || die "wrong qualification Node runtime"
  exit 0
fi
[ ! -e "${NODE_PREFIX}" ] || die "incomplete qualification Node runtime"
mkdir -p "${RUNTIME_ROOT}"
NODE_STAGE="$(mktemp -d "${RUNTIME_ROOT}/.node-stage.XXXXXX")"
cleanup_node_stage() { rm -rf -- "${NODE_STAGE}"; }
trap cleanup_node_stage EXIT
curl -fsSLo "${NODE_STAGE}/node.tar.xz" "https://nodejs.org/dist/v24.20.0/${NODE_DIST}.tar.xz"
tar -xJf "${NODE_STAGE}/node.tar.xz" -C "${NODE_STAGE}"
[ "$("${NODE_STAGE}/${NODE_DIST}/bin/node" --version)" = v24.20.0 ] || die "qualification Node did not execute"
mv "${NODE_STAGE}/${NODE_DIST}" "${NODE_PREFIX}"
chmod -R a-w "${NODE_PREFIX}"
