#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/mnt/d/Coding/MOSS-Transcribe-Diarize"
LINUX_USER_DIR="$(getent passwd "$(id -un)" | cut -d: -f6)"
UNIT_DIR="${LINUX_USER_DIR}/.config/systemd/user"

mkdir -p "${UNIT_DIR}"
install -m 0644 "${PROJECT_DIR}/ops/systemd/moss-vllm.service" "${UNIT_DIR}/moss-vllm.service"
install -m 0644 "${PROJECT_DIR}/ops/systemd/moss-web.service" "${UNIT_DIR}/moss-web.service"

systemctl --user daemon-reload
systemctl --user enable moss-vllm.service moss-web.service
systemctl --user start moss-vllm.service moss-web.service

echo "Installed and started MOSS user services."

