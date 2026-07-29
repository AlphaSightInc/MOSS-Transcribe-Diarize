#!/bin/bash
# Ralph F2 - the 300 s LOCKED certification run, LANE-SEPARATING and repo-tracked. Runs ON the
# capture Mac.
#
# The PRD clause this measures, word by word:
#   "300-second locked certification passes: simultaneous lanes, silence/mute, a 5-second
#    network interruption, ambiguous retry, duplicate retry, two speakers, clean stop/drain -
#    plus a separate mic-granted / system-audio-denied run that still produces transcript.
#    User-visible p95 <= 6 s ...; decoder p95 RTF < 1; zero accepted-audio loss; outbox and
#    memory bounded."
#
# WHAT IS AND IS NOT IN THIS FILE, stated plainly so a green run is not over-read:
#
#   IN  - simultaneous lanes, a silence/mute window, two voices, the 5 s network interruption
#         (and therefore the ambiguous-retry and duplicate-retry paths, which are DOWNSTREAM of
#         it: a frame the client cannot confirm is retried, and the retry arrives as a
#         duplicate), clean stop/drain, and the same evidence layout every other driver writes.
#   OUT - the "system-audio-denied" variant. It is a SEPARATE RUN by the PRD's own wording, and
#         producing it means taking a TCC grant away from com.alphasight.moss.capture. The
#         grants are `auth_value=2` today and the PRD forbids ever asking the operator for those
#         clicks again, so a driver that resets them would spend the one input this loop cannot
#         obtain. That variant needs its own recorded plan and is NOT attempted here.
#   OUT - the interruption itself. It happens at the SERVER, because the capture Mac has no
#         passwordless sudo and its ssh rides the same tailnet the drop would cut. See
#         scripts/ralph-afk/live-cert-interrupt.sh, which is armed BEFORE this driver launches.
#
# WHY THE INTERRUPTION IS NOT COORDINATED WITH THIS SCRIPT, which looks like a gap and is not.
# Arming the server job first and launching this driver second means nothing after launch
# depends on the orchestrator still being alive - the lesson iteration 8 of this run paid for,
# where a dead orchestrator nearly cost a 17-minute gate. The price is skew between the armed
# delay and this driver's own clock, and it is paid for by making the phase the interruption
# lands in SIXTY SECONDS WIDE and by sampling the client's status at 1 Hz for the whole run, so
# whatever the skew, the outbox's retain-and-replay is bracketed by the evidence. The
# authoritative record of when the network was actually down is the server job's own report,
# measured on CLOCK_MONOTONIC because that host's wall clock steps backwards (candidate 56).
#
# Prints only non-secret evidence: counts, states, timings, HTTP codes, device names, and the
# transcript of a program this script itself spoke. The view token is read once from the
# pasteboard into a shell variable and handed to curl through `curl -K -` on stdin, so it never
# reaches argv, never reaches disk, and is never printed.
#
# RECIPE (from the orchestrator; the two halves are launched in this order and no other):
#   1. on the server, in WSL:
#        bash live-cert-interrupt.sh --delay 215 --duration 5 --out /tmp/ralph-cert-interrupt.json
#      215 s = ~15 s of this driver's setup + ~200 s of meeting, which lands the window inside
#      the 60 s `program-interrupt` phase with ~20 s of slack on either side.
#   2. on the capture Mac:
#        scp live-cert.sh ga0@m4mbp:/tmp/
#        nohup env OUTPUT_MODE=muted bash /tmp/live-cert.sh <label> > /tmp/ralph-cert-run.log 2>&1 &
#   3. afterwards, copy the server's report into the evidence dir as interrupt.json and reduce:
#        python3 live-canary-clauses.py <dir> --user-visible-gate-ms 6000 \
#                --interrupt-report <dir>/interrupt.json
#
# Usage:  bash live-cert.sh <label>
# Knobs (env): OUTPUT_MODE=muted|audible  CERT_SECONDS  POLL_INTERVAL  STATUS_INTERVAL
#              SILENCE_SECONDS  ROOM_WINDOW_SECONDS  MARKER_SYSTEM  MARKER_ROOM  VOICE_A  VOICE_B
#              CERT_OUT  SETTLE_SECONDS  MTD_CLI  LIVE_SAN  LIVE_IP  LIVE_PIN  LIVE_PORT
#              FULL_SNAPSHOT_EVERY
set -uo pipefail

CLI="${MTD_CLI:-$HOME/.local/bin/mtd-capture}"
OUT="${CERT_OUT:-/tmp/ralph-cert}"
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
CERT_SECONDS="${CERT_SECONDS:-300}"
SILENCE_SECONDS="${SILENCE_SECONDS:-30}"
ROOM_WINDOW_SECONDS="${ROOM_WINDOW_SECONDS:-30}"
POLL_INTERVAL="${POLL_INTERVAL:-1}"
# 1 Hz, not the soak's 10 s. The whole point of this run is a 5 s window: a 10 s sampler can
# miss it entirely, and `outboxRetainedFrames` rising and falling is the evidence that the
# client retained accepted audio rather than losing it.
STATUS_INTERVAL="${STATUS_INTERVAL:-1}"
SETTLE_SECONDS="${SETTLE_SECONDS:-15}"
FULL_SNAPSHOT_EVERY="${FULL_SNAPSHOT_EVERY:-30}"

now() { perl -MTime::HiRes -e 'printf "%.3f\n", Time::HiRes::time()'; }

# The snapshot, shape intact, with only the transcript text removed - live-soak.sh's projection,
# unchanged, so one reducer reads canary, soak and certification directories alike.
SNAP_PRUNE='. as $r | ($r.snapshot.session // {}) as $s
  | {snapshot: {session: ($s + {committed: [ ($s.committed // [])[] | {span_id: .span_id} ]}),
                terminal_failure: $r.snapshot.terminal_failure},
     descriptor: {bounds: ($r.descriptor.bounds // null)},
     v2_session: $r.v2_session}'

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
  seq=0; n=0
  while :; do
    t=$(now)
    # -m 4, not the soak's 8. During the interruption every request must FAIL FAST and be
    # recorded, otherwise a single 8 s timeout swallows most of a 5 s window and the poll rate
    # collapses exactly where the evidence is needed.
    body=$(cfg | curl -K - -m 4 -w '\n%{http_code}' "$BASE/api/live/sessions/$SID/snapshot" 2>/dev/null)
    code=${body##*$'\n'}; snap=${body%$'\n'*}
    if [ "$code" = "200" ]; then
      pruned=$(printf '%s' "$snap" | jq -c "$SNAP_PRUNE" 2>/dev/null | tr -d '\n')
      [ -z "$pruned" ] && pruned=$(printf '%s' "$snap" | tr -d '\n')
      if [ $((n % FULL_SNAPSHOT_EVERY)) -eq 0 ]; then
        printf '%s' "$snap" > "$OUT/snap-full-$(printf '%04d' "$n").json"
      fi
    else
      pruned=$(printf '%s' "$snap" | tr -d '\n')
    fi
    printf '%s\t%s\t%s\n' "$t" "$code" "$pruned" >> "$OUT/snapshot.tsv"
    t=$(now)
    body=$(cfg | curl -K - -m 4 -w '\n%{http_code}' "$BASE/api/live/sessions/$SID/events?since_seq=$seq" 2>/dev/null)
    code=${body##*$'\n'}; ev=${body%$'\n'*}
    printf '%s\t%s\t%s\n' "$t" "$code" "$(printf '%s' "$ev" | tr -d '\n')" >> "$OUT/events.tsv"
    if [ "$code" = "200" ]; then
      m=$(printf '%s' "$ev" | jq -r '[.events[]?.seq] | max // empty' 2>/dev/null)
      [ -n "$m" ] && seq=$m
    fi
    n=$((n+1))
    sleep "$POLL_INTERVAL"
  done
fi

# ---------------------------------------------------------------- status mode
if [ "${1:-}" = "--status-poll" ]; then
  while :; do
    printf '%s\t%s\n' "$(now)" "$("$CLI" status 2>&1 | tr -d '\n')" >> "$OUT/status.tsv"
    sleep "$STATUS_INTERVAL"
  done
fi

# ---------------------------------------------------------------- main
LABEL="${1:?usage: live-cert.sh <label>}"
mkdir -p "$OUT"
# Truncate every file a poller APPENDS to. A second run into the same $OUT would concatenate two
# meetings and the reducer's monotone-version and first-non-200 clauses would answer about no
# run that happened.
for f in snapshot.tsv events.tsv status.tsv phases.tsv view-checks.tsv; do
  [ -s "$OUT/$f" ] && echo "note: truncating $OUT/$f ($(wc -l < "$OUT/$f" | tr -d ' ') lines) from an earlier run"
  : > "$OUT/$f"
done
rm -f "$OUT"/snap-full-*.json "$OUT"/interrupt.json
SNAPSHOT_TSV="$OUT/snapshot.tsv"

phase_begin() { PH_NAME="$1"; PH_LANE="$2"; PH_MARKER="${3:-}"; PH_T0=$(now); }
phase_end() {
  printf '%s\t%s\t%s\t%s\t%s\n' "$PH_NAME" "$PH_T0" "$(now)" "$PH_LANE" "$PH_MARKER" >> "$OUT/phases.tsv"
}

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
T_AUDIO0=$(now)

echo "== step 5: arm the app-owned latency probe (first measure() schedules the poll)"
"$CLI" latency | jq -c '{ok, latency: (.latency | {polling, mixerOriginResolved, sufficientSamples})}'

echo "== step 6: handoff -> view authority onto the pasteboard (app-only), session id"
T_HANDOFF=$(now)
"$CLI" handoff > "$OUT/handoff.json" 2>&1
jq -c '{ok, sessionID, portalURL, viewAuthority}' < "$OUT/handoff.json"
SID=$(jq -r '.sessionID // empty' < "$OUT/handoff.json")
if [ -z "$SID" ]; then echo "FATAL: no session id from handoff"; exit 5; fi

TOK=$(pbpaste)
if [ -z "$TOK" ]; then echo "FATAL: pasteboard empty"; exit 6; fi
echo "view_authority_on_pasteboard=yes token_len=${#TOK} t_handoff=$T_HANDOFF"

cfg() {
  printf 'header = "Authorization: Bearer %s"\n' "$TOK"
  printf 'silent\n'
  printf 'cacert = "%s"\n' "$OUT/leaf.pem"
  printf 'resolve = "%s:%s:%s"\n' "$SAN" "$PORT" "$IP"
}

check_view() {
  local tag="$1" t age snap_code ev_code portal_code
  t=$(now); age=$(perl -e "printf '%.1f', $t-$T_START")
  snap_code=$(cfg | curl -K - -m 8 -o "$OUT/view-$tag-snapshot.json" -w '%{http_code}' \
    "$BASE/api/live/sessions/$SID/snapshot" 2>/dev/null)
  ev_code=$(cfg | curl -K - -m 8 -o "$OUT/view-$tag-events.json" -w '%{http_code}' \
    "$BASE/api/live/sessions/$SID/events?since_seq=0" 2>/dev/null)
  portal_code=$(curl -s --cacert "$OUT/leaf.pem" --resolve "$SAN:$PORT:$IP" \
    -o "$OUT/view-$tag-live.html" -w '%{http_code}' "$BASE/live" 2>/dev/null)
  echo "view_check=$tag t=$t token_age_since_start_s=$age snapshot_http=$snap_code events_http=$ev_code portal_http=$portal_code"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$tag" "$t" "$age" "$snap_code" "$ev_code" "$portal_code" \
    >> "$OUT/view-checks.tsv"
}

echo "== step 7: the portal page itself, unauthenticated, as a browser loads it"
curl -s --cacert "$OUT/leaf.pem" --resolve "$SAN:$PORT:$IP" \
  -o "$OUT/live.html" -w 'portal_http=%{http_code} bytes=%{size_download}\n' "$BASE/live"
check_view t0

echo "== step 8: start the portal poller (what the browser does) and the status poller"
printf '%s\n' "$TOK" | nohup bash "$0" --poll "$SID" >/dev/null 2>&1 &
POLLER=$!
nohup bash "$0" --status-poll >/dev/null 2>&1 &
SPOLLER=$!
echo "poller=$POLLER status_poller=$SPOLLER"
sleep 2

# ---------------------------------------------------------------- the program
# A LOCKED run: the phase boundaries are wall-clock offsets from T_START, not "however long the
# speech took". `say` returns when the utterance finishes, so a line-count program drifts by
# tens of seconds over 300 s and the interruption would land wherever the drift left it.
elapsed() { perl -e "printf '%.1f', $(now)-$T_START"; }
until_offset() {   # sleep until $1 seconds past T_START, and never sleep negative
  local target="$1" left
  left=$(perl -e "printf '%.2f', $target-($(now)-$T_START)")
  case "$left" in -*) return 0 ;; esac
  sleep "$left"
}
LINES_A=(
  "$VOICE_A|Good afternoon. This is the three hundred second locked certification run."
  "$VOICE_B|Both capture lanes are streaming at sixteen kilohertz, simultaneously."
  "$VOICE_A|The decoder should keep the real time factor comfortably under one."
  "$VOICE_B|Speaker labels are expected to stay stable while two of us are talking."
  "$VOICE_A|Please confirm the system side codeword before the silence window."
  "$VOICE_B|The system audio codeword for this run is $MARKER_SYSTEM."
)
LINES_B=(
  "$VOICE_A|Back from the silence window. The transcript should have kept its place."
  "$VOICE_B|Nothing was spoken for half a minute and the session stayed active."
  "$VOICE_A|Continuing with two speakers so the labels have something to separate."
  "$VOICE_B|The outbox is expected to stay empty while the network is healthy."
)
LINES_INT=(
  "$VOICE_A|This stretch is deliberately continuous so no frame is silent."
  "$VOICE_B|If the network drops now, the client must retain every accepted frame."
  "$VOICE_A|A frame the client cannot confirm is retried, and the retry is a duplicate."
  "$VOICE_B|The server is expected to account for the duplicate exactly once."
  "$VOICE_A|Nothing about this stretch should end the meeting."
  "$VOICE_B|The outbox should rise while the link is down and drain when it returns."
  "$VOICE_A|Continuing to speak so the endpointer keeps freezing spans."
  "$VOICE_B|Every one of these sentences is another two and a half seconds of audio."
)
LINES_D=(
  "$VOICE_A|The link should be back and the backlog should be gone by now."
  "$VOICE_B|Winding down the certification run with the last few utterances."
  "$VOICE_A|The codeword $MARKER_SYSTEM is recorded once more for the system lane."
  "$VOICE_B|That concludes the agenda. Stopping the capture shortly."
)
# Speak from an array, round robin, until the deadline offset passes. Deliberately does NOT cut
# an utterance short: `say` is the audio source, and killing it mid-word would produce exactly
# the truncated-span artefact this run is trying to measure the absence of.
speak_until() {
  local deadline="$1"; shift
  local -a lines=("$@")
  local i=0 n=${#lines[@]} v txt
  while :; do
    left=$(perl -e "printf '%.2f', $deadline-($(now)-$T_START)")
    case "$left" in -*) return 0 ;; esac
    [ "$(perl -e "print(($left > 3) ? 1 : 0)")" = "0" ] && return 0
    v="${lines[$((i % n))]%%|*}"; txt="${lines[$((i % n))]#*|}"
    say -v "$v" "$txt"
    i=$((i+1))
  done
}

# The locked timeline, as offsets from T_START. Scaled from CERT_SECONDS so a shorter smoke run
# keeps the same shape.
S=$CERT_SECONDS
OFF_A_END=$((S * 70 / 300))
OFF_SIL_END=$((OFF_A_END + SILENCE_SECONDS))
OFF_B_END=$((S * 170 / 300))
OFF_ROOM_END=$((OFF_B_END + ROOM_WINDOW_SECONDS))
OFF_INT_END=$((S * 260 / 300))
OFF_END=$S
echo "timeline offsets: program-a<=${OFF_A_END}s silence<=${OFF_SIL_END}s program-b<=${OFF_B_END}s room<=${OFF_ROOM_END}s program-interrupt<=${OFF_INT_END}s program-d<=${OFF_END}s"

echo "== step 9 phase A: two voices on the SYSTEM lane"
phase_begin program-a system "$MARKER_SYSTEM"
speak_until "$OFF_A_END" "${LINES_A[@]}"
# The marker alone, repeated, slowly. Measured twice: a rare noun buried in a fluent sentence is
# reliably rewritten by the decoder's language model (F1's "pineapple" -> "Hi Apple"). An
# isolated, repeated, slow-rate token is the only delivery that gives the cross-check a chance,
# and even then the decoder may rewrite it PHONETICALLY - candidate 59.
say -v "$VOICE_A" -r 130 "$MARKER_SYSTEM. $MARKER_SYSTEM. $MARKER_SYSTEM."
until_offset "$OFF_A_END"
phase_end
echo "phase_a_done t_offset=$(elapsed)"

echo "== step 10 phase SILENCE: the PRD's silence/mute window - NEITHER lane is given content"
phase_begin silence none ""
echo "SILENCE_WINDOW_OPEN t=$(now) seconds=$SILENCE_SECONDS"
until_offset "$OFF_SIL_END"
echo "SILENCE_WINDOW_CLOSED t=$(now) t_offset=$(elapsed)"
phase_end

echo "== step 11 phase B: back to two voices, so the silence window has a boundary on both sides"
phase_begin program-b system "$MARKER_SYSTEM"
speak_until "$OFF_B_END" "${LINES_B[@]}"
until_offset "$OFF_B_END"
phase_end
check_view mid

echo "== step 12 phase ROOM: this host stays silent so the microphone lane can carry its own content"
phase_begin room-window microphone "$MARKER_ROOM"
touch "$OUT/room-open"
echo "ROOM_WINDOW_OPEN t=$(now) seconds=$ROOM_WINDOW_SECONDS expect_marker=$MARKER_ROOM"
until_offset "$OFF_ROOM_END"
echo "ROOM_WINDOW_CLOSED t=$(now) t_offset=$(elapsed)"
rm -f "$OUT/room-open"
phase_end

echo "== step 13 phase INTERRUPT: sixty seconds of CONTINUOUS speech - the armed 5 s network"
echo "   window is expected to land inside this phase. Continuous, because a silent frame is"
echo "   not audio the client has to retain, so a drop over silence would prove nothing."
phase_begin program-interrupt system "$MARKER_SYSTEM"
echo "INTERRUPT_PHASE_OPEN t=$(now) t_offset=$(elapsed)"
speak_until "$OFF_INT_END" "${LINES_INT[@]}"
until_offset "$OFF_INT_END"
echo "INTERRUPT_PHASE_CLOSED t=$(now) t_offset=$(elapsed)"
phase_end

echo "== step 14 phase D: wind-down, and the recovery has room to be visible"
phase_begin program-d system "$MARKER_SYSTEM"
speak_until "$OFF_END" "${LINES_D[@]}"
until_offset "$OFF_END"
phase_end
T_SPEECH_END=$(now)

echo "== step 15: let the trailing span commit and the portal catch up"
sleep "$SETTLE_SECONDS"
check_view post

echo "== step 16: status and latency while still running"
"$CLI" status > "$OUT/status-final.json" 2>&1
jq -c '{ok, running, lanes, publishedFrameCount, outboxRetainedFrames, outboxDegradation, pumpFailure, sessionRefusal}' < "$OUT/status-final.json"
"$CLI" latency > "$OUT/latency-final.json" 2>&1
jq -c '.latency' < "$OUT/latency-final.json"

echo "== step 17: stop and drain"
T_STOP=$(now)
"$CLI" stop > "$OUT/stop.json" 2>&1; echo "stop_rc=$?"
jq -c '{ok, running, lanes, publishedFrameCount, outboxRetainedFrames, sessionRefusal}' < "$OUT/stop.json"
"$CLI" latency > "$OUT/latency-after-stop.json" 2>&1
jq -c '.latency' < "$OUT/latency-after-stop.json"
# Candidate 60 (Q4) is FIXED ON THE BRANCH as of iteration 24: the client now calls the server's
# stop route after its final drain, so a 200 here is the defect and a 401/403 is the fix. Until
# the installed app on this Mac is REBUILT from a build carrying Q4, this still reads 200 - the
# app that answers `stop` is the one in /Applications, not the one in this checkout.
check_view post-stop

sleep 3
kill "$POLLER" "$SPOLLER" 2>/dev/null
wait "$POLLER" "$SPOLLER" 2>/dev/null

echo "== step 18: restore the audio topology this run changed"
restore_audio
snap_audio | tee "$OUT/topology-after.txt"

echo "== step 19: hygiene - clear the pasteboard, drop the token"
pbcopy < /dev/null
TOK=
echo "pasteboard_cleared=yes pasteboard_len=$(pbpaste | wc -c | tr -d ' ')"

cat > "$OUT/times.env" <<EOT
T_START=$T_START
T_AUDIO0=$T_AUDIO0
T_HANDOFF=$T_HANDOFF
T_SPEECH_END=$T_SPEECH_END
T_STOP=$T_STOP
MARKER_SYSTEM=$MARKER_SYSTEM
MARKER_ROOM=$MARKER_ROOM
OUTPUT_MODE=$OUTPUT_MODE
CERT_SECONDS=$CERT_SECONDS
SID=$SID
LABEL=$LABEL
EOT
echo "== done; evidence in $OUT"
echo "   REMINDER: copy the server's interrupt report into $OUT/interrupt.json before reducing,"
echo "   and reduce with --user-visible-gate-ms 6000 --interrupt-report $OUT/interrupt.json"
cat "$OUT/phases.tsv"
