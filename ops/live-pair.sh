#!/bin/bash
#
# Mint one live pairing payload on the server and print it once.
#
# Pairing has to start here: `issue_pairing` refuses any peer that is not loopback, so there
# is no remote way to mint a code, by design. The operator runs this on the server and relays
# the one line it prints to the Mac over the SSH channel they already have.
#
# The payload is a secret with a 300-second, single-use life. This tool therefore:
#
#   * prints it exactly once, on its own `payload:` line, and writes it nowhere — no temp
#     file, no log, no argument list, no shell trace. Nothing else the tool prints is secret.
#   * cross-checks the certificate digest the *running service* embedded in the payload
#     against the certificate file on disk, and refuses to print anything when they differ.
#     That difference means the service is still serving material that was rotated away, which
#     would otherwise surface as an unexplained pinning failure on the Mac.
#   * refuses any URL that is not loopback before it sends anything, so a mistyped host cannot
#     put a mint request on the network.
#
# `curl -k` is deliberate and is not a weakened posture: this connection is to 127.0.0.1, and
# the certificate is then verified by exact digest against the operator's own file — a
# stronger check on this hop than PKI, which the loopback name is not even in the SANs for.
#
# Usage:
#   ops/live-pair.sh [--dry-run] [--url https://127.0.0.1:7861] [--cert PATH] [--timeout N]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ops/moss-ops-lib.sh
. "${SCRIPT_DIR}/moss-ops-lib.sh"

LIVE_DIR="${MOSS_LIVE_DIR:-${HOME}/.local/share/moss-transcribe-diarize/live}"
# Domain contract (prd.md): the live service is TLS on 7861; 7860 stays plaintext batch.
URL="https://127.0.0.1:7861"
CERT="${LIVE_DIR}/live.crt"
TIMEOUT=15
# Domain contract (live_auth.PAIRING_TTL_SECONDS / PAIRING_PAYLOAD_PREFIX).
PAYLOAD_PREFIX="mtd1"

usage() {
    sed -n '3,26p' "${BASH_SOURCE[0]}" | sed -e 's/^#[[:space:]]\{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) MOSS_TOOL_DRY_RUN=1 ;;
        --url) URL="${2:?--url needs a URL}"; shift ;;
        --cert) CERT="${2:?--cert needs a path}"; shift ;;
        --timeout) TIMEOUT="${2:?--timeout needs seconds}"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1 (try --help)" ;;
    esac
    shift
done

require_cmd curl openssl awk sed tr

case "$TIMEOUT" in
    "" | *[!0-9]*) die "--timeout must be a whole number of seconds: ${TIMEOUT}" ;;
esac
[ "$TIMEOUT" -ge 1 ] || die "--timeout must be at least 1 second: ${TIMEOUT}"

# --- the URL is checked before anything is sent --------------------------------------------
case "$URL" in
    https://*) ;;
    *) die "refusing ${URL}: the live service is TLS-only" ;;
esac
AUTHORITY="${URL#https://}"
AUTHORITY="${AUTHORITY%%/*}"
case "${URL#https://}" in
    "$AUTHORITY" | "${AUTHORITY}/") ;;
    *) die "refusing ${URL}: pass the service origin only, without a path" ;;
esac
URL="https://${AUTHORITY}"
HOST="${AUTHORITY}"
case "$HOST" in
    \[*\]*) HOST="${HOST#[}"; HOST="${HOST%%]*}" ;;
    *:*) HOST="${HOST%%:*}" ;;
esac
case "$HOST" in
    localhost | ::1 | 0:0:0:0:0:0:0:1) ;;
    127.*)
        private_live_ipv4 "$HOST" || die "refusing ${HOST}: not a usable loopback address"
        ;;
    *) die "refusing ${HOST}: minting a pairing payload requires a loopback peer, so this must run on the server" ;;
esac

[ -f "$CERT" ] ||
    die "certificate not found: ${CERT} (the payload can only be checked against the material the service serves)"
CERT_PIN="$(certificate_pin "$CERT")"
[ -n "$CERT_PIN" ] || die "could not read a certificate digest from ${CERT}"

plan "POST ${URL}/api/live/pairing-codes from this host, which is the only peer allowed to mint"
plan "check the certificate digest in the minted payload against ${CERT}"
plan "print the payload once on stdout; it is a secret, expires in 300 s, and works once"

if dry_run; then
    rollback "none needed: an unused payload expires in 300 s. Once a device has paired, revoke it with curl -sk -X DELETE '${URL}/api/live/devices/<device-id>'"
    evidence "url" "$URL"
    evidence "certificate" "$CERT"
    evidence "pin" "$CERT_PIN"
    exit 0
fi

rollback "curl -sk -X DELETE '${URL}/api/live/devices/<device-id>' after the Mac pairs; an unused payload just expires in 300 s"

# The body carries the secret, so it stays in a shell variable: no -o file, no tee, no log.
# `-w` appends the status code on its own last line.
RESPONSE="$(curl -sS -k --max-time "$TIMEOUT" -X POST -H 'Accept: application/json' \
    -w '\n%{http_code}' "${URL}/api/live/pairing-codes")" ||
    die "could not reach ${URL}/api/live/pairing-codes (is the live service running on this host?)"

STATUS="${RESPONSE##*$'\n'}"
BODY="${RESPONSE%$'\n'*}"
[ "$STATUS" = "200" ] ||
    die "the live service answered ${STATUS} instead of 200; pairing was not minted"

PAYLOAD=""
if [[ "$BODY" =~ \"pairing_payload\"[[:space:]]*:[[:space:]]*\"([^\"]+)\" ]]; then
    PAYLOAD="${BASH_REMATCH[1]}"
fi
[ -n "$PAYLOAD" ] || die "the live service did not return a pairing payload"

EXPIRES_AT=""
if [[ "$BODY" =~ \"expires_at\"[[:space:]]*:[[:space:]]*([0-9]+(\.[0-9]+)?) ]]; then
    EXPIRES_AT="${BASH_REMATCH[1]}"
fi

# `<prefix>.<secret>.<certificate digest>` — only the middle field is the secret.
PAYLOAD_PIN="${PAYLOAD##*.}"
case "$PAYLOAD" in
    "${PAYLOAD_PREFIX}."*"."*) ;;
    *) die "the minted payload is not in the ${PAYLOAD_PREFIX} pairing format" ;;
esac
[ "$PAYLOAD_PIN" = "$CERT_PIN" ] ||
    die "the running service is serving a certificate whose digest is ${PAYLOAD_PIN}, but ${CERT} hashes to ${CERT_PIN}; restart the live service on the current certificate before pairing"

TTL="unknown"
if [ -n "$EXPIRES_AT" ]; then
    TTL="$(awk -v expires="$EXPIRES_AT" -v now="$(date -u +%s)" 'BEGIN { printf "%d", expires - now }')"
fi

evidence "url" "$URL"
evidence "certificate" "$CERT"
evidence "pin" "$CERT_PIN"
evidence "payload_matches_certificate" "true"
evidence "expires_in_seconds" "$TTL"
evidence "single_use" "true"
printf 'payload: %s\n' "$PAYLOAD"
