#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/mnt/d/Coding/MOSS-Transcribe-Diarize"
LINUX_USER_DIR="$(getent passwd "$(id -un)" | cut -d: -f6)"
VENV_DIR="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/venv"
MODEL_DIR="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/model"

speaker_identity_args=()
case "${MOSS_SPEAKER_IDENTITY_TIER_B:-0}" in
  0) ;;
  1)
    : "${MOSS_SPEAKER_IDENTITY_STATE:?MOSS_SPEAKER_IDENTITY_STATE is required when Tier B is enabled}"
    : "${MOSS_SPEAKER_IDENTITY_FIXTURE:?MOSS_SPEAKER_IDENTITY_FIXTURE is required when Tier B is enabled}"
    speaker_identity_args+=(
      --speaker-identity-tier-b
      --speaker-identity-state "${MOSS_SPEAKER_IDENTITY_STATE}"
      --speaker-identity-fixture "${MOSS_SPEAKER_IDENTITY_FIXTURE}"
    )
    ;;
  *)
    echo "MOSS_SPEAKER_IDENTITY_TIER_B must be 0 or 1" >&2
    exit 2
    ;;
esac

web_args=(
  --backend vllm \
  --model "${MODEL_DIR}" \
  --vllm-base-url http://127.0.0.1:8000/v1 \
  --vllm-model OpenMOSS-Team/MOSS-Transcribe-Diarize \
  --vllm-timeout 1800 \
  --runs-dir "${PROJECT_DIR}/runs" \
  --host 0.0.0.0 \
  --port 7860 \
  --max-len "${MOSS_MAX_MODEL_LEN:-16384}" \
  --max-new-tokens "${MOSS_MAX_NEW_TOKENS:-12000}"
)
if ((${#speaker_identity_args[@]})); then
  web_args+=("${speaker_identity_args[@]}")
fi

exec "${VENV_DIR}/bin/mtd-subtitle-web" "${web_args[@]}"
