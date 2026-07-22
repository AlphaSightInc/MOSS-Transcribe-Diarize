#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/mnt/d/Coding/MOSS-Transcribe-Diarize"
LINUX_USER_DIR="$(getent passwd "$(id -un)" | cut -d: -f6)"
VENV_DIR="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/venv"
MODEL_DIR="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/model"

exec "${VENV_DIR}/bin/mtd-subtitle-web" \
  --backend vllm \
  --model "${MODEL_DIR}" \
  --vllm-base-url http://127.0.0.1:8000/v1 \
  --vllm-model OpenMOSS-Team/MOSS-Transcribe-Diarize \
  --vllm-timeout 1800 \
  --runs-dir "${PROJECT_DIR}/runs" \
  --host 0.0.0.0 \
  --port 7860 \
  --max-new-tokens "${MOSS_MAX_NEW_TOKENS:-12000}"
