#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/mnt/d/Coding/MOSS-Transcribe-Diarize"
LINUX_USER_DIR="$(getent passwd "$(id -un)" | cut -d: -f6)"
VENV_DIR="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/venv"
MODEL_ID="OpenMOSS-Team/MOSS-Transcribe-Diarize"
MODEL_DIR="${PROJECT_DIR}/pretrained/moss-transcribe-diarize"
RUNTIME_MODEL_DIR="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/model"

mkdir -p "${MODEL_DIR}"
"${VENV_DIR}/bin/hf" download "${MODEL_ID}" --local-dir "${MODEL_DIR}"
mkdir -p "${RUNTIME_MODEL_DIR}"
cp -a "${MODEL_DIR}/." "${RUNTIME_MODEL_DIR}/"

echo "Model ready: ${MODEL_DIR}"
echo "Runtime copy ready: ${RUNTIME_MODEL_DIR}"
