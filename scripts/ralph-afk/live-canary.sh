#!/bin/bash
# Ralph live-certification canary - the LANE-SEPARATING driver. Runs ON the capture Mac.
#
# Why this exists (candidate 51). The first canary spoke its program through the Mac's own
# speakers, so the same audio reached the system tap directly AND the microphone acoustically:
# the server mixed a program with its own echo, and the run measured 16 canonical speakers for
# 2 real voices with whole sentences transcribed twice. A meeting does not look like that. The
# two lanes must carry DIFFERENT content, and this driver arranges that with the only mechanism
# available on a stock Mac (no virtual audio device, no extra software):
#
#   * the program is spoken to the system output with that output MUTED, so it reaches the
#     process tap but never the room - and therefore never the microphone lane;
#   * a "room window" of local silence is announced on stdout (ROOM_WINDOW_OPEN), during which
#     an EXTERNAL sound source - another host's speaker, a person - supplies the microphone
#     lane's own content;
#   * every phase is written to phases.tsv with its wall-clock bounds, its expected lane and its
#     marker word, so the reducer can ask "did this lane's marker land, and only in its phase".
#
# The mute is a hypothesis this driver TESTS, it does not assume it: if the system marker never
# appears in the transcript, the tap is downstream of the output volume and the mechanism is
# wrong. That is a result, and the run records it.
#
# Prints only non-secret evidence: counts, states, timings, device names, and the transcript of
# a program this script itself spoke. The view token is read once from the pasteboard into a
# shell variable and handed to curl through `curl -K -` on stdin, so it never reaches argv,
# never reaches disk, and is never printed.
#
# Usage:  bash live-canary.sh <label>
# Knobs (env): OUTPUT_MODE=muted|audible  PROGRAM_SECONDS_HINT  ROOM_WINDOW_SECONDS
#              MARKER_SYSTEM  MARKER_ROOM  VOICE_A  VOICE_B  CANARY_OUT  SETTLE_SECONDS
#              MTD_CLI  LIVE_SAN  LIVE_IP  LIVE_PIN  LIVE_PORT
set -uo pipefail

CLI="${MTD_CLI:-$HOME/.local/bin/mtd-capture}"
OUT="${CANARY_OUT:-/tmp/ralph-canary}"
SAN="${LIVE_SAN:-ga0-alienware-rtx4070ti.tailnet.aisight.us}"
IP="${LIVE_IP:-100.64.0.8}"
PORT="${LIVE_PORT:-7861}"
PIN="${LIVE_PIN:-a35ca9fc4a0f5b32bf7da6dc2e03c1fa5b4ac60992f0ee49b6d5677d22b680ff}"
BASE="https://$SAN:$PORT"
VOICE_A="${VOICE_A:-Samantha}"
VOICE_B="${VOICE_B:-Reed}"
MARKER_SYSTEM="${MARKER_SYSTEM:-cardamom}"
MARKER_ROOM="${MARKER_ROOM:-obsidian}"
OUTPUT_MODE="${OUTPUT_MODE:-muted}"
ROOM_WINDOW_SECONDS="${ROOM_WINDOW_SECONDS:-25}"
SETTLE_SECONDS="${SETTLE_SECONDS:-12}"

now() { perl -MTime::HiRes -e 'printf "%.3f\n", Time::HiRes::time()'; }

# ---------------------------------------------------------------- poller mode
if [ "${1:-}" = "--poll" ]; then
  SID="$2"
  IFS= read -r TOK
  cfg() {
    printf 'header = "Authorization: Bearer %s"\n' "$TOK"
    printf 'silent\n'
    printf 'cacert = "%s"\n' "$OUT/leaf.pem"
    printf 'resolve = "%s:%s:%s"\n' "$SAN" "$PORT" "$IP"
  }
  seq=0
  while :; do
    t=$(now)
    body=$(cfg | curl -K - -m 8 -w '\n%{http_code}' "$BASE/api/live/sessions/$SID/snapshot" 2>/dev/null)
    code=${body##*$'\n'}; snap=${body%$'\n'*}
    printf '%s\t%s\t%s\n' "$t" "$code" "$(printf '%s' "$snap" | tr -d '\n')" >> "$OUT/snapshot.tsv"
    t=$(now)
    body=$(cfg | curl -K - -m 8 -w '\n%{http_code}' "$BASE/api/live/sessions/$SID/events?since_seq=$seq" 2>/dev/null)
    code=${body##*$'\n'}; ev=${body%$'\n'*}
    printf '%s\t%s\t%s\n' "$t" "$code" "$(printf '%s' "$ev" | tr -d '\n')" >> "$OUT/events.tsv"
    if [ "$code" = "200" ]; then
      m=$(printf '%s' "$ev" | jq -r '[.events[]?.seq] | max // empty' 2>/dev/null)
      [ -n "$m" ] && seq=$m
    fi
    sleep 1
  done
fi

# ---------------------------------------------------------------- status mode
if [ "${1:-}" = "--status-poll" ]; then
  while :; do
    printf '%s\t%s\n' "$(now)" "$("$CLI" status 2>&1 | tr -d '\n')" >> "$OUT/status.tsv"
    sleep 3
  done
fi

# ---------------------------------------------------------------- main
LABEL="${1:?usage: live-canary.sh <label>}"
mkdir -p "$OUT"
# Truncate every file the pollers APPEND to, not just the ones this script writes. A canary is
# retried - iteration 21's attempt died in setup - and a second run into the same $OUT would
# silently concatenate two meetings, so the reducer's "version is monotone" and "first non-200"
# clauses would read across the seam and answer about no run that happened.
for f in snapshot.tsv events.tsv status.tsv phases.tsv; do
  [ -s "$OUT/$f" ] && echo "note: truncating $OUT/$f ($(wc -l < "$OUT/$f" | tr -d ' ') lines) from an earlier run"
  : > "$OUT/$f"
done

# Phase bookkeeping: every stretch of the meeting names the lane it is supposed to reach.
phase_begin() { PH_NAME="$1"; PH_LANE="$2"; PH_MARKER="${3:-}"; PH_T0=$(now); }
phase_end() {
  printf '%s\t%s\t%s\t%s\t%s\n' "$PH_NAME" "$PH_T0" "$(now)" "$PH_LANE" "$PH_MARKER" >> "$OUT/phases.tsv"
}

# --------------------------------------------------- audio topology + rollback
# What device each lane is actually bound to is transient operator state (headphones connect,
# a monitor is plugged in) and it silently changes what a canary measures. Record it, both
# before and after, and restore whatever was found.
snap_audio() {
  {
    printf 'output_volume=%s\n' "$(osascript -e 'output volume of (get volume settings)' 2>&1)"
    printf 'output_muted=%s\n'  "$(osascript -e 'output muted of (get volume settings)' 2>&1)"
    printf 'default_output=%s\n' \
      "$(system_profiler SPAudioDataType 2>/dev/null | awk '/^ *[^ ].*:$/{d=$0} /Default Output Device: Yes/{gsub(/^ *| *:$/,"",d); print d; exit}')"
    printf 'default_input=%s\n' \
      "$(system_profiler SPAudioDataType 2>/dev/null | awk '/^ *[^ ].*:$/{d=$0} /Default Input Device: Yes/{gsub(/^ *| *:$/,"",d); print d; exit}')"
  } 2>&1
}

echo "== step 0: audio topology BEFORE (this is the run's rollback state)"
snap_audio | tee "$OUT/topology-before.txt"
WAS_MUTED=$(osascript -e 'output muted of (get volume settings)' 2>/dev/null)

AUDIO_RESTORED=no
restore_audio() {
  [ "$AUDIO_RESTORED" = yes ] && return 0
  AUDIO_RESTORED=yes
  if [ "$WAS_MUTED" = "true" ]; then
    osascript -e 'set volume with output muted' >/dev/null 2>&1
  else
    osascript -e 'set volume without output muted' >/dev/null 2>&1
  fi
}
cleanup() {
  restore_audio
  kill "${POLLER:-}" "${SPOLLER:-}" 2>/dev/null
}
trap cleanup EXIT INT TERM

echo "== step 1: pin the served leaf before trusting it"
echo | openssl s_client -connect "$IP:$PORT" -servername "$SAN" 2>/dev/null \
  | openssl x509 > "$OUT/leaf.pem"
GOT=$(openssl x509 -in "$OUT/leaf.pem" -outform DER | shasum -a 256 | cut -d' ' -f1)
echo "leaf_sha256=$GOT"
if [ "$GOT" != "$PIN" ]; then echo "FATAL: served leaf is not the pin"; exit 3; fi
echo "pin_match=yes"

echo "== step 2: pre-start status"
"$CLI" status; echo "rc=$?"

echo "== step 3: separate the lanes - the program must not reach the room"
case "$OUTPUT_MODE" in
  muted)
    osascript -e 'set volume with output muted' >/dev/null 2>&1
    echo "output_mode=muted (system lane gets the program, microphone lane gets the room)"
    ;;
  audible)
    echo "output_mode=audible (CONTROL run: both lanes get the program - this is the confound)"
    ;;
  *) echo "FATAL: OUTPUT_MODE must be muted or audible"; exit 2 ;;
esac
osascript -e 'output muted of (get volume settings)' | sed 's/^/muted_now=/'

echo "== step 4: start"
T_START=$(now)
"$CLI" start --label "$LABEL" > "$OUT/start.json" 2>&1; RC=$?
cat "$OUT/start.json"; echo "start_rc=$RC t=$T_START"
if [ $RC -ne 0 ]; then echo "FATAL: start failed"; exit 4; fi
T_AUDIO0=$(now)   # best estimate of the mixer origin: first audio is pumped right after start

echo "== step 5: arm the app-owned latency probe (first measure() schedules the poll)"
"$CLI" latency | jq -c '{ok, latency: (.latency | {polling, mixerOriginResolved, sufficientSamples})}'

echo "== step 6: handoff -> view authority onto the pasteboard (app-only), session id"
"$CLI" handoff > "$OUT/handoff.json" 2>&1
jq -c '{ok, sessionID, portalURL, viewAuthority}' < "$OUT/handoff.json"
SID=$(jq -r '.sessionID // empty' < "$OUT/handoff.json")
if [ -z "$SID" ]; then echo "FATAL: no session id from handoff"; exit 5; fi

TOK=$(pbpaste)
if [ -z "$TOK" ]; then echo "FATAL: pasteboard empty"; exit 6; fi
echo "view_authority_on_pasteboard=yes token_len=${#TOK}"

echo "== step 7: the portal page itself, unauthenticated, as a browser loads it"
curl -s --cacert "$OUT/leaf.pem" --resolve "$SAN:$PORT:$IP" \
  -o "$OUT/live.html" -w 'portal_http=%{http_code} bytes=%{size_download}\n' "$BASE/live"

echo "== step 8: start the portal poller (what the browser does) and the status poller"
printf '%s\n' "$TOK" | nohup bash "$0" --poll "$SID" >/dev/null 2>&1 &
POLLER=$!
nohup bash "$0" --status-poll >/dev/null 2>&1 &
SPOLLER=$!
echo "poller=$POLLER status_poller=$SPOLLER"
sleep 2

# ------------------------------------------------------------------ the program
echo "== step 9 phase A: the two-voice program, spoken to the SYSTEM lane only"
phase_begin program-a system "$MARKER_SYSTEM"
say -v "$VOICE_A" "Good afternoon everyone, let us begin the weekly transcription status review."
say -v "$VOICE_B" "Thanks. The capture client is now streaming both lanes at sixteen kilohertz."
say -v "$VOICE_A" "How is the decoder holding up under continuous speech from two speakers?"
say -v "$VOICE_B" "Real time factor is well under one, so the backlog stays bounded."
say -v "$VOICE_A" "Please confirm the system side codeword before we hand over to the room."
say -v "$VOICE_B" "The system audio codeword for this run is $MARKER_SYSTEM."
# Say the marker again ALONE and slowly, three times. Measured twice (F1's "pineapple" -> "Hi
# Apple", this driver's first run losing "umbrella" entirely): a rare noun buried in a fluent
# sentence is reliably rewritten by the decoder's language model. An isolated, repeated,
# slow-rate token is the only delivery that gives the cross-check a chance.
say -v "$VOICE_A" -r 130 "$MARKER_SYSTEM. $MARKER_SYSTEM. $MARKER_SYSTEM."
phase_end
echo "phase_a_done t=$(now) marker=$MARKER_SYSTEM"

echo "== step 10 phase B: the room window - THIS HOST STAYS SILENT"
phase_begin room-window microphone "$MARKER_ROOM"
touch "$OUT/room-open"
echo "ROOM_WINDOW_OPEN t=$(now) seconds=$ROOM_WINDOW_SECONDS expect_marker=$MARKER_ROOM"
sleep "$ROOM_WINDOW_SECONDS"
echo "ROOM_WINDOW_CLOSED t=$(now)"
rm -f "$OUT/room-open"
phase_end

echo "== step 11 phase C: back to the system lane, so the room window has a boundary on both sides"
phase_begin program-c system "$MARKER_SYSTEM"
say -v "$VOICE_A" "Thank you. Returning to the system audio side of the meeting now."
say -v "$VOICE_B" "Understood. The codeword $MARKER_SYSTEM is recorded for the system lane."
say -v "$VOICE_A" "That concludes the agenda. Stopping the capture shortly."
phase_end
T_SPEECH_END=$(now)

echo "== step 12: let the trailing span commit and the portal catch up"
sleep "$SETTLE_SECONDS"

echo "== step 13: status and latency while still running"
"$CLI" status > "$OUT/status-final.json" 2>&1
jq -c '{ok, running, lanes, publishedFrameCount, outboxRetainedFrames, outboxDegradation, pumpFailure, sessionRefusal}' < "$OUT/status-final.json"
"$CLI" latency > "$OUT/latency-final.json" 2>&1
jq -c '.latency' < "$OUT/latency-final.json"

echo "== step 14: stop and drain"
T_STOP=$(now)
"$CLI" stop > "$OUT/stop.json" 2>&1; echo "stop_rc=$?"
jq -c '{ok, running, lanes, publishedFrameCount, outboxRetainedFrames, sessionRefusal}' < "$OUT/stop.json"
"$CLI" latency > "$OUT/latency-after-stop.json" 2>&1
jq -c '.latency' < "$OUT/latency-after-stop.json"

sleep 3
kill "$POLLER" "$SPOLLER" 2>/dev/null
wait "$POLLER" "$SPOLLER" 2>/dev/null

echo "== step 15: restore the audio topology this run changed"
restore_audio
snap_audio | tee "$OUT/topology-after.txt"

echo "== step 16: hygiene - clear the pasteboard, drop the token"
pbcopy < /dev/null
TOK=
echo "pasteboard_cleared=yes pasteboard_len=$(pbpaste | wc -c | tr -d ' ')"

cat > "$OUT/times.env" <<EOT
T_START=$T_START
T_AUDIO0=$T_AUDIO0
T_SPEECH_END=$T_SPEECH_END
T_STOP=$T_STOP
MARKER_SYSTEM=$MARKER_SYSTEM
MARKER_ROOM=$MARKER_ROOM
OUTPUT_MODE=$OUTPUT_MODE
SID=$SID
LABEL=$LABEL
EOT
echo "== done; evidence in $OUT"
cat "$OUT/phases.tsv"
