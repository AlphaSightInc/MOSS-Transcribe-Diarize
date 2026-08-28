#!/usr/bin/env bash
# Relocatable, release-owned Account web launcher. The systemd unit supplies the 0600 host profile.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
RUNTIME_DIR="$(cd "${SELF_DIR}/.." && pwd)"
SQLITE_PREFIX="${HOME}/.local/share/moss-transcribe-diarize/sqlite-3.53.4"
MODEL_DIR="${HOME}/.local/share/moss-transcribe-diarize/model"

required=(
  MOSS_GOOGLE_CLIENT_ID MOSS_GOOGLE_CLIENT_SECRET_FILE MOSS_OAUTH_COOKIE_SECRET_FILE
  MOSS_TLS_CERTFILE MOSS_TLS_KEYFILE MOSS_LIVE_PROVIDER_MANIFEST
  MOSS_LIVE_HELPER_LEASE_SECONDS MOSS_PHASE2_DATABASE MOSS_PHASE2_CONTROL_SOCKET
  MOSS_FILE_WORK_ROOT MOSS_MEETING_AUDIO_ROOT
)
for name in "${required[@]}"; do
  [ -n "${!name-}" ] || { echo "${name} is required" >&2; exit 2; }
done
[ -f "${SQLITE_PREFIX}/lib/libsqlite3.so" ] || {
  echo "SQLite 3.53.4 runtime is missing: ${SQLITE_PREFIX}" >&2
  exit 2
}

export LD_LIBRARY_PATH="${SQLITE_PREFIX}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
exec "${RUNTIME_DIR}/bin/python" -m moss_transcribe_diarize.app.phase2_web_cli \
  --database "${MOSS_PHASE2_DATABASE}" \
  --control-socket "${MOSS_PHASE2_CONTROL_SOCKET}" \
  --google-client-id "${MOSS_GOOGLE_CLIENT_ID}" \
  --google-client-secret-file "${MOSS_GOOGLE_CLIENT_SECRET_FILE}" \
  --oauth-cookie-secret-file "${MOSS_OAUTH_COOKIE_SECRET_FILE}" \
  --tls-certfile "${MOSS_TLS_CERTFILE}" \
  --tls-keyfile "${MOSS_TLS_KEYFILE}" \
  --backend vllm \
  --model "${MODEL_DIR}" \
  --vllm-base-url http://127.0.0.1:8000/v1 \
  --vllm-model OpenMOSS-Team/MOSS-Transcribe-Diarize \
  --vllm-timeout 1800 \
  --file-work-root "${MOSS_FILE_WORK_ROOT}" \
  --meeting-audio-root "${MOSS_MEETING_AUDIO_ROOT}" \
  --live-provider-manifest "${MOSS_LIVE_PROVIDER_MANIFEST}" \
  --live-helper-lease-seconds "${MOSS_LIVE_HELPER_LEASE_SECONDS}" \
  --host 0.0.0.0 \
  --port 7861 \
  --max-len "${MOSS_MAX_MODEL_LEN:-16384}" \
  --max-new-tokens "${MOSS_MAX_NEW_TOKENS:-12000}"
