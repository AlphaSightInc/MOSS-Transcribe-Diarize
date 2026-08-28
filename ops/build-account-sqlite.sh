#!/usr/bin/env bash
# Build the one SQLite library admitted to the Account web process. The vLLM process does not load it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/moss-ops-lib.sh"

SQLITE_VERSION=3.53.4
SQLITE_ARCHIVE=sqlite-autoconf-3530400.tar.gz
SQLITE_URL="https://www.sqlite.org/2026/${SQLITE_ARCHIVE}"
SQLITE_SHA3_256=454e45f61c6bd75b7420e7190732dea03ce6639c63ada47bbc592f67fc340338
LINUX_USER_DIR="$(getent passwd "$(id -un)" | cut -d: -f6)"
RUNTIME_ROOT="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize"
SQLITE_PREFIX="${RUNTIME_ROOT}/sqlite-${SQLITE_VERSION}"
BUILD_ROOT=""

cleanup_build_root() {
  local status=$?
  [ -z "${BUILD_ROOT}" ] || rm -rf -- "${BUILD_ROOT}"
  exit "${status}"
}
trap cleanup_build_root EXIT

usage() { printf 'usage: build-account-sqlite.sh [--dry-run]\n'; }
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) MOSS_TOOL_DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
  shift
done

require_cmd /usr/bin/python3.12 curl tar make cc getent

exact_runtime() {
  local prefix="$1"
  [ -f "${prefix}/lib/libsqlite3.so" ] &&
    LD_LIBRARY_PATH="${prefix}/lib" /usr/bin/python3.12 -c \
      'import sqlite3,sys; sys.exit(0 if sqlite3.sqlite_version == "3.53.4" else 1)'
}

if exact_runtime "${SQLITE_PREFIX}"; then
  unchanged "SQLite ${SQLITE_VERSION} Account runtime already verified"
  evidence sqlite_runtime "${SQLITE_VERSION}"
  evidence sqlite_prefix "${SQLITE_PREFIX}"
  exit 0
fi
[ ! -e "${SQLITE_PREFIX}" ] || die "existing SQLite prefix is not the accepted runtime: ${SQLITE_PREFIX}"

plan "download pinned ${SQLITE_URL}"
plan "verify SHA3-256 ${SQLITE_SHA3_256}"
plan "build shared SQLite only under ${SQLITE_PREFIX}"
rollback "leave the additive build inert; moss-web continues to use its prior runtime"
evidence sqlite_runtime "${SQLITE_VERSION}"
evidence sqlite_prefix "${SQLITE_PREFIX}"
dry_run && exit 0

mkdir -p "${RUNTIME_ROOT}"
BUILD_ROOT="$(mktemp -d "${RUNTIME_ROOT}/.sqlite-${SQLITE_VERSION}-build.XXXXXX")"
ARCHIVE_PATH="${BUILD_ROOT}/${SQLITE_ARCHIVE}"
INSTALL_PREFIX="${BUILD_ROOT}/verified-prefix"
curl -fsSLo "${ARCHIVE_PATH}" "${SQLITE_URL}"
/usr/bin/python3.12 - "${ARCHIVE_PATH}" "${SQLITE_SHA3_256}" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
actual = hashlib.sha3_256(path.read_bytes()).hexdigest()
if actual != sys.argv[2]:
    raise SystemExit(f"SQLite source SHA3-256 mismatch: {actual}")
PY
tar -xzf "${ARCHIVE_PATH}" -C "${BUILD_ROOT}"
(
  cd "${BUILD_ROOT}/sqlite-autoconf-3530400"
  ./configure --prefix="${INSTALL_PREFIX}" --disable-static --enable-shared
  make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
  make install
)
exact_runtime "${INSTALL_PREFIX}" || die "built Account SQLite runtime did not report ${SQLITE_VERSION}"
mv "${INSTALL_PREFIX}" "${SQLITE_PREFIX}"
change "installed exact Account SQLite runtime"
