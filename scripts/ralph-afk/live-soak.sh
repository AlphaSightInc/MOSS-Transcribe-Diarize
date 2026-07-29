#!/bin/bash
# Ralph F3 - the 16-minute active-view soak, LANE-SEPARATING and repo-tracked. Runs ON the
# capture Mac.
#
# The PRD clause this measures, word by word:
#   "capture remains active with periodic accepted audio and /live polling; the same view
#    authority works after minute 15, then clean stop immediately revokes it."
#
# Why this file exists rather than /tmp/ralph-f3-soak.sh, which ran F3 the first time:
#
#   1. THE FIFTH AMENDMENT'S GATE REQUIRES CANDIDATE 51'S HARNESS ON F3 TOO. The original soak
#      driver spoke its program through the Mac's own speakers, so the same audio reached the
#      system tap directly AND the microphone acoustically - the confound F1 measured (16
#      canonical speakers for 2 voices, whole sentences transcribed twice). This driver mutes the
#      system output for the program, which iteration 12 proved the process tap is upstream of,
#      and records the audio topology before and after so a run says which devices it measured.
#   2. ONE EVIDENCE LAYOUT, ONE REDUCER. The original wrote snapshot.tsv as a positional jq
#      projection, so live-canary-clauses.py refuses that directory by name. This driver writes
#      the canary's (t, code, body) layout, so the same reducer decides both runs.
#   3. IT WAS ONLY IN /tmp. A certification driver that exists on two hosts' scratch disks is one
#      reboot away from being unreproducible.
#
# WHY THE SNAPSHOT BODY IS PRUNED, and it is a measured decision rather than a tidy-up. F1's
# full snapshot body grew 2796 -> 18210 bytes across 42 committed spans (~366 bytes per span,
# mean 10.3 KB per poll over 56 polls). A 17-minute soak commits ~412 spans, so logging the full
# body would reach ~150 KB per poll and ~38 MB of snapshot.tsv - quadratic, written on the
# capture Mac, during the run whose latency is being measured. So each poll stores the snapshot
# with its SHAPE INTACT and only `committed[]` replaced by its span ids: every scalar the reducer
# reads survives, `len(committed)` stays exact, and the transcript text - which lives in the
# event stream anyway, where it is linear because `since_seq` advances - is what is dropped. A
# full untouched snapshot is still written every FULL_SNAPSHOT_EVERY polls.
#
# INVOCATION LESSON, PAID FOR ONCE (run 20260728-181020 iteration 21): start this NOHUP'D on the
# capture Mac and poll its log. A foreground ssh dies with the link - the tailnet dropped three
# times during that iteration's setup alone - and a drop 40 s into a meeting kills the driver
# mid-run, leaving the output muted, the session hot and the pasteboard written.
#
# Prints only non-secret evidence: counts, states, timings, HTTP codes, device names, and the
# transcript of a program this script itself spoke. The view token is read once from the
# pasteboard into a shell variable and handed to curl through `curl -K -` on stdin, so it never
# reaches argv, never reaches disk, and is never printed.
#
# Usage:  bash live-soak.sh <label>
# Knobs (env): OUTPUT_MODE=muted|audible  SOAK_SECONDS  UTTERANCE_INTERVAL  POLL_INTERVAL
#              STATUS_INTERVAL  ROOM_WINDOW_MINUTES  MARKER_SYSTEM  MARKER_ROOM  VOICE_A  VOICE_B
#              SOAK_OUT  MTD_CLI  LIVE_SAN  LIVE_IP  LIVE_PIN  LIVE_PORT  FULL_SNAPSHOT_EVERY
set -uo pipefail

CLI="${MTD_CLI:-$HOME/.local/bin/mtd-capture}"
OUT="${SOAK_OUT:-/tmp/ralph-soak}"
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
SOAK_SECONDS="${SOAK_SECONDS:-1020}"          # 17 min of capture, so the view check is past 900 s
UTTERANCE_INTERVAL="${UTTERANCE_INTERVAL:-60}"
POLL_INTERVAL="${POLL_INTERVAL:-2}"
STATUS_INTERVAL="${STATUS_INTERVAL:-10}"
ROOM_WINDOW_MINUTES="${ROOM_WINDOW_MINUTES:-4,12}"   # minutes this host stays silent
FULL_SNAPSHOT_EVERY="${FULL_SNAPSHOT_EVERY:-30}"
VIEW_CLAUSE_AGE="${VIEW_CLAUSE_AGE:-900}"     # the retired fixed expiry; the clause is "after" it

now() { perl -MTime::HiRes -e 'printf "%.3f\n", Time::HiRes::time()'; }

# The snapshot, shape intact, with only the transcript text removed. See the header.
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
    body=$(cfg | curl -K - -m 8 -w '\n%{http_code}' "$BASE/api/live/sessions/$SID/snapshot" 2>/dev/null)
    code=${body##*$'\n'}; snap=${body%$'\n'*}
    if [ "$code" = "200" ]; then
      pruned=$(printf '%s' "$snap" | jq -c "$SNAP_PRUNE" 2>/dev/null | tr -d '\n')
      # A prune that fails must not become a silently skipped poll: keep the raw body so the
      # reducer still reads the poll, and let the file say the prune failed.
      [ -z "$pruned" ] && pruned=$(printf '%s' "$snap" | tr -d '\n')
      if [ $((n % FULL_SNAPSHOT_EVERY)) -eq 0 ]; then
        printf '%s' "$snap" > "$OUT/snap-full-$(printf '%04d' "$n").json"
      fi
    else
      pruned=$(printf '%s' "$snap" | tr -d '\n')
    fi
    printf '%s\t%s\t%s\n' "$t" "$code" "$pruned" >> "$OUT/snapshot.tsv"
    t=$(now)
    body=$(cfg | curl -K - -m 8 -w '\n%{http_code}' "$BASE/api/live/sessions/$SID/events?since_seq=$seq" 2>/dev/null)
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
LABEL="${1:?usage: live-soak.sh <label>}"
mkdir -p "$OUT"
# Every file the pollers APPEND to is truncated here, not just the ones the main script writes.
# A soak is retried - iteration 21's attempt died in setup - and a second run into the same $OUT
# would silently concatenate two meetings: the reducer's "version is monotone" and "first non-200"
# clauses would both read across the seam and answer about no run that happened. Say so out loud
# when there was something to truncate, because an orphaned poller from the previous attempt would
# keep appending regardless and that is visible only if the operator knows to look.
for f in snapshot.tsv events.tsv status.tsv phases.tsv view-checks.tsv; do
  [ -s "$OUT/$f" ] && echo "note: truncating $OUT/$f ($(wc -l < "$OUT/$f" | tr -d ' ') lines) from an earlier run"
  : > "$OUT/$f"
done
rm -f "$OUT"/snap-full-*.json
SNAPSHOT_TSV="$OUT/snapshot.tsv"

phase_begin() { PH_NAME="$1"; PH_LANE="$2"; PH_MARKER="${3:-}"; PH_T0=$(now); }
phase_end() {
  printf '%s\t%s\t%s\t%s\t%s\n' "$PH_NAME" "$PH_T0" "$(now)" "$PH_LANE" "$PH_MARKER" >> "$OUT/phases.tsv"
}

# --------------------------------------------------- audio topology + rollback
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

# One explicit, separately logged exercise of the view authority. $1 is a tag.
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

# ------------------------------------------------------------------ the soak
# One short utterance per UTTERANCE_INTERVAL, spoken to the SYSTEM lane only (the output is
# muted), except on the ROOM_WINDOW_MINUTES where this host stays silent so the microphone lane
# is the only thing carrying audio. Every minute is written to phases.tsv with the lane it is
# supposed to reach, so the reducer can ask "did this lane's marker land, and only in its phase".
# >>> soak-abort-decision (extracted and exercised by scripts/ralph-afk/soak-abort-probe.py;
# keep it self-contained - it may read only its two arguments and $SNAPSHOT_TSV)
#
# WHAT MAY END A 17-MINUTE SOAK EARLY, ruled deliberately rather than pattern-matched.
#
#   THE PREVIOUS VERSION OF THIS BLOCK ABORTED EVERY RUN AT MINUTE 1, and it never ran once to
#   find out. It asked `case "$snaplast" in *terminal*|*failed*)`, but the snapshot body carries
#   the literal KEY `terminal_failure` on every healthy poll (and `failed_samples` on every
#   lane), so the glob matched unconditionally. Measured on F1's 56 real recorded bodies:
#   56/56 abort, including the 54 that are a perfectly healthy meeting. A substring test over a
#   JSON document tests the schema, not the state.
#
#   THE RULING. Abort only on a session that GENUINELY CANNOT CONTINUE - the same rule the third
#   and fifth amendments settled for the product itself:
#     * the client says `running: false`                       -> the capture is gone;
#     * `snapshot.terminal_failure` is non-null                -> the server ended the meeting;
#     * `v2_session.status` is anything but `active`           -> likewise, with its reason;
#     * three consecutive snapshot polls refused               -> F3's own death shape (the view
#       routes 401 once the session is released), and the body then carries no state to read.
#   A LANE FAULT IS RECORDED AND NEVER ABORTS. Phase M's governing rule is that a fault on one
#   lane must not end the meeting, so a soak that stopped there would destroy the one piece of
#   evidence 53/48/49/D-a exist to produce. The lane timeline goes to the reducer, which decides
#   it (`live-canary-clauses.py` section 8); this driver only has to keep the run alive.
lane_states() {
  printf '%s' "${1:-}" | jq -r '[.v2_session.lanes[]? | "\(.lane):\(.health)\(if (.failure_code // null) != null then "/" + .failure_code else "" end)"] | join(" ")' 2>/dev/null
}
abort_reason() {
  local last="${1:-}" snaplast="${2:-}" running verdict codes seen ok
  # NOT `.running // empty`: jq's alternative operator treats `false` itself as an absent value,
  # so that form silently swallows the exact case this line exists to catch. The probe found it.
  running=$(printf '%s' "$last" | jq -r 'try (if .running == false then "false" else empty end) catch empty' 2>/dev/null)
  if [ "$running" = "false" ]; then printf 'client reports running=false\n'; return 0; fi
  verdict=$(printf '%s' "$snaplast" | jq -r '
      if (.snapshot.terminal_failure // null) != null
        then "session terminal_failure: " + ((.snapshot.terminal_failure | tostring)[0:140])
      elif ((.v2_session.status // "active") != "active")
        then "v2 session status=" + (.v2_session.status | tostring)
             + (if (.v2_session.terminal_reason // null) != null
                  then " reason=" + (.v2_session.terminal_reason | tostring) else "" end)
      else empty end' 2>/dev/null)
  if [ -n "$verdict" ]; then printf '%s\n' "$verdict"; return 0; fi
  codes=$(tail -3 "${SNAPSHOT_TSV:-/dev/null}" 2>/dev/null | cut -f2)
  seen=$(printf '%s\n' "$codes" | grep -c '^[0-9][0-9][0-9]$')
  ok=$(printf '%s\n' "$codes" | grep -c '^200$')
  if [ "$seen" -ge 3 ] && [ "$ok" -eq 0 ]; then
    printf 'snapshot poll refused %s times in a row: %s\n' "$seen" "$(printf '%s' "$codes" | tr '\n' ' ')"
  fi
  return 0
}
# <<< soak-abort-decision

echo "== step 9: the soak - one utterance per ${UTTERANCE_INTERVAL}s for ${SOAK_SECONDS}s"
LINES=(
  "$VOICE_A|Minute one. Opening the long running transcription soak for today."
  "$VOICE_B|Minute two. Both capture lanes are streaming at sixteen kilohertz."
  "$VOICE_A|Minute three. The transcript should keep advancing between these utterances."
  "$VOICE_B|Minute four. Nothing is written to disk, only counts and timings leave the machine."
  "$VOICE_A|Minute five. The view authority is derived from the session, not from a fixed clock."
  "$VOICE_B|Minute six. A quiet minute still carries accepted audio on both lanes."
  "$VOICE_A|Minute seven. The endpointer freezes a span at the hard cap or at silence."
  "$VOICE_B|Minute eight. Halfway through the soak and the session is still active."
  "$VOICE_A|Minute nine. The portal keeps polling the snapshot and the event stream."
  "$VOICE_B|Minute ten. The helper lease renews on every heartbeat from the client."
  "$VOICE_A|Minute eleven. No operator input is required anywhere in this run."
  "$VOICE_B|Minute twelve. The outbox retains every frame until the server acknowledges it."
  "$VOICE_A|Minute thirteen. Three minutes remain before the fifteen minute boundary."
  "$VOICE_B|Minute fourteen. The old fixed expiry would have refused the next request."
  "$VOICE_A|Minute fifteen. Crossing the boundary that the fixed nine hundred second expiry set."
  "$VOICE_B|Minute sixteen. Past the boundary, and the same view authority still answers."
  "$VOICE_A|Minute seventeen. Closing the soak and stopping the capture cleanly."
)
T_SOAK_START=$(now)
echo "soak_start=$T_SOAK_START room_window_minutes=$ROOM_WINDOW_MINUTES"
i=0
ABORT=
POST900_DONE=no
while :; do
  el=$(perl -e "printf '%.0f', $(now)-$T_SOAK_START")
  [ "$el" -ge "$SOAK_SECONDS" ] && break
  minute=$(( i + 1 ))
  if printf ',%s,' "$ROOM_WINDOW_MINUTES" | grep -q ",$minute,"; then
    # The room window. This host says nothing; whatever the microphone lane hears is its own
    # content. Iteration 12 measured that a remote speaker does NOT reach this microphone, so a
    # room window here is a QUIET minute unless a person is present - which is exactly the
    # "periodic accepted audio" the clause asks about, and it is recorded as such rather than
    # promised as a second speaker.
    phase_begin "room-window-$minute" microphone "$MARKER_ROOM"
    touch "$OUT/room-open"
    echo "ROOM_WINDOW_OPEN minute=$minute t=$(now) expect_marker=$MARKER_ROOM"
    phase_end
    rm -f "$OUT/room-open"
  else
    idx=$(( i % ${#LINES[@]} ))
    voice=${LINES[$idx]%%|*}
    text=${LINES[$idx]#*|}
    phase_begin "program-$minute" system "$MARKER_SYSTEM"
    say -v "$voice" "$text"
    # The marker alone, repeated, at a slow rate - measured twice (F1's "pineapple" -> "Hi
    # Apple"; the canary losing "umbrella"), a rare noun buried in a fluent sentence is reliably
    # rewritten by the decoder's language model.
    if [ "$minute" = 1 ] || [ "$minute" = 9 ] || [ "$minute" = 17 ]; then
      say -v "$VOICE_A" -r 130 "$MARKER_SYSTEM. $MARKER_SYSTEM. $MARKER_SYSTEM."
    fi
    phase_end
  fi
  last=$(tail -1 "$OUT/status.tsv" 2>/dev/null | cut -f2)
  snaplast=$(tail -1 "$OUT/snapshot.tsv" 2>/dev/null | cut -f3-)
  echo "minute=$minute at=+${el}s status=$(printf '%s' "$last" | cut -c1-200)"
  echo "                 snapshot=$(printf '%s' "$snaplast" | cut -c1-200)"
  echo "                 lanes=$(lane_states "$snaplast")"
  ABORT=$(abort_reason "$last" "$snaplast")
  if [ -n "$ABORT" ]; then echo "ABORT at +${el}s: $ABORT"; break; fi
  i=$((i+1))
  target=$(( i * UTTERANCE_INTERVAL ))
  el=$(perl -e "printf '%.0f', $(now)-$T_SOAK_START")
  rest=$(( target - el ))
  [ "$rest" -gt 0 ] && sleep "$rest"
  # The clause is "after minute 15", and the retired fixed expiry was 900 s. Check the authority
  # the moment it crosses that age, not only at the end of the soak: F3's single post-run check
  # landed 125 s late, which is why that run could not say whether the token was refused at 900 s
  # or by the session dying.
  if [ "$POST900_DONE" = no ]; then
    age=$(perl -e "printf '%.0f', $(now)-$T_START")
    if [ "$age" -ge "$VIEW_CLAUSE_AGE" ]; then POST900_DONE=yes; check_view post900; fi
  fi
done
T_SOAK_END=$(now)
echo "soak_end=$T_SOAK_END soak_seconds=$(perl -e "printf '%.1f', $T_SOAK_END-$T_SOAK_START") utterances=$i"

echo "== step 10: the clause - the SAME view authority, after minute 15"
check_view post15

echo "== step 11: status and latency while still running"
"$CLI" status > "$OUT/status-final.json" 2>&1
jq -c '{ok, running, lanes, publishedFrameCount, outboxRetainedFrames, outboxDegradation, pumpFailure, sessionRefusal}' < "$OUT/status-final.json"
"$CLI" latency > "$OUT/latency-final.json" 2>&1
jq -c '.latency' < "$OUT/latency-final.json"

echo "== step 12: clean stop, then the SAME authority immediately after"
T_STOP=$(now)
"$CLI" stop > "$OUT/stop.json" 2>&1; echo "stop_rc=$? t_stop=$T_STOP"
jq -c '{ok, running, lanes, publishedFrameCount, outboxRetainedFrames, sessionRefusal}' < "$OUT/stop.json"
check_view post-stop
echo "revoke_latency_s=$(perl -e "printf '%.1f', $(tail -1 "$OUT/view-checks.tsv" | cut -f2)-$T_STOP")"
"$CLI" latency > "$OUT/latency-after-stop.json" 2>&1
jq -c '.latency' < "$OUT/latency-after-stop.json"

sleep 6
kill "$POLLER" "$SPOLLER" 2>/dev/null
wait "$POLLER" "$SPOLLER" 2>/dev/null

echo "== step 13: restore the audio topology this run changed"
restore_audio
snap_audio | tee "$OUT/topology-after.txt"

echo "== step 14: hygiene - clear the pasteboard, drop the token"
pbcopy < /dev/null
TOK=
echo "pasteboard_cleared=yes pasteboard_len=$(pbpaste | wc -c | tr -d ' ')"

cat > "$OUT/times.env" <<EOT
T_START=$T_START
T_AUDIO0=$T_AUDIO0
T_HANDOFF=$T_HANDOFF
T_SOAK_START=$T_SOAK_START
T_SOAK_END=$T_SOAK_END
T_STOP=$T_STOP
MARKER_SYSTEM=$MARKER_SYSTEM
MARKER_ROOM=$MARKER_ROOM
OUTPUT_MODE=$OUTPUT_MODE
ROOM_WINDOW_MINUTES=$ROOM_WINDOW_MINUTES
VIEW_CLAUSE_AGE=$VIEW_CLAUSE_AGE
SID=$SID
LABEL=$LABEL
UTTERANCES=$i
ABORT=${ABORT:-none}
EOT
echo "== done; evidence in $OUT"
cat "$OUT/phases.tsv"
