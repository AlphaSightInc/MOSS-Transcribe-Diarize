#!/bin/zsh
set -euo pipefail

AUDIO_PATH="${1:?audio path required}"
RUN_DIR="${2:?run directory required}"
ROOT="${3:?remote prototype helper directory required}"
APP="/Users/ga0/Library/Developer/Xcode/DerivedData/ProjectClerk-fixgsybplqduioeuzrsjkqdadjyn/Build/Products/Debug/ProjectClerk.app"
BINARY="${APP}/Contents/MacOS/ProjectClerk"
AX="${ROOT}/projectclerk_ax"
WATCHER="${ROOT}/watch_projectclerk_sessions.py"
SESSIONS="/Users/ga0/Library/Application Support/com.projectclerk.app/sessions"

mkdir -p "$RUN_DIR/live-snapshots" "$RUN_DIR/pre-stop-pages" "$RUN_DIR/post-stop-snapshots"
if pgrep -f "${BINARY}" >"${RUN_DIR}/preexisting-pids.txt"; then
  echo "ProjectClerk was already running; refusing to adopt or terminate it" >&2
  exit 10
fi

ORIGINAL_VOLUME="$(osascript -e 'output volume of (get volume settings)')"
APP_PID=""
AFPLAY_PID=""
WATCH_PID=""
cleanup() {
  touch "$RUN_DIR/.stop-watcher" 2>/dev/null || true
  if [[ -n "$WATCH_PID" ]] && kill -0 "$WATCH_PID" 2>/dev/null; then wait "$WATCH_PID" 2>/dev/null || true; fi
  if [[ -n "$AFPLAY_PID" ]] && kill -0 "$AFPLAY_PID" 2>/dev/null; then kill "$AFPLAY_PID" 2>/dev/null || true; fi
  osascript -e "set volume output volume ${ORIGINAL_VOLUME}" >/dev/null 2>&1 || true
  if [[ -n "$APP_PID" ]] && kill -0 "$APP_PID" 2>/dev/null; then kill "$APP_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

codesign -dv --verbose=4 "$APP" >"$RUN_DIR/codesign.txt" 2>&1
shasum -a 256 "$BINARY" >"$RUN_DIR/binary-sha256.txt"
stat -f '%m %z %N' "$BINARY" >"$RUN_DIR/binary-stat.txt"
python3 - "$AUDIO_PATH" "$RUN_DIR/audio.json" <<'PY'
import hashlib,json,sys,time,wave
audio,out=sys.argv[1:]
with wave.open(audio,'rb') as w:
    state={"channels":w.getnchannels(),"sample_width":w.getsampwidth(),"sample_rate":w.getframerate(),"samples":w.getnframes()}
state["duration_seconds"]=state["samples"]/state["sample_rate"]
state["sha256"]=hashlib.sha256(open(audio,'rb').read()).hexdigest()
open(out,'w').write(json.dumps(state,indent=2,sort_keys=True)+'\n')
PY

MARKER_NS="$(python3 -c 'import time; print(time.time_ns())')"
open -n "$APP"
for _ in {1..60}; do
  APP_PID="$(pgrep -n -f "${BINARY}" || true)"
  [[ -n "$APP_PID" ]] && break
  sleep 0.25
done
[[ -n "$APP_PID" ]] || { echo "ProjectClerk failed to launch" >&2; exit 11; }
echo "$APP_PID" >"$RUN_DIR/app-pid.txt"
for _ in {1..60}; do
  "$AX" snapshot >"$RUN_DIR/launch-snapshot.json" 2>/dev/null || true
  grep -q 'Start Recording' "$RUN_DIR/launch-snapshot.json" && break
  sleep 0.25
done
grep -q 'Start Recording' "$RUN_DIR/launch-snapshot.json"

# Exact measured button geometry in the packaged app: mic 252x40, Start/Stop 252x46.
"$AX" click-button 252 40 >"$RUN_DIR/mic-click.json"
sleep 0.5
"$AX" snapshot >"$RUN_DIR/mic-muted-snapshot.json"
grep -q 'Muted' "$RUN_DIR/mic-muted-snapshot.json"
START_ISSUED_NS="$(python3 -c 'import time; print(time.time_ns())')"
"$AX" click-button 252 46 >"$RUN_DIR/start-click.json"
for _ in {1..120}; do
  "$AX" snapshot >"$RUN_DIR/recording-ready-snapshot.json" 2>/dev/null || true
  grep -q 'Stop Recording' "$RUN_DIR/recording-ready-snapshot.json" && break
  sleep 0.25
done
grep -q 'Stop Recording' "$RUN_DIR/recording-ready-snapshot.json"
python3 "$WATCHER" --sessions "$SESSIONS" --output "$RUN_DIR/session-versions" --marker-ns "$MARKER_NS" --stop-file "$RUN_DIR/.stop-watcher" &
WATCH_PID=$!

osascript -e 'set volume output volume 20'
PLAYBACK_START_NS="$(python3 -c 'import time; print(time.time_ns())')"
afplay "$AUDIO_PATH" >"$RUN_DIR/afplay.stdout.log" 2>"$RUN_DIR/afplay.stderr.log" &
AFPLAY_PID=$!
echo "$AFPLAY_PID" >"$RUN_DIR/afplay-pid.txt"
tick=0
while kill -0 "$AFPLAY_PID" 2>/dev/null; do
  sleep 1
  tick=$((tick + 1))
  "$AX" snapshot >"$RUN_DIR/live-snapshots/t_$(printf '%04d' "$tick").json" 2>/dev/null || true
done
wait "$AFPLAY_PID" 2>/dev/null || true
AFPLAY_PID=""
PLAYBACK_END_NS="$(python3 -c 'import time; print(time.time_ns())')"
sleep 3
"$AX" snapshot >"$RUN_DIR/pre-stop-pages/page-000.json"
previous=""
same=0
for page in {1..60}; do
  "$AX" scroll 12
  sleep 0.3
  target="$RUN_DIR/pre-stop-pages/page-$(printf '%03d' "$page").json"
  "$AX" snapshot >"$target"
  digest="$(shasum -a 256 "$target" | awk '{print $1}')"
  if [[ "$digest" == "$previous" ]]; then same=$((same + 1)); else same=0; fi
  previous="$digest"
  (( same >= 2 )) && break
done
PRE_STOP_CAPTURED_NS="$(python3 -c 'import time; print(time.time_ns())')"

STOP_ISSUED_NS="$(python3 -c 'import time; print(time.time_ns())')"
"$AX" click-button 252 46 >"$RUN_DIR/stop-click.json"

seen_recluster=0
last_version_count=0
stable_ticks=0
for tick in {1..300}; do
  sleep 1
  "$AX" snapshot >"$RUN_DIR/post-stop-snapshots/t_$(printf '%04d' "$tick").json" 2>/dev/null || true
  grep -q '重新计算' "$RUN_DIR/post-stop-snapshots/t_$(printf '%04d' "$tick").json" && seen_recluster=1
  count="$(find "$RUN_DIR/session-versions" -name '*.json' ! -name 'events.jsonl' 2>/dev/null | wc -l | tr -d ' ')"
  if (( count > 0 && count == last_version_count )); then stable_ticks=$((stable_ticks + 1)); else stable_ticks=0; fi
  last_version_count="$count"
  if (( seen_recluster == 1 )) && ! grep -q '重新计算' "$RUN_DIR/post-stop-snapshots/t_$(printf '%04d' "$tick").json" && (( stable_ticks >= 5 )); then
    break
  fi
  if (( seen_recluster == 0 && tick >= 90 && stable_ticks >= 10 )); then
    break
  fi
done
TERMINAL_CAPTURED_NS="$(python3 -c 'import time; print(time.time_ns())')"
touch "$RUN_DIR/.stop-watcher"
wait "$WATCH_PID" 2>/dev/null || true
WATCH_PID=""

python3 - "$RUN_DIR" "$START_ISSUED_NS" "$PLAYBACK_START_NS" "$PLAYBACK_END_NS" "$PRE_STOP_CAPTURED_NS" "$STOP_ISSUED_NS" "$TERMINAL_CAPTURED_NS" "$seen_recluster" <<'PY'
import json,shutil,sys
from pathlib import Path
run=Path(sys.argv[1])
events=[]
events_path=run/'session-versions/events.jsonl'
if events_path.exists():
    events=[json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
versions=[run/'session-versions'/event['target'] for event in events]
stop_ns=int(sys.argv[6])
pre_stop=[path for path,event in zip(versions,events) if event['observed_epoch_ns'] < stop_ns]
post_stop=[path for path,event in zip(versions,events) if event['observed_epoch_ns'] >= stop_ns]
if pre_stop:
    shutil.copyfile(pre_stop[-1],run/'pre-stop-last-persisted.json')
if post_stop:
    shutil.copyfile(post_stop[0],run/'post-stop-raw.json')
    shutil.copyfile(post_stop[-1],run/'post-stop-stable.json')
payload={
 "start_issued_epoch_ns":int(sys.argv[2]),"playback_start_epoch_ns":int(sys.argv[3]),
 "playback_end_epoch_ns":int(sys.argv[4]),"pre_stop_captured_epoch_ns":int(sys.argv[5]),
 "stop_issued_epoch_ns":int(sys.argv[6]),"terminal_captured_epoch_ns":int(sys.argv[7]),
 "recluster_status_observed":bool(int(sys.argv[8])),
 "persisted_versions":len(versions),"pre_stop_persisted_versions":len(pre_stop),
 "post_stop_persisted_versions":len(post_stop),"raw_captured":bool(post_stop),"stable_captured":bool(post_stop),
}
(run/'clocks.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
if not post_stop: raise SystemExit('no post-Stop persisted ProjectClerk session captured')
PY

echo "restoring_volume=${ORIGINAL_VOLUME}" >"$RUN_DIR/cleanup.txt"
