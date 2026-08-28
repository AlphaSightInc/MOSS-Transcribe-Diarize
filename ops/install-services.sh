#!/usr/bin/env bash
# Install the single Account web unit and its vLLM dependency. This never restarts an
# already-running unit; deploying a changed candidate remains an attended cutover action.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/moss-ops-lib.sh"
UNITS="moss-vllm.service moss-web.service"

usage() { printf 'usage: install-services.sh [--dry-run]
'; }
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) MOSS_TOOL_DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
  shift
done

require_cmd systemctl install getent cmp stat readlink
LINUX_USER_DIR="$(getent passwd "$(id -un)" | cut -d: -f6)"
UNIT_DIR="${LINUX_USER_DIR}/.config/systemd/user"
CONFIG_DIR="${LINUX_USER_DIR}/.config/moss-transcribe-diarize"
ACCOUNT_PROFILE="${CONFIG_DIR}/moss-account.env"
VLLM_PROFILE="${CONFIG_DIR}/vllm.env"
ACCOUNT_CURRENT="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/account-current"

for profile in "${ACCOUNT_PROFILE}" "${VLLM_PROFILE}"; do
  [ -f "${profile}" ] || die "required ext4 service profile is missing: ${profile}"
  [ "$(stat -c '%a' "${profile}")" = "600" ] || die "service profile must be mode 0600: ${profile}"
done
[ -L "${ACCOUNT_CURRENT}" ] || die "reviewed Account release is not activated: ${ACCOUNT_CURRENT}"
ACTIVE_RELEASE="$(readlink -f "${ACCOUNT_CURRENT}")"
for launcher in mtd-account-web mtd-admin mtd-vllm; do
  [ -x "${ACTIVE_RELEASE}/bin/${launcher}" ] || die "active release launcher is missing: ${launcher}"
done

stamp="$(utc_stamp)"
changing=""
for unit in ${UNITS}; do
  source_unit="${SCRIPT_DIR}/systemd/${unit}"
  target_unit="${UNIT_DIR}/${unit}"
  [ -f "${source_unit}" ] || die "tracked unit is missing: ${source_unit}"
  if [ -f "${target_unit}" ] && cmp -s "${source_unit}" "${target_unit}"; then
    unchanged "${unit} already matches the tracked unit"
  else
    changing="${changing} ${unit}"
    plan "install ${source_unit} to ${target_unit}"
    if [ -f "${target_unit}" ]; then
      rollback "mv '${target_unit}.backup-${stamp}' '${target_unit}' && systemctl --user daemon-reload"
    else
      rollback "rm -f '${target_unit}' && systemctl --user daemon-reload"
    fi
  fi
done
plan "systemctl --user daemon-reload"
plan "systemctl --user enable ${UNITS}"
plan "systemctl --user start ${UNITS}"
evidence unit_dir "${UNIT_DIR}"
evidence active_release "${ACTIVE_RELEASE}"
evidence web_listener "tls:7861"
evidence restart_required "$( [ -n "${changing}" ] && echo "${changing}" || echo none )"
dry_run && exit 0

mkdir -p "${UNIT_DIR}"
for unit in ${changing}; do
  source_unit="${SCRIPT_DIR}/systemd/${unit}"
  target_unit="${UNIT_DIR}/${unit}"
  if [ -f "${target_unit}" ]; then
    mv "${target_unit}" "${target_unit}.backup-${stamp}"
  fi
  install -m 0644 "${source_unit}" "${target_unit}"
done
systemctl --user daemon-reload
systemctl --user enable ${UNITS}
systemctl --user start ${UNITS}
echo "Installed MOSS Account product services."
