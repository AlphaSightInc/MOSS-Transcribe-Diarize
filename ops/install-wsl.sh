#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/mnt/d/Coding/MOSS-Transcribe-Diarize"
LINUX_USER="$(id -un)"
LINUX_USER_DIR="$(getent passwd "${LINUX_USER}" | cut -d: -f6)"
UV_DIR="${LINUX_USER_DIR}/.local/bin"
UV_BIN="${UV_DIR}/uv"
VENV_DIR="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/venv"
VLLM_WHEEL_INDEX="https://wheels.vllm.ai/68b4a1d582818e67adc903bf1b8fc5a5447da2fa/cu130"

mkdir -p "${UV_DIR}" "$(dirname "${VENV_DIR}")"

if [[ ! -x "${UV_BIN}" ]]; then
  echo "Installing uv for ${LINUX_USER}..."
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="${UV_DIR}" sh
fi

echo "Installing uv-managed Python 3.12..."
"${UV_BIN}" python install 3.12

echo "Creating the isolated Python environment..."
"${UV_BIN}" venv --python 3.12 --managed-python --seed "${VENV_DIR}"

echo "Installing the pinned vLLM backend and project..."
"${UV_BIN}" pip install \
  --python "${VENV_DIR}/bin/python" \
  --upgrade vllm \
  --torch-backend=auto \
  --extra-index-url "${VLLM_WHEEL_INDEX}"
"${UV_BIN}" pip install \
  --python "${VENV_DIR}/bin/python" \
  --editable "${PROJECT_DIR}"
"${UV_BIN}" pip install \
  --python "${VENV_DIR}/bin/python" \
  pytest ninja

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Installing FFmpeg for video/subtitle support..."
  sudo -n apt-get update
  sudo -n apt-get install -y ffmpeg
fi

echo "Environment ready: ${VENV_DIR}"
"${VENV_DIR}/bin/python" --version
"${UV_BIN}" --version
