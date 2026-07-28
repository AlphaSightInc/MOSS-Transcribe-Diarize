#!/bin/bash
#
# Build, bundle and sign MOSSCapture.app plus the mtd-capture CLI into build output.
#
# This tool never installs anything: it writes only under --output (build output, gitignored),
# so a build can never disturb an installed app or the TCC grants attached to it. Installing
# is install-app.sh's job, and it consumes this tool's evidence file.
#
# Two contracts this tool enforces, both learned the hard way:
#
#   * The *signing* entitlements are derived from the tracked entitlements, with
#     `keychain-access-groups` dropped. The tracked file declares
#     `$(AppIdentifierPrefix)com.alphasight.moss.capture`, a literal SwiftPM never
#     substitutes, and a self-signed identity has no Team ID to substitute anyway. The
#     Keychain secret store is dormant (the file store is the production default), so signing
#     that entitlement would assert an identity the certificate cannot satisfy. The tracked
#     file keeps the key as documentation of intent for a future real Team ID.
#
#   * Acceptance reads the *embedded* entitlements and designated requirement back out of the
#     signature with `codesign -d`. What was passed in on the command line is an input, not
#     evidence.
#
# Usage:
#   macos/scripts/build-app.sh [--dry-run] [--configuration release|debug] [--output DIR]
#       [--sign-identity NAME|-] [--keychain PATH] [--password-file PATH] [--no-build]
#
#   --sign-identity -   ad-hoc signs. Useful for a scratch bundle, but its designated
#                       requirement is cdhash-based, so a rebuild invalidates TCC grants.
#                       A real install uses the identity from bootstrap-signing-identity.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=macos/scripts/moss-tool-lib.sh
. "${SCRIPT_DIR}/moss-tool-lib.sh"

PACKAGE_ROOT="$(cd "${SCRIPT_DIR}/../MOSSCapture" && pwd)"
RESOURCES="${PACKAGE_ROOT}/Resources"

# Domain contract (prd.md): the bundle identifier and app path are fixed, not incidental.
BUNDLE_IDENTIFIER="com.alphasight.moss.capture"
APP_EXECUTABLE="MOSSCaptureApp"
CLI_EXECUTABLE="mtd-capture"
EVIDENCE_SCHEMA="moss-capture-build-evidence.v1"
USAGE_DESCRIPTION_KEYS=(NSAudioCaptureUsageDescription NSMicrophoneUsageDescription)
AUDIO_INPUT_ENTITLEMENT='com\.apple\.security\.device\.audio-input'

CONFIGURATION="release"
OUTPUT="${PACKAGE_ROOT}/.build/product"
SIGN_IDENTITY="MOSS Capture Local Signing"
KEYCHAIN="${HOME}/Library/Keychains/moss-signing.keychain-db"
PASSWORD_FILE="${HOME}/.config/moss-capture/signing-keychain.password"
RUN_SWIFT_BUILD=1

usage() {
    sed -n '3,30p' "${BASH_SOURCE[0]}" | sed -e 's/^#[[:space:]]\{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) MOSS_TOOL_DRY_RUN=1 ;;
        --configuration) CONFIGURATION="${2:?--configuration needs release or debug}"; shift ;;
        --output) OUTPUT="${2:?--output needs a directory}"; shift ;;
        --sign-identity) SIGN_IDENTITY="${2:?--sign-identity needs a name or -}"; shift ;;
        --keychain) KEYCHAIN="${2:?--keychain needs a path}"; shift ;;
        --password-file) PASSWORD_FILE="${2:?--password-file needs a path}"; shift ;;
        --no-build) RUN_SWIFT_BUILD=0 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1 (try --help)" ;;
    esac
    shift
done

case "$CONFIGURATION" in
    release|debug) ;;
    *) die "unknown configuration: $CONFIGURATION (expected release or debug)" ;;
esac

require_darwin
require_cmd swift codesign plutil security shasum awk sed ditto

# Build output only. Installing into a system location is install-app.sh's job, and doing it
# here would replace a running app's bundle without recording a rollback.
case "$OUTPUT" in
    /Applications|/Applications/*|/System/*|/usr/*|/bin/*|/sbin/*)
        die "refusing to build into an install location: $OUTPUT (use install-app.sh)" ;;
esac

BUNDLE="${OUTPUT}/MOSSCapture.app"
EVIDENCE="${OUTPUT}/build-evidence.json"
SIGNING_ENTITLEMENTS="${OUTPUT}/MOSSCapture.signing.entitlements"
EMBEDDED_ENTITLEMENTS="${OUTPUT}/embedded-entitlements.plist"

plan "swift build ${CONFIGURATION}: ${APP_EXECUTABLE} and ${CLI_EXECUTABLE}"
plan "compose ${BUNDLE} from the built product and ${RESOURCES}/Info.plist"
plan "derive signing entitlements from ${RESOURCES}/MOSSCapture.entitlements, dropping keychain-access-groups"
plan "codesign --options runtime --identifier ${BUNDLE_IDENTIFIER} --sign '${SIGN_IDENTITY}'"
plan "sign ${CLI_EXECUTABLE} as ${BUNDLE_IDENTIFIER}.cli"
plan "read the embedded entitlements and designated requirement back out with codesign -d"
plan "write ${EVIDENCE} (${EVIDENCE_SCHEMA})"
rollback "rm -rf '${OUTPUT}'"

if dry_run; then
    exit 0
fi

if [ "$RUN_SWIFT_BUILD" = "1" ]; then
    swift build --package-path "$PACKAGE_ROOT" -c "$CONFIGURATION" --product "$APP_EXECUTABLE" >&2
    swift build --package-path "$PACKAGE_ROOT" -c "$CONFIGURATION" --product "$CLI_EXECUTABLE" >&2
fi

BIN_PATH="$(swift build --package-path "$PACKAGE_ROOT" -c "$CONFIGURATION" --show-bin-path)"
BUILT_APP="${BIN_PATH}/${APP_EXECUTABLE}"
BUILT_CLI="${BIN_PATH}/${CLI_EXECUTABLE}"
for product in "$BUILT_APP" "$BUILT_CLI"; do
    [ -f "$product" ] ||
        die "built product missing: ${product} (build both Swift products, or drop --no-build)"
done

BUILT_APP_SHA="$(sha256_file "$BUILT_APP")"
BUILT_CLI_SHA="$(sha256_file "$BUILT_CLI")"

json_string() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

read_evidence_field() {
    [ -f "$EVIDENCE" ] || return 1
    sed -n "s/^[[:space:]]*\"$1\": \"\(.*\)\",\{0,1\}$/\1/p" "$EVIDENCE" | head -1
}

# --- reuse -------------------------------------------------------------------------------
# The same sources signed by the same identity produce the same bundle; re-signing it would
# only churn mtimes. Verifying is still cheap, so an existing bundle is re-checked, never
# trusted on the strength of its evidence file alone.
if [ -d "$BUNDLE" ] && [ -f "$EVIDENCE" ]; then
    if [ "$(read_evidence_field built_app_sha256)" = "$BUILT_APP_SHA" ] &&
        [ "$(read_evidence_field built_cli_sha256)" = "$BUILT_CLI_SHA" ] &&
        [ "$(read_evidence_field configuration)" = "$CONFIGURATION" ] &&
        [ "$(read_evidence_field signed_by)" = "$(json_string "$SIGN_IDENTITY")" ] &&
        [ "$(read_evidence_field bundle_digest)" = "$(directory_digest "$BUNDLE")" ] &&
        codesign --verify --strict "$BUNDLE" >/dev/null 2>&1; then
        unchanged "${BUNDLE} already carries this build, signed by '${SIGN_IDENTITY}'"
        evidence "bundle" "$BUNDLE"
        evidence "designated_requirement" "$(designated_requirement "$BUNDLE")"
        exit 0
    fi
fi

# --- compose -----------------------------------------------------------------------------
rm -rf "$BUNDLE"
mkdir -p "${BUNDLE}/Contents/MacOS"
ditto "$BUILT_APP" "${BUNDLE}/Contents/MacOS/${APP_EXECUTABLE}"
chmod 755 "${BUNDLE}/Contents/MacOS/${APP_EXECUTABLE}"

INFO_PLIST="${BUNDLE}/Contents/Info.plist"
ditto "${RESOURCES}/Info.plist" "$INFO_PLIST"
plutil -replace CFBundleExecutable -string "$APP_EXECUTABLE" "$INFO_PLIST"
plutil -replace CFBundlePackageType -string APPL "$INFO_PLIST"

DECLARED_IDENTIFIER="$(plutil -extract CFBundleIdentifier raw -o - "$INFO_PLIST")"
[ "$DECLARED_IDENTIFIER" = "$BUNDLE_IDENTIFIER" ] ||
    die "Info.plist declares ${DECLARED_IDENTIFIER}, expected ${BUNDLE_IDENTIFIER}"
for key in "${USAGE_DESCRIPTION_KEYS[@]}"; do
    value="$(plutil -extract "$key" raw -o - "$INFO_PLIST" 2>/dev/null || true)"
    # Without a usage string macOS kills the process instead of prompting, so a lane could
    # never be granted at all.
    [ -n "${value// /}" ] || die "Info.plist lacks a usable ${key}"
done
change "composed ${BUNDLE}"

# --- entitlements ------------------------------------------------------------------------
ditto "${RESOURCES}/MOSSCapture.entitlements" "$SIGNING_ENTITLEMENTS"
if plutil -extract keychain-access-groups raw -o - "$SIGNING_ENTITLEMENTS" >/dev/null 2>&1; then
    plutil -remove keychain-access-groups "$SIGNING_ENTITLEMENTS"
    change "dropped keychain-access-groups from the signing entitlements (unsatisfiable by this identity)"
fi
plutil -extract "$AUDIO_INPUT_ENTITLEMENT" raw -o - "$SIGNING_ENTITLEMENTS" >/dev/null 2>&1 ||
    die "signing entitlements lack com.apple.security.device.audio-input"

# --- sign --------------------------------------------------------------------------------
# `codesign --keychain` is accepted and ignored, so the identity is reachable only through the
# user's keychain search list. Bootstrapping owns that list; this tool only refuses to build a
# bundle it cannot sign, and unlocks the keychain so a rebuilt-after-reboot machine still signs
# over SSH without a human.
if [ "$SIGN_IDENTITY" != "-" ]; then
    keychain_in_search_list "$KEYCHAIN" ||
        die "${KEYCHAIN} is not in the user keychain search list; run macos/scripts/bootstrap-signing-identity.sh"
    if [ -f "$PASSWORD_FILE" ]; then
        security unlock-keychain -p "$(cat "$PASSWORD_FILE")" "$KEYCHAIN" >/dev/null 2>&1 ||
            die "could not unlock ${KEYCHAIN} with ${PASSWORD_FILE}"
    fi
fi

codesign_args=(--force --options runtime --timestamp=none)

codesign "${codesign_args[@]}" \
    --identifier "$BUNDLE_IDENTIFIER" \
    --entitlements "$SIGNING_ENTITLEMENTS" \
    --sign "$SIGN_IDENTITY" "$BUNDLE"

ditto "$BUILT_CLI" "${OUTPUT}/${CLI_EXECUTABLE}"
chmod 755 "${OUTPUT}/${CLI_EXECUTABLE}"
# The CLI holds no view authority and captures no audio, so it is signed without entitlements.
codesign "${codesign_args[@]}" \
    --identifier "${BUNDLE_IDENTIFIER}.cli" \
    --sign "$SIGN_IDENTITY" "${OUTPUT}/${CLI_EXECUTABLE}"
change "signed ${BUNDLE} and ${OUTPUT}/${CLI_EXECUTABLE} with '${SIGN_IDENTITY}'"

# --- read the signature back -------------------------------------------------------------
codesign --verify --strict "$BUNDLE" ||
    die "the freshly signed bundle does not verify: ${BUNDLE}"
codesign --verify --strict "${OUTPUT}/${CLI_EXECUTABLE}" ||
    die "the freshly signed CLI does not verify"

embedded_entitlements "$BUNDLE" >"$EMBEDDED_ENTITLEMENTS"
plutil -lint "$EMBEDDED_ENTITLEMENTS" >/dev/null ||
    die "codesign returned unreadable embedded entitlements"
plutil -extract "$AUDIO_INPUT_ENTITLEMENT" raw -o - "$EMBEDDED_ENTITLEMENTS" >/dev/null 2>&1 ||
    die "the signature does not carry com.apple.security.device.audio-input"
if plutil -extract keychain-access-groups raw -o - "$EMBEDDED_ENTITLEMENTS" >/dev/null 2>&1; then
    die "the signature carries keychain-access-groups, which this identity cannot satisfy"
fi

OBSERVED_IDENTIFIER="$(bundle_identifier "$BUNDLE")"
[ "$OBSERVED_IDENTIFIER" = "$BUNDLE_IDENTIFIER" ] ||
    die "the signature names ${OBSERVED_IDENTIFIER}, expected ${BUNDLE_IDENTIFIER}"

BUNDLE_REQUIREMENT="$(designated_requirement "$BUNDLE")"
CLI_REQUIREMENT="$(designated_requirement "${OUTPUT}/${CLI_EXECUTABLE}")"
BUNDLE_DIGEST="$(directory_digest "$BUNDLE")"

cat >"$EVIDENCE" <<JSON
{
  "schema": "$(json_string "$EVIDENCE_SCHEMA")",
  "configuration": "$(json_string "$CONFIGURATION")",
  "signed_by": "$(json_string "$SIGN_IDENTITY")",
  "bundle_path": "$(json_string "$BUNDLE")",
  "bundle_identifier": "$(json_string "$BUNDLE_IDENTIFIER")",
  "bundle_executable": "$(json_string "$APP_EXECUTABLE")",
  "bundle_digest": "$(json_string "$BUNDLE_DIGEST")",
  "bundle_designated_requirement": "$(json_string "$BUNDLE_REQUIREMENT")",
  "built_app_sha256": "$(json_string "$BUILT_APP_SHA")",
  "built_cli_sha256": "$(json_string "$BUILT_CLI_SHA")",
  "cli_path": "$(json_string "${OUTPUT}/${CLI_EXECUTABLE}")",
  "cli_designated_requirement": "$(json_string "$CLI_REQUIREMENT")",
  "embedded_audio_input_entitlement": "true",
  "embedded_keychain_access_groups": "absent"
}
JSON

evidence "bundle" "$BUNDLE"
evidence "bundle_identifier" "$BUNDLE_IDENTIFIER"
evidence "bundle_digest" "$BUNDLE_DIGEST"
evidence "designated_requirement" "$BUNDLE_REQUIREMENT"
evidence "cli" "${OUTPUT}/${CLI_EXECUTABLE}"
evidence "cli_designated_requirement" "$CLI_REQUIREMENT"
evidence "build_evidence" "$EVIDENCE"
