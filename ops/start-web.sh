#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/mnt/d/Coding/MOSS-Transcribe-Diarize"
LINUX_USER_DIR="$(getent passwd "$(id -un)" | cut -d: -f6)"
VENV_DIR="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/venv"
MODEL_DIR="${LINUX_USER_DIR}/.local/share/moss-transcribe-diarize/model"

# One adapter, two services. The batch service keeps the plaintext contract port and the
# repository runs directory; the live service is the same script under a second unit that
# loads the live profile and overrides both. `--live` hands the certificate to uvicorn, so
# TLS covers the *whole* listener (`web_cli.main`): a live profile served on the batch port
# would replace the plaintext batch surface rather than sit beside it.
BATCH_PORT=7860
BATCH_RUNS_DIR="${PROJECT_DIR}/runs"

# `${VAR-default}`, not `${VAR:-default}`: a variable a profile sets to nothing is a typo in
# that profile, not a request for the default, and it must be refused rather than absorbed.
web_port="${MOSS_WEB_PORT-${BATCH_PORT}}"
runs_dir="${MOSS_RUNS_DIR-${BATCH_RUNS_DIR}}"

case "${web_port}" in
  "" | *[!0-9]*)
    echo "MOSS_WEB_PORT must be a decimal port number, got '${web_port}'" >&2
    exit 2
    ;;
esac
if [ "${#web_port}" -gt 5 ] || [ "${web_port}" -lt 1 ] || [ "${web_port}" -gt 65535 ]; then
  echo "MOSS_WEB_PORT must be between 1 and 65535, got '${web_port}'" >&2
  exit 2
fi
if [ -z "${runs_dir}" ]; then
  echo "MOSS_RUNS_DIR must not be empty" >&2
  exit 2
fi

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

live_args=()
case "${MOSS_LIVE_ENABLED:-0}" in
  0) ;;
  1)
    : "${MOSS_LIVE_PROVIDER_MANIFEST:?MOSS_LIVE_PROVIDER_MANIFEST is required when live mode is enabled}"
    : "${MOSS_LIVE_AUTH_STATE:?MOSS_LIVE_AUTH_STATE is required when live mode is enabled}"
    : "${MOSS_LIVE_TLS_CERTFILE:?MOSS_LIVE_TLS_CERTFILE is required when live mode is enabled}"
    : "${MOSS_LIVE_TLS_KEYFILE:?MOSS_LIVE_TLS_KEYFILE is required when live mode is enabled}"
    : "${MOSS_LIVE_HELPER_LEASE_SECONDS:?MOSS_LIVE_HELPER_LEASE_SECONDS is required when live mode is enabled}"
    : "${MOSS_WEB_PORT:?MOSS_WEB_PORT is required when live mode is enabled}"
    : "${MOSS_RUNS_DIR:?MOSS_RUNS_DIR is required when live mode is enabled}"
    if [ "${web_port}" = "${BATCH_PORT}" ]; then
      echo "MOSS_WEB_PORT must not be the plaintext batch port ${BATCH_PORT} when live mode is enabled: --live puts TLS on the whole listener" >&2
      exit 2
    fi
    if [ "${runs_dir}" = "${BATCH_RUNS_DIR}" ]; then
      echo "MOSS_RUNS_DIR must not be the batch runs directory ${BATCH_RUNS_DIR} when live mode is enabled" >&2
      exit 2
    fi
    live_args+=(
      --live
      --live-provider-manifest "${MOSS_LIVE_PROVIDER_MANIFEST}"
      --live-auth-state "${MOSS_LIVE_AUTH_STATE}"
      --live-tls-certfile "${MOSS_LIVE_TLS_CERTFILE}"
      --live-tls-keyfile "${MOSS_LIVE_TLS_KEYFILE}"
      --live-helper-lease-seconds "${MOSS_LIVE_HELPER_LEASE_SECONDS}"
    )
    ;;
  *)
    echo "MOSS_LIVE_ENABLED must be 0 or 1" >&2
    exit 2
    ;;
esac

web_args=(
  --backend vllm \
  --model "${MODEL_DIR}" \
  --vllm-base-url http://127.0.0.1:8000/v1 \
  --vllm-model OpenMOSS-Team/MOSS-Transcribe-Diarize \
  --vllm-timeout 1800 \
  --runs-dir "${runs_dir}" \
  --host 0.0.0.0 \
  --port "${web_port}" \
  --max-len "${MOSS_MAX_MODEL_LEN:-16384}" \
  --max-new-tokens "${MOSS_MAX_NEW_TOKENS:-12000}"
)
if ((${#speaker_identity_args[@]})); then
  web_args+=("${speaker_identity_args[@]}")
fi
if ((${#live_args[@]})); then
  web_args+=("${live_args[@]}")
fi

exec "${VENV_DIR}/bin/mtd-subtitle-web" "${web_args[@]}"
