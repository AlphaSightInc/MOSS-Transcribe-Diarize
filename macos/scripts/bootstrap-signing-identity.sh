#!/bin/bash
#
# Create (or reuse) the project-owned code-signing identity used to sign MOSSCapture.
#
# Why a self-signed identity in a dedicated keychain, and not the login keychain:
#   * m4mbp's login keychain is locked to SSH sessions, so `codesign -s "<login identity>"`
#     fails `errSecInternalComponent` and cannot be scripted.
#   * ad-hoc signing (`codesign -s -`) works, but its designated requirement is cdhash-based,
#     so every rebuild produces a different DR and *invalidates the TCC grants* a human had
#     to click. A certificate-backed identity gives a DR of the form
#     `identifier "…" and certificate leaf = H"…"`, which is identical across rebuilds.
#
# Nothing here needs Apple: no Developer ID, no notarization, no Gatekeeper or SIP change.
# Locally built binaries carry no quarantine attribute.
#
# Acceptance is `codesign`'s exit status and the emitted designated requirement — never
# `security find-identity -v -p codesigning`, which reports *0 valid identities* for a
# self-signed leaf even when signing succeeds.
#
# The keychain password protects only this dedicated keychain (it guards no other secret)
# and is written to a 0600 file. `security` takes it on argv, which is visible to other
# local users via `ps`; that is the documented cost of a scriptable keychain, and the reason
# this identity is never reused for anything else.
#
# Usage:
#   macos/scripts/bootstrap-signing-identity.sh [--dry-run]
#       [--keychain PATH] [--password-file PATH] [--common-name NAME] [--days N]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=macos/scripts/moss-tool-lib.sh
. "${SCRIPT_DIR}/moss-tool-lib.sh"

KEYCHAIN="${HOME}/Library/Keychains/moss-signing.keychain-db"
PASSWORD_FILE="${HOME}/.config/moss-capture/signing-keychain.password"
COMMON_NAME="MOSS Capture Local Signing"
DAYS=3650

usage() {
    sed -n '3,28p' "${BASH_SOURCE[0]}" | sed -e 's/^#[[:space:]]\{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) MOSS_TOOL_DRY_RUN=1 ;;
        --keychain) KEYCHAIN="${2:?--keychain needs a path}"; shift ;;
        --password-file) PASSWORD_FILE="${2:?--password-file needs a path}"; shift ;;
        --common-name) COMMON_NAME="${2:?--common-name needs a name}"; shift ;;
        --days) DAYS="${2:?--days needs a number}"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1 (try --help)" ;;
    esac
    shift
done

require_darwin
require_cmd security codesign shasum awk sed

# System `openssl` (LibreSSL) is preferred: an OpenSSL 3 PKCS#12 uses PBES2 by default,
# which `security import` refuses.
OPENSSL_BIN="${MOSS_OPENSSL:-/usr/bin/openssl}"
[ -x "$OPENSSL_BIN" ] || OPENSSL_BIN="$(command -v openssl || true)"
[ -n "$OPENSSL_BIN" ] && [ -x "$OPENSSL_BIN" ] || die "no usable openssl found (set MOSS_OPENSSL)"

# This tool manages only a keychain it owns. A keychain the login session depends on is
# refused outright — recreating or deleting one would take the user's whole session with it.
assert_tool_owned_keychain() {
    local target="$1" base directory default_keychain
    base="$(basename "$target")"
    directory="$(dirname "$target")"
    case "$base" in
        login.keychain|login.keychain-db|System.keychain|System.keychain-db)
            die "refusing to manage the session keychain: $target" ;;
    esac
    case "$directory" in
        /Library/Keychains|/System/Library/Keychains|/Library/Keychains/*)
            die "refusing to manage a system keychain directory: $directory" ;;
    esac
    default_keychain="$(security default-keychain -d user 2>/dev/null |
        sed -e 's/^[[:space:]]*"//' -e 's/"[[:space:]]*$//' || true)"
    if [ -n "$default_keychain" ] && [ "$default_keychain" = "$target" ]; then
        die "refusing to manage the default keychain: $target"
    fi
}

assert_tool_owned_keychain "$KEYCHAIN"

plan "keychain ${KEYCHAIN} (dedicated; the login keychain is never touched)"
plan "password file ${PASSWORD_FILE}, mode 0600, in a 0700 directory"
plan "reuse the existing identity when a scratch codesign probe already succeeds"
plan "create the keychain with a random password and no auto-lock timeout"
plan "generate a self-signed certificate: openssl req -x509, extendedKeyUsage=critical,codeSigning, ${DAYS} days"
plan "import the PKCS#12 into that keychain with -T /usr/bin/codesign"
plan "security set-key-partition-list -S apple-tool:,apple:,codesign: so codesign runs unattended"
plan "append the keychain to the user keychain search list, keeping every existing entry"
plan "verify by signing a scratch binary with codesign and reading its designated requirement"
plan "never gate on security find-identity: it reports 0 valid identities for a self-signed leaf"

rollback "security delete-keychain '${KEYCHAIN}' && rm -f '${PASSWORD_FILE}'   # also restores the search list"

if dry_run; then
    exit 0
fi

WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/moss-signing.XXXXXX")"
cleanup() { rm -rf "$WORKSPACE"; }
trap cleanup EXIT

read_password() {
    [ -f "$PASSWORD_FILE" ] || die "keychain password file missing: $PASSWORD_FILE"
    cat "$PASSWORD_FILE"
}

# Membership of the user's keychain search list is what makes an identity reachable by
# `codesign` — its `--keychain` flag is accepted and ignored. Every existing entry is kept,
# and the pre-change list is printed as the rollback command before the list is touched.
ensure_in_search_list() {
    local entry
    local -a current=()
    if keychain_in_search_list "$KEYCHAIN"; then
        return 0
    fi
    while IFS= read -r entry; do
        [ -n "$entry" ] && current+=("$entry")
    done < <(user_keychain_search_list)
    rollback "security list-keychains -d user -s $(printf "'%s' " "${current[@]}")"
    security list-keychains -d user -s "${current[@]}" "$KEYCHAIN"
    change "added ${KEYCHAIN} to the user keychain search list"
}

# The only acceptance check: does `codesign` actually sign with this identity?
probe_signs() {
    local password="$1" probe="${WORKSPACE}/probe-$$"
    security unlock-keychain -p "$password" "$KEYCHAIN" >/dev/null 2>&1 || return 1
    keychain_in_search_list "$KEYCHAIN" || return 1
    cp /usr/bin/true "$probe"
    codesign --force --options runtime --timestamp=none \
        --identifier "com.alphasight.moss.capture.signing-probe" \
        --sign "$COMMON_NAME" "$probe" >/dev/null 2>&1 || return 1
    codesign --verify --strict "$probe" >/dev/null 2>&1 || return 1
    designated_requirement "$probe"
}

leaf_sha256() {
    security find-certificate -c "$COMMON_NAME" -p "$KEYCHAIN" 2>/dev/null |
        "$OPENSSL_BIN" x509 -outform DER 2>/dev/null | shasum -a 256 | awk '{print $1}'
}

certificate_not_after() {
    security find-certificate -c "$COMMON_NAME" -p "$KEYCHAIN" 2>/dev/null |
        "$OPENSSL_BIN" x509 -noout -enddate 2>/dev/null | sed -e 's/^notAfter=//'
}

report() {
    local requirement="$1"
    evidence "keychain" "$KEYCHAIN"
    evidence "password_file" "$PASSWORD_FILE"
    evidence "password_file_mode" "$(stat -f '%OLp' "$PASSWORD_FILE")"
    evidence "identity_common_name" "$COMMON_NAME"
    evidence "leaf_sha256" "$(leaf_sha256)"
    evidence "certificate_not_after" "$(certificate_not_after)"
    evidence "in_user_keychain_search_list" "$(keychain_in_search_list "$KEYCHAIN" && echo true || echo false)"
    evidence "probe_designated_requirement" "$requirement"
}

# --- reuse ------------------------------------------------------------------------------
if [ -f "$KEYCHAIN" ] && [ -f "$PASSWORD_FILE" ]; then
    PASSWORD="$(read_password)"
    if REQUIREMENT="$(probe_signs "$PASSWORD")"; then
        unchanged "codesign already signs with '${COMMON_NAME}' from ${KEYCHAIN}"
        report "$REQUIREMENT"
        exit 0
    fi
    # An interrupted earlier run can leave the certificate present but unusable. Repair the
    # one reversible cause (partition list / lock state) before giving up.
    if security find-certificate -c "$COMMON_NAME" "$KEYCHAIN" >/dev/null 2>&1; then
        ensure_in_search_list
        security unlock-keychain -p "$PASSWORD" "$KEYCHAIN" >/dev/null 2>&1 || true
        security set-key-partition-list -S apple-tool:,apple:,codesign: \
            -s -k "$PASSWORD" "$KEYCHAIN" >/dev/null 2>&1 || true
        change "repaired the key partition list on ${KEYCHAIN}"
        if REQUIREMENT="$(probe_signs "$PASSWORD")"; then
            report "$REQUIREMENT"
            exit 0
        fi
        die "keychain ${KEYCHAIN} holds '${COMMON_NAME}' but codesign still fails; run the rollback command above and re-run"
    fi
fi

# --- create -----------------------------------------------------------------------------
mkdir -p "$(dirname "$PASSWORD_FILE")"
chmod 700 "$(dirname "$PASSWORD_FILE")"
if [ ! -f "$PASSWORD_FILE" ]; then
    (
        umask 077
        "$OPENSSL_BIN" rand -base64 32 >"$PASSWORD_FILE"
    )
    chmod 600 "$PASSWORD_FILE"
    change "wrote a new keychain password to ${PASSWORD_FILE} (mode 0600)"
fi
PASSWORD="$(read_password)"

mkdir -p "$(dirname "$KEYCHAIN")"
if [ ! -f "$KEYCHAIN" ]; then
    security create-keychain -p "$PASSWORD" "$KEYCHAIN"
    change "created keychain ${KEYCHAIN}"
fi
# No auto-lock timeout and no lock-on-sleep: an unattended rebuild must not need a human.
security set-keychain-settings "$KEYCHAIN"
security unlock-keychain -p "$PASSWORD" "$KEYCHAIN"

cat >"${WORKSPACE}/openssl.cnf" <<CONFIG
[ req ]
distinguished_name = dn
prompt             = no
x509_extensions    = v3

[ dn ]
CN = ${COMMON_NAME}

[ v3 ]
basicConstraints     = critical,CA:false
keyUsage             = critical,digitalSignature
extendedKeyUsage     = critical,codeSigning
subjectKeyIdentifier = hash
CONFIG

"$OPENSSL_BIN" req -x509 -newkey rsa:2048 -sha256 -days "$DAYS" -nodes \
    -keyout "${WORKSPACE}/key.pem" -out "${WORKSPACE}/cert.pem" \
    -config "${WORKSPACE}/openssl.cnf" >/dev/null 2>&1 ||
    die "openssl could not generate the signing certificate"

"$OPENSSL_BIN" pkcs12 -export -inkey "${WORKSPACE}/key.pem" -in "${WORKSPACE}/cert.pem" \
    -name "$COMMON_NAME" -out "${WORKSPACE}/identity.p12" -passout "pass:${PASSWORD}" \
    >/dev/null 2>&1 || die "openssl could not export the PKCS#12 identity"

security import "${WORKSPACE}/identity.p12" -k "$KEYCHAIN" -P "$PASSWORD" \
    -T /usr/bin/codesign -f pkcs12 >/dev/null
change "imported '${COMMON_NAME}' into ${KEYCHAIN}"

# Without this, every codesign run raises a GUI "allow access" prompt — which an SSH session
# can never answer. `-S` lists the partitions allowed to use the key without prompting.
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$PASSWORD" "$KEYCHAIN" \
    >/dev/null

ensure_in_search_list

if ! REQUIREMENT="$(probe_signs "$PASSWORD")"; then
    die "the identity was imported but codesign still refuses to sign with it"
fi
change "verified codesign signs with '${COMMON_NAME}'"
report "$REQUIREMENT"
