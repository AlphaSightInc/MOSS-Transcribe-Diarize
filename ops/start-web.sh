#!/usr/bin/env bash
set -euo pipefail

LINUX_USER_DIR="$(getent passwd "$(id -un)" | cut -d: -f6)"
ACCOUNT_CURRENT="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/account-current"
[ -x "${ACCOUNT_CURRENT}/bin/mtd-account-web" ] || {
  echo "activated Account runtime is missing: ${ACCOUNT_CURRENT}" >&2
  exit 2
}
exec "${ACCOUNT_CURRENT}/bin/mtd-account-web"
