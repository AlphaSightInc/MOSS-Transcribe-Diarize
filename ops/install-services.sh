#!/usr/bin/env bash
# Install the tracked systemd user units for this checkout.
#
# Default: exactly the two batch units this script has always installed. `--with-live` adds
# the second web service (TLS, live profile) as a separate unit; it is never enabled or
# started implicitly, because enabling it is a reviewed deployment step and the batch service
# on the plaintext contract port must keep running untouched either way.
#
# Output follows `moss-ops-lib.sh`: `plan:` / `rollback:` / `change:` / `unchanged:` /
# `evidence:`, with every `rollback:` line printed before the first mutation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
# shellcheck source=ops/moss-ops-lib.sh
. "${SCRIPT_DIR}/moss-ops-lib.sh"

BATCH_UNITS="moss-vllm.service moss-web.service"
LIVE_UNIT="moss-live-web.service"
LIVE_ENV="${SCRIPT_DIR}/moss-live.env"
LIVE_ENV_EXAMPLE="${SCRIPT_DIR}/moss-live.env.example"

usage() {
    cat <<'USAGE'
usage: install-services.sh [--with-live] [--dry-run]

  --with-live   also install, enable and start the live web unit (TLS). Requires
                ops/moss-live.env to exist; copy ops/moss-live.env.example and fill it in.
  --dry-run     print the ordered plan and the rollback command, mutate nothing.
USAGE
}

with_live=0
while [ $# -gt 0 ]; do
    case "$1" in
        --with-live) with_live=1 ;;
        --dry-run) MOSS_TOOL_DRY_RUN=1 ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            die "unknown argument: $1"
            ;;
    esac
    shift
done

require_cmd systemctl install getent cmp

LINUX_USER_DIR="$(getent passwd "$(id -un)" | cut -d: -f6)"
[ -n "${LINUX_USER_DIR}" ] || die "could not resolve the home directory of $(id -un)"
UNIT_DIR="${LINUX_USER_DIR}/.config/systemd/user"

units="${BATCH_UNITS}"
if [ "${with_live}" = "1" ]; then
    # The live unit's EnvironmentFile is required, so a unit installed without its profile
    # would fail at start. Refuse before touching anything instead.
    [ -f "${LIVE_ENV}" ] ||
        die "--with-live needs ${LIVE_ENV}; copy ${LIVE_ENV_EXAMPLE} and replace every REPLACE_WITH_ path"
    units="${units} ${LIVE_UNIT}"
fi

for unit in ${units}; do
    [ -f "${SCRIPT_DIR}/systemd/${unit}" ] || die "tracked unit is missing: ${SCRIPT_DIR}/systemd/${unit}"
done

stamp="$(utc_stamp)"
changing=""
for unit in ${units}; do
    source_unit="${SCRIPT_DIR}/systemd/${unit}"
    target_unit="${UNIT_DIR}/${unit}"
    if [ -f "${target_unit}" ] && cmp -s "${source_unit}" "${target_unit}"; then
        unchanged "${unit} already matches the tracked unit"
        continue
    fi
    changing="${changing} ${unit}"
    if [ -f "${target_unit}" ]; then
        plan "back up ${target_unit} to ${target_unit}.backup-${stamp}"
        plan "install ${source_unit} to ${target_unit}"
    else
        plan "install ${source_unit} to ${target_unit}"
    fi
done

# `enable` and `start` are no-ops on a unit that is already enabled and running, so the batch
# pair stays unconditional exactly as it has always been. The live unit is asked first: its
# activation is the mutation the operator has to be able to undo, so a re-run must be able to
# say it changed nothing.
activate_live=0
if [ "${with_live}" = "1" ]; then
    if systemctl --user is-enabled "${LIVE_UNIT}" >/dev/null 2>&1 &&
        systemctl --user is-active "${LIVE_UNIT}" >/dev/null 2>&1; then
        unchanged "${LIVE_UNIT} is already enabled and running"
    else
        activate_live=1
    fi
fi

plan "systemctl --user daemon-reload"
plan "systemctl --user enable ${BATCH_UNITS}"
plan "systemctl --user start ${BATCH_UNITS}"
if [ "${activate_live}" = "1" ]; then
    plan "systemctl --user enable ${LIVE_UNIT}"
    plan "systemctl --user start ${LIVE_UNIT}"
fi

for unit in ${changing}; do
    target_unit="${UNIT_DIR}/${unit}"
    if [ -f "${target_unit}" ]; then
        rollback "mv '${target_unit}.backup-${stamp}' '${target_unit}' && systemctl --user daemon-reload"
    else
        rollback "rm -f '${target_unit}' && systemctl --user daemon-reload"
    fi
done
if [ "${activate_live}" = "1" ]; then
    rollback "systemctl --user disable --now ${LIVE_UNIT}"
fi

evidence project_dir "${PROJECT_DIR}"
evidence unit_dir "${UNIT_DIR}"
evidence live_unit_installed "${with_live}"
# A changed unit file does not reach a running service until it is restarted, and restarting
# is a deployment decision: this tool never bounces a service that is already up.
if [ -n "${changing}" ]; then
    evidence restart_required "$(echo ${changing})"
else
    evidence restart_required none
fi

if dry_run; then
    exit 0
fi

mkdir -p "${UNIT_DIR}"
for unit in ${changing}; do
    source_unit="${SCRIPT_DIR}/systemd/${unit}"
    target_unit="${UNIT_DIR}/${unit}"
    if [ -f "${target_unit}" ]; then
        mv "${target_unit}" "${target_unit}.backup-${stamp}"
        change "backed up the previous ${unit} to ${target_unit}.backup-${stamp}"
    fi
    install -m 0644 "${source_unit}" "${target_unit}"
    change "installed ${unit} to ${target_unit}"
done

systemctl --user daemon-reload
# `enable` and `start` on an already-running unit are no-ops, so a live-only install leaves
# the batch service exactly as it was.
systemctl --user enable ${BATCH_UNITS}
systemctl --user start ${BATCH_UNITS}
if [ "${activate_live}" = "1" ]; then
    systemctl --user enable "${LIVE_UNIT}"
    systemctl --user start "${LIVE_UNIT}"
    change "enabled and started ${LIVE_UNIT}"
fi

echo "Installed and started MOSS user services."
