# Shared discipline for the tracked Mac packaging and install tools.
#
# Sourced, never executed. Every tool that can mutate this Mac follows one contract:
#
#   * `--dry-run` prints the ordered plan plus the rollback command and changes nothing,
#     so a reviewer can read exactly what a real run would do.
#   * the `rollback:` line is printed *before* the first mutation, never after it.
#   * re-running with the same inputs prints `unchanged:` and mutates nothing. That is not
#     just tidiness: an installed bundle that is not replaced keeps its inode and its code
#     signature, and therefore keeps the TCC grants a human had to click for.
#
# Output is line-oriented so acceptance tests can read it without parsing prose:
#
#   plan: <ordered step>          what a real run will do
#   rollback: <command>           the exact command that undoes the mutation
#   change: <what moved>          a mutation that happened
#   unchanged: <why>              a mutation that was correctly skipped
#   evidence: <key>=<value>       observed facts, safe to log (never a secret)
#   error: <message>              on stderr, immediately before a non-zero exit

MOSS_TOOL_DRY_RUN="${MOSS_TOOL_DRY_RUN:-0}"

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

plan() { printf 'plan: %s\n' "$*"; }
rollback() { printf 'rollback: %s\n' "$*"; }
change() { printf 'change: %s\n' "$*"; }
unchanged() { printf 'unchanged: %s\n' "$*"; }
evidence() { printf 'evidence: %s=%s\n' "$1" "$2"; }

dry_run() { [ "$MOSS_TOOL_DRY_RUN" = "1" ]; }

require_darwin() {
    [ "$(uname -s)" = "Darwin" ] || die "this tool only runs on macOS (uname -s = $(uname -s))"
}

require_cmd() {
    for candidate in "$@"; do
        command -v "$candidate" >/dev/null 2>&1 || die "required tool not found on PATH: $candidate"
    done
}

sha256_file() {
    [ -f "$1" ] || die "cannot hash a missing file: $1"
    shasum -a 256 "$1" | awk '{print $1}'
}

# One digest over a directory's whole file inventory: relative path and content, both
# fixed into the hash so a renamed or added file changes the answer. Symlinks are refused
# rather than followed — a signed bundle has none, and following one would let a link
# outside the tree decide the digest.
directory_digest() {
    local root="$1"
    [ -d "$root" ] || die "cannot digest a missing directory: $root"
    local links
    links="$(find "$root" -type l -print 2>/dev/null || true)"
    [ -z "$links" ] || die "unexpected symlink under $root: $(printf '%s' "$links" | head -1)"
    (
        cd "$root" || exit 1
        find . -type f -print0 |
            LC_ALL=C sort -z |
            while IFS= read -r -d '' relative; do
                printf '%s\0%s\0' "${relative#./}" "$(shasum -a 256 "$relative" | awk '{print $1}')"
            done
    ) | shasum -a 256 | awk '{print $1}'
}

# The designated requirement `codesign` would enforce. An implicit (ad-hoc, cdhash-based)
# requirement is emitted commented out, so the leading `# ` is stripped before matching.
designated_requirement() {
    local target="$1" requirement
    requirement="$(codesign -d -r- "$target" 2>&1 | sed -e 's/^#[[:space:]]*//' |
        grep -m1 '^designated =>' || true)"
    [ -n "$requirement" ] || die "codesign -d -r- reported no designated requirement for $target"
    printf '%s\n' "$requirement"
}

# The entitlements actually embedded in a signature, as an XML plist on stdout. This is the
# only trustworthy source: the file passed to `--entitlements` is an input, not evidence.
embedded_entitlements() {
    local target="$1"
    codesign -d --entitlements - --xml "$target" 2>/dev/null
}

bundle_identifier() {
    local target="$1"
    codesign -d -vv "$target" 2>&1 | sed -n 's/^Identifier=//p' | head -1
}

# `/tmp/x` and `/private/tmp/x` are the same keychain, and `security` reports the second form.
resolve_path() {
    local target="$1" directory
    directory="$(cd "$(dirname "$target")" 2>/dev/null && pwd -P)" || {
        printf '%s\n' "$target"
        return 0
    }
    printf '%s/%s\n' "$directory" "$(basename "$target")"
}

# One entry per line, unquoted.
user_keychain_search_list() {
    security list-keychains -d user | sed -e 's/^[[:space:]]*"//' -e 's/"[[:space:]]*$//'
}

# `codesign --keychain` is accepted and then ignored: measured on macOS 26, signing with an
# identity that is only in that keychain fails `no identity found`, and the same command
# succeeds once the keychain is in the user's search list. So membership of the search list —
# not the flag — is what makes an identity usable.
keychain_in_search_list() {
    local target resolved entry
    target="$1"
    resolved="$(resolve_path "$target")"
    while IFS= read -r entry; do
        [ -n "$entry" ] || continue
        if [ "$(resolve_path "$entry")" = "$resolved" ]; then
            return 0
        fi
    done < <(user_keychain_search_list)
    return 1
}
