#!/bin/bash
#
# Install a signed MOSSCapture.app and the mtd-capture CLI from build output.
#
# The one thing this tool protects is the pair of TCC grants (Microphone, System Audio
# Recording) that only a human can click:
#
#   * An install whose bundle is byte-identical to what is already there does nothing at all.
#     The installed bundle keeps its inode and its signature, so the grants survive.
#   * A replacement never deletes the previous bundle. It moves it aside to a backup path and
#     prints the exact command that puts it back, before the first mutation.
#   * A replacement whose designated requirement differs from the installed one is reported
#     loudly: that is precisely the case where macOS treats the app as a different program and
#     the human has to click again.
#
# The source bundle is verified before anything moves — signature, bundle identifier, and the
# entitlements actually embedded in the signature. An unsigned or tampered bundle is refused,
# not installed and then discovered.
#
# Usage:
#   macos/scripts/install-app.sh [--dry-run] [--bundle PATH] [--cli PATH]
#       [--applications DIR] [--bin-dir DIR]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=macos/scripts/moss-tool-lib.sh
. "${SCRIPT_DIR}/moss-tool-lib.sh"

PACKAGE_ROOT="$(cd "${SCRIPT_DIR}/../MOSSCapture" && pwd)"
PRODUCT_DIR="${PACKAGE_ROOT}/.build/product"

# Domain contract (prd.md): /Applications/MOSSCapture.app with this identifier.
BUNDLE_IDENTIFIER="com.alphasight.moss.capture"
CLI_EXECUTABLE="mtd-capture"
AUDIO_INPUT_ENTITLEMENT='com\.apple\.security\.device\.audio-input'

BUNDLE="${PRODUCT_DIR}/MOSSCapture.app"
CLI="${PRODUCT_DIR}/${CLI_EXECUTABLE}"
APPLICATIONS="/Applications"
BIN_DIR="${HOME}/.local/bin"

usage() {
    sed -n '3,22p' "${BASH_SOURCE[0]}" | sed -e 's/^#[[:space:]]\{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) MOSS_TOOL_DRY_RUN=1 ;;
        --bundle) BUNDLE="${2:?--bundle needs a path}"; shift ;;
        --cli) CLI="${2:?--cli needs a path}"; shift ;;
        --applications) APPLICATIONS="${2:?--applications needs a directory}"; shift ;;
        --bin-dir) BIN_DIR="${2:?--bin-dir needs a directory}"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1 (try --help)" ;;
    esac
    shift
done

require_darwin
require_cmd codesign plutil ditto shasum awk sed date

INSTALLED_BUNDLE="${APPLICATIONS}/MOSSCapture.app"
INSTALLED_CLI="${BIN_DIR}/${CLI_EXECUTABLE}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

plan "verify ${BUNDLE}: signature, identifier ${BUNDLE_IDENTIFIER}, embedded entitlements"
plan "install to ${INSTALLED_BUNDLE} only when its contents actually differ"
plan "move any existing install aside to ${INSTALLED_BUNDLE}.backup-<utc> instead of deleting it"
plan "install ${CLI_EXECUTABLE} to ${INSTALLED_CLI}"
plan "verify the installed bundle and compare its designated requirement with the source"

if dry_run; then
    rollback "rm -rf '${INSTALLED_BUNDLE}' && rm -f '${INSTALLED_CLI}'   # plus 'mv <backup> <path>' when one is created"
    exit 0
fi

# --- verify the source before anything moves ---------------------------------------------
[ -d "$BUNDLE" ] || die "source bundle missing: ${BUNDLE} (run build-app.sh first)"
[ -f "$CLI" ] || die "source CLI missing: ${CLI} (run build-app.sh first)"

codesign --verify --strict "$BUNDLE" >/dev/null 2>&1 ||
    die "source bundle fails codesign --verify --strict: ${BUNDLE}"
codesign --verify --strict "$CLI" >/dev/null 2>&1 ||
    die "source CLI fails codesign --verify --strict: ${CLI}"

SOURCE_IDENTIFIER="$(bundle_identifier "$BUNDLE")"
[ "$SOURCE_IDENTIFIER" = "$BUNDLE_IDENTIFIER" ] ||
    die "source bundle is signed as ${SOURCE_IDENTIFIER}, expected ${BUNDLE_IDENTIFIER}"

WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/moss-install.XXXXXX")"
cleanup() { rm -rf "$WORKSPACE"; }
trap cleanup EXIT

embedded_entitlements "$BUNDLE" >"${WORKSPACE}/entitlements.plist"
plutil -extract "$AUDIO_INPUT_ENTITLEMENT" raw -o - "${WORKSPACE}/entitlements.plist" >/dev/null 2>&1 ||
    die "source bundle is not signed with com.apple.security.device.audio-input"
if plutil -extract keychain-access-groups raw -o - "${WORKSPACE}/entitlements.plist" >/dev/null 2>&1; then
    die "source bundle carries keychain-access-groups, which this identity cannot satisfy"
fi

SOURCE_DIGEST="$(directory_digest "$BUNDLE")"
SOURCE_REQUIREMENT="$(designated_requirement "$BUNDLE")"
SOURCE_CLI_SHA="$(sha256_file "$CLI")"

# --- the app bundle ----------------------------------------------------------------------
BACKUP_BUNDLE="none"
if [ -L "$INSTALLED_BUNDLE" ]; then
    die "refusing to install over a symlink: ${INSTALLED_BUNDLE}"
fi

if [ -d "$INSTALLED_BUNDLE" ] && [ "$(directory_digest "$INSTALLED_BUNDLE")" = "$SOURCE_DIGEST" ]; then
    # Not replacing it is the whole point: the inode, the signature and the TCC grants stay.
    unchanged "${INSTALLED_BUNDLE} already holds this exact bundle"
else
    if [ -d "$INSTALLED_BUNDLE" ]; then
        BACKUP_BUNDLE="${INSTALLED_BUNDLE}.backup-${STAMP}"
        INSTALLED_REQUIREMENT="$(designated_requirement "$INSTALLED_BUNDLE")"
        rollback "rm -rf '${INSTALLED_BUNDLE}' && mv '${BACKUP_BUNDLE}' '${INSTALLED_BUNDLE}'"
        if [ "$INSTALLED_REQUIREMENT" != "$SOURCE_REQUIREMENT" ]; then
            change "designated requirement changes on install: TCC grants reset, the human must click again"
            evidence "previous_designated_requirement" "$INSTALLED_REQUIREMENT"
        fi
    else
        rollback "rm -rf '${INSTALLED_BUNDLE}'"
    fi

    mkdir -p "$APPLICATIONS"
    INCOMING="${INSTALLED_BUNDLE}.incoming-${STAMP}"
    rm -rf "$INCOMING"
    # ditto, not cp: it preserves the signature's resource fork and permissions verbatim.
    ditto "$BUNDLE" "$INCOMING"
    if [ -d "$INSTALLED_BUNDLE" ]; then
        mv "$INSTALLED_BUNDLE" "$BACKUP_BUNDLE"
        change "moved the previous install aside to ${BACKUP_BUNDLE}"
    fi
    mv "$INCOMING" "$INSTALLED_BUNDLE"
    change "installed ${INSTALLED_BUNDLE}"
fi

codesign --verify --strict "$INSTALLED_BUNDLE" >/dev/null 2>&1 ||
    die "the installed bundle does not verify: ${INSTALLED_BUNDLE}"
INSTALLED_DIGEST="$(directory_digest "$INSTALLED_BUNDLE")"
[ "$INSTALLED_DIGEST" = "$SOURCE_DIGEST" ] ||
    die "the installed bundle differs from the source after install: ${INSTALLED_BUNDLE}"
INSTALLED_REQUIREMENT="$(designated_requirement "$INSTALLED_BUNDLE")"
[ "$INSTALLED_REQUIREMENT" = "$SOURCE_REQUIREMENT" ] ||
    die "the install changed the designated requirement: ${INSTALLED_REQUIREMENT}"

# --- the CLI ------------------------------------------------------------------------------
BACKUP_CLI="none"
if [ -f "$INSTALLED_CLI" ] && [ "$(sha256_file "$INSTALLED_CLI")" = "$SOURCE_CLI_SHA" ]; then
    unchanged "${INSTALLED_CLI} already holds this exact CLI"
else
    if [ -f "$INSTALLED_CLI" ]; then
        BACKUP_CLI="${INSTALLED_CLI}.backup-${STAMP}"
        rollback "rm -f '${INSTALLED_CLI}' && mv '${BACKUP_CLI}' '${INSTALLED_CLI}'"
    else
        rollback "rm -f '${INSTALLED_CLI}'"
    fi
    mkdir -p "$BIN_DIR"
    [ "$BACKUP_CLI" = "none" ] || mv "$INSTALLED_CLI" "$BACKUP_CLI"
    ditto "$CLI" "$INSTALLED_CLI"
    chmod 755 "$INSTALLED_CLI"
    change "installed ${INSTALLED_CLI}"
fi

codesign --verify --strict "$INSTALLED_CLI" >/dev/null 2>&1 ||
    die "the installed CLI does not verify: ${INSTALLED_CLI}"

case ":${PATH}:" in
    *":${BIN_DIR}:"*) ON_PATH="true" ;;
    *) ON_PATH="false" ;;
esac

evidence "installed_bundle" "$INSTALLED_BUNDLE"
evidence "bundle_identifier" "$BUNDLE_IDENTIFIER"
evidence "bundle_digest" "$INSTALLED_DIGEST"
evidence "designated_requirement" "$INSTALLED_REQUIREMENT"
evidence "backup_bundle" "$BACKUP_BUNDLE"
evidence "installed_cli" "$INSTALLED_CLI"
evidence "cli_sha256" "$SOURCE_CLI_SHA"
evidence "backup_cli" "$BACKUP_CLI"
evidence "bin_dir_on_path" "$ON_PATH"
