#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/mnt/d/Coding/MOSS-Transcribe-Diarize"
LINUX_USER_DIR="$(getent passwd "$(id -un)" | cut -d: -f6)"
VENV_DIR="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/venv"
MODEL_DIR="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/model"

required=(
  MOSS_GOOGLE_CLIENT_ID MOSS_GOOGLE_CLIENT_SECRET_FILE MOSS_OAUTH_COOKIE_SECRET_FILE
  MOSS_TLS_CERTFILE MOSS_TLS_KEYFILE MOSS_LIVE_PROVIDER_MANIFEST
  MOSS_LIVE_HELPER_LEASE_SECONDS MOSS_PHASE2_DATABASE MOSS_PHASE2_CONTROL_SOCKET
  MOSS_FILE_WORK_ROOT MOSS_MEETING_AUDIO_ROOT
)
for name in "${required[@]}"; do
  [ -n "${!name-}" ] || { echo "${name} is required" >&2; exit 2; }
done

exec "${VENV_DIR}/bin/mtd-phase2-web"   --database "${MOSS_PHASE2_DATABASE}"   --control-socket "${MOSS_PHASE2_CONTROL_SOCKET}"   --google-client-id "${MOSS_GOOGLE_CLIENT_ID}"   --google-client-secret-file "${MOSS_GOOGLE_CLIENT_SECRET_FILE}"   --oauth-cookie-secret-file "${MOSS_OAUTH_COOKIE_SECRET_FILE}"   --tls-certfile "${MOSS_TLS_CERTFILE}"   --tls-keyfile "${MOSS_TLS_KEYFILE}"   --backend vllm   --model "${MODEL_DIR}"   --vllm-base-url http://127.0.0.1:8000/v1   --vllm-model OpenMOSS-Team/MOSS-Transcribe-Diarize   --vllm-timeout 1800   --file-work-root "${MOSS_FILE_WORK_ROOT}"   --meeting-audio-root "${MOSS_MEETING_AUDIO_ROOT}"   --live-provider-manifest "${MOSS_LIVE_PROVIDER_MANIFEST}"   --live-helper-lease-seconds "${MOSS_LIVE_HELPER_LEASE_SECONDS}"   --host 0.0.0.0   --port 7861   --max-len "${MOSS_MAX_MODEL_LEN:-16384}"   --max-new-tokens "${MOSS_MAX_NEW_TOKENS:-12000}"
