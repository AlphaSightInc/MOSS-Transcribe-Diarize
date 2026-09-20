#!/bin/sh
set -eu
set +x

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
PYTHON_BIN=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
KEY_FILE=${HOME}/.config/moss/openrouter.env
APP_PORT=18442
PROVIDER_PORT=18443
EVIDENCE_DIR=$REPO_ROOT/evidence/round4/surfaces
RUN_DIR=$(mktemp -d /private/tmp/moss-r4-summaries.XXXXXX)
SERVER_PID=

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$RUN_DIR"
}
trap cleanup EXIT INT TERM

test -f "$KEY_FILE"
set -a
. "$KEY_FILE"
set +a
mkdir -p "$EVIDENCE_DIR"

openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=localhost \
  -addext subjectAltName=IP:127.0.0.1,DNS:localhost \
  -keyout "$RUN_DIR/key.pem" -out "$RUN_DIR/cert.pem" >/dev/null 2>&1

sandbox-exec -f "$REPO_ROOT/prototypes/surfaces/loopback.sb" \
  env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PYTHON_BIN" \
  "$REPO_ROOT/prototypes/surfaces/summary_fixture.py" \
  --state "$RUN_DIR/state" --app-port "$APP_PORT" --provider-port "$PROVIDER_PORT" \
  --cert "$RUN_DIR/cert.pem" --key "$RUN_DIR/key.pem" \
  --receipt "$EVIDENCE_DIR/provider-requests.jsonl" --ready "$RUN_DIR/ready.json" \
  >"$EVIDENCE_DIR/summary-fixture.log" 2>&1 &
SERVER_PID=$!

attempt=0
while [ ! -s "$RUN_DIR/ready.json" ]; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 300 ] || ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "local fixture failed readiness" >&2
    exit 1
  fi
  sleep 0.1
done

sandbox-exec -f "$REPO_ROOT/prototypes/surfaces/loopback.sb" \
  env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PYTHON_BIN" \
  "$REPO_ROOT/prototypes/browser-stress/run.py" 13 \
  --base "https://127.0.0.1:$APP_PORT" --output "$RUN_DIR/case-13" \
  >"$EVIDENCE_DIR/case-13.log" 2>&1
cp "$RUN_DIR/case-13/campaign-results.json" "$EVIDENCE_DIR/case-13-results.json"

sandbox-exec -f "$REPO_ROOT/prototypes/surfaces/loopback.sb" \
  env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_BASE="https://127.0.0.1:$APP_PORT" \
  MOSS_SUMMARY_PROVIDERS=external MOSS_SUMMARY_ENDPOINT="https://127.0.0.1:$PROVIDER_PORT/v1" \
  MOSS_SUMMARY_MODEL=fixture-pass TRIALS=1 "$PYTHON_BIN" tests/e2e/verify_summaries.py \
  >"$EVIDENCE_DIR/summaries-exit-0.log" 2>&1

set +e
sandbox-exec -f "$REPO_ROOT/prototypes/surfaces/loopback.sb" \
  env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_BASE="https://127.0.0.1:$APP_PORT" \
  MOSS_SUMMARY_PROVIDERS=external MOSS_SUMMARY_ENDPOINT="https://127.0.0.1:$PROVIDER_PORT/v1" \
  MOSS_SUMMARY_MODEL=fixture-one-fail TRIALS=1 "$PYTHON_BIN" tests/e2e/verify_summaries.py \
  >"$EVIDENCE_DIR/summaries-exit-1.log" 2>&1
FAILED_EXIT=$?

sandbox-exec -f "$REPO_ROOT/prototypes/surfaces/loopback.sb" \
  env -u OPENROUTER_API_KEY -u MOSS_DEMO_OPENROUTER_API_KEY \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_BASE="https://127.0.0.1:$APP_PORT" \
  MOSS_SUMMARY_PROVIDERS=external "$PYTHON_BIN" tests/e2e/verify_summaries.py \
  >"$EVIDENCE_DIR/summaries-exit-77.log" 2>&1
UNCONFIGURED_EXIT=$?
set -e

test "$FAILED_EXIT" -eq 1
test "$UNCONFIGURED_EXIT" -eq 77
"$PYTHON_BIN" - "$EVIDENCE_DIR/case-13-results.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1]))["13"]
assert result["status"] == "PASS" and result["provider_posts"] == 0, result
print("case13 provider POSTs: 0")
PY
printf 'verify_summaries exits: 0, %s, %s\n' "$FAILED_EXIT" "$UNCONFIGURED_EXIT"
