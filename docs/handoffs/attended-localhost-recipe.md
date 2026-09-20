# Attended localhost recipe — MacStudio to m4mbp

**Outcome:** serve the frozen round-4 candidate only on MacStudio loopback, forward it
to m4mbp loopback, and use plain `http://localhost`. Browsers treat localhost as a
secure context, so microphone capture and voiceprints need neither TLS nor deployment.

## 1. Preconditions and mute check

On both Macs: mute built-in speakers and displays. Connect headphones to m4mbp; keep
MacStudio output muted. Do not start capture until the operator confirms the route.

On MacStudio, use the supported Python receipt from R4-7. The current Homebrew Python
reports SQLite 3.53.0 and is not acceptable; the candidate requires exactly 3.53.4.

```sh
cd /Users/gao/Documents/Codex/2026-09-20/moss-round4/candidate
git status --short --branch
git rev-parse HEAD

R4_PYTHON=/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python
"$R4_PYTHON" -c 'import sqlite3; print(sqlite3.sqlite_version); assert sqlite3.sqlite_version == "3.53.4"'

APP_PORT=18442
STATE_DIR=/private/tmp/moss-round4-attended-localhost
MODEL_META=.
LIVE_MANIFEST="$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
DECODER_URL=http://127.0.0.1:18000/v1
mkdir -p "$STATE_DIR"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$R4_PYTHON" \
  prototypes/surfaces/serve_localhost.py \
  --state "$STATE_DIR" --port "$APP_PORT" \
  --model "$MODEL_META" --vllm-base-url "$DECODER_URL" \
  --live-provider-manifest "$LIVE_MANIFEST" \
  >"$STATE_DIR/server.log" 2>&1 &
MOSS_SERVER_PID=$!

for ATTEMPT in $(seq 1 180); do
  curl --fail --silent "http://127.0.0.1:$APP_PORT/" >/dev/null && break
  sleep 1
done
curl --fail --silent --show-error "http://127.0.0.1:$APP_PORT/" >/dev/null
echo "MacStudio loopback ready; PID $MOSS_SERVER_PID"
```

The decoder tunnel/lease is lead-owned and must already exist. This recipe never opens
one. Record the printed candidate SHA, runtime receipt, manifest identity, and PID.

## 2. Forward and open from m4mbp

Run on `ga0@m4mbp` in one terminal:

```sh
APP_PORT=18442
ssh -N -o ExitOnForwardFailure=yes \
  -L "$APP_PORT":127.0.0.1:"$APP_PORT" gao@MacStudio.local
```

Then, in another m4mbp terminal:

```sh
open http://localhost:18442
```

Keep the SSH terminal open. The browser origin remains localhost and is a secure
context. Do not substitute a LAN/Tailnet HTTP URL; that loses the localhost exception.

## 3. Echo kit on the same route

On MacStudio, from the same frozen candidate:

```sh
cd /Users/gao/Documents/Codex/2026-09-20/moss-round4/candidate
R4_PYTHON=/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$R4_PYTHON" \
  scripts/attended-echo/measure.py serve --port 18733
```

On m4mbp, open a second forward and then the recorder:

```sh
ssh -N -o ExitOnForwardFailure=yes \
  -L 18733:127.0.0.1:18733 gao@MacStudio.local
open http://localhost:18733/capture.html
```

The operator—not this recipe—performs Start/share/Stop. Keep recordings private.

## 4. Stop and verify cleanup

Use `Ctrl-C` in both m4mbp SSH-forward terminals and the MacStudio echo-kit terminal.
Then on MacStudio:

```sh
kill "$MOSS_SERVER_PID"
wait "$MOSS_SERVER_PID"
lsof -nP -iTCP:18442 -sTCP:LISTEN
lsof -nP -iTCP:18733 -sTCP:LISTEN
```

Both `lsof` commands must print nothing. Preserve `STATE_DIR` until evidence review;
do not delete recordings or the candidate state as routine cleanup.

## Verified and unverified scope

- Verified here: full candidate composition used the R4-7 Python reporting SQLite
  3.53.4, loaded the Live manifest, bound only to `127.0.0.1:18442`, and answered a
  MacStudio loopback `curl`. No transcription/capture was started. The echo command is
  the existing loopback-only server.
- Unverified here: m4mbp SSH/DNS, browser secure-context behavior, microphone,
  playback, capture, voiceprints, decoder reachability, and media inference. Those
  require the attended operator and lead-owned decoder readiness.
