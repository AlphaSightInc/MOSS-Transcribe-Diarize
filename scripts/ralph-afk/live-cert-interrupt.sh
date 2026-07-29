#!/bin/bash
# Ralph F2 - THE 5-SECOND NETWORK INTERRUPTION. Runs ON THE LIVE SERVER, inside WSL.
#
# The PRD's 300 s locked certification names "a 5-second network interruption" among its
# scenarios, and neither live-canary.sh nor live-soak.sh has ever produced one. This is the
# instrument for it, and the mechanism was chosen deliberately rather than by convenience
# (run 20260729-025318 iteration 10):
#
#   REJECTED - dropping the tailnet on the capture Mac. There is no passwordless sudo there,
#     `tailscale` is not on PATH, and ssh to that host RIDES the tailnet, so a client-side drop
#     would strand it mid-run behind a recovery path that may need GUI auth.
#   REJECTED - restarting or stopping the live service. The live session lives in that process's
#     memory; a restart destroys it. That is a server crash, not a network interruption, and it
#     tests nothing the clause asks about.
#   REJECTED - kill -STOP / -CONT on the live process. It does produce client timeouts, but the
#     server then RECEIVES and processes every frame after CONT, so "the network dropped it" and
#     "the server got it late" become indistinguishable in the evidence - and the clause is about
#     audio the client must retain BECAUSE it never arrived.
#   CHOSEN - drop inbound TCP to the live port at the server for exactly $DURATION seconds.
#     Packets are dropped, so the server never sees them and the client's outbox must retain and
#     replay. The live PROCESS is untouched, so the SESSION SURVIVES the interruption - which is
#     what makes the rest of the run measurable at all.
#
# Three properties this file is built around, each of which cost something to learn:
#
#   1. `! -i lo` - the server's own loopback path (ops/live-pair.sh, a local descriptor fetch)
#      keeps working through the window. A blanket dport rule would also cut the host off from
#      its own service, which is not what "the network dropped" means.
#   2. `--dport $PORT` only. The batch service on 7860 is a PRD acceptance clause in its own
#      right ("batch service unharmed") and must be provably untouched; this rule cannot reach it.
#   3. IT DELETES ITSELF, from a detached process, in a loop that keeps deleting until the rule
#      is gone. An orchestrator that dies mid-window must not leave the live service unreachable.
#      That is why the work happens in a `setsid nohup` child and not in this script's own body.
#
# Usage (from the orchestrator, over ssh into WSL):
#     bash live-cert-interrupt.sh --delay <sec> --duration <sec> [--port 7861] [--out <path>]
#
# It returns as soon as the job is ARMED and prints the arming record. The window itself happens
# later, in the detached child. Fetch $OUT afterwards - that file, not this script's stdout, is
# the authoritative record of when the network was actually down. It is written by the detached
# child, which runs under sudo, so $OUT is ROOT-OWNED: readable by anyone (it holds only
# timestamps and iptables chain text, never a secret) but removable only with sudo. Measured
# once, so the next reader does not file it as a permissions bug.
#
# Arm BEFORE launching the capture driver, with a delay that clears the driver's setup. Then
# nothing after launch depends on the orchestrator still being alive - the same reason the soak
# driver is nohup'd on the Mac (run 20260728-181020 iteration 21, and iteration 8 of this run,
# where a dead orchestrator would otherwise have thrown away the gate).
set -uo pipefail

DELAY=210
DURATION=5
PORT=7861
OUT=/tmp/ralph-cert-interrupt.json

while [ $# -gt 0 ]; do
  case "$1" in
    --delay)    DELAY="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --port)     PORT="$2"; shift 2 ;;
    --out)      OUT="$2"; shift 2 ;;
    *) echo "FATAL: unknown argument $1" >&2; exit 2 ;;
  esac
done

case "$DURATION" in ''|*[!0-9]*) echo "FATAL: --duration must be whole seconds" >&2; exit 2 ;; esac
case "$DELAY"    in ''|*[!0-9]*) echo "FATAL: --delay must be whole seconds"    >&2; exit 2 ;; esac
if [ "$DURATION" -lt 1 ] || [ "$DURATION" -gt 30 ]; then
  # A window longer than the 30 s helper lease stops being an interruption and becomes a
  # different experiment: the lease expires and the server ends the meeting on purpose.
  echo "FATAL: --duration must be 1..30 s (the helper lease is 30 s)" >&2; exit 2
fi

RULE_ARGS=(INPUT ! -i lo -p tcp --dport "$PORT" -j DROP)

if ! sudo -n true 2>/dev/null; then
  echo "FATAL: passwordless sudo is required to insert the DROP rule" >&2; exit 3
fi
if ! sudo -n iptables -S INPUT >/dev/null 2>&1; then
  echo "FATAL: iptables is not usable here" >&2; exit 3
fi

# Refuse to arm on top of an existing identical rule: a second armed job would delete the first
# job's rule early and both reports would then be wrong about what the client saw.
if sudo -n iptables -C "${RULE_ARGS[@]}" 2>/dev/null; then
  echo "FATAL: the DROP rule for tcp/$PORT is ALREADY PRESENT - refusing to arm on top of it." >&2
  echo "       remove it first:  sudo iptables -D ${RULE_ARGS[*]}" >&2
  exit 4
fi

CHAIN_BEFORE=$(sudo -n iptables -S INPUT 2>&1 | tr '\n' ';')
T_ARM=$(date +%s.%N)

# The window, in a detached self-limiting child. Every timestamp it records is taken with
# CLOCK_MONOTONIC as well as the wall clock: this host's wall clock steps ~1.5 s BACKWARDS every
# ~32.3 s (candidate 56, measured), so a wall-clock difference here could report a 5 s outage as
# 3.5 s - the exact class of defect Phase P was authorized to remove from the product. An
# instrument that measures a duration on this host's wall clock would be repeating it.
setsid nohup sudo -n bash -c '
  set -u
  OUT="$1"; DELAY="$2"; DURATION="$3"; PORT="$4"; CHAIN_BEFORE="$5"; T_ARM="$6"
  mono() { awk "{print \$1}" /proc/uptime; }
  sleep "$DELAY"
  M0=$(mono); W0=$(date +%s.%N)
  iptables -I INPUT ! -i lo -p tcp --dport "$PORT" -j DROP
  CHAIN_DURING=$(iptables -S INPUT 2>&1 | tr "\n" ";")
  sleep "$DURATION"
  n=0
  while iptables -C INPUT ! -i lo -p tcp --dport "$PORT" -j DROP 2>/dev/null && [ $n -lt 20 ]; do
    iptables -D INPUT ! -i lo -p tcp --dport "$PORT" -j DROP
    n=$((n+1))
  done
  M1=$(mono); W1=$(date +%s.%N)
  CHAIN_AFTER=$(iptables -S INPUT 2>&1 | tr "\n" ";")
  STILL=no; iptables -C INPUT ! -i lo -p tcp --dport "$PORT" -j DROP 2>/dev/null && STILL=yes
  printf "{\"port\": %s, \"nominal_delay_s\": %s, \"nominal_duration_s\": %s,
 \"t_arm_wall\": %s, \"t_drop_begin_wall\": %s, \"t_drop_end_wall\": %s,
 \"measured_duration_s\": %.3f, \"wall_duration_s\": %.3f, \"deletes\": %s,
 \"rule_still_present\": \"%s\", \"chain_before\": \"%s\", \"chain_during\": \"%s\",
 \"chain_after\": \"%s\"}\n" \
    "$PORT" "$DELAY" "$DURATION" "$T_ARM" "$W0" "$W1" \
    "$(awk -v a="$M0" -v b="$M1" "BEGIN{print b-a}")" \
    "$(awk -v a="$W0" -v b="$W1" "BEGIN{print b-a}")" \
    "$n" "$STILL" "$CHAIN_BEFORE" "$CHAIN_DURING" "$CHAIN_AFTER" > "$OUT"
' _ "$OUT" "$DELAY" "$DURATION" "$PORT" "$CHAIN_BEFORE" "$T_ARM" >/dev/null 2>&1 < /dev/null &

sleep 0.3
echo "armed=yes port=$PORT delay_s=$DELAY duration_s=$DURATION t_arm=$T_ARM out=$OUT"
echo "chain_before=$CHAIN_BEFORE"
echo "expected_window_wall=$(awk -v a="$T_ARM" -v d="$DELAY" 'BEGIN{printf "%.3f", a+d}')"
echo "rollback_if_anything_looks_wrong: sudo iptables -D ${RULE_ARGS[*]}"
