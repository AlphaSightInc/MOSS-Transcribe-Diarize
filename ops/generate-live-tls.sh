#!/bin/bash
#
# Generate the self-signed TLS material the dedicated live service serves on its own port.
#
# The material has one job beyond encryption: its leaf certificate *is* the client's trust
# anchor. `PinnedCertificateURLSessionDelegate` on the Mac compares SHA-256 over the leaf's
# DER bytes and never evaluates a chain, and the server derives the same digest from this
# certificate at startup and stamps it into every pairing payload. So:
#
#   * The pin this tool prints is the exact 64-character lowercase digest the client accepts
#     and the server will advertise. It is read back out of the generated file, both as a DER
#     digest and as `x509 -fingerprint`, and the two must agree before anything is installed.
#   * Regenerating rotates that pin, which invalidates every paired client's stored pin and
#     every outstanding pairing payload. A re-run with the same names therefore prints
#     `unchanged:` and rotates nothing; rotation requires `--rotate`, and the previous pair is
#     moved aside rather than deleted.
#   * The names are flags, not constants: a deployment states its own DNS names and addresses.
#     Addresses are refused unless they are inside the private networks live access admits at
#     all, so this tool cannot mint material for a name the server itself would reject.
#
# The browser is the only party that validates names (the Mac client does not), so the DNS
# names and addresses a human will type into the address bar have to be present here.
#
# Usage:
#   ops/generate-live-tls.sh [--dry-run] [--rotate] --dns NAME [--dns NAME ...]
#       --ip ADDRESS [--ip ADDRESS ...] [--cert PATH] [--key PATH]
#       [--common-name NAME] [--days N] [--min-remaining-days N]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ops/moss-ops-lib.sh
. "${SCRIPT_DIR}/moss-ops-lib.sh"

LIVE_DIR="${MOSS_LIVE_DIR:-${HOME}/.local/share/moss-transcribe-diarize/live}"
CERT="${LIVE_DIR}/live.crt"
KEY="${LIVE_DIR}/live.key"
COMMON_NAME=""
# 825 days is the longest validity a TLS server certificate is accepted with; the browser
# warning this material already carries is about self-signing, not about lifetime.
DAYS=825
MAX_DAYS=825
MIN_REMAINING_DAYS=30
ROTATE=0
DNS_NAMES=()
IP_ADDRESSES=()

usage() {
    sed -n '3,27p' "${BASH_SOURCE[0]}" | sed -e 's/^#[[:space:]]\{0,1\}//'
}

contains() {
    local needle="$1"
    shift
    for value in "$@"; do
        [ "$value" = "$needle" ] || continue
        return 0
    done
    return 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) MOSS_TOOL_DRY_RUN=1 ;;
        --rotate) ROTATE=1 ;;
        --dns)
            name="${2:?--dns needs a name}"
            shift
            valid_dns_name "$name" || {
                if address_like "$name"; then
                    die "--dns got an address: ${name} (pass it with --ip so it becomes an IP name)"
                fi
                die "not a DNS name: ${name}"
            }
            if contains "$name" ${DNS_NAMES[@]+"${DNS_NAMES[@]}"}; then
                die "--dns repeated: ${name}"
            fi
            DNS_NAMES+=("$name")
            ;;
        --ip)
            address="${2:?--ip needs an address}"
            shift
            private_live_ipv4 "$address" ||
                die "refusing ${address}: live access admits only loopback, RFC1918 and 100.64.0.0/10 IPv4 peers"
            if contains "$address" ${IP_ADDRESSES[@]+"${IP_ADDRESSES[@]}"}; then
                die "--ip repeated: ${address}"
            fi
            IP_ADDRESSES+=("$address")
            ;;
        --cert) CERT="${2:?--cert needs a path}"; shift ;;
        --key) KEY="${2:?--key needs a path}"; shift ;;
        --common-name) COMMON_NAME="${2:?--common-name needs a name}"; shift ;;
        --days) DAYS="${2:?--days needs a count}"; shift ;;
        --min-remaining-days) MIN_REMAINING_DAYS="${2:?--min-remaining-days needs a count}"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1 (try --help)" ;;
    esac
    shift
done

require_cmd openssl awk sed grep tr date mktemp

# --- inputs are validated before the plan, so a dry run refuses what a real run would ------
[ "${#DNS_NAMES[@]}" -gt 0 ] || die "at least one --dns is required: the browser matches names, not addresses"
[ "${#IP_ADDRESSES[@]}" -gt 0 ] || die "at least one --ip is required: the server is reached by address on the tailnet and the LAN"
case "$DAYS" in
    "" | *[!0-9]*) die "--days must be a whole number of days: ${DAYS}" ;;
esac
[ "$DAYS" -ge 1 ] || die "--days must be at least 1: ${DAYS}"
[ "$DAYS" -le "$MAX_DAYS" ] || die "--days must not exceed ${MAX_DAYS}: ${DAYS}"
case "$MIN_REMAINING_DAYS" in
    "" | *[!0-9]*) die "--min-remaining-days must be a whole number of days: ${MIN_REMAINING_DAYS}" ;;
esac
[ "$CERT" != "$KEY" ] || die "--cert and --key must be different paths: ${CERT}"
[ -z "$COMMON_NAME" ] || valid_dns_name "$COMMON_NAME" || die "not a DNS name: ${COMMON_NAME}"
[ -n "$COMMON_NAME" ] || COMMON_NAME="${DNS_NAMES[0]}"
contains "$COMMON_NAME" "${DNS_NAMES[@]}" ||
    die "--common-name ${COMMON_NAME} is not one of the --dns names, so a browser would not match it"

REQUESTED_SANS=""
for name in "${DNS_NAMES[@]}"; do
    REQUESTED_SANS="${REQUESTED_SANS}DNS:${name}
"
done
for address in "${IP_ADDRESSES[@]}"; do
    REQUESTED_SANS="${REQUESTED_SANS}IP:${address}
"
done
REQUESTED_SANS="$(printf '%s' "$REQUESTED_SANS" | LC_ALL=C sort)"
SAN_SUMMARY="$(printf '%s' "$REQUESTED_SANS" | tr '\n' ',' | sed -e 's/,$//')"

CERT_DIR="$(dirname "$CERT")"
KEY_DIR="$(dirname "$KEY")"
STAMP="$(utc_stamp)"

plan "generate a self-signed ${DAYS}-day certificate for CN=${COMMON_NAME} with exactly ${SAN_SUMMARY}"
plan "read the generated names, key pairing and pin back out of the file before installing it"
plan "install the certificate at ${CERT} mode 0644 and the private key at ${KEY} mode 0600"
plan "print the pin the Mac client must store; pairing payloads minted before this run stop working"
if [ "$ROTATE" = "1" ]; then
    plan "--rotate: move any existing certificate and key aside to <path>.backup-${STAMP}"
else
    plan "leave an existing certificate that already carries these names alone (rotation needs --rotate)"
fi

if dry_run; then
    rollback "rm -f '${CERT}' '${KEY}'   # plus 'mv <path>.backup-<utc> <path>' when --rotate creates one"
    exit 0
fi

# --- an existing pair is inspected before it is touched ------------------------------------
[ ! -L "$CERT" ] || die "refusing to write over a symlink: ${CERT}"
[ ! -L "$KEY" ] || die "refusing to write over a symlink: ${KEY}"

reject_or_rotate() {
    local reason="$1"
    [ "$ROTATE" = "1" ] ||
        die "${reason}; re-run with --rotate to replace it, then re-pair every client with the new pin"
    # Announced as a plan step, not as a change: nothing has moved yet, and the `rollback:`
    # line still has to be printed before the first mutation.
    plan "rotate because ${reason}"
}

if [ -f "$CERT" ] && [ -f "$KEY" ]; then
    INSTALLED_SANS="$(certificate_sans "$CERT" | LC_ALL=C sort)"
    INSTALLED_CN="$(openssl x509 -in "$CERT" -noout -subject 2>/dev/null | sed -e 's/.*CN[[:space:]]*=[[:space:]]*//' -e 's/,.*//')"
    if [ "$INSTALLED_SANS" != "$REQUESTED_SANS" ]; then
        reject_or_rotate "${CERT} carries $(printf '%s' "$INSTALLED_SANS" | tr '\n' ',' | sed -e 's/,$//') instead of ${SAN_SUMMARY}"
    elif [ "$INSTALLED_CN" != "$COMMON_NAME" ]; then
        reject_or_rotate "${CERT} has CN=${INSTALLED_CN} instead of CN=${COMMON_NAME}"
    elif ! openssl x509 -in "$CERT" -noout -checkend "$((MIN_REMAINING_DAYS * 86400))" >/dev/null 2>&1; then
        reject_or_rotate "${CERT} expires within ${MIN_REMAINING_DAYS} days"
    elif [ "$(certificate_public_key "$CERT")" != "$(private_key_public_key "$KEY")" ]; then
        reject_or_rotate "${KEY} does not belong to ${CERT}"
    else
        # Not rotating is the point: the installed pin is what every paired client stores.
        unchanged "${CERT} already carries ${SAN_SUMMARY} and its key still matches"
        evidence "certificate" "$CERT"
        evidence "private_key" "$KEY"
        evidence "pin" "$(certificate_pin "$CERT")"
        evidence "subject_common_name" "$INSTALLED_CN"
        evidence "subject_alt_names" "$SAN_SUMMARY"
        evidence "not_after" "$(openssl x509 -in "$CERT" -noout -enddate | sed -e 's/^notAfter=//')"
        evidence "certificate_mode" "$(file_mode "$CERT")"
        evidence "private_key_mode" "$(file_mode "$KEY")"
        evidence "rotated" "false"
        exit 0
    fi
elif [ -f "$CERT" ] || [ -f "$KEY" ]; then
    reject_or_rotate "only one of ${CERT} and ${KEY} exists, so the pair on disk cannot be served"
fi

# --- generate into scratch space; nothing lands until every read-back check passes ---------
WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/moss-live-tls.XXXXXX")"
cleanup() { rm -rf "$WORKSPACE"; }
trap cleanup EXIT

{
    printf '%s\n' "[req]" "distinguished_name=dn" "x509_extensions=v3_req" "prompt=no"
    printf '%s\n' "[dn]" "CN=${COMMON_NAME}"
    printf '%s\n' "[v3_req]" "basicConstraints=critical,CA:FALSE" \
        "keyUsage=critical,digitalSignature,keyEncipherment" \
        "extendedKeyUsage=critical,serverAuth" \
        "subjectKeyIdentifier=hash" \
        "subjectAltName=@alt_names"
    printf '%s\n' "[alt_names]"
    index=0
    for name in "${DNS_NAMES[@]}"; do
        index=$((index + 1))
        printf 'DNS.%s=%s\n' "$index" "$name"
    done
    index=0
    for address in "${IP_ADDRESSES[@]}"; do
        index=$((index + 1))
        printf 'IP.%s=%s\n' "$index" "$address"
    done
} >"${WORKSPACE}/openssl.cnf"

NEW_CERT="${WORKSPACE}/live.crt"
NEW_KEY="${WORKSPACE}/live.key"
umask 077
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days "$DAYS" \
    -config "${WORKSPACE}/openssl.cnf" -extensions v3_req \
    -keyout "$NEW_KEY" -out "$NEW_CERT" >/dev/null 2>&1 ||
    die "openssl could not generate the certificate (config: ${WORKSPACE}/openssl.cnf)"

# What was asked for is an input; what the file says is evidence.
GENERATED_SANS="$(certificate_sans "$NEW_CERT" | LC_ALL=C sort)"
[ "$GENERATED_SANS" = "$REQUESTED_SANS" ] ||
    die "the generated certificate carries $(printf '%s' "$GENERATED_SANS" | tr '\n' ',' | sed -e 's/,$//') instead of ${SAN_SUMMARY}"
openssl x509 -in "$NEW_CERT" -noout -text 2>/dev/null | grep -q 'TLS Web Server Authentication' ||
    die "the generated certificate is not usable for server authentication"
[ "$(certificate_public_key "$NEW_CERT")" = "$(private_key_public_key "$NEW_KEY")" ] ||
    die "the generated key does not belong to the generated certificate"
PIN="$(certificate_pin "$NEW_CERT")"
FINGERPRINT_PIN="$(certificate_fingerprint_pin "$NEW_CERT")"
[ "$PIN" = "$FINGERPRINT_PIN" ] ||
    die "the DER digest ${PIN} and the reported fingerprint ${FINGERPRINT_PIN} disagree"
case "$PIN" in
    [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
    *) die "the pin is not 64 lowercase hex characters, which is the only form the client accepts: ${PIN}" ;;
esac

# --- install ------------------------------------------------------------------------------
BACKUP_CERT="none"
BACKUP_KEY="none"
if [ -f "$CERT" ]; then
    BACKUP_CERT="${CERT}.backup-${STAMP}"
fi
if [ -f "$KEY" ]; then
    BACKUP_KEY="${KEY}.backup-${STAMP}"
fi

ROLLBACK="rm -f '${CERT}' '${KEY}'"
[ "$BACKUP_CERT" = "none" ] || ROLLBACK="${ROLLBACK} && mv '${BACKUP_CERT}' '${CERT}'"
[ "$BACKUP_KEY" = "none" ] || ROLLBACK="${ROLLBACK} && mv '${BACKUP_KEY}' '${KEY}'"
rollback "$ROLLBACK"

for directory in "$CERT_DIR" "$KEY_DIR"; do
    if [ -d "$directory" ]; then
        mode="$(file_mode "$directory")"
        case "$mode" in
            *[2367]) die "${directory} is group- or world-writable (${mode}); the private key there could be replaced" ;;
            *[2367]?) die "${directory} is group- or world-writable (${mode}); the private key there could be replaced" ;;
        esac
    else
        mkdir -p -m 0700 "$directory"
        change "created ${directory} mode 0700"
    fi
done

[ "$BACKUP_CERT" = "none" ] || { mv "$CERT" "$BACKUP_CERT"; change "moved the previous certificate aside to ${BACKUP_CERT}"; }
[ "$BACKUP_KEY" = "none" ] || { mv "$KEY" "$BACKUP_KEY"; change "moved the previous private key aside to ${BACKUP_KEY}"; }

cp "$NEW_KEY" "${KEY}.incoming-${STAMP}"
chmod 0600 "${KEY}.incoming-${STAMP}"
mv "${KEY}.incoming-${STAMP}" "$KEY"
cp "$NEW_CERT" "${CERT}.incoming-${STAMP}"
chmod 0644 "${CERT}.incoming-${STAMP}"
mv "${CERT}.incoming-${STAMP}" "$CERT"
change "installed ${CERT} and ${KEY}"

# --- prove what landed, not what was generated --------------------------------------------
[ "$(certificate_pin "$CERT")" = "$PIN" ] || die "the installed certificate does not carry the generated pin: ${CERT}"
[ "$(certificate_public_key "$CERT")" = "$(private_key_public_key "$KEY")" ] ||
    die "the installed key does not belong to the installed certificate"
[ "$(file_mode "$KEY")" = "600" ] || die "the installed private key is mode $(file_mode "$KEY"), expected 600"
[ "$(file_mode "$CERT")" = "644" ] || die "the installed certificate is mode $(file_mode "$CERT"), expected 644"

evidence "certificate" "$CERT"
evidence "private_key" "$KEY"
evidence "pin" "$PIN"
evidence "subject_common_name" "$COMMON_NAME"
evidence "subject_alt_names" "$SAN_SUMMARY"
evidence "not_before" "$(openssl x509 -in "$CERT" -noout -startdate | sed -e 's/^notBefore=//')"
evidence "not_after" "$(openssl x509 -in "$CERT" -noout -enddate | sed -e 's/^notAfter=//')"
evidence "validity_days" "$DAYS"
evidence "certificate_mode" "$(file_mode "$CERT")"
evidence "private_key_mode" "$(file_mode "$KEY")"
evidence "backup_certificate" "$BACKUP_CERT"
evidence "backup_private_key" "$BACKUP_KEY"
evidence "rotated" "true"
