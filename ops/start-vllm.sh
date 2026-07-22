#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/mnt/d/Coding/MOSS-Transcribe-Diarize"
LINUX_USER_DIR="$(getent passwd "$(id -un)" | cut -d: -f6)"
VENV_DIR="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/venv"
MODEL_DIR="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/model"
CUDA_HOME="${VENV_DIR}/lib/python3.12/site-packages/nvidia/cu13"

export HF_HOME="${LINUX_USER_DIR}/.cache/huggingface"
export TOKENIZERS_PARALLELISM="false"
export CUDA_HOME
export PATH="${VENV_DIR}/bin:${CUDA_HOME}/bin:${PATH}"
export LD_LIBRARY_PATH="${CUDA_HOME}/lib:${LD_LIBRARY_PATH:-}"
# vLLM's V2 runner requires CUDA UVA, which NVIDIA does not expose in WSL.
export VLLM_USE_V2_MODEL_RUNNER="0"
# Avoid FlashInfer's sampling JIT: its bundled CUDA headers do not match the
# cu130 compiler package in the pinned vLLM wheel. PyTorch sampling is sufficient
# for this model's deterministic transcription requests.
export VLLM_USE_FLASHINFER_SAMPLER="0"

exec "${VENV_DIR}/bin/vllm" serve "${MODEL_DIR}" \
  --served-model-name "OpenMOSS-Team/MOSS-Transcribe-Diarize" \
  --trust-remote-code \
  --host 127.0.0.1 \
  --port 8000 \
  --dtype bfloat16 \
  --no-async-scheduling \
  --gpu-memory-utilization "${MOSS_GPU_MEMORY_UTILIZATION:-0.38}" \
  --max-model-len "${MOSS_MAX_MODEL_LEN:-16384}" \
  --max-num-seqs "${MOSS_MAX_NUM_SEQS:-2}"
